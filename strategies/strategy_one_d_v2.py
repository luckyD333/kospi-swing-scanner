"""
strategies/strategy_one_d_v2.py — Strategy 1: Strategy D v2 (RSI + BB + 쌍바닥 + 장악형 양봉).

기존 daily_only_scanner.DailyOnlyScanner.scan 의 Phase 2 로직을 Strategy Protocol
구현으로 마이그레이션. 내부적으로 backtest_engine.StrategyD 를 사용하며 결과를
TradeSignal → Candidate 로 변환.

회귀 보장:
  동일 ScanContext 입력 → daily_only_scanner.py snapshot 과 동일 후보 리스트
  (ticker·confidence·entry_price·stop_loss·target_1·target_2 모두 일치).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from backtest_engine.detectors import (
    DoubleBottomDetector,
    DoubleBottomFractal,
    DoubleBottomProminence,
    DoubleBottomSimple,
)
from backtest_engine.strategy import StrategyD, StrategyDConfig

from core.strategy_base import Candidate, ScanContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyOneDv2Config:
    """Strategy D v2 파라미터. snapshot capture 시 detector='simple', volume>=100_000."""
    min_daily_volume: int = 100_000
    detector_name: str = "simple"           # "simple" | "fractal" | "prominence"
    min_lookback_bars: int = 25
    prominence_pct: float = 0.015


def _build_detector(name: str, prominence_pct: float) -> DoubleBottomDetector:
    if name == "simple":
        return DoubleBottomSimple()
    if name == "fractal":
        return DoubleBottomFractal()
    if name == "prominence":
        return DoubleBottomProminence(prominence_pct=prominence_pct)
    raise ValueError(f"unknown detector: {name}")


class StrategyOneDv2:
    """Strategy Protocol 구현 — RSI + BB + 쌍바닥 + 장악형 양봉."""

    name = "strategy_one_d_v2"

    def __init__(self, config: StrategyOneDv2Config | None = None):
        self.config = config or StrategyOneDv2Config()
        self._engine = StrategyD(
            config=StrategyDConfig(min_lookback_bars=self.config.min_lookback_bars),
            double_bottom_detector=_build_detector(
                self.config.detector_name, self.config.prominence_pct
            ),
        )

    def scan(self, ctx: ScanContext, top_n: int) -> List[Candidate]:
        """
        ScanContext 입력 → top_n Candidate.

        절차:
          1. 각 ticker 의 OHLCV 에 대해 거래량 필터 (20일 평균 ≥ min_daily_volume)
          2. StrategyD.prepare → check_entry 로 진입 시그널 추출
          3. confidence 내림차순 정렬, 상위 top_n 반환

        snapshot 회귀 보장: ctx.universe 의 iteration 순서가 그대로 정렬 안정성 키.
        """
        candidates: List[Candidate] = []
        failed = 0

        for ticker in ctx.universe:
            df = ctx.ohlcv.get(ticker)
            if df is None or len(df) < 30:
                continue

            try:
                avg_volume = float(df["volume"].tail(20).mean())
                if avg_volume < self.config.min_daily_volume:
                    continue

                prepared = self._engine.prepare(df)
                last_idx = len(prepared) - 1
                signal = self._engine.check_entry(prepared, last_idx, ticker=ticker)
                if signal is None:
                    continue

                cap_won = ctx.market_caps.get(ticker, 0.0)
                cap_bil = float(cap_won) / 100_000_000

                candidates.append(Candidate(
                    ticker=ticker,
                    name=ctx.names.get(ticker, ticker),
                    strategy=self.name,
                    signal_date=signal.timestamp,
                    score=signal.confidence,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    target_1=signal.target_1,
                    target_2=signal.target_2,
                    market_cap_bil=cap_bil,
                    volume_20d_avg=avg_volume,
                    conditions_met=dict(signal.conditions_met),
                    metadata={"market": ctx.market},
                ))
            except Exception as e:
                failed += 1
                if failed <= 3:
                    logger.debug(f"  {ticker} 분석 실패: {e}")

        # confidence 내림차순 (Python 안정 정렬 → 동일 score 의 입력 순서 유지)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]
