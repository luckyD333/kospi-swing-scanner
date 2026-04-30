"""
core/indicators.py — 지표 계산 헬퍼.

기존 backtest_engine.core 의 RSI/BB/MACD/ATR 함수를 그대로 re-export 하고,
멀티 전략에서 공통으로 쓰는 helper(MA, 모멘텀, 거래량 z-score)만 추가한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# backtest_engine 지표 재사용 (재구현 금지)
from backtest_engine.core import (
    calc_rsi,
    calc_bollinger,
    calc_macd,
    calc_atr,
)

__all__ = [
    "calc_rsi",
    "calc_bollinger",
    "calc_macd",
    "calc_atr",
    "moving_average",
    "momentum_pct",
    "volume_zscore",
]


def moving_average(prices: pd.Series, period: int) -> pd.Series:
    """단순 이동평균 (SMA)"""
    return prices.rolling(window=period, min_periods=period).mean()


def momentum_pct(prices: pd.Series, lookback: int) -> pd.Series:
    """
    모멘텀 = 현재가 / N봉 전 가격 - 1.

    Strategy 2 후보(time-series momentum/trend-following)에서 활용 예정.
    NaN 안전: lookback 봉 미만 구간은 NaN 유지.
    """
    if lookback <= 0:
        raise ValueError(f"lookback must be positive, got {lookback}")
    return prices / prices.shift(lookback) - 1.0


def volume_zscore(volume: pd.Series, window: int = 20) -> pd.Series:
    """
    거래량 z-score = (volume - rolling_mean) / rolling_std.

    거래량 스파이크 감지에 사용. window 미만 구간은 NaN.
    """
    if window <= 1:
        raise ValueError(f"window must be > 1, got {window}")
    mean = volume.rolling(window=window, min_periods=window).mean()
    std = volume.rolling(window=window, min_periods=window).std()
    # std == 0 시 NaN 반환 (0 division 회피)
    return (volume - mean) / std.replace(0, np.nan)
