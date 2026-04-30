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
from typing import List

import numpy as np
import pandas as pd

from core.strategy_base import Candidate, ScanContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyTwoConfig:
    lookback: int = 15                  # 모멘텀 산출 기간 (10~20일)
    entry_percentile: float = 0.75      # 상위 25% 만 진입 (≥ 75 percentile)
    volume_filter_window: int = 20      # 거래량 평균 비교 윈도우
    require_volume_above_avg: bool = True  # 당일 거래량 > 평균 강제
    stop_loss_pct: float = 0.025        # -2.5%
    target_1_pct: float = 0.03          # +3%
    target_2_pct: float = 0.05          # +5%


class StrategyTwoCrossSectionalMomentum:
    """Cross-sectional Momentum — universe 전체 ranking 기반 매매."""

    name = "strategy_two_cross_sectional_momentum"

    def __init__(self, config: StrategyTwoConfig | None = None):
        cfg = config or StrategyTwoConfig()
        if cfg.lookback <= 0:
            raise ValueError(f"lookback must be positive, got {cfg.lookback}")
        if not (0.0 <= cfg.entry_percentile <= 1.0):
            raise ValueError(
                f"entry_percentile must be in [0,1], got {cfg.entry_percentile}"
            )
        self.config = cfg

    # ------------------------------------------------------------------
    # Strategy Protocol
    # ------------------------------------------------------------------

    def scan(self, ctx: ScanContext, top_n: int) -> List[Candidate]:
        """ScanContext → percentile rank 상위 후보 (top_n 개)."""
        cfg = self.config

        # 1) 각 ticker 의 모멘텀 + volume 필터 적용 (순차)
        rows = []
        for ticker in ctx.universe:
            df = ctx.ohlcv.get(ticker)
            if df is None or len(df) < cfg.lookback + 1:
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

                # volume filter
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
        order = np.argsort(np.argsort(moms))
        ranks = (order + 1) / len(moms)  # 1/N..1.0

        # 3) entry_percentile 이상만 후보 — 임계값 = 분포 중 entry_percentile 위치값
        candidates: List[Candidate] = []
        for (ticker, mom, df), rank in zip(rows, ranks):
            if rank < cfg.entry_percentile:
                continue

            close_now = float(df["close"].iloc[-1])
            sl = close_now * (1 - cfg.stop_loss_pct)
            t1 = close_now * (1 + cfg.target_1_pct)
            t2 = close_now * (1 + cfg.target_2_pct)

            cap_won = ctx.market_caps.get(ticker, 0.0)
            cap_bil = float(cap_won) / 100_000_000
            avg_vol_20 = float(df["volume"].iloc[-cfg.volume_filter_window:].mean()) \
                if len(df) >= cfg.volume_filter_window else float(df["volume"].mean())

            candidates.append(Candidate(
                ticker=ticker,
                name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=df.index[-1],
                score=float(rank),
                entry_price=close_now,
                stop_loss=sl,
                target_1=t1,
                target_2=t2,
                market_cap_bil=cap_bil,
                volume_20d_avg=avg_vol_20,
                conditions_met={
                    "momentum_top_quartile": True,
                    "volume_above_avg": cfg.require_volume_above_avg,
                },
                metadata={
                    "momentum_pct": float(mom),
                    "lookback": cfg.lookback,
                    "rank": float(rank),
                    "market": ctx.market,
                },
            ))

        # 4) score 내림차순 (안정 정렬: 동률 시 universe 입력 순서 유지)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]
