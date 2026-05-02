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
import math
from dataclasses import dataclass

from backtest_engine.core import calc_atr
from backtest_engine.detectors import (
    DoubleBottomDetector,
    DoubleBottomFractal,
    DoubleBottomProminence,
    DoubleBottomSimple,
)
from backtest_engine.strategy import StrategyD, StrategyDConfig
from core.strategy_base import Candidate, ScanContext

logger = logging.getLogger(__name__)


def _round_to_100(x: float) -> float:
    """100원 단위 반올림 (50원 이상 올림, 미만 내림)."""
    return math.floor(x / 100 + 0.5) * 100


def _floor_to_100(x: float) -> float:
    """100원 단위 반내림 (버림)."""
    return math.floor(x / 100) * 100


@dataclass(frozen=True)
class StrategyOneDv2Config:
    """Strategy D v2 파라미터. snapshot capture 시 detector='simple', volume>=100_000."""
    min_daily_volume: int = 100_000
    detector_name: str = "simple"           # "simple" | "fractal" | "prominence"
    min_lookback_bars: int = 25
    prominence_pct: float = 0.015
    engulf_strict: bool = True              # False: 완화 기준(전일 종가 +0.5% 돌파)
    db_freshness: int = 2                   # DoubleBottomSimple freshness
    db_price_tolerance: float = 0.03        # DoubleBottomSimple price_tolerance


def _build_detector(
    name: str,
    prominence_pct: float,
    freshness: int = 2,
    price_tolerance: float = 0.03,
) -> DoubleBottomDetector:
    if name == "simple":
        return DoubleBottomSimple(freshness=freshness, price_tolerance=price_tolerance)
    if name == "fractal":
        return DoubleBottomFractal()
    if name == "prominence":
        return DoubleBottomProminence(prominence_pct=prominence_pct)
    raise ValueError(f"unknown detector: {name}")


# timeframe → registry name suffix 매핑 (단일 클래스 멀티 등록용)
_TF_SUFFIX = {"1D": "d", "1W": "w", "1h": "1h", "30m": "30m"}


class StrategyOneDv2:
    """
    Strategy Protocol 구현 — RSI + BB + 쌍바닥 + 장악형 양봉.

    `timeframe` 파라미터로 4개 타임프레임 변형을 단일 클래스로 처리:
      - "1D" → name="strategy_one_d_v2"
      - "1W" → name="strategy_one_w_v2"
      - "1h" → name="strategy_one_1h_v2"
      - "30m" → name="strategy_one_30m_v2"
    scan() 은 ctx.ohlcv_by_tf[self.timeframe] 을 사용한다 (없으면 빈 결과).
    """

    # 클래스 기본 name (REGISTRY 키 안정성 · test_strategy_name_constant 호환)
    name = "strategy_one_d_v2"

    def __init__(
        self,
        config: StrategyOneDv2Config | None = None,
        timeframe: str = "1D",
        name_suffix: str = "",
    ):
        if timeframe not in _TF_SUFFIX:
            raise ValueError(
                f"unsupported timeframe: {timeframe}. 지원: {list(_TF_SUFFIX)}"
            )
        self.config = config or StrategyOneDv2Config()
        self.timeframe = timeframe
        self.name = f"strategy_one_{_TF_SUFFIX[timeframe]}_v2{name_suffix}"
        self._engine = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=self.config.min_lookback_bars,
                engulf_strict=self.config.engulf_strict,
            ),
            double_bottom_detector=_build_detector(
                self.config.detector_name,
                self.config.prominence_pct,
                freshness=self.config.db_freshness,
                price_tolerance=self.config.db_price_tolerance,
            ),
        )

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        """
        ScanContext 입력 → top_n Candidate.

        절차:
          1. 각 ticker 의 OHLCV (self.timeframe 슬라이스) 에서 거래량 필터
          2. StrategyD.prepare → check_entry 로 진입 시그널 추출
          3. confidence 내림차순 정렬, 상위 top_n 반환

        snapshot 회귀 보장: ctx.universe 의 iteration 순서가 그대로 정렬 안정성 키.
        """
        candidates: list[Candidate] = []
        failed = 0
        # multi-tf 지원: ctx.ohlcv_by_tf 우선, 없으면 legacy ctx.ohlcv (1D)
        tf_data = ctx.ohlcv_by_tf.get(self.timeframe, {}) or (
            ctx.ohlcv if self.timeframe == "1D" else {}
        )

        for ticker in ctx.universe:
            df = tf_data.get(ticker)
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

                raw_entry = signal.entry_price
                entry_price = _round_to_100(raw_entry)
                stop_loss = _floor_to_100(signal.stop_loss)
                # 반올림된 진입가 기준으로 목표가 재계산
                engine_cfg = self._engine.config
                target_1 = entry_price * (1 + engine_cfg.target_1_pct)
                target_2 = entry_price * (1 + engine_cfg.target_2_pct)

                # 신규 metadata 키 계산
                risk_pct = (entry_price - stop_loss) / entry_price * 100
                reward_pct_t2 = (target_2 - entry_price) / entry_price * 100
                rr_ratio = 0.0 if risk_pct == 0 else reward_pct_t2 / risk_pct
                if rr_ratio < 2.0:
                    rr_band = "below"
                elif rr_ratio < 2.5:
                    rr_band = "sweet"
                else:
                    rr_band = "over"

                # ATR 14일 계산 (NaN이면 None)
                atr_series = calc_atr(df["high"], df["low"], df["close"], period=14)
                atr_val = atr_series.iloc[-1]
                if atr_val is not None and (atr_val != atr_val):  # NaN 체크
                    atr_14 = None
                else:
                    atr_14 = float(atr_val) if atr_val is not None else None

                candidates.append(Candidate(
                    ticker=ticker,
                    name=ctx.names.get(ticker, ticker),
                    strategy=self.name,
                    signal_date=signal.timestamp,
                    score=signal.confidence * 1000,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    target_1=target_1,
                    target_2=target_2,
                    current_price=raw_entry,
                    market_cap_bil=cap_bil,
                    volume_20d_avg=avg_volume,
                    conditions_met=dict(signal.conditions_met),
                    metadata={
                        "market": ctx.market,
                        "source_strategy": self.name,
                        "rr_ratio": rr_ratio,
                        "rr_band": rr_band,
                        "atr_14": atr_14,
                    },
                ))
            except Exception as e:
                failed += 1
                if failed <= 3:
                    logger.debug(f"  {ticker} 분석 실패: {e}")

        # confidence 내림차순 (Python 안정 정렬 → 동일 score 의 입력 순서 유지)
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]
