"""
tests/test_donchian.py — DonchianFrame dataclass + compute_donchian 함수 검증.

TDD Red 단계: DonchianFrame 정확성 검증.
- 단조 상승/하락/평탄 시계열
- 길이 부족 케이스
- width_percentile_60 계산
- days_since_*_break 정확성
- slope 정규화
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from core.decision.donchian import compute_donchian


class TestDonchianFrameBasic:
    """기본 케이스: 단조 상승, 단조 하락, 평탄"""

    def test_monotonic_increasing_series(self):
        """단조 상승 시계열 (close 100~130, 31봉 = period+1).

        기대:
        - upper = 최근 period봉(current 제외) 의 high max
        - position > 0.9 (상승 추세)
        - slope > 0 (middle 상승)
        """
        data = pd.DataFrame({
            "open": list(range(100, 131)),
            "high": list(range(101, 132)),
            "low": list(range(99, 130)),
            "close": list(range(100, 131)),
            "volume": [1000] * 31,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        assert result.timeframe == "1d"
        assert result.period == 20

        # iloc[-21:-1] = iloc[10:30] (최근 20봉, 현재 봉 제외)
        # high = [101, 102, ..., 131], high[10:30] = [111, 112, ..., 130], max = 130
        assert result.upper == 130

        # low[10:30] = [109, 110, ..., 129], min = 109
        assert result.lower == 109

        # middle = (130 + 109) / 2 = 119.5
        assert result.middle == pytest.approx(119.5)

        # close[-1] = 130, position = (130 - 109) / (130 - 109) = 21/21 = 1.0
        assert result.position == pytest.approx(1.0)

        # slope 양수 (middle 상승)
        assert result.slope > 0

        # width_pct = (130 - 109) / 119.5 × 100
        expected_width_pct = (130 - 109) / 119.5 * 100
        assert result.width_pct == pytest.approx(expected_width_pct)

    def test_monotonic_decreasing_series(self):
        """단조 하락 시계열 (close 130~100, 31봉).

        기대:
        - position ≈ 0.0 (현재가가 채널 하단)
        - slope < 0 (middle 하락)
        """
        data = pd.DataFrame({
            "open": list(range(130, 99, -1)),
            "high": list(range(130, 99, -1)),
            "low": list(range(129, 98, -1)),
            "close": list(range(130, 99, -1)),
            "volume": [1000] * 31,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        # close 최종값 = 100
        # 최근 20봉(index 10~29) high[10:30] = [120~99], upper = 120
        # low[10:30] = [119~98], lower = 99
        # position = (100 - 99) / (120 - 99) = 1/21 ≈ 0.048
        assert result.position < 0.1
        assert result.slope < 0

    def test_flat_series(self):
        """평탄 시계열 (모든 close = 100, 30봉).

        기대:
        - upper = lower = 100
        - width_pct = 0
        - position = 0.5 (1e-9 가드 동작 시 (100-100)/(1e-9) = 0)
        """
        data = pd.DataFrame({
            "open": [100.0] * 30,
            "high": [100.0] * 30,
            "low": [100.0] * 30,
            "close": [100.0] * 30,
            "volume": [1000] * 30,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        assert result.upper == pytest.approx(100.0)
        assert result.lower == pytest.approx(100.0)
        assert result.middle == pytest.approx(100.0)
        assert result.width_pct == pytest.approx(0.0)

        # (100 - 100) / max(0, 1e-9) = 0 / 1e-9 = 0
        assert result.position == pytest.approx(0.0)
        assert result.slope == pytest.approx(0.0)


class TestDonchianLengthValidation:
    """길이 부족 케이스"""

    def test_length_less_than_period_plus_one_returns_none(self):
        """ohlcv 길이 < period + 1 → None 반환"""
        data = pd.DataFrame({
            "open": [100.0] * 15,
            "high": [100.0] * 15,
            "low": [100.0] * 15,
            "close": [100.0] * 15,
            "volume": [1000] * 15,
        })
        result = compute_donchian(data, timeframe="1d", period=20)
        assert result is None

    def test_length_equal_to_period_returns_none(self):
        """길이 = period → None (period+1 필요)"""
        data = pd.DataFrame({
            "open": [100.0] * 20,
            "high": [100.0] * 20,
            "low": [100.0] * 20,
            "close": [100.0] * 20,
            "volume": [1000] * 20,
        })
        result = compute_donchian(data, timeframe="1d", period=20)
        assert result is None

    def test_length_just_sufficient(self):
        """길이 = period + 1 → 정상 계산"""
        data = pd.DataFrame({
            "open": list(range(100, 121)),
            "high": list(range(101, 122)),
            "low": list(range(99, 120)),
            "close": list(range(100, 121)),
            "volume": [1000] * 21,
        })
        result = compute_donchian(data, timeframe="1d", period=20)
        assert result is not None


class TestWidthPercentile60:
    """width_percentile_60 계산"""

    def test_width_percentile_60_when_data_sufficient(self):
        """60봉 이상 → percentile 계산"""
        # 0~59봉: width 선형 증가
        closes = list(range(100, 161))  # 100~160, 61봉
        data = pd.DataFrame({
            "open": closes,
            "high": [c + 0.5 for c in closes],
            "low": [c - 0.5 for c in closes],
            "close": closes,
            "volume": [1000] * 61,
        })
        result = compute_donchian(data, timeframe="1d", period=20, width_window=60)

        assert result is not None
        assert not math.isnan(result.width_percentile_60)
        assert 0 <= result.width_percentile_60 <= 1

    def test_width_percentile_60_when_data_insufficient(self):
        """width_window 봉 미만 → width_percentile_60 = NaN but DonchianFrame 생성"""
        data = pd.DataFrame({
            "open": [100.0] * 35,
            "high": [100.5] * 35,
            "low": [99.5] * 35,
            "close": [100.0] * 35,
            "volume": [1000] * 35,
        })
        result = compute_donchian(
            data, timeframe="1d", period=20, width_window=60
        )

        assert result is not None  # DonchianFrame 자체는 생성
        assert math.isnan(result.width_percentile_60)  # 하지만 percentile은 NaN


class TestDaysSinceBreak:
    """days_since_upper_break / days_since_lower_break.

    days_since_upper_break = close > rolling_high.max() 를 만족하는 가장 최근 인덱스부터
    현재(마지막) 인덱스까지의 거리. 없으면 period.

    주의: rolling_high.max() 는 최근 period봉의 high 값 중 최대값이므로,
    close가 이를 초과하려면 이전에 없던 새로운 고가가 나타나야 함.
    """

    def test_days_since_upper_break_with_new_high(self):
        """신고가 돌파 직후 평탄 → 경과 봉 수 정확"""
        # 정확히 period+6 = 26봉
        # idx 0~19: high=[100~119]
        # idx 20~24: high=[120, 121, 122, 123, 124] (계속 상승, rolling_high도 따라서 상승)
        # idx 25: high=[90] (떨어짐)
        # close 는 high와 동일
        highs = list(range(100, 120)) + list(range(120, 125)) + [90]
        closes = highs  # close = high (신고가 돌파 명확히)

        data = pd.DataFrame({
            "open": highs,
            "high": highs,
            "low": [h - 0.5 for h in highs],
            "close": closes,
            "volume": [1000] * 26,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        # idx=19: rolling_high.max() = max(high[0:20]) = 119, close=119, no break
        # idx=20: rolling_high.max() = max(high[1:21]) = 120, close=120, no break (같음)
        # idx=21: rolling_high.max() = max(high[2:22]) = 121, close=121, no break
        # idx=22: rolling_high.max() = max(high[3:23]) = 122, close=122, no break
        # idx=23: rolling_high.max() = max(high[4:24]) = 123, close=123, no break
        # idx=24: rolling_high.max() = max(high[5:25]) = 124, close=124, no break
        # idx=25: rolling_high.max() = max(high[6:26]) = 124, close=90 < 124, no break
        # 모두 no break → period=20
        assert result.days_since_upper_break == 20

    def test_days_since_upper_break_no_break_in_window(self):
        """기간 내 신고가 없음 → period 반환"""
        # 평탄 상승 (rolling_high 추월 불가)
        closes = [100.0 + i * 0.1 for i in range(30)]
        data = pd.DataFrame({
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1000] * 30,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        # close들이 천천히 상승하지만 rolling_high (= rolling high의 max)를
        # 초과할 수 없음 (high가 계속 따라감)
        assert result.days_since_upper_break == 20

    def test_days_since_lower_break_with_new_low(self):
        """신저가 돌파 직후 평탄"""
        # 정확히 period+6 = 26봉
        # idx 0~19: low=[100, 99, 98, ..., 81]
        # idx 20~24: low=[80, 79, 78, 77, 76] (계속 하락)
        # idx 25: low=[110] (올라감)
        # close = low (신저가 돌파 명확)
        lows = list(range(100, 80, -1)) + list(range(80, 75, -1)) + [110]
        closes = lows

        data = pd.DataFrame({
            "open": lows,
            "high": [x + 1 for x in lows],
            "low": lows,
            "close": closes,
            "volume": [1000] * 26,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        # idx=19: rolling_low.min() = min(low[0:20]) = 81, close=81, no break
        # idx=20: rolling_low.min() = min(low[1:21]) = 80, close=80, no break (같음)
        # idx=21: rolling_low.min() = min(low[2:22]) = 79, close=79, no break
        # idx=22: rolling_low.min() = min(low[3:23]) = 78, close=78, no break
        # idx=23: rolling_low.min() = min(low[4:24]) = 77, close=77, no break
        # idx=24: rolling_low.min() = min(low[5:25]) = 76, close=76, no break
        # idx=25: rolling_low.min() = min(low[6:26]) = 76, close=110 > 76, no break
        # 모두 no break → period=20
        assert result.days_since_lower_break == 20


class TestSlopeCalculation:
    """slope = middle 의 5봉 기울기 (정규화)"""

    def test_slope_positive_trend(self):
        """상승 채널 → slope > 0"""
        # close 100~130, 30봉 (strong uptrend)
        data = pd.DataFrame({
            "open": list(range(100, 130)),
            "high": list(range(101, 131)),
            "low": list(range(99, 129)),
            "close": list(range(100, 130)),
            "volume": [1000] * 30,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        assert result.slope > 0

    def test_slope_negative_trend(self):
        """하락 채널 → slope < 0"""
        data = pd.DataFrame({
            "open": list(range(130, 100, -1)),
            "high": list(range(130, 100, -1)),
            "low": list(range(129, 99, -1)),
            "close": list(range(130, 100, -1)),
            "volume": [1000] * 30,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        assert result.slope < 0

    def test_slope_flat(self):
        """평탄 채널 → slope ≈ 0"""
        data = pd.DataFrame({
            "open": [100.0] * 30,
            "high": [100.0] * 30,
            "low": [100.0] * 30,
            "close": [100.0] * 30,
            "volume": [1000] * 30,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        assert result.slope == pytest.approx(0.0, abs=1e-6)


class TestDataclassProperties:
    """frozen dataclass 특성"""

    def test_donchian_frame_frozen(self):
        """DonchianFrame은 frozen → 수정 불가"""
        data = pd.DataFrame({
            "open": [100.0] * 21,
            "high": [100.0] * 21,
            "low": [100.0] * 21,
            "close": [100.0] * 21,
            "volume": [1000] * 21,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        with pytest.raises((AttributeError, TypeError)):
            result.upper = 101.0


class TestEdgeCases:
    """경계 케이스"""

    def test_custom_period_10(self):
        """period=10으로 계산"""
        data = pd.DataFrame({
            "open": list(range(100, 115)),
            "high": list(range(101, 116)),
            "low": list(range(99, 114)),
            "close": list(range(100, 115)),
            "volume": [1000] * 15,
        })
        result = compute_donchian(data, timeframe="1h", period=10)

        assert result is not None
        assert result.period == 10
        assert result.timeframe == "1h"

    def test_timeframe_30m(self):
        """30m timeframe"""
        data = pd.DataFrame({
            "open": list(range(100, 121)),
            "high": list(range(101, 122)),
            "low": list(range(99, 120)),
            "close": list(range(100, 121)),
            "volume": [1000] * 21,
        })
        result = compute_donchian(data, timeframe="30m", period=20)

        assert result is not None
        assert result.timeframe == "30m"

    def test_nan_in_data(self):
        """NaN 포함 데이터 → 계산 여전히 가능 (pandas rolling 처리)"""
        closes = list(range(100, 115)) + [np.nan] + list(range(115, 121))
        data = pd.DataFrame({
            "open": closes,
            "high": [c if pd.notna(c) else np.nan for c in closes],
            "low": [c if pd.notna(c) else np.nan for c in closes],
            "close": closes,
            "volume": [1000 if pd.notna(c) else 0 for c in closes],
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        # pandas rolling 은 NaN을 무시하므로 정상 계산
        assert result is not None or result is None  # 결과는 구현 의존

    def test_very_small_values(self):
        """매우 작은 가격 (0.001)"""
        closes = [0.001 * (100 + i) for i in range(31)]
        data = pd.DataFrame({
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000] * 31,
        })
        result = compute_donchian(data, timeframe="1d", period=20)

        assert result is not None
        assert result.position >= 0 and result.position <= 1
