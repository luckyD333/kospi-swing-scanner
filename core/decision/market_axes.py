"""
core/decision/market_axes.py — Trend / Volatility 축 계산.

HMM 단일 추정과 직교하는 두 축:
  - Trend score: 평균 log return의 sign+magnitude → -100 ~ +100
  - Volatility regime: rolling std percentile → LOW / MID / HIGH
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_trend_score(returns: pd.Series, lookback: int = 20) -> int:
    """평균 log return → -100 ~ +100 정수 스코어.

    일봉 log return 기준 ±2%를 만점으로 clip. 내부 시장 proxy 가
    종목 평균 log return이므로 단일 종목보다 변동폭이 좁음.
    """
    if returns.empty:
        return 0
    recent = returns.iloc[-lookback:] if len(returns) >= lookback else returns
    avg = float(recent.mean())
    if avg != avg:  # NaN guard
        return 0
    capped = float(np.clip(avg / 0.02, -1.0, 1.0))
    return int(round(capped * 100))


def compute_volatility_regime(rolling_std: pd.Series) -> str:
    """rolling std percentile → 'LOW' / 'MID' / 'HIGH'.

    현재 값이 전체 시계열의 상위 30% 이상이면 HIGH,
    하위 30% 이하면 LOW, 그 외 MID.
    """
    if rolling_std.empty:
        return "MID"
    valid = rolling_std.dropna()
    if valid.empty:
        return "MID"
    current = float(valid.iloc[-1])
    if current != current:  # NaN guard
        return "MID"
    pct = float((valid <= current).mean())
    if pct >= 0.7:
        return "HIGH"
    if pct <= 0.3:
        return "LOW"
    return "MID"
