"""
test_market_axes.py — compute_trend_score / compute_volatility_regime 단위 테스트.
"""
from __future__ import annotations

import pandas as pd

from core.decision.market_axes import compute_trend_score, compute_volatility_regime


# ---------------------------------------------------------------------------
# compute_trend_score
# ---------------------------------------------------------------------------

def test_trend_score_positive_returns_positive():
    """양수 평균 log return → 양수 score."""
    returns = pd.Series([0.005] * 30)
    assert compute_trend_score(returns) > 0


def test_trend_score_negative_returns_negative():
    """음수 평균 log return → 음수 score."""
    returns = pd.Series([-0.005] * 30)
    assert compute_trend_score(returns) < 0


def test_trend_score_capped_at_100():
    """매우 강한 상승 → 최대 +100."""
    returns = pd.Series([1.0] * 30)
    assert compute_trend_score(returns) == 100


def test_trend_score_capped_at_minus_100():
    """매우 강한 하락 → 최소 -100."""
    returns = pd.Series([-1.0] * 30)
    assert compute_trend_score(returns) == -100


def test_trend_score_zero_returns_zero():
    """평균 0 → score 0."""
    returns = pd.Series([0.0] * 30)
    assert compute_trend_score(returns) == 0


def test_trend_score_empty_returns_zero():
    """빈 Series → 0."""
    assert compute_trend_score(pd.Series([], dtype=float)) == 0


def test_trend_score_uses_last_lookback_rows():
    """lookback 윈도우만 사용하는지 검증 — 앞부분은 영향 없음."""
    # 앞 100개는 큰 양수, 뒤 20개는 강한 음수
    front = pd.Series([0.05] * 100)
    back = pd.Series([-0.05] * 20)
    returns = pd.concat([front, back], ignore_index=True)
    score = compute_trend_score(returns, lookback=20)
    assert score < 0


# ---------------------------------------------------------------------------
# compute_volatility_regime
# ---------------------------------------------------------------------------

def test_volatility_high():
    """현재 값이 전체 상위 70%+ → HIGH."""
    s = pd.Series(range(1, 11), dtype=float)  # 1~10, 현재=10 → percentile=1.0
    assert compute_volatility_regime(s) == "HIGH"


def test_volatility_low():
    """현재 값(마지막)이 전체 하위 30%- → LOW."""
    # 1~10 중 현재=1 → percentile=0.1 → LOW
    s = pd.Series(list(range(2, 11)) + [1.0])
    assert compute_volatility_regime(s) == "LOW"


def test_volatility_mid():
    """현재 값(마지막)이 중간 구간 → MID."""
    # 1~10 중 현재=5 → (valid<=5).mean()=0.5 → MID
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0, 5.0])
    assert compute_volatility_regime(s) == "MID"


def test_volatility_empty_returns_mid():
    """빈 Series → MID."""
    assert compute_volatility_regime(pd.Series([], dtype=float)) == "MID"


def test_volatility_all_nan_returns_mid():
    """전부 NaN → MID."""
    assert compute_volatility_regime(pd.Series([float("nan")] * 5)) == "MID"


def test_volatility_single_value_returns_high():
    """단일 값 → percentile 1.0 → HIGH."""
    assert compute_volatility_regime(pd.Series([3.0])) == "HIGH"
