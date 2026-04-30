"""
core/runner.py — 멀티 전략 스캔 오케스트레이터.

책임:
  1. 유니버스 필터 (시총·유동성)
  2. OHLCV 단일 fetch (OhlcvCache 로 ticker 별 1회)
  3. 등록된 N개 전략을 동일 ScanContext 로 실행
  4. {strategy_name: list[Candidate]} 반환

설계 결정:
  - 전략 인스턴스는 호출자가 주입 (Strategy Protocol 충족)
  - Cache 는 인스턴스 생명주기 = run() 1회
  - run() 안에서 예외 → 해당 전략만 실패 표시, 다른 전략은 계속 진행
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .data_fetch import DataClient, OhlcvCache
from .strategy_base import Candidate, ScanContext, Strategy
from .universe import UniverseFilter, build_universe

logger = logging.getLogger(__name__)


@dataclass
class RunnerConfig:
    """Runner 실행 설정."""
    market: str = "KOSPI"
    min_market_cap_bil: float = 2000.0
    max_market_cap_bil: float = 30000.0
    min_daily_volume: int = 100_000
    lookback_days: int = 90
    top_n: int = 20


@dataclass
class RunResult:
    """전략별 결과 + 메타."""
    target_date: str
    universe_size: int
    candidates_by_strategy: Dict[str, List[Candidate]] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)  # strategy_name → 에러 메시지
    cache_stats: Dict[str, int] = field(default_factory=dict)


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
        config: Optional[RunnerConfig] = None,
    ):
        self.client = client
        self.config = config or RunnerConfig()

    def run(
        self,
        strategies: List[Strategy],
        target_date: Optional[str] = None,
    ) -> RunResult:
        if target_date is None:
            target_date = self._latest_business_day()

        end_str = target_date
        start_dt = datetime.strptime(target_date, "%Y%m%d") - timedelta(
            days=self.config.lookback_days + 30
        )
        start_str = start_dt.strftime("%Y%m%d")

        logger.info(f"🔍 ScanRunner 시작: {self.config.market} @ {target_date}")

        # 1) 유니버스 필터
        univ = build_universe(
            self.client,
            target_date,
            UniverseFilter(
                min_market_cap_bil=self.config.min_market_cap_bil,
                max_market_cap_bil=self.config.max_market_cap_bil,
                min_daily_volume=self.config.min_daily_volume,
                market=self.config.market,
            ),
        )
        logger.info(f"📊 유니버스: {len(univ.tickers)}종목")

        # 2) OHLCV 단일 fetch (캐시 경유)
        cache = OhlcvCache(self.client)
        ohlcv: Dict[str, pd.DataFrame] = {}
        for ticker in univ.tickers:
            try:
                df = cache.get_or_fetch(ticker, start_str, end_str)
                if not df.empty and len(df) >= 30:
                    ohlcv[ticker] = df
            except Exception as e:
                logger.debug(f"  {ticker} fetch 실패: {e}")

        logger.info(f"📦 OHLCV 확보: {len(ohlcv)}종목 (cache stats={cache.stats})")

        # 3) ScanContext 생성 후 전략 실행
        ctx = ScanContext(
            target_date=target_date,
            universe=tuple(ohlcv.keys()),
            ohlcv=ohlcv,
            names=univ.name_lookup,
            market_caps=univ.cap_lookup,  # 원 단위
            market=self.config.market,
        )

        result = RunResult(
            target_date=target_date,
            universe_size=len(univ.tickers),
            cache_stats=cache.stats,
        )
        for strat in strategies:
            try:
                candidates = strat.scan(ctx, self.config.top_n)
                result.candidates_by_strategy[strat.name] = candidates
                logger.info(f"✅ {strat.name}: 후보 {len(candidates)}개")
            except Exception as e:
                logger.exception(f"❌ {strat.name} 실패")
                result.errors[strat.name] = str(e)

        return result

    @staticmethod
    def _latest_business_day() -> str:
        """장 마감(15:30) 이전이면 전일 기준."""
        today = date.today()
        now = datetime.now()
        if now.hour < 16:
            today -= timedelta(days=1)
        while today.weekday() >= 5:
            today -= timedelta(days=1)
        return today.strftime("%Y%m%d")
