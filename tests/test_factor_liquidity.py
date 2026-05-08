"""
test_factor_liquidity.py — 유동성 점수 factor 테스트.

liquidity = log(market_cap + 1) × log(avg_turnover_20d + 1)
cross-sectional rank 정규화는 aggregator 담당.
"""
from __future__ import annotations

import math

import pytest

from core.decision.factors.liquidity import compute_liquidity_score


class TestComputeLiquidityScore:
    """유동성 점수 계산 테스트."""

    def test_valid_inputs_positive_score(self):
        """정상 입력 — 양수 score 반환."""
        market_cap = 1e12  # 1조 원
        avg_turnover = 1e10  # 100억 원
        result = compute_liquidity_score(market_cap, avg_turnover)

        # log(1e12 + 1) × log(1e10 + 1)
        expected = math.log(1e12 + 1) * math.log(1e10 + 1)
        assert result == pytest.approx(expected, rel=1e-9)
        assert result > 0

    def test_both_none_returns_zero(self):
        """market_cap, avg_turnover 모두 None → 0.0."""
        result = compute_liquidity_score(None, None)
        assert result == 0.0

    def test_market_cap_none_returns_zero(self):
        """market_cap None → 0.0."""
        result = compute_liquidity_score(None, 1e10)
        assert result == 0.0

    def test_avg_turnover_none_returns_zero(self):
        """avg_turnover None → 0.0."""
        result = compute_liquidity_score(1e12, None)
        assert result == 0.0

    def test_market_cap_zero_returns_zero(self):
        """market_cap = 0 → 0.0."""
        result = compute_liquidity_score(0, 1e10)
        assert result == 0.0

    def test_avg_turnover_zero_returns_zero(self):
        """avg_turnover = 0 → 0.0."""
        result = compute_liquidity_score(1e12, 0)
        assert result == 0.0

    def test_market_cap_negative_returns_zero(self):
        """market_cap < 0 → 0.0."""
        result = compute_liquidity_score(-1e12, 1e10)
        assert result == 0.0

    def test_avg_turnover_negative_returns_zero(self):
        """avg_turnover < 0 → 0.0."""
        result = compute_liquidity_score(1e12, -1e10)
        assert result == 0.0

    def test_large_cap_vs_small_cap(self):
        """대형주(시총 크고 거래량 많음) > 소형주."""
        large_cap = compute_liquidity_score(1e13, 1e11)  # 10조, 1000억
        small_cap = compute_liquidity_score(1e10, 1e8)   # 100억, 1억
        assert large_cap > small_cap

    def test_monotonic_increasing_market_cap(self):
        """market_cap 고정, avg_turnover 증가 → score 증가."""
        mcap = 1e12
        score1 = compute_liquidity_score(mcap, 1e9)
        score2 = compute_liquidity_score(mcap, 1e10)
        score3 = compute_liquidity_score(mcap, 1e11)
        assert score1 < score2 < score3

    def test_monotonic_increasing_avg_turnover(self):
        """avg_turnover 고정, market_cap 증가 → score 증가."""
        turnover = 1e10
        score1 = compute_liquidity_score(1e10, turnover)
        score2 = compute_liquidity_score(1e11, turnover)
        score3 = compute_liquidity_score(1e12, turnover)
        assert score1 < score2 < score3

    def test_symmetry_log_product(self):
        """log 곱셈의 교환성: log(a)×log(b) = log(b)×log(a)."""
        cap1, turn1 = 1e12, 1e10
        cap2, turn2 = 1e10, 1e12
        score1 = compute_liquidity_score(cap1, turn1)
        score2 = compute_liquidity_score(cap2, turn2)
        assert score1 == pytest.approx(score2, rel=1e-9)
