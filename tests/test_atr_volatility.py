"""tests/test_atr_volatility.py — ATR bucket 분류기 단위 검증.

검증 포인트:
  - compute_atr_pct: ATR(14) / latest close 계산 정확성
  - bucket_atr: universe-wide p33/p67 분기 (LOW/MID/HIGH)
  - 결측 처리: atr None 또는 close ≤ 0 → "MID" fallback
"""
from __future__ import annotations

import pandas as pd

from core.decision.atr_volatility import bucket_atr, compute_atr_pct


def _make_df(closes: list[float], atr_pct: float = 0.02) -> pd.DataFrame:
    """OHLCV — close 시리즈 주어지면 ATR%(=high-low / close) ≈ atr_pct 되도록."""
    n = len(closes)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    half_range = [c * atr_pct / 2 for c in closes]
    return pd.DataFrame(
        {
            "open":  closes,
            "high":  [c + h for c, h in zip(closes, half_range)],
            "low":   [c - h for c, h in zip(closes, half_range)],
            "close": closes,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )


def test_compute_atr_pct_basic():
    """단조 가격 + 정해진 ATR% — 기대값 매칭."""
    # 30봉 (lookback 충분), atr_pct=0.04 의미: high-low ≈ 4% of close
    df = _make_df([100.0] * 30, atr_pct=0.04)
    pct = compute_atr_pct(df, period=14)
    # close=100, ATR(14) ≈ 4 (high-low 평균), so pct ≈ 0.04
    assert 0.03 < pct < 0.05


def test_bucket_atr_universe_p33_p67():
    """universe 분포 기반 LOW/MID/HIGH 분기."""
    # 9 ticker, atr_pct 분포: 0.01 ~ 0.09
    universe = {f"T{i:02d}": 0.01 * (i + 1) for i in range(9)}
    # p33 ≈ 0.034 (T02 ~ T03 사이), p67 ≈ 0.067 (T05 ~ T06 사이)
    assert bucket_atr(0.02, universe) == "LOW"   # < p33
    assert bucket_atr(0.05, universe) == "MID"   # p33 ~ p67
    assert bucket_atr(0.08, universe) == "HIGH"  # > p67


def test_bucket_atr_missing_fallback():
    """결측 (None 또는 ≤ 0) → MID fallback."""
    universe = {f"T{i:02d}": 0.01 * (i + 1) for i in range(9)}
    assert bucket_atr(None, universe) == "MID"
    assert bucket_atr(0.0, universe) == "MID"
    assert bucket_atr(-1.0, universe) == "MID"


def test_bucket_atr_empty_universe():
    """universe 비어 있으면 MID fallback (분포 계산 불가)."""
    assert bucket_atr(0.05, {}) == "MID"


def test_compute_atr_pct_insufficient_bars():
    """lookback 부족 → NaN."""
    df = _make_df([100.0] * 5, atr_pct=0.04)  # 14봉 필요
    pct = compute_atr_pct(df, period=14)
    assert pct != pct or pct == 0.0  # NaN 또는 0
