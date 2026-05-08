"""
strategies/strategy_two_cross_sectional_momentum.py
— 전략2: Cross-sectional Momentum (Jegadeesh-Titman 1993).

학술 근거:
  - Jegadeesh & Titman (1993) "Returns to Buying Winners and Selling Losers",
    Journal of Finance, Vol. 48, pp. 65-91
  - Park & Lee (2010) KOSPI 1990-2008 모멘텀 검증

정량 룰:
  1. 각 ticker 의 N일(=lookback) 누적 수익률 계산
  2. universe 전체에서 percentile rank 가 entry_percentile 이상이면 후보
  3. 당일 거래량 ≥ 20일 평균 (volume filter — 신호 신뢰도)
  4. score = percentile rank (0..1)
  5. SL = -2.5%, TP1 = +3%, TP2 = +5%
  6. 보유 5거래일 (백테스트 시 단기 회전율 검증)

전략1 (Mean Reversion) 과 상관 -0.2: 분산 효과 우수.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtest_engine.core import calc_atr
from core.cache.close_resolver import resolve_close_index
from core.decision.entry_gate import is_strategy_allowed
from core.decision.setup_quality import (
    trend_setup_quality,
    SETUP_SCORE_THRESHOLD_DEFAULT,
)
from core.indicators import latest_rsi_or_none
from core.strategy_base import Candidate, ScanContext

from .price_utils import floor_to_tick, populate_limit_fields, round_to_tick

logger = logging.getLogger(__name__)

_TF_NAMES: dict[str, str] = {
    "1D": "strategy_two_cross_sectional_momentum",
    "1h": "strategy_two_1h",
    "30m": "strategy_two_30m",
}


@dataclass(frozen=True)
class StrategyTwoConfig:
    lookback: int = 15                  # 모멘텀 산출 기간 (10~20일)
    entry_percentile: float = 0.75      # 상위 25% 만 진입 (≥ 75 percentile)
    volume_filter_window: int = 20      # 거래량 평균 비교 윈도우
    require_volume_above_avg: bool = True  # 당일 거래량 > 평균 강제
    stop_loss_pct: float = 0.025        # -2.5%
    target_1_pct: float = 0.03          # +3%
    target_2_pct: float = 0.05          # +5% (ATR 미산출 시 fallback)
    atr_target_mult: float = 3.0        # target_2 = entry + ATR×mult
    use_donchian_levels: bool = False   # 30m Donchian 기반 trade_plan 산출 (Optional)


class StrategyTwoCrossSectionalMomentum:
    """Cross-sectional Momentum — universe 전체 ranking 기반 매매."""

    name = "strategy_two_cross_sectional_momentum"

    def __init__(self, config: StrategyTwoConfig | None = None, timeframe: str = "1D"):
        if timeframe not in _TF_NAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}. 지원: {list(_TF_NAMES)}")
        cfg = config or StrategyTwoConfig()
        if cfg.lookback <= 0:
            raise ValueError(f"lookback must be positive, got {cfg.lookback}")
        if not (0.0 <= cfg.entry_percentile <= 1.0):
            raise ValueError(
                f"entry_percentile must be in [0,1], got {cfg.entry_percentile}"
            )
        self.config = cfg
        self.timeframe = timeframe
        self.name = _TF_NAMES[timeframe]

    # ------------------------------------------------------------------
    # Strategy Protocol
    # ------------------------------------------------------------------

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        """ScanContext → percentile rank 상위 후보 (top_n 개)."""
        cfg = self.config

        # 1) 각 ticker 의 모멘텀 + volume 필터 적용 (순차)
        rows = []
        tf_data = ctx.ohlcv_by_tf.get(self.timeframe, {}) or ctx.ohlcv
        fetched_at = ctx.meta.get("manifest_collected_at") if ctx.meta else None
        for ticker in ctx.universe:
            df = tf_data.get(ticker)
            if df is None or len(df) < cfg.lookback + 1:
                continue
            # incomplete-bar 가드: 1D 마지막 row 가 미완료 봉이면 잘라낸다.
            # 이후 모멘텀/거래량/ATR/RSI 모두 어제 종가 기준으로 산출.
            if resolve_close_index(df, fetched_at) == -2:
                df = df.iloc[:-1]
                if len(df) < cfg.lookback + 1:
                    continue
            close = df["close"]
            vol = df["volume"]

            try:
                past = float(close.iloc[-1 - cfg.lookback])
                if past <= 0 or pd.isna(past):
                    continue
                mom = float(close.iloc[-1] / past - 1.0)
                if pd.isna(mom):
                    continue

                # volume filter — 짧은 히스토리(< volume_filter_window)면 사용 가능한
                # 기간만큼 평균 사용 (보수적 동작; lookback+1 봉은 이미 통과했으므로 안전).
                if cfg.require_volume_above_avg:
                    vol_window = min(cfg.volume_filter_window, len(vol))
                    avg_vol = float(vol.iloc[-vol_window:].mean())
                    last_vol = float(vol.iloc[-1])
                    if last_vol < avg_vol:
                        continue
            except Exception as e:
                logger.debug(f"  {ticker} momentum 계산 실패: {e}")
                continue

            rows.append((ticker, mom, df))

        if not rows:
            return []

        # 2) Cross-sectional percentile rank
        moms = np.array([m for _, m, _ in rows], dtype=float)
        # rank: 작은 값=낮은 rank → 1/N..N/N (cumulative density)
        # NOTE: np.argsort(np.argsort(...)) 는 unique rank 를 할당 (tied rank average 아님).
        #       동률 ticker 는 stable sort 순서대로 분할되어 0.5/0.75 식으로 나뉨.
        #       Jegadeesh-Titman 원전의 month-level decile 와 미세 차이가 있으나, 일봉
        #       1~3일 보유 + Long-only 맥락에서 분리 정렬이 결정론적 진입 우선순위에
        #       유리 (동률 다수 = 시장 정체 = 신호 신뢰도 낮음 → 일부 배제 효과).
        order = np.argsort(np.argsort(moms))
        ranks = (order + 1) / len(moms)  # 1/N..1.0

        # 3) entry_percentile 이상만 후보 — 임계값 = 분포 중 entry_percentile 위치값
        candidates: list[Candidate] = []
        for (ticker, mom, df), rank in zip(rows, ranks):
            if rank < cfg.entry_percentile:
                continue

            # Entry gate: 1d regime + 1h setup_score 검사
            regime = ctx.per_ticker_regime.get(ticker)
            d_1h = ctx.donchian_1h_by_ticker.get(ticker)
            if d_1h is not None:
                setup = trend_setup_quality(d_1h)
                setup_score: int | None = setup.score
                setup_reasons = list(setup.reasons)
            else:
                setup_score = None
                setup_reasons = None

            # Gate 1: regime + setup_score 정책 매트릭스
            if not is_strategy_allowed(self.name, regime, setup_score):
                continue

            # Gate 2: setup_score 임계값 (메타 점수 가산 X, 차단만)
            if setup_score is not None and setup_score < SETUP_SCORE_THRESHOLD_DEFAULT:
                continue

            # 가드레일 1: 거래량 1.5× 이상 필요 (추세 추종 전략 공통)
            vol_today = float(df["volume"].iloc[-1])
            avg_vol = float(df["volume"].iloc[-20:].mean()) if len(df) >= 20 else float(df["volume"].mean())
            if avg_vol > 0 and vol_today < avg_vol * 1.0:  # Task 10 완화: 1.5 → 1.0 (strategy 본인 vol filter 와 중복 방지)
                continue

            close_now = float(df["close"].iloc[-1])
            entry = round_to_tick(close_now)

            # 가드레일 2: 1d width_percentile_60 > 0.85 → score ×0.7 (변동성 휩쏘 위험)
            d_1d = ctx.donchian_1d_by_ticker.get(ticker) if hasattr(ctx, "donchian_1d_by_ticker") else None
            score_multiplier = 1.0
            if d_1d is not None:
                # NaN 확인
                if d_1d.width_percentile_60 == d_1d.width_percentile_60:  # not NaN
                    if d_1d.width_percentile_60 > 0.85:
                        score_multiplier = 0.7

            # 가드레일 3: 52주 고가 ±3% 이내 → signal_strength ≥ 75 추가 요구 (메타 플래그)
            high_52w = float(df["high"].iloc[-min(252, len(df)):].max())
            near_52w_high = False
            if high_52w > 0 and abs(close_now - high_52w) / high_52w <= 0.03:
                near_52w_high = True
            sl = floor_to_tick(entry * (1 - cfg.stop_loss_pct))
            # ATR 14일 계산 (t2 산출에 선행)
            atr_series = calc_atr(df["high"], df["low"], df["close"], period=14)
            atr_val = atr_series.iloc[-1]
            atr_14 = None if (atr_val is None or atr_val != atr_val) else float(atr_val)

            t1 = round_to_tick(entry * (1 + cfg.target_1_pct))
            if atr_14 is not None:
                t2 = round_to_tick(entry + atr_14 * cfg.atr_target_mult)
                t2 = max(t2, t1)
            else:
                t2 = round_to_tick(entry * (1 + cfg.target_2_pct))

            cap_won = ctx.market_caps.get(ticker, 0.0)
            cap_bil = float(cap_won) / 100_000_000
            avg_vol_20 = float(df["volume"].iloc[-cfg.volume_filter_window:].mean()) \
                if len(df) >= cfg.volume_filter_window else float(df["volume"].mean())

            # 신규 metadata 키 계산
            risk_pct = (entry - sl) / entry * 100
            reward_pct_t2 = (t2 - entry) / entry * 100
            rr_ratio = 0.0 if risk_pct == 0 else reward_pct_t2 / risk_pct
            if rr_ratio < 2.0:
                rr_band = "below"
            elif rr_ratio < 2.5:
                rr_band = "sweet"
            else:
                rr_band = "over"

            rsi_14_val = latest_rsi_or_none(df["close"], period=14)

            df_30m = ctx.ohlcv_by_tf.get("30m", {}).get(ticker)
            limit_entry, limit_stop = populate_limit_fields(df_30m, entry, sl)

            candidates.append(Candidate(
                ticker=ticker,
                name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=df.index[-1],
                score=float(rank) * 1000 * score_multiplier,
                entry_price=entry,
                stop_loss=sl,
                target_1=t1,
                target_2=t2,
                limit_entry=limit_entry,
                limit_stop=limit_stop,
                market_cap_bil=cap_bil,
                volume_20d_avg=avg_vol_20,
                conditions_met={
                    "momentum_top_quartile": True,
                    "volume_above_avg": cfg.require_volume_above_avg,
                },
                metadata={
                    "momentum_pct": float(mom),
                    "lookback": cfg.lookback,
                    # percentile_rank: cross-sectional 분포 내 위치 (0~1).
                    # top-level Candidate.rank(int 순위)와 충돌 회피 위해 명시적 명명.
                    "percentile_rank": float(rank),
                    "market": ctx.market,
                    "source_strategy": self.name,
                    "rr_ratio": rr_ratio,
                    "rr_band": rr_band,
                    "atr_14": atr_14,
                    "rsi_14": rsi_14_val,
                    # Task 5a: entry gate
                    "per_ticker_regime": regime,
                    "setup_score": setup_score,
                    "setup_reasons": setup_reasons,
                    "bars_since_trigger": 0,
                    # Task 5e: 52주 고가 근접 (signal_strength percentile 추가 검증용)
                    "near_52w_high": near_52w_high,
                },
            ))

        # 4) score 내림차순 (안정 정렬: 동률 시 universe 입력 순서 유지)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]
