"""tests/test_channel_grid.py — strategies/_channel_grid.py 순수 기하 함수 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.indicators import calc_atr
from strategies._channel_grid import (
    Line,
    LineRef,
    build_grid,
    build_support_line,
    channel_reasserted,
    find_breakout_day,
    find_confirmed_pivots,
    has_confluence,
    nearest_line_above,
    touched_from_above,
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


def _scenario_arrays():
    df = scenario_df()
    close = df["close"].to_numpy()
    volume = df["volume"].to_numpy()
    atr = calc_atr(df["high"], df["low"], df["close"], period=14).to_numpy()
    grid = build_grid(df["high"].to_numpy(), df["low"].to_numpy(),
                      lookback_bars=60, pivot_window=3, max_level=3.0)
    return df, close, volume, atr, grid


def test_시나리오의_돌파일은_62_하나다():
    _, close, volume, atr, grid = _scenario_arrays()
    d = find_breakout_day(close, volume, atr, grid.baseline, start=grid.i_b,
                          atr_mult=0.5, vol_bars=20)
    assert d == 62


def test_거래량_조건이_빠지면_돌파일이_없다():
    _, close, volume, atr, grid = _scenario_arrays()
    volume = volume.copy()
    volume[62] = 200_000
    assert find_breakout_day(close, volume, atr, grid.baseline, start=grid.i_b,
                             atr_mult=0.5, vol_bars=20) is None


def test_돌파_후_채널_복귀가_없으면_False():
    _, close, _, atr, grid = _scenario_arrays()
    assert channel_reasserted(close, atr, grid.baseline, d=62, band_mult=0.3) is False


def test_돌파_후_기준선_아래_마감이_있으면_True():
    _, close, _, atr, grid = _scenario_arrays()
    close = close.copy()
    close[66] = 920.0
    assert channel_reasserted(close, atr, grid.baseline, d=62, band_mult=0.3) is True


def _ref(kind, level, now, prev=None, future=None):
    return LineRef(kind=kind, level=level, value_now=now,
                   value_prev=prev if prev is not None else now,
                   value_future=future if future is not None else now)


def test_위에서_내려와_밴드_안에_닿고_선_위로_마감하면_터치다():
    ref = _ref("grid", 0.5, now=929.37, prev=931.0)
    assert touched_from_above(low_t=929.0, close_t=933.0, close_prev=940.0,
                              ref=ref, atr_t=6.44, band_mult=0.3) is True


def test_어제_선_아래였으면_터치가_아니다():
    ref = _ref("grid", 0.5, now=929.37, prev=931.0)
    assert touched_from_above(low_t=929.0, close_t=933.0, close_prev=930.0,
                              ref=ref, atr_t=6.44, band_mult=0.3) is False


def test_종가가_선_아래면_터치가_아니다():
    ref = _ref("grid", 0.5, now=929.37, prev=931.0)
    assert touched_from_above(low_t=925.0, close_t=928.0, close_prev=940.0,
                              ref=ref, atr_t=6.44, band_mult=0.3) is False


def test_다른_종류의_선이_밴드_안에_있으면_합류다():
    ref = _ref("grid", 1.0, now=952.8)
    others = [ref, _ref("grid", 1.5, now=976.0), _ref("support", None, now=954.0)]
    assert has_confluence(ref, others, atr_t=6.44, band_mult=0.3) is True
    assert has_confluence(ref, [ref, _ref("grid", 1.5, now=976.0)], atr_t=6.44, band_mult=0.3) is False


def test_목표선은_진입가_위_가장_가까운_선이며_터치선과_합류한_선은_제외한다():
    touched = _ref("grid", 0.5, now=929.37)
    refs = [touched, _ref("support", None, now=930.5), _ref("grid", 1.0, now=952.8),
            _ref("grid", 1.5, now=976.3)]
    target = nearest_line_above(entry=933.0, refs=refs, touched=touched, atr_t=6.44, band_mult=0.3)
    assert target is not None and target.level == 1.0


def test_진입가_위에_선이_없으면_None():
    touched = _ref("grid", 3.0, now=1000.0)
    assert nearest_line_above(entry=1005.0, refs=[touched], touched=touched,
                              atr_t=6.0, band_mult=0.3) is None


def test_동률_피벗이면_늦은_쪽을_고른다():
    base = np.linspace(900, 860, 70)                # 단조 하락이라 자체 피벗이 없다
    high = base.copy()
    high[15] = 1000.0                               # A
    high[30] = 960.0
    high[50] = 960.0                                # A 이후 동률 확정 고점 피벗 두 개
    grid = build_grid(high, high - 20.0, lookback_bars=60, pivot_window=3, max_level=3.0)
    assert (grid.i_a, grid.i_b) == (15, 50)

    low = -base + 1800                              # 단조 상승
    low[15] = 800.0                                 # P
    low[30] = 850.0
    low[50] = 850.0                                 # 동률 확정 저점 피벗 두 개
    line = build_support_line(low, lookback_bars=60, pivot_window=3)
    assert (line.x1, line.x2) == (15, 50)
