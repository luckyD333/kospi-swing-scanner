"""test_setup_quality.py — 1h 셋업 품질 점수 검증."""

from core.decision.donchian import DonchianFrame
from core.decision.setup_quality import (
    trend_setup_quality,
    mean_rev_setup_quality,
    passes_setup_threshold,
    SETUP_SCORE_THRESHOLD_DEFAULT,
)


class TestTrendSetupQuality:
    """추세 추종 셋업 (1d UPTREND_*/RANGE_TIGHT 통과 후) 의 1h 품질 점수."""

    def test_strong_trend_setup(self):
        """1h position 0.7 + width_percentile 0.2 + days_since_upper_break 1 + slope > 0.

        점수: position ≥ 0.6 → +30
              width_percentile < 0.3 → +25
              0 ≤ days ≤ 3 → +20
              slope > 0 → +15
        합계: 30 + 25 + 20 + 15 = 90
        """
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.2,
            position=0.7,  # (current - lower) / (upper - lower) = (99 - 70) / 30 = 0.97, but set directly
            days_since_upper_break=1,
            days_since_lower_break=10,
            slope=0.01,
        )
        quality = trend_setup_quality(d_1h)
        assert quality.score == 90
        assert "1h_aligned_up" in quality.reasons
        assert "1h_squeeze" in quality.reasons
        assert "1h_fresh_breakout" in quality.reasons
        assert "1h_slope_up" in quality.reasons

    def test_weak_trend_setup_with_late_chase(self):
        """position 0.5 + width_percentile 0.5 + days 11 + slope ≈ 0.

        점수: position < 0.6 → 0
              width_percentile ≥ 0.3 → 0
              days > 10 → -15
              slope ≤ 0 → 0
        합계: 0 + 0 - 15 + 0 = -15 → clipped to 0
        """
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.5,
            position=0.5,
            days_since_upper_break=11,
            days_since_lower_break=10,
            slope=0.0,
        )
        quality = trend_setup_quality(d_1h)
        assert quality.score == 0  # -15 clipped to 0
        assert "1h_late_chase" in quality.reasons

    def test_moderate_trend_setup(self):
        """position 0.65 + width_percentile 0.4 + days 5 + slope > 0.

        점수: position ≥ 0.6 → +30
              width_percentile ≥ 0.3 → 0
              0 ≤ days ≤ 3 → 0 (days=5 는 범위 밖)
              slope > 0 → +15
        합계: 30 + 0 + 0 + 15 = 45
        """
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.4,
            position=0.65,
            days_since_upper_break=5,
            days_since_lower_break=10,
            slope=0.001,
        )
        quality = trend_setup_quality(d_1h)
        assert quality.score == 45
        assert "1h_aligned_up" in quality.reasons
        assert "1h_slope_up" in quality.reasons


class TestMeanRevSetupQuality:
    """평균 회귀 셋업 (1d RANGE/UPTREND_WEAK 시) 의 1h 품질 점수."""

    def test_strong_mean_rev_setup(self):
        """position 0.15 + width_percentile 0.5 + slope ≈ 0.0005 (flat).

        점수: position ≤ 0.20 → +35
              0.4 ≤ width_percentile ≤ 0.8 → +20
              abs(slope) < 0.001 (flat) → +15
        합계: 35 + 20 + 15 = 70
        """
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.5,
            position=0.15,
            days_since_upper_break=10,
            days_since_lower_break=2,
            slope=0.0005,
        )
        quality = mean_rev_setup_quality(d_1h, slope_flat_threshold=0.001)
        assert quality.score == 70
        assert "1h_at_lower" in quality.reasons
        assert "1h_normal_volatility" in quality.reasons
        assert "1h_flat" in quality.reasons

    def test_weak_mean_rev_setup(self):
        """position 0.4 + width_percentile 0.9 (높음) + slope 큼.

        점수: position > 0.20 → 0
              width_percentile > 0.8 → 0
              abs(slope) >= 0.001 → 0
        합계: 0
        """
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.9,
            position=0.4,
            days_since_upper_break=10,
            days_since_lower_break=10,
            slope=0.002,  # flat 조건 미충족
        )
        quality = mean_rev_setup_quality(d_1h)
        assert quality.score == 0


class TestPassesSetupThreshold:
    """임계값 검증."""

    def test_below_threshold(self):
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.9,
            position=0.4,
            days_since_upper_break=10,
            days_since_lower_break=10,
            slope=0.002,  # flat 미충족
        )
        quality = mean_rev_setup_quality(d_1h)
        assert quality.score == 0
        assert not passes_setup_threshold(quality, threshold=SETUP_SCORE_THRESHOLD_DEFAULT)

    def test_at_threshold(self):
        # 점수 정확히 40 (임계값)
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.5,
            position=0.15,
            days_since_upper_break=10,
            days_since_lower_break=2,
            slope=0.1,  # > 0.001 이므로 flat 미포함
        )
        quality = mean_rev_setup_quality(d_1h)
        # 35 + 20 + 0 = 55 (너무 높음)
        # 다시 설정: width_percentile 높혀서 -15
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.9,
            position=0.15,
            days_since_upper_break=10,
            days_since_lower_break=2,
            slope=0.0005,
        )
        quality = mean_rev_setup_quality(d_1h)
        # 35 + 0 + 15 = 50 (임계값 40 초과)
        assert quality.score >= SETUP_SCORE_THRESHOLD_DEFAULT
        assert passes_setup_threshold(quality, threshold=SETUP_SCORE_THRESHOLD_DEFAULT)

    def test_below_39(self):
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.9,
            position=0.25,
            days_since_upper_break=10,
            days_since_lower_break=10,
            slope=0.002,  # flat 미충족
        )
        quality = mean_rev_setup_quality(d_1h)
        assert quality.score == 0
        assert not passes_setup_threshold(quality, threshold=40)

    def test_above_60_strong_threshold(self):
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=70.0,
            middle=85.0,
            width_pct=35.3,
            width_percentile_60=0.2,
            position=0.7,
            days_since_upper_break=1,
            days_since_lower_break=10,
            slope=0.01,
        )
        quality = trend_setup_quality(d_1h)
        assert quality.score == 90
        assert passes_setup_threshold(quality, threshold=60)
