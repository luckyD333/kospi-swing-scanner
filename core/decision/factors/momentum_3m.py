"""
core/decision/factors/momentum_3m.py — 3개월 모멘텀 factor.

momentum_3m = (close[-1] / close[-(bars+1)] - 1) × 100 (%)

설계:
  - 데이터 부족 (< bars+1) → None (cross-sectional rank에서 sentinel)
  - 기본 bars=60 (약 3개월, 영업일 기준)
"""
from __future__ import annotations

import pandas as pd


def compute_momentum_3m(
    ohlcv_1d: pd.DataFrame | None,
    bars: int = 60,
) -> float | None:
    """60봉 누적 수익률 (%) 계산.

    Args:
        ohlcv_1d: 일봉 OHLCV DataFrame. "close" 컬럼 필수.
        bars: lookback 기간 (기본 60 = 약 3개월). 내부적으로 bars+1 개 필요.

    Returns:
        float | None: 누적 수익률 (%). 데이터 부족 시 None.
    """
    if ohlcv_1d is None or len(ohlcv_1d) < bars + 1:
        return None

    close = ohlcv_1d["close"]
    return float(close.iloc[-1] / close.iloc[-(bars + 1)] - 1)
