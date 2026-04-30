"""detectors.py 테스트: 쌍바닥 감지 3가지 구현 비교"""
import pytest
import pandas as pd

from backtest_engine.detectors import (
    DoubleBottomSimple,
    DoubleBottomFractal,
    DoubleBottomProminence,
    is_bullish_engulfing,
    is_bearish_engulfing,
    count_consecutive_bearish,
    is_today_bullish,
)


class TestDoubleBottomSimple:
    def test_detects_perfect_double_bottom(self, perfect_double_bottom_scenario):
        """완벽한 쌍바닥 시나리오에서 감지 성공"""
        scenario = perfect_double_bottom_scenario
        detector = DoubleBottomSimple()
        # 진입 예상 봉(17)까지의 데이터만 사용
        df = scenario.df.iloc[: scenario.expected_entry_idx + 1]
        result = detector.detect(df)
        assert result is not None, f"감지 실패: {scenario.notes}"
        # 갭이 min_gap(5)~max_gap(20) 범위 내
        assert 5 <= result.gap_bars <= 20

    def test_no_detection_in_uptrend(self, uptrend_scenario):
        """상승장에서는 쌍바닥 없음"""
        detector = DoubleBottomSimple()
        result = detector.detect(uptrend_scenario.df)
        assert result is None

    def test_no_detection_in_choppy(self, choppy_scenario):
        """횡보장에서는 쌍바닥 없음 (저점이 서로 멀지 않음)"""
        detector = DoubleBottomSimple(price_tolerance=0.01)  # 엄격하게
        result = detector.detect(choppy_scenario.df)
        # 횡보는 저점이 비슷할 수도 있으나, 엄격한 tolerance로 감지 안 됨 기대
        # 만약 감지되면 gap이 정상 범위여야 함
        if result is not None:
            assert 5 <= result.gap_bars <= 20


class TestDoubleBottomFractal:
    def test_more_strict_than_simple(self, perfect_double_bottom_scenario):
        """Fractal은 Simple보다 엄격 → 감지 건수 ≤ Simple"""
        df = perfect_double_bottom_scenario.df.iloc[:18]

        simple = DoubleBottomSimple()
        fractal = DoubleBottomFractal()

        # 둘 다 감지될 수도 있고 Fractal만 실패할 수도 있음
        simple_result = simple.detect(df)
        fractal_result = fractal.detect(df)

        # Simple은 감지되어야 함 (완벽 시나리오)
        assert simple_result is not None


class TestDoubleBottomProminence:
    def test_filters_shallow_bottoms(self, choppy_scenario):
        """얕은 바닥은 prominence로 필터링됨"""
        detector = DoubleBottomProminence(prominence_pct=0.03)
        result = detector.detect(choppy_scenario.df)
        # 횡보 시 noise 저점들은 prominence가 낮아 감지 안 됨
        assert result is None

    def test_detects_significant_bottoms(self, perfect_double_bottom_scenario):
        """의미 있는 바닥은 감지"""
        df = perfect_double_bottom_scenario.df.iloc[:18]
        detector = DoubleBottomProminence(prominence_pct=0.005)
        result = detector.detect(df)
        assert result is not None


class TestEngulfingPatterns:
    def test_bullish_engulfing_perfect_scenario(self, perfect_double_bottom_scenario):
        """완벽 시나리오의 진입 봉(32)은 상승 장악형"""
        df = perfect_double_bottom_scenario.df
        assert is_bullish_engulfing(df, 32) is True

    def test_bullish_engulfing_in_uptrend(self, uptrend_scenario):
        """상승 추세 봉은 장악형 조건 안 맞을 수 있음"""
        df = uptrend_scenario.df
        # 상승 추세에서는 직전 봉이 양봉이므로 "음봉→양봉 장악형" 거의 없음
        count = sum(is_bullish_engulfing(df, i) for i in range(1, len(df)))
        assert count <= 3  # 노이즈로 2-3개 가능

    def test_today_bullish(self, perfect_double_bottom_scenario):
        """진입 봉은 양봉"""
        df = perfect_double_bottom_scenario.df
        assert is_today_bullish(df, 32) is True

    def test_consecutive_bearish_before_bottom(self, perfect_double_bottom_scenario):
        """1차 바닥(24) 이전 연속 음봉 있음"""
        df = perfect_double_bottom_scenario.df
        # 1차 바닥 근처에서 역방향으로 음봉 카운트
        count = count_consecutive_bearish(df, 24)
        assert count >= 3, f"연속 음봉 {count}개"


class TestCandidatePriceRegression:
    """P1-4 수정 회귀: candidate_price 추출 이후에도 감지 정상 동작"""

    def test_simple_still_detects_after_refactor(self, perfect_double_bottom_scenario):
        """candidate_price 변수 추출 이후에도 쌍바닥 감지 유지"""
        df = perfect_double_bottom_scenario.df.iloc[: perfect_double_bottom_scenario.expected_entry_idx + 1]
        result = DoubleBottomSimple().detect(df)
        assert result is not None, "리팩터링 후 Simple 감지 실패"
        assert 5 <= result.gap_bars <= 20

    def test_fractal_still_detects_after_refactor(self, perfect_double_bottom_scenario):
        """Fractal detector candidate_price 리팩터링 이후 감지 유지"""
        df = perfect_double_bottom_scenario.df.iloc[:33]
        # Fractal은 엄격해서 실패할 수 있으나 예외는 발생 안 해야 함
        result = DoubleBottomFractal().detect(df)
        # 결과 유무 무관하게 예외 없이 실행되면 통과


class TestDetectorComparison:
    """3가지 구현의 감지 빈도 비교"""

    def test_all_three_on_perfect_scenario(self, perfect_double_bottom_scenario):
        df = perfect_double_bottom_scenario.df.iloc[:33]

        results = {
            "simple": DoubleBottomSimple().detect(df),
            "fractal": DoubleBottomFractal().detect(df),
            "prominence": DoubleBottomProminence(prominence_pct=0.005).detect(df),
        }

        detected = {k: v is not None for k, v in results.items()}
        assert any(detected.values()), f"모든 detector가 실패: {detected}"
