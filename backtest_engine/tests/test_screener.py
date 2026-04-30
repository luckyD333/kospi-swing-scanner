"""screener.py 테스트"""
import pytest
import pandas as pd

from backtest_engine.screener import (
    MultiTimeframeScreener,
    ScreenerHit,
    ScreenerResult,
    SUPPORTED_TIMEFRAMES,
    resample_ohlcv,
)
from backtest_engine.strategy import StrategyDConfig
from backtest_engine.scenarios import ScenarioBuilder


class TestScreenerSingleTicker:
    def test_detects_hit_in_perfect_scenario_at_last_bar(
        self, perfect_double_bottom_scenario
    ):
        """완벽 시나리오의 마지막 봉이 진입 조건 충족이면 hit 반환"""
        # perfect 시나리오의 idx 32가 진입봉 → df를 32번까지 잘라서 "마지막 봉"으로
        df_truncated = perfect_double_bottom_scenario.df.iloc[:33]
        screener = MultiTimeframeScreener(
            strategy_config=StrategyDConfig(min_lookback_bars=25),
            timeframes=["1D"],
        )
        hits = screener.scan_single_ticker("TEST", {"1D": df_truncated})
        assert len(hits) == 1
        hit = hits[0]
        assert hit.ticker == "TEST"
        assert hit.timeframe == "1D"
        assert hit.entry_price > 0
        assert hit.stop_loss < hit.entry_price
        assert hit.target_1 > hit.entry_price
        assert hit.target_2 > hit.target_1

    def test_no_hit_in_uptrend(self, uptrend_scenario):
        screener = MultiTimeframeScreener(timeframes=["1D"])
        hits = screener.scan_single_ticker("UP", {"1D": uptrend_scenario.df})
        assert len(hits) == 0

    def test_risk_reward_metrics(self, perfect_double_bottom_scenario):
        df_truncated = perfect_double_bottom_scenario.df.iloc[:33]
        screener = MultiTimeframeScreener(
            strategy_config=StrategyDConfig(min_lookback_bars=25),
            timeframes=["1D"],
        )
        hits = screener.scan_single_ticker("TEST", {"1D": df_truncated})
        assert len(hits) == 1
        hit = hits[0]
        # 위험:보상 비율이 합리적 (손익비 1:2 근처)
        assert 1.5 < hit.risk_reward_ratio < 2.5
        # 손절 폭이 -2.5% 근처
        assert 2.0 < hit.risk_pct < 3.0
        # 2차 목표 +5% 근처
        assert 4.5 < hit.reward_pct_target_2 < 5.5


class TestScreenerMultiTicker:
    def test_multi_ticker_scan(
        self,
        perfect_double_bottom_scenario,
        uptrend_scenario,
    ):
        """여러 종목 동시 스캔 — 일부만 hit"""
        screener = MultiTimeframeScreener(
            strategy_config=StrategyDConfig(min_lookback_bars=25),
            timeframes=["1D"],
        )
        universe = {
            "WIN_STOCK": {"1D": perfect_double_bottom_scenario.df.iloc[:33]},
            "UP_STOCK": {"1D": uptrend_scenario.df},
        }
        result = screener.scan_multi(universe)
        assert result.total_scanned == 2
        assert len(result.hits) == 1
        assert result.hits[0].ticker == "WIN_STOCK"

    def test_summary_table(self, perfect_double_bottom_scenario):
        screener = MultiTimeframeScreener(
            strategy_config=StrategyDConfig(min_lookback_bars=25),
            timeframes=["1D"],
        )
        universe = {
            f"STOCK_{i}": {"1D": perfect_double_bottom_scenario.df.iloc[:33]}
            for i in range(3)
        }
        result = screener.scan_multi(universe)
        summary = result.summary_table(top_n=5)
        assert not summary.empty
        expected_cols = {"ticker", "timeframe", "entry_price", "stop_loss", "target_1", "target_2", "confidence"}
        assert expected_cols.issubset(set(summary.columns))

    def test_top_by_confidence(self, perfect_double_bottom_scenario):
        screener = MultiTimeframeScreener(
            strategy_config=StrategyDConfig(min_lookback_bars=25),
            timeframes=["1D"],
        )
        universe = {
            f"STOCK_{i}": {"1D": perfect_double_bottom_scenario.df.iloc[:33]}
            for i in range(5)
        }
        result = screener.scan_multi(universe)
        top3 = result.top_by_confidence(3)
        assert len(top3) <= 3
        # 정렬 확인
        confidences = [h.confidence for h in top3]
        assert confidences == sorted(confidences, reverse=True)


class TestResampling:
    def test_resample_daily_to_daily_noop(self):
        """1D → 1D 리샘플링은 결과 길이가 비슷해야 함"""
        times = pd.date_range("2026-01-01", periods=30, freq="1D")
        df = pd.DataFrame({
            "open": [100.0] * 30,
            "high": [105.0] * 30,
            "low": [99.0] * 30,
            "close": [103.0] * 30,
            "volume": [1000] * 30,
        }, index=times)
        result = resample_ohlcv(df, "1D")
        assert len(result) == len(df)

    def test_resample_invalid_timeframe_raises(self):
        df = pd.DataFrame({
            "open": [100.0], "high": [105.0], "low": [99.0],
            "close": [103.0], "volume": [1000],
        }, index=pd.date_range("2026-01-01", periods=1, freq="1D"))
        with pytest.raises(ValueError):
            resample_ohlcv(df, "7h")


class TestSupportedTimeframes:
    def test_all_timeframes_are_supported(self):
        assert "30m" in SUPPORTED_TIMEFRAMES
        assert "1h" in SUPPORTED_TIMEFRAMES
        assert "2h" in SUPPORTED_TIMEFRAMES
        assert "4h" in SUPPORTED_TIMEFRAMES
        assert "1D" in SUPPORTED_TIMEFRAMES
