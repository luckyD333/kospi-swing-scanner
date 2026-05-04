"""
core/runner.py — 멀티 전략 + 멀티 타임프레임 스캔 오케스트레이터.

책임:
  1. 유니버스 필터 (시총·유동성) — TF 무관 1회
  2. OHLCV per-timeframe fetch (OhlcvCache + 옵션 OhlcvDiskCache)
  3. 각 전략의 self.timeframe 에 해당하는 ohlcv_by_tf 슬라이스로 scan 실행
  4. {(strategy_name, timeframe): list[Candidate]} 반환

설계 결정:
  - 전략 인스턴스는 호출자가 주입 (Strategy Protocol 충족 + .timeframe 속성)
  - Cache 는 인스턴스 생명주기 = run() 1회. cache_root 주어지면 디스크 영속화.
  - 30m/1h 는 1m fetch 후 resample. 1W 는 1D fetch 후 resample.
  - run() 안에서 예외 → 해당 전략만 실패 표시, 다른 전략은 계속 진행
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .dates import latest_business_day

from .cache.ohlcv_disk import OhlcvDiskCache
from .cache.resampler import resample_to
from .data_fetch import DataClient, OhlcvCache
from .data_sources.naver import naver_detail_url
from .strategy_base import Candidate, ScanContext, Strategy
from .universe import UniverseFilter, build_universe

logger = logging.getLogger(__name__)


def _none_if_nan(value):
    """pandas NaN을 JSON 호환 None으로 정규화. 일반 값은 그대로 통과."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


@dataclass
class RunnerConfig:
    """Runner 실행 설정."""
    market: str = "KOSPI"
    min_market_cap_bil: float = 2000.0
    max_market_cap_bil: float = 30000.0
    min_daily_volume: int = 100_000
    lookback_days: int = 90
    top_n: int = 20
    max_universe_size: int = 500
    timeframes: list[str] = field(default_factory=lambda: ["1D"])
    cache_root: Path | None = None  # 주어지면 .cache/ohlcv/ 디스크 영속


@dataclass
class RunResult:
    """전략별 × timeframe별 결과 + 메타."""
    target_date: str
    universe_size: int
    # legacy: {strategy_name: List[Candidate]} — 1D 기본 (회귀 호환)
    candidates_by_strategy: dict[str, list[Candidate]] = field(default_factory=dict)
    # multi-tf: {(strategy_name, timeframe): List[Candidate]}
    candidates_by_strategy_tf: dict[tuple[str, str], list[Candidate]] = field(
        default_factory=dict
    )
    errors: dict[str, str] = field(default_factory=dict)  # strategy_name → 에러 메시지
    cache_stats: dict[str, int] = field(default_factory=dict)
    funnel_stats: dict[str, Any] = field(default_factory=dict)
    regime: dict | None = None  # regime_analysis.json 로드 결과


class ScanRunner:
    """
    멀티 전략 스캔 진입점.

    사용 예:
        runner = ScanRunner(client, RunnerConfig(...))
        result = runner.run([strategy_d_v2, momentum_strat], target_date="20260418")
    """

    def __init__(
        self,
        client: DataClient,
        config: RunnerConfig | None = None,
    ):
        self.client = client
        self.config = config or RunnerConfig()

    def run(
        self,
        strategies: list[Strategy],
        target_date: str | None = None,
        fallbacks: dict[str, list[Strategy]] | None = None,
    ) -> RunResult:
        if target_date is None:
            target_date = latest_business_day()

        end_str = target_date
        target_dt = datetime.strptime(target_date, "%Y%m%d")
        # 1D/1W 용 long window (lookback_days + 버퍼)
        start_dt = target_dt - timedelta(days=self.config.lookback_days + 30)
        start_str = start_dt.strftime("%Y%m%d")
        # 디스크 캐시 모드: collect.py가 누적한 전체 1m 히스토리 활용 (lookback 확장)
        # live 모드: 네이버 API가 최근 ~3-7일만 반환하므로 7일 유지
        if self.config.cache_root:
            minute_start_str = start_str   # lookback_days + 30일 전 (1D와 동일)
        else:
            minute_start_str = (target_dt - timedelta(days=7)).strftime("%Y%m%d")

        logger.info(
            f"🔍 ScanRunner 시작: {self.config.market} @ {target_date} "
            f"timeframes={self.config.timeframes}"
        )

        # 시장 국면 로드 (cache_root 지정 시)
        regime_data: dict | None = None
        if self.config.cache_root:
            try:
                from core.decision.market_regime import load_regime_analysis
                regime_data = load_regime_analysis(self.config.cache_root)
                if regime_data:
                    logger.info(
                        f"📊 시장 국면: {regime_data.get('current_regime')} "
                        f"(score={regime_data.get('current_score')})"
                    )
            except Exception as e:
                logger.debug(f"시장 국면 로드 실패: {e}")

        # 1) 유니버스 필터 (TF 무관 1회)
        univ = build_universe(
            self.client,
            target_date,
            UniverseFilter(
                min_market_cap_bil=self.config.min_market_cap_bil,
                max_market_cap_bil=self.config.max_market_cap_bil,
                min_daily_volume=self.config.min_daily_volume,
                market=self.config.market,
                max_universe_size=self.config.max_universe_size,
            ),
        )
        logger.info(f"📊 유니버스: {len(univ.tickers)}종목")

        # 1b) 펀더멘털 (PER/ROE/외인비율/naver_url) — 1회 fetch, 후보 metadata에 사후 주입.
        # source 미지원 시 빈 결과 → naver_url만 ticker 패턴으로 채움 (UI 일관성).
        fundamentals_lookup = self._collect_fundamentals(univ.tickers, target_date)

        # 2) OHLCV per-timeframe fetch — disk cache 옵션
        disk = OhlcvDiskCache(self.config.cache_root) if self.config.cache_root else None
        cache = OhlcvCache(self.client, disk=disk)
        ohlcv_by_tf: dict[str, dict[str, pd.DataFrame]] = {}

        # funnel 초기화 (모든 TF 의 fetch 결과 합산)
        funnel: dict[str, Any] = {
            "universe_size": len(univ.tickers),
            "pre_cap_limit_size": univ.pre_cap_limit_size,
            "universe_cap_limit": self.config.max_universe_size or 0,
            "fetch_success": 0,
            "fetch_failed": 0,
            "short_bars": 0,
            "fetch_exceptions": Counter(),
            "source_counts": Counter(),
            "per_tf_size": {},
        }

        for tf in self.config.timeframes:
            tf_data: dict[str, pd.DataFrame] = {}
            for ticker in univ.tickers:
                try:
                    df = self._fetch_for_tf(
                        cache, ticker, tf, start_str, end_str,
                        minute_start_str, funnel,
                    )
                except Exception as e:
                    funnel["fetch_failed"] += 1
                    funnel["fetch_exceptions"][type(e).__name__] += 1
                    logger.debug(f"  {ticker}/{tf} fetch 예외: {e}")
                    continue

                if df is None or df.empty:
                    funnel["fetch_failed"] += 1
                elif len(df) < 30:
                    funnel["short_bars"] += 1
                else:
                    tf_data[ticker] = df
                    funnel["fetch_success"] += 1

            ohlcv_by_tf[tf] = tf_data
            funnel["per_tf_size"][tf] = len(tf_data)
            logger.info(f"📦 OHLCV/{tf}: {len(tf_data)}종목")

        logger.info(f"💾 cache stats={cache.stats}")

        # 3) ScanContext 1회 생성 (모든 TF 포함)
        legacy_ohlcv = ohlcv_by_tf.get("1D", {})
        # universe 는 어떤 TF 라도 데이터 있는 ticker 합집합 (univ.tickers 순서 유지)
        tickers_with_data: set = set()
        for tf_data in ohlcv_by_tf.values():
            tickers_with_data.update(tf_data.keys())
        ctx_universe = tuple(t for t in univ.tickers if t in tickers_with_data)
        ctx = ScanContext(
            target_date=target_date,
            universe=ctx_universe,
            ohlcv=legacy_ohlcv,
            names=univ.name_lookup,
            market_caps=univ.cap_lookup,
            market=self.config.market,
            ohlcv_by_tf=ohlcv_by_tf,
            fundamentals=fundamentals_lookup,
            regime=regime_data,
        )

        result = RunResult(
            target_date=target_date,
            universe_size=len(univ.tickers),
            cache_stats=cache.stats,
            funnel_stats=dict(funnel),  # Counter를 일반 dict로 변환
            regime=regime_data,
        )

        # 4) 전략 실행 — strategy 의 self.timeframe 으로 ohlcv_by_tf 슬라이스 자동 선택
        for strat in strategies:
            tf = getattr(strat, "timeframe", "1D")
            try:
                candidates = strat.scan(ctx, self.config.top_n)
                # 펀더멘털 사후 주입 — 전략 코드 무수정 원칙 (CLAUDE.md).
                # 전략은 metadata에 자체 키를 넣을 수 있고 보존된다 (update 만 함).
                for cand in candidates:
                    cand.metadata.update(fundamentals_lookup.get(cand.ticker, {
                        "per": None, "roe": None, "foreign_pct": None,
                        "naver_url": naver_detail_url(cand.ticker),
                    }))
                result.candidates_by_strategy_tf[(strat.name, tf)] = candidates
                # legacy 1D alias
                if tf == "1D":
                    result.candidates_by_strategy[strat.name] = candidates
                logger.info(f"✅ {strat.name}/{tf}: 후보 {len(candidates)}개")

                # fallback: 0개면 완화 버전 순차 시도
                if not candidates and fallbacks and strat.name in fallbacks:
                    for fb_strat in fallbacks[strat.name]:
                        fb_tf = getattr(fb_strat, "timeframe", "1D")
                        try:
                            fb_candidates = fb_strat.scan(ctx, self.config.top_n)
                            for cand in fb_candidates:
                                cand.metadata.update(fundamentals_lookup.get(cand.ticker, {
                                    "per": None, "roe": None, "foreign_pct": None,
                                    "naver_url": naver_detail_url(cand.ticker),
                                }))
                            result.candidates_by_strategy_tf[(fb_strat.name, fb_tf)] = fb_candidates
                            if fb_tf == "1D":
                                result.candidates_by_strategy[fb_strat.name] = fb_candidates
                            logger.info(f"  ↳ fallback {fb_strat.name}/{fb_tf}: 후보 {len(fb_candidates)}개")
                            if fb_candidates:
                                break
                        except Exception as e:
                            logger.exception(f"❌ fallback {fb_strat.name}/{fb_tf} 실패")
                            result.errors[fb_strat.name] = str(e)
            except Exception as e:
                logger.exception(f"❌ {strat.name}/{tf} 실패")
                result.errors[strat.name] = str(e)

        return result

    def _collect_fundamentals(
        self, tickers: list[str], target_date: str,
    ) -> dict[str, dict]:
        """
        펀더멘털 1회 fetch 후 ticker별 dict로 정규화.

        - source가 데이터를 주면 per/roe/foreign_pct를 그대로 (None 가능)
        - 미지원/실패: 모든 ticker에 None
        - naver_url: 항상 ticker 기반 패턴 (UI 일관성)
        """
        try:
            df = self.client.get_fundamentals(self.config.market, target_date)
        except Exception as e:
            logger.warning(f"펀더멘털 fetch 실패: {e}")
            df = pd.DataFrame()

        out: dict[str, dict] = {}
        for ticker in tickers:
            row = df.loc[ticker].to_dict() if (not df.empty and ticker in df.index) else {}
            out[ticker] = {
                "per": _none_if_nan(row.get("per")),
                "roe": _none_if_nan(row.get("roe")),
                "foreign_pct": _none_if_nan(row.get("foreign_pct")),
                "naver_url": row.get("naver_url") or naver_detail_url(ticker),
            }
        return out

    def _fetch_for_tf(
        self,
        cache: OhlcvCache,
        ticker: str,
        tf: str,
        start_str: str,
        end_str: str,
        minute_start_str: str,
        funnel: dict[str, Any],
    ) -> pd.DataFrame | None:
        """단일 ticker × 단일 tf 의 DataFrame 반환. resample 분기 처리."""
        if tf == "1D":
            source, df = cache.get_or_fetch_with_source(
                ticker, start_str, end_str, timeframe="1D"
            )
            funnel["source_counts"][source] += 1
            return df
        if tf == "1W":
            source, df_d = cache.get_or_fetch_with_source(
                ticker, start_str, end_str, timeframe="1D"
            )
            funnel["source_counts"][source] += 1
            return resample_to(df_d, "1W") if not df_d.empty else df_d
        if tf in ("30m", "1h", "2h", "4h"):
            # 분봉 end 는 YYYYMMDD2359 — 그 날 분봉 raw 끝까지 포함 (장중 미완료 분봉도)
            minute_end = f"{end_str}2359"
            source, df_m = cache.get_or_fetch_with_source(
                ticker, minute_start_str, minute_end, timeframe="1m"
            )
            funnel["source_counts"][source] += 1
            return resample_to(df_m, tf) if not df_m.empty else df_m
        raise ValueError(f"unsupported timeframe: {tf}")


def _classify_zero_candidate(result: RunResult) -> str:
    """
    후보 0개 결과의 funnel_stats 를 보고 4 분류 중 하나 반환.

    분류:
      - FETCH_FAILURE: fetch_failed 가 fetch_success 의 50% 초과 (네트워크/API 장애)
      - UNIVERSE_TOO_SMALL: fetch_success < 50 (시총 필터 과다)
      - NORMAL_NO_SIGNAL: 정상 작동 but 5조건 AND 미충족 (자연 시장에서 흔함)
    """
    f = result.funnel_stats
    fetch_success = f.get("fetch_success", 0)
    fetch_failed = f.get("fetch_failed", 0)
    if fetch_failed > max(fetch_success, 1) * 0.5:
        return "FETCH_FAILURE"
    if fetch_success < 50:
        return "UNIVERSE_TOO_SMALL"
    return "NORMAL_NO_SIGNAL"
