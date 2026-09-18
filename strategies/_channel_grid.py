"""
strategies/_channel_grid.py — 추세선·평행 격자 순수 기하 (Strategy Six 전용 부품).

ScanContext/Candidate 를 모르는 numpy 함수만 둔다. 모든 인덱스는 전역 봉 인덱스.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import argrelextrema


def find_confirmed_pivots(values: np.ndarray, window: int, *, highs: bool) -> list[int]:
    """좌우 window 봉보다 높은(highs=True) 또는 낮은 값의 인덱스.

    - 오른쪽 window 봉이 존재해야 확정 (미래 정보 유입 방지).
    - argrelextrema 는 mode="clip" 이라 첫·끝 봉을 돌려주므로 경계를 잘라낸다.
    - 같은 값이 연속되는 평탄 구간은 마지막 인덱스 하나로 접는다.
    """
    n = len(values)
    if n < 2 * window + 1:
        return []
    cmp = np.greater_equal if highs else np.less_equal
    idx = argrelextrema(np.asarray(values, dtype=float), cmp, order=window)[0]
    idx = idx[(idx >= window) & (idx <= n - 1 - window)]
    if len(idx) == 0:
        return []
    runs = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    return [int(r[-1]) for r in runs]


@dataclass(frozen=True)
class Line:
    """두 점 (x1,y1),(x2,y2) 를 지나는 직선. x 는 봉 인덱스."""
    x1: int
    y1: float
    x2: int
    y2: float

    @property
    def slope(self) -> float:
        return (self.y2 - self.y1) / (self.x2 - self.x1)

    def value_at(self, x):
        """x 는 int 또는 ndarray. 외삽 허용."""
        return self.y1 + self.slope * (np.asarray(x, dtype=float) - self.x1)


@dataclass(frozen=True)
class Grid:
    """레벨 0 기준선과 폭 W 로 정의되는 평행 격자."""
    baseline: Line
    width: float
    i_a: int
    i_b: int
    i_w: int
    levels: tuple[float, ...]

    def level_value(self, k: float, x) -> float:
        return float(self.baseline.value_at(x) + k * self.width)


def build_grid(high: np.ndarray, low: np.ndarray, *, lookback_bars: int,
               pivot_window: int, max_level: float) -> Grid | None:
    """룩백 최고점 A, 이후 최고 확정 고점 피벗 B, A~B 최저점으로 폭 W.

    A 가 마지막 pivot_window 봉 안이면 (오늘이 신고가) 채널 없음 → None.
    """
    n = len(high)
    if n < lookback_bars:
        return None
    s = n - lookback_bars
    i_a = s + int(np.argmax(high[s:]))
    if i_a > n - 1 - pivot_window:
        return None
    pivots = [s + i for i in find_confirmed_pivots(high[s:], pivot_window, highs=True)]
    pivots = [i for i in pivots if i > i_a and high[i] < high[i_a]]
    if not pivots:
        return None
    i_b = max(pivots, key=lambda i: (high[i], i))  # 가장 높은 것, 동률이면 늦은 것
    baseline = Line(i_a, float(high[i_a]), i_b, float(high[i_b]))
    seg = np.arange(i_a, i_b + 1)
    dist = baseline.value_at(seg) - low[i_a:i_b + 1]
    j = int(np.argmax(dist))
    width = float(dist[j])
    if width <= 0:
        return None
    levels = tuple(float(k) for k in np.arange(-1.0, max_level + 0.25, 0.5))
    return Grid(baseline, width, i_a, i_b, i_a + j, levels)
