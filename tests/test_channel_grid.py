"""tests/test_channel_grid.py — strategies/_channel_grid.py 순수 기하 함수 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies._channel_grid import (
    Line,
    build_grid,
    build_support_line,
    find_confirmed_pivots,
)
from tests.fixtures_channel_grid import scenario_df


def test_확정_피벗만_반환하고_평탄_고점은_마지막_인덱스로_접는다():
    vals = np.array([1, 2, 3, 5, 5, 5, 3, 2, 1, 2, 4, 2, 1, 1, 1], dtype=float)
    # 고점 5 는 인덱스 3,4,5 연속 → 5 하나. 인덱스 10(값 4)은 오른쪽 3봉이 있어 확정.
    assert find_confirmed_pivots(vals, 3, highs=True) == [5, 10]


def test_오른쪽_봉이_부족한_마지막_고점은_미확정이다():
    vals = np.array([1, 2, 1, 1, 1, 1, 9], dtype=float)
    assert find_confirmed_pivots(vals, 2, highs=True) == []


def test_저점_피벗은_부호를_뒤집은_고점과_같다():
    vals = np.array([9, 8, 7, 5, 5, 5, 7, 8, 9, 8, 6, 8, 9, 9, 9], dtype=float)
    assert find_confirmed_pivots(vals, 3, highs=False) == [5, 10]


def test_길이가_창의_두_배보다_짧으면_빈_리스트():
    assert find_confirmed_pivots(np.array([1.0, 2.0, 3.0]), 3, highs=True) == []


def test_두_점_직선은_기울기와_외삽값을_계산한다():
    line = Line(x1=0, y1=100.0, x2=10, y2=90.0)
    assert line.slope == -1.0
    assert line.value_at(20) == 80.0


def test_시나리오에서_A_B_W_를_찾는다():
    df = scenario_df()
    grid = build_grid(df["high"].to_numpy(), df["low"].to_numpy(),
                      lookback_bars=60, pivot_window=3, max_level=3.0)
    assert grid is not None
    assert (grid.i_a, grid.i_b, grid.i_w) == (22, 40, 31)
    assert abs(grid.width - 46.9) < 0.2
    assert grid.baseline.slope < 0
    assert grid.levels[0] == -1.0 and grid.levels[-1] == 3.0 and len(grid.levels) == 9
    # 레벨 k 값 = 기준선 + k×W
    x = 79
    assert abs(grid.level_value(1.0, x) - (grid.baseline.value_at(x) + grid.width)) < 1e-9


def test_최고점이_마지막_창_안이면_격자가_없다():
    df = scenario_df()
    high = df["high"].to_numpy().copy()
    high[-1] = 1010.0
    assert build_grid(high, df["low"].to_numpy(),
                      lookback_bars=60, pivot_window=3, max_level=3.0) is None


def test_A_이후_확정_고점_피벗이_없으면_격자가_없다():
    n = 80
    high = np.linspace(1000, 900, n)  # 단조 하락: A=룩백 첫 봉, 이후 피벗 없음
    low = high - 5
    assert build_grid(high, low, lookback_bars=60, pivot_window=3, max_level=3.0) is None


def test_시나리오에서_P_Q_상승_지지선을_찾는다():
    df = scenario_df()
    line = build_support_line(df["low"].to_numpy(), lookback_bars=60, pivot_window=3)
    assert line is not None
    assert (line.x1, line.x2) == (61, 73)
    assert line.slope > 0


def test_최저점_이후_더_높은_저점_피벗이_없으면_지지선이_없다():
    low = np.linspace(1000, 900, 80)  # 단조 하락: 최저점이 마지막 봉
    assert build_support_line(low, lookback_bars=60, pivot_window=3) is None
