"""
tests/test_per_ticker_regime.py — 일봉 Donchian 기반 7단계 regime 분류 단위 테스트.

TDD: Red → Green → Verify
"""
import pandas as pd

from core.decision.donchian import DonchianFrame
from core.decision.per_ticker_regime import (
    REGIME_LABELS,
    build_per_ticker_regime_map,
    daily_regime,
)


class TestDailyRegime:
    """7단계 regime 분류 단위 테스트."""

    def test_uptrend_strong(self):
        """pos ≥ 0.70 and slope > 0 → UPTREND_STRONG."""
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=50.0,
            middle=75.0,
            width_pct=66.7,
            width_percentile_60=0.5,
            position=0.75,  # >= 0.70
            days_since_upper_break=2,
            days_since_lower_break=10,
            slope=0.05,  # > 0
        )
        assert daily_regime(frame) == "UPTREND_STRONG"

    def test_uptrend_weak(self):
        """pos ≥ 0.55 and slope ≥ 0 → UPTREND_WEAK."""
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=50.0,
            middle=75.0,
            width_pct=66.7,
            width_percentile_60=0.5,
            position=0.60,  # >= 0.55, < 0.70
            days_since_upper_break=5,
            days_since_lower_break=10,
            slope=0.0,  # >= 0
        )
        assert daily_regime(frame) == "UPTREND_WEAK"

    def test_range_tight(self):
        """0.30 ≤ pos ≤ 0.70 and w_pct < 0.4 → RANGE_TIGHT."""
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=95.0,
            middle=97.5,
            width_pct=5.1,  # (100-95)/97.5*100 = 5.1 (낮음, 에너지 응축)
            width_percentile_60=0.25,  # < 0.4
            position=0.50,  # 0.30 <= pos <= 0.70
            days_since_upper_break=10,
            days_since_lower_break=10,
            slope=-0.02,
        )
        assert daily_regime(frame) == "RANGE_TIGHT"

    def test_range(self):
        """0.30 ≤ pos ≤ 0.70 and w_pct ≥ 0.4 → RANGE."""
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=60.0,
            middle=80.0,
            width_pct=50.0,  # (100-60)/80*100 = 50
            width_percentile_60=0.6,  # >= 0.4
            position=0.50,  # 0.30 <= pos <= 0.70
            days_since_upper_break=10,
            days_since_lower_break=10,
            slope=-0.01,
        )
        assert daily_regime(frame) == "RANGE"

    def test_downtrend_weak(self):
        """0.15 ≤ pos < 0.30 and slope ≤ 0 → DOWNTREND_WEAK."""
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=50.0,
            middle=75.0,
            width_pct=66.7,
            width_percentile_60=0.5,
            position=0.20,  # 0.15 <= pos < 0.30
            days_since_upper_break=15,
            days_since_lower_break=3,
            slope=-0.05,  # <= 0
        )
        assert daily_regime(frame) == "DOWNTREND_WEAK"

    def test_downtrend_strong(self):
        """pos < 0.15 and slope < 0 → DOWNTREND_STRONG."""
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=50.0,
            middle=75.0,
            width_pct=66.7,
            width_percentile_60=0.5,
            position=0.05,  # < 0.15
            days_since_upper_break=20,
            days_since_lower_break=1,
            slope=-0.10,  # < 0
        )
        assert daily_regime(frame) == "DOWNTREND_STRONG"

    def test_mixed_fallback(self):
        """조건을 만족하지 않는 경우 → MIXED."""
        # pos < 0.15, slope >= 0 인 경우 (상승 신호였지만 저점에 있음)
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=50.0,
            middle=75.0,
            width_pct=66.7,
            width_percentile_60=0.5,
            position=0.10,  # < 0.15
            days_since_upper_break=20,
            days_since_lower_break=5,
            slope=0.05,  # > 0 (상승 신호이지만 저점)
        )
        assert daily_regime(frame) == "MIXED"

    def test_flat_channel_range(self):
        """평탄 채널 (slope=0, position=0.5, width_percentile=NaN) → RANGE."""
        # plan에서 명시: 평탄 시계열은 RANGE로 빠짐
        frame = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=100.0,
            middle=100.0,
            width_pct=0.0,
            width_percentile_60=float("nan"),
            position=0.5,
            days_since_upper_break=20,
            days_since_lower_break=20,
            slope=0.0,
        )
        result = daily_regime(frame)
        # 0.30 <= 0.5 <= 0.70 (yes) and not isnan(NaN) (false) → 다음 조건
        # 0.30 <= 0.5 <= 0.70 (yes) → RANGE
        assert result == "RANGE"

    def test_all_regime_labels_defined(self):
        """REGIME_LABELS에 7개 라벨이 모두 정의됨."""
        expected = [
            "UPTREND_STRONG",
            "UPTREND_WEAK",
            "RANGE_TIGHT",
            "RANGE",
            "DOWNTREND_WEAK",
            "DOWNTREND_STRONG",
            "MIXED",
        ]
        assert sorted(REGIME_LABELS) == sorted(expected)
        assert len(REGIME_LABELS) == 7


class TestBuildPerTickerRegimeMap:
    """전체 종목 regime map 구축 단위 테스트."""

    def _make_ohlcv(self, length: int, close_vals=None) -> pd.DataFrame:
        """테스트용 OHLCV 데이터 생성."""
        if close_vals is None:
            close_vals = [100.0 + i * 0.1 for i in range(length)]
        return pd.DataFrame({
            "open": [c - 0.5 for c in close_vals],
            "high": [c + 1.0 for c in close_vals],
            "low": [c - 1.0 for c in close_vals],
            "close": close_vals,
            "volume": [1000000] * length,
        })

    def test_normal_case(self):
        """정상 종목 map 구축."""
        ohlcv_by_ticker = {
            "005930": self._make_ohlcv(100),  # UPTREND 시뮬레이션
            "000660": self._make_ohlcv(100),  # RANGE 시뮬레이션
        }
        result = build_per_ticker_regime_map(ohlcv_by_ticker, period=20)
        assert len(result) == 2
        assert "005930" in result
        assert "000660" in result
        assert all(v in REGIME_LABELS for v in result.values())

    def test_insufficient_data_ticker(self):
        """데이터 부족 종목 → MIXED."""
        short_ohlcv = self._make_ohlcv(10)  # period=20 < 10
        ohlcv_by_ticker = {"TICK001": short_ohlcv}
        result = build_per_ticker_regime_map(ohlcv_by_ticker, period=20)
        assert result["TICK001"] == "MIXED"

    def test_empty_input(self):
        """빈 dict 입력."""
        result = build_per_ticker_regime_map({}, period=20)
        assert result == {}

    def test_multiple_tickers(self):
        """여러 종목 동시 처리."""
        ohlcv_by_ticker = {
            f"TICK{i:03d}": self._make_ohlcv(50) for i in range(10)
        }
        result = build_per_ticker_regime_map(ohlcv_by_ticker, period=20)
        assert len(result) == 10
        assert all(k in result for k in ohlcv_by_ticker.keys())

    def test_custom_period(self):
        """커스텀 period 파라미터."""
        ohlcv = self._make_ohlcv(50)
        result = build_per_ticker_regime_map({"TEST": ohlcv}, period=30)
        # period=30, len=50 → 가능 (50 > 30)
        assert "TEST" in result
        assert result["TEST"] in REGIME_LABELS
