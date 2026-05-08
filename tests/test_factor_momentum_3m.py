"""
test_factor_momentum_3m.py — 3개월 모멘텀 factor 테스트.

momentum_3m = close[-1] / close[-(bars+1)] - 1
기본 bars=60 (약 3개월 영업일).
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.decision.factors.momentum_3m import compute_momentum_3m


class TestComputeMomentum3m:
    """3개월 모멘텀 계산 테스트."""

    def test_valid_ohlcv_positive_momentum(self):
        """정상 OHLCV — 상승 추세 → 양수 반환."""
        # 60봉 + 1 = 61개 필요
        n = 61
        closes = [100 * (1.003 ** i) for i in range(n)]  # 매일 0.3% 상승
        ohlcv = pd.DataFrame({
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
        })
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result is not None
        assert result > 0
        # 대략 (100 × 1.003^60) / 100 - 1 ≈ 0.196 (약 19.6%)
        assert result == pytest.approx(closes[-1] / closes[0] - 1, rel=1e-9)

    def test_valid_ohlcv_negative_momentum(self):
        """정상 OHLCV — 하락 추세 → 음수 반환."""
        n = 61
        closes = [100 * (0.997 ** i) for i in range(n)]  # 매일 0.3% 하락
        ohlcv = pd.DataFrame({"close": closes})
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result is not None
        assert result < 0
        assert result == pytest.approx(closes[-1] / closes[0] - 1, rel=1e-9)

    def test_flat_series_zero_momentum(self):
        """평탄 시계열 → 0.0."""
        n = 61
        closes = [100.0] * n
        ohlcv = pd.DataFrame({"close": closes})
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_insufficient_data_returns_none(self):
        """데이터 < bars+1 → None."""
        n = 50  # bars=60 이면 부족
        closes = list(range(100, 100 + n))
        ohlcv = pd.DataFrame({"close": closes})
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result is None

    def test_exact_boundary_bars_plus_one(self):
        """데이터 정확히 bars+1 개 → 계산."""
        n = 61
        closes = [100 + i for i in range(n)]  # 100~160
        ohlcv = pd.DataFrame({"close": closes})
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result is not None
        assert result == pytest.approx(160 / 100 - 1, rel=1e-9)

    def test_less_than_bars_plus_one_returns_none(self):
        """데이터 = bars → None (bars+1 필요)."""
        n = 60
        closes = list(range(100, 100 + n))
        ohlcv = pd.DataFrame({"close": closes})
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result is None

    def test_empty_dataframe_returns_none(self):
        """빈 DataFrame → None."""
        ohlcv = pd.DataFrame({"close": []})
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result is None

    def test_none_ohlcv_returns_none(self):
        """None ohlcv → None."""
        result = compute_momentum_3m(None, bars=60)
        assert result is None

    def test_custom_bars_parameter(self):
        """bars 파라미터 커스텀 — 30봉."""
        n = 31  # bars=30 + 1
        closes = [100 * (1.01 ** i) for i in range(n)]
        ohlcv = pd.DataFrame({"close": closes})
        result = compute_momentum_3m(ohlcv, bars=30)
        assert result is not None
        expected = closes[-1] / closes[0] - 1
        assert result == pytest.approx(expected, rel=1e-9)

    def test_real_scenario_significant_gain(self):
        """실제 시나리오 — 3개월 +30% 수익."""
        n = 61
        base = 10000
        closes = [base * (1.004 ** i) for i in range(n)]  # 일일 0.4%
        ohlcv = pd.DataFrame({"close": closes})
        result = compute_momentum_3m(ohlcv, bars=60)
        assert result is not None
        assert 0.25 < result < 0.35  # 약 30% 수익
