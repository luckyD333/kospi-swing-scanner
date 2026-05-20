"""core/decision/atr_volatility.py — ATR 변동성 bucket 분류기.

본 모듈은 ticker 의 ATR%(= ATR(14) / latest close) 를 universe-wide 분포의
p33/p67 분위수 기준으로 LOW/MID/HIGH bucket 으로 분류한다.

상황별 holding 추천 feature (plan: warm-percolating-cosmos.md) 의 ATR 축
입력으로 사용. 시장 환경 변화에 자동 적응 (절대 임계값 대신 분위수).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_engine.core import calc_atr


def compute_atr_pct(df: pd.DataFrame, period: int = 14) -> float:
    """latest ATR(period) / latest close.

    Args:
        df: OHLCV DataFrame (high/low/close 컬럼 필수).
        period: ATR 기간 (기본 14).

    Returns:
        ATR% (예: 0.025 = 2.5%). lookback 부족 또는 결측 시 NaN.
    """
    if len(df) < period + 1:
        return float("nan")
    atr_series = calc_atr(df["high"], df["low"], df["close"], period=period)
    atr = atr_series.iloc[-1]
    close = df["close"].iloc[-1]
    if pd.isna(atr) or close <= 0:
        return float("nan")
    return float(atr) / float(close)


def bucket_atr(atr_pct: float | None, universe_distribution: dict[str, float]) -> str:
    """universe 분포 기준 LOW/MID/HIGH 분기.

    분기 규칙:
      atr_pct < p33  → LOW
      p33 ≤ atr_pct ≤ p67 → MID
      atr_pct > p67  → HIGH

    Args:
        atr_pct: 분류 대상 ticker 의 ATR%. None/0/음수면 MID fallback.
        universe_distribution: {ticker: atr_pct} — universe-wide 분포.
            비어 있으면 MID fallback (분위수 계산 불가).

    Returns:
        "LOW" | "MID" | "HIGH".
    """
    if atr_pct is None or atr_pct <= 0 or pd.isna(atr_pct):
        return "MID"
    if not universe_distribution:
        return "MID"

    values = np.array([v for v in universe_distribution.values() if v > 0 and not pd.isna(v)])
    if len(values) < 3:
        return "MID"

    p33 = float(np.quantile(values, 0.33))
    p67 = float(np.quantile(values, 0.67))
    if atr_pct < p33:
        return "LOW"
    if atr_pct > p67:
        return "HIGH"
    return "MID"
