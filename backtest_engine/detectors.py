"""
detectors.py — 패턴 감지기

쌍바닥 감지는 3가지 방안을 구현하여 백테스트로 비교한다:
  - DoubleBottomSimple:   단순 swing low 기반 (빠름, 노이즈 많음)
  - DoubleBottomFractal:  Williams Fractal 기반 (엄격, 놓치는 패턴 많음)
  - DoubleBottomProminence: scipy find_peaks 기반 (깊이 고려)

Version A/B/C 중 어느 것이 실전 백테스트에서 최고 성과인지 비교하는 것이 목적.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

# ============================================================================
# 쌍바닥 감지 인터페이스
# ============================================================================

@dataclass
class DoubleBottomResult:
    """쌍바닥 감지 결과"""
    first_bottom_idx: int
    second_bottom_idx: int
    first_bottom_price: float
    second_bottom_price: float
    gap_bars: int

    def __repr__(self):
        return (
            f"DoubleBottom(idx_1={self.first_bottom_idx}, idx_2={self.second_bottom_idx}, "
            f"gap={self.gap_bars} bars)"
        )


class DoubleBottomDetector(ABC):
    """쌍바닥 감지기 추상 베이스"""

    @abstractmethod
    def detect(self, df: pd.DataFrame) -> DoubleBottomResult | None:
        """
        최근 쌍바닥 감지.

        Args:
            df: OHLCV DataFrame (최근 N봉)

        Returns:
            DoubleBottomResult 또는 None. 2차 바닥이 최근 2봉 이내여야 함.
        """
        ...


# ============================================================================
# Version A: 단순 swing low 기반
# ============================================================================

class DoubleBottomSimple(DoubleBottomDetector):
    """
    단순 swing low 기반 쌍바닥.

    알고리즘:
      1. 2차 바닥: 최근 freshness+1 봉 중 최저점. 왼쪽 swing_window 봉보다 낮아야 함
         (rightward swing은 진입 시점에 확인 불가능하므로 생략)
      2. 1차 바닥: 2차 바닥 이전 구간에서 standard swing low (좌우 모두)
      3. 두 바닥 간격 [min_gap, max_gap], 가격 차이 ≤ price_tolerance

    장점: 빠름, 구현 간단
    단점: 2차 바닥 확정 어려움 (rightward 확인 불가)
    """

    def __init__(
        self,
        swing_window: int = 3,
        min_gap: int = 5,
        max_gap: int = 20,
        price_tolerance: float = 0.03,
        freshness: int = 2,
    ):
        self.swing_window = swing_window
        self.min_gap = min_gap
        self.max_gap = max_gap
        self.price_tolerance = price_tolerance
        self.freshness = freshness

    def detect(self, df: pd.DataFrame) -> DoubleBottomResult | None:
        n = len(df)
        if n < self.swing_window * 2 + self.min_gap + 1:
            return None

        lows = df["low"].values

        # Step 1: 2차 바닥 후보 = 최근 freshness+1 봉 중 최저점
        region_size = self.freshness + 1
        start = n - region_size
        region = lows[start:]
        idx_2 = start + int(region.argmin())

        # 2차 바닥은 왼쪽 swing_window 봉보다 낮아야 (좌측 swing 확인)
        left_start = max(0, idx_2 - self.swing_window)
        if idx_2 <= left_start:
            return None
        if lows[idx_2] >= lows[left_start:idx_2].min():
            return None

        # Step 2: 1차 바닥 후보 탐색 (2차 바닥 이전 구간)
        candidates = self._find_left_swing_lows(lows, upper_bound=idx_2)
        if not candidates:
            return None

        # Step 3: 가장 최근 후보부터 유효성 검사
        for idx_1 in reversed(candidates):
            result = self._validate(df, idx_1, idx_2)
            if result is not None:
                return result

        return None

    def _find_left_swing_lows(self, lows, upper_bound: int) -> list[int]:
        """standard swing low (좌우 swing_window 봉보다 낮은 지점)"""
        candidate_price = lows[upper_bound]  # 2차 바닥 가격
        candidates = []
        for i in range(self.swing_window, upper_bound - self.swing_window):
            window = lows[i - self.swing_window : i + self.swing_window + 1]
            if lows[i] == window.min() and lows[i] < candidate_price * 1.05:
                # 1차 바닥 후보는 2차 바닥과 비슷한 레벨 근처여야
                candidates.append(i)
        return candidates

    def _validate(self, df: pd.DataFrame, idx_1: int, idx_2: int) -> DoubleBottomResult | None:
        gap = idx_2 - idx_1
        if not (self.min_gap <= gap <= self.max_gap):
            return None

        p1 = float(df["low"].iloc[idx_1])
        p2 = float(df["low"].iloc[idx_2])
        if abs(p2 - p1) / p1 > self.price_tolerance:
            return None

        return DoubleBottomResult(
            first_bottom_idx=idx_1,
            second_bottom_idx=idx_2,
            first_bottom_price=p1,
            second_bottom_price=p2,
            gap_bars=gap,
        )


# ============================================================================
# Version B: Williams Fractal (5봉)
# ============================================================================

class DoubleBottomFractal(DoubleBottomSimple):
    """
    Williams Fractal (5봉): 중간 봉이 좌우 2봉씩보다 모두 낮음.

    더 엄격한 1차 바닥 판정. 2차 바닥은 Simple과 동일 방식.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("swing_window", 2)
        super().__init__(**kwargs)

    def _find_left_swing_lows(self, lows, upper_bound: int) -> list[int]:
        """Williams fractal: 중간이 좌우 2봉 모두보다 엄격하게 낮음"""
        candidate_price = lows[upper_bound]  # 2차 바닥 가격
        candidates = []
        for i in range(2, upper_bound - 2):
            if (
                lows[i] < lows[i - 1]
                and lows[i] < lows[i - 2]
                and lows[i] < lows[i + 1]
                and lows[i] < lows[i + 2]
                and lows[i] < candidate_price * 1.05
            ):
                candidates.append(i)
        return candidates


# ============================================================================
# Version C: scipy prominence 기반
# ============================================================================

class DoubleBottomProminence(DoubleBottomSimple):
    """
    scipy.signal.find_peaks로 1차 바닥 탐색.
    prominence 기반: 얕은 바닥은 필터링.

    2차 바닥은 Simple과 동일 (마지막 구간 최저점).
    """

    def __init__(self, prominence_pct: float = 0.015, **kwargs):
        super().__init__(**kwargs)
        self.prominence_pct = prominence_pct

    def _find_left_swing_lows(self, lows, upper_bound: int) -> list[int]:
        if upper_bound < 5:
            return []

        inverted = -lows[:upper_bound]
        median_price = float(np.median(lows[:upper_bound]))
        min_prominence = median_price * self.prominence_pct

        peaks, _ = find_peaks(inverted, prominence=min_prominence, distance=self.min_gap)
        if len(peaks) == 0:
            return []

        # 2차 바닥 레벨의 ±5% 이내만
        ref_low = lows[upper_bound]
        return [int(p) for p in peaks if lows[p] <= ref_low * 1.05]


# ============================================================================
# 캔들 패턴
# ============================================================================

def is_bullish_engulfing(df: pd.DataFrame, idx: int) -> bool:
    """
    상승 장악형 양봉: 직전 음봉 몸통을 완전히 감싸는 양봉.

    조건:
      - 직전 봉: close < open (음봉)
      - 현재 봉: close > open (양봉)
      - 현재 시가 <= 직전 종가
      - 현재 종가 >= 직전 시가
    """
    if idx < 1 or idx >= len(df):
        return False
    prev = df.iloc[idx - 1]
    curr = df.iloc[idx]
    prev_bearish = prev["close"] < prev["open"]
    curr_bullish = curr["close"] > curr["open"]
    engulf = curr["open"] <= prev["close"] and curr["close"] >= prev["open"]
    return bool(prev_bearish and curr_bullish and engulf)


def is_bearish_engulfing(df: pd.DataFrame, idx: int) -> bool:
    """하락 장악형 음봉"""
    if idx < 1 or idx >= len(df):
        return False
    prev = df.iloc[idx - 1]
    curr = df.iloc[idx]
    prev_bullish = prev["close"] > prev["open"]
    curr_bearish = curr["close"] < curr["open"]
    engulf = curr["open"] >= prev["close"] and curr["close"] <= prev["open"]
    return bool(prev_bullish and curr_bearish and engulf)


def count_consecutive_bearish(df: pd.DataFrame, idx: int, max_lookback: int = 10) -> int:
    """idx 이하에서 연속 음봉 수를 센다 (idx 포함)"""
    if idx < 0 or idx >= len(df):
        return 0
    count = 0
    for i in range(idx, max(-1, idx - max_lookback), -1):
        row = df.iloc[i]
        if row["close"] < row["open"]:
            count += 1
        else:
            break
    return count


def is_today_bullish(df: pd.DataFrame, idx: int) -> bool:
    """당일 봉이 양봉인가"""
    if idx < 0 or idx >= len(df):
        return False
    row = df.iloc[idx]
    return bool(row["close"] > row["open"])
