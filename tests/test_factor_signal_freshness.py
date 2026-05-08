"""
test_factor_signal_freshness.py — 신호 freshness factor 검증.

trigger 봉 이후 경과 봉 수에 따른 exponential decay score.
- bars=0 → 1.0 (즉시)
- bars=3 (half_life) → 0.5
- bars >> half_life → ~0
"""
from __future__ import annotations

from core.decision.factors.signal_freshness import compute_signal_freshness


def test_freshness_zero_bars_is_one():
    """trigger 봉 즉시 = 1.0."""
    score = compute_signal_freshness(bars_since_trigger=0)
    assert abs(score - 1.0) < 0.001


def test_freshness_half_life_is_half():
    """bars = half_life (3.0) → 0.5."""
    score = compute_signal_freshness(bars_since_trigger=3, decay_half_life=3.0)
    assert abs(score - 0.5) < 0.001


def test_freshness_one_bar_is_reasonable():
    """bars=1 → decay 1단계."""
    score = compute_signal_freshness(bars_since_trigger=1, decay_half_life=3.0)
    expected = 0.5 ** (1.0 / 3.0)
    assert abs(score - expected) < 0.001


def test_freshness_five_bars_is_low():
    """bars=5 (half_life=3) → ~0.31."""
    score = compute_signal_freshness(bars_since_trigger=5, decay_half_life=3.0)
    expected = 0.5 ** (5.0 / 3.0)
    assert abs(score - expected) < 0.001
    assert score < 0.35


def test_freshness_ten_bars_is_very_low():
    """bars=10 → ~0.099."""
    score = compute_signal_freshness(bars_since_trigger=10, decay_half_life=3.0)
    expected = 0.5 ** (10.0 / 3.0)
    assert abs(score - expected) < 0.001
    assert score < 0.15


def test_freshness_negative_bars_fallback_is_one():
    """미래 이벤트 (bars < 0) → 1.0 (fallback)."""
    score = compute_signal_freshness(bars_since_trigger=-1)
    assert abs(score - 1.0) < 0.001


def test_freshness_custom_half_life():
    """decay_half_life=5 인 경우."""
    score = compute_signal_freshness(bars_since_trigger=5, decay_half_life=5.0)
    assert abs(score - 0.5) < 0.001


def test_freshness_is_monotonic_decreasing():
    """bars가 증가하면 score는 감소."""
    bars_list = [0, 1, 3, 5, 10, 20]
    scores = [compute_signal_freshness(b) for b in bars_list]
    for i in range(len(scores) - 1):
        assert scores[i] > scores[i + 1], f"scores[{i}]={scores[i]} <= scores[{i+1}]={scores[i+1]}"


def test_freshness_returns_float():
    """반환 타입은 float."""
    score = compute_signal_freshness(bars_since_trigger=2)
    assert isinstance(score, float)
