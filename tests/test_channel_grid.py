"""tests/test_channel_grid.py — strategies/_channel_grid.py 순수 기하 함수 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies._channel_grid import find_confirmed_pivots


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
