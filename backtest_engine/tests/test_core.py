"""core.py 테스트: 지표 계산"""
import pytest
import pandas as pd
import numpy as np

from backtest_engine.core import calc_rsi, calc_bollinger, calc_macd, calc_atr


class TestRSI:
    def test_rsi_range(self):
        """RSI는 항상 0~100 범위"""
        prices = pd.Series(np.cumsum(np.random.default_rng(42).normal(0, 1, 100)) + 100)
        rsi = calc_rsi(prices, period=14)
        valid = rsi.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rsi_uptrend_above_50(self):
        """지속 상승 시 RSI > 50"""
        prices = pd.Series(range(50, 150))
        rsi = calc_rsi(prices, period=14)
        assert rsi.iloc[-1] > 70

    def test_rsi_downtrend_below_50(self):
        """지속 하락 시 RSI < 50"""
        prices = pd.Series(range(150, 50, -1))
        rsi = calc_rsi(prices, period=14)
        assert rsi.iloc[-1] < 30

    def test_rsi_insufficient_data(self):
        """데이터 부족 시 NaN"""
        prices = pd.Series([100, 101, 102])
        rsi = calc_rsi(prices, period=14)
        assert rsi.isna().all()


class TestBollinger:
    def test_bollinger_bands_order(self):
        """upper > middle > lower"""
        prices = pd.Series(np.cumsum(np.random.default_rng(1).normal(0, 1, 50)) + 100)
        mid, upper, lower = calc_bollinger(prices, period=20, std_dev=2.0)
        valid = mid.dropna().index
        assert (upper.loc[valid] > mid.loc[valid]).all()
        assert (mid.loc[valid] > lower.loc[valid]).all()

    def test_bollinger_symmetric(self):
        """상하 밴드가 중간선 기준 대칭"""
        prices = pd.Series(np.cumsum(np.random.default_rng(1).normal(0, 1, 50)) + 100)
        mid, upper, lower = calc_bollinger(prices, period=20, std_dev=2.0)
        valid_idx = mid.dropna().index[-1]
        assert abs((upper[valid_idx] - mid[valid_idx]) - (mid[valid_idx] - lower[valid_idx])) < 1e-6


class TestMACD:
    def test_macd_components(self):
        """MACD line, signal line, histogram 반환"""
        prices = pd.Series(np.cumsum(np.random.default_rng(1).normal(0, 1, 50)) + 100)
        macd, signal, hist = calc_macd(prices)
        assert len(macd) == len(prices)
        assert len(signal) == len(prices)
        assert len(hist) == len(prices)

    def test_macd_histogram_equals_diff(self):
        """histogram = macd - signal"""
        prices = pd.Series(np.cumsum(np.random.default_rng(1).normal(0, 1, 50)) + 100)
        macd, signal, hist = calc_macd(prices)
        pd.testing.assert_series_equal(hist, macd - signal, check_names=False)


class TestRSINaN:
    def test_rsi_early_values_are_nan(self):
        """period 이전 구간은 NaN (fillna(50) 마스킹 금지)

        gain/loss는 delta.where()로 NaN→0 처리되어 index 0부터 비-NaN.
        EWM min_periods=14 → index 13(0-based)부터 유효값. 0~12는 NaN.
        """
        prices = pd.Series(range(50, 80), dtype=float)  # 30개
        rsi = calc_rsi(prices, period=14)
        # 인덱스 0~12 (13개) 은 NaN
        assert rsi.iloc[:13].isna().all(), "초기 구간이 NaN이어야 함"
        # 충분한 데이터가 있는 마지막 값은 유효
        assert not pd.isna(rsi.iloc[-1])

    def test_rsi_nan_not_fifty(self):
        """불충분 데이터 구간의 RSI가 50이 아닌 NaN"""
        prices = pd.Series([100.0] * 20)
        rsi = calc_rsi(prices, period=14)
        # 인덱스 0~12는 NaN (fillna(50) 제거 후)
        assert rsi.iloc[:13].isna().all()


class TestBollingerBreach:
    def test_lower_band_breach(self):
        """급락 시 가격이 하단 밴드 아래"""
        # 안정적인 30개 + 마지막에 급락
        prices = pd.Series([100.0] * 30 + [70.0])
        mid, upper, lower = calc_bollinger(prices, period=20, std_dev=2.0)
        assert prices.iloc[-1] < lower.iloc[-1], (
            f"급락 가격({prices.iloc[-1]})이 하단 밴드({lower.iloc[-1]:.2f}) 위에 있음"
        )

    def test_upper_band_breach(self):
        """급등 시 가격이 상단 밴드 위"""
        prices = pd.Series([100.0] * 30 + [135.0])
        mid, upper, lower = calc_bollinger(prices, period=20, std_dev=2.0)
        assert prices.iloc[-1] > upper.iloc[-1]


class TestATR:
    def test_atr_positive(self):
        """ATR은 항상 0 이상"""
        df_data = {
            "high": np.linspace(105, 125, 30),
            "low": np.linspace(95, 115, 30),
            "close": np.linspace(100, 120, 30),
        }
        df = pd.DataFrame(df_data)
        atr = calc_atr(df["high"], df["low"], df["close"], period=14)
        assert atr.dropna().min() >= 0
