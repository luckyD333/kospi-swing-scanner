"""
tests/test_donchian_levels.py — 30m Donchian 기반 trade_plan 자동 산출 테스트.

Task 5d: execution_levels() + can_use_donchian_levels() + strategy config flag.
"""
import pytest
from core.decision.donchian import DonchianFrame
from core.decision.donchian_levels import (
    can_use_donchian_levels,
    execution_levels,
    TREND_FAMILIES,
    MEAN_REVERSION_FAMILIES,
)


class TestCanUseDonchianLevels:
    """can_use_donchian_levels() 테스트 — fallback 판정."""

    def test_none_returns_false(self):
        """DonchianFrame = None → False."""
        assert can_use_donchian_levels(None) is False

    def test_nan_width_percentile_returns_false(self):
        """width_percentile_60 = NaN → False."""
        frame = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=float("nan"),  # NaN check
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        assert can_use_donchian_levels(frame) is False

    def test_valid_frame_returns_true(self):
        """정상 DonchianFrame → True."""
        frame = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=0.45,
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        assert can_use_donchian_levels(frame) is True


class TestExecutionLevelsTrendFollowing:
    """execution_levels() 테스트 — 추세 추종 (Strategy 2/3/4/5)."""

    def test_strategy_three_trend_following(self):
        """
        추세 추종 셋업:
        - d_30m: upper=100, lower=90, middle=95
        - d_1h: upper=110, lower=85, middle=97.5
        - atr_30m=2.0, tick=0.5
        - strategy="strategy_three"

        기대값:
        - entry = 100 + 0.5 = 100.5 (30m upper + tick)
        - stop = max(90, 97.5 - 0.5*2.0) = max(90, 96.5) = 96.5
        - T1 = 95 + (100 - 95) = 100 (middle + channel_width/2)
        - T2 = 100 + (100 - 90) = 110 (upper + channel_width)
        - trailing = "1h_lower"
        """
        d_30m = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=0.5,
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=110.0,
            lower=85.0,
            middle=97.5,
            width_pct=22.86,
            width_percentile_60=0.4,
            position=0.6,
            days_since_upper_break=1,
            days_since_lower_break=8,
            slope=0.08,
        )

        result = execution_levels("strategy_three", d_30m, d_1h, atr_30m=2.0, tick=0.5)

        assert result["entry"] == 100.5
        assert result["stop"] == 96.5
        assert result["T1"] == 100.0
        assert result["T2"] == 110.0
        assert result["trailing"] == "1h_lower"

    def test_strategy_two_trend_following(self):
        """strategy_two 도 동일한 추세 추종 로직."""
        d_30m = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=0.5,
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=110.0,
            lower=85.0,
            middle=97.5,
            width_pct=22.86,
            width_percentile_60=0.4,
            position=0.6,
            days_since_upper_break=1,
            days_since_lower_break=8,
            slope=0.08,
        )

        result = execution_levels("strategy_two", d_30m, d_1h, atr_30m=2.0, tick=0.5)

        assert result["entry"] == 100.5
        assert result["stop"] == 96.5
        assert result["T1"] == 100.0
        assert result["T2"] == 110.0
        assert result["trailing"] == "1h_lower"

    def test_trend_family_all_strategies(self):
        """TREND_FAMILIES 모든 전략이 추세 추종 로직."""
        d_30m = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=0.5,
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=110.0,
            lower=85.0,
            middle=97.5,
            width_pct=22.86,
            width_percentile_60=0.4,
            position=0.6,
            days_since_upper_break=1,
            days_since_lower_break=8,
            slope=0.08,
        )

        for strategy in TREND_FAMILIES:
            result = execution_levels(strategy, d_30m, d_1h, atr_30m=2.0, tick=0.5)
            assert result["entry"] == 100.5
            assert result["trailing"] == "1h_lower"


class TestExecutionLevelsMeanReversion:
    """execution_levels() 테스트 — 평균 회귀 (Strategy 1)."""

    def test_strategy_one_mean_reversion(self):
        """
        평균 회귀 셋업:
        - d_30m: upper=100, lower=90, middle=95, width=10
        - d_1h: (사용 안함)
        - atr_30m=2.0
        - strategy="strategy_one"

        기대값:
        - entry = 90 + 0.3*(95-90) = 90 + 0.3*5 = 91.5 (lower + 0.3*channel_width)
        - stop = 90 - 1.0*2.0 = 88.0 (lower - ATR)
        - T1 = 95 (middle, 회귀 1차)
        - T2 = 100 (upper, 회귀 2차)
        - trailing = None
        """
        d_30m = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=0.5,
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=110.0,
            lower=85.0,
            middle=97.5,
            width_pct=22.86,
            width_percentile_60=0.4,
            position=0.6,
            days_since_upper_break=1,
            days_since_lower_break=8,
            slope=0.08,
        )

        result = execution_levels("strategy_one", d_30m, d_1h, atr_30m=2.0)

        assert result["entry"] == 91.5
        assert result["stop"] == 88.0
        assert result["T1"] == 95.0
        assert result["T2"] == 100.0
        assert result["trailing"] is None

    def test_mean_reversion_family_strategies(self):
        """MEAN_REVERSION_FAMILIES 모든 전략."""
        d_30m = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=0.5,
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=110.0,
            lower=85.0,
            middle=97.5,
            width_pct=22.86,
            width_percentile_60=0.4,
            position=0.6,
            days_since_upper_break=1,
            days_since_lower_break=8,
            slope=0.08,
        )

        for strategy in MEAN_REVERSION_FAMILIES:
            result = execution_levels(strategy, d_30m, d_1h, atr_30m=2.0)
            assert result["entry"] == 91.5
            assert result["trailing"] is None


class TestExecutionLevelsUnknownStrategy:
    """execution_levels() 테스트 — 알 수 없는 strategy."""

    def test_unknown_strategy_raises_error(self):
        """알 수 없는 strategy_name → ValueError."""
        d_30m = DonchianFrame(
            timeframe="30m",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.53,
            width_percentile_60=0.5,
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=5,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=110.0,
            lower=85.0,
            middle=97.5,
            width_pct=22.86,
            width_percentile_60=0.4,
            position=0.6,
            days_since_upper_break=1,
            days_since_lower_break=8,
            slope=0.08,
        )

        with pytest.raises(ValueError, match="알 수 없는|unknown"):
            execution_levels("strategy_unknown", d_30m, d_1h, atr_30m=2.0)


class TestStrategyConfigFlag:
    """Strategy config 에 use_donchian_levels flag 추가 검증."""

    def test_strategy_one_config_default_false(self):
        """Strategy 1 config: use_donchian_levels = False (기본값)."""
        from strategies.strategy_one_d_v2 import StrategyOneDv2Config
        cfg = StrategyOneDv2Config()
        assert hasattr(cfg, "use_donchian_levels")
        assert cfg.use_donchian_levels is False

    def test_strategy_two_config_default_false(self):
        """Strategy 2 config: use_donchian_levels = False (기본값)."""
        from strategies.strategy_two_cross_sectional_momentum import StrategyTwoConfig
        cfg = StrategyTwoConfig()
        assert hasattr(cfg, "use_donchian_levels")
        assert cfg.use_donchian_levels is False

    def test_strategy_three_config_default_false(self):
        """Strategy 3 config: use_donchian_levels = False (기본값)."""
        from strategies.strategy_three_trend_following import StrategyThreeConfig
        cfg = StrategyThreeConfig()
        assert hasattr(cfg, "use_donchian_levels")
        assert cfg.use_donchian_levels is False

    def test_strategy_four_config_default_false(self):
        """Strategy 4 config: use_donchian_levels = False (기본값)."""
        from strategies.strategy_four_pullback_ma import StrategyFourConfig
        cfg = StrategyFourConfig()
        assert hasattr(cfg, "use_donchian_levels")
        assert cfg.use_donchian_levels is False

    def test_strategy_five_config_default_false(self):
        """Strategy 5 config: use_donchian_levels = False (기본값)."""
        from strategies.strategy_five_bull_flag import StrategyFiveConfig
        cfg = StrategyFiveConfig()
        assert hasattr(cfg, "use_donchian_levels")
        assert cfg.use_donchian_levels is False
