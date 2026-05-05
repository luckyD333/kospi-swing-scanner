"""tests/test_price_utils_limit.py — find_limit_entry, compute_limit_stop, populate_limit_fields 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd

from strategies.price_utils import (
    compute_limit_stop,
    find_limit_entry,
    populate_limit_fields,
)


def _make_df(lows: list[float], highs: list[float] | None = None) -> pd.DataFrame:
    """30m OHLCV mock — low 시리즈만 의미 있고 나머지는 채움."""
    n = len(lows)
    highs = highs or [v + 10 for v in lows]
    return pd.DataFrame(
        {
            "open": lows,
            "high": highs,
            "low": lows,
            "close": [(h + lo) / 2 for h, lo in zip(highs, lows)],
            "volume": [10000] * n,
        }
    )


# ──────────── find_limit_entry ────────────


def test_find_limit_entry_pivot_in_range():
    # 13봉 중 가운데 봉이 pivot low (980), 나머지는 더 높음
    lows = [1000, 990, 985, 980, 985, 990, 995, 998, 1000, 1002, 1005, 1003, 1001]
    df = _make_df(lows)
    result = find_limit_entry(df, entry=1000, stop_loss=975)
    assert result == 980


def test_find_limit_entry_pivot_below_stop():
    # pivot이 stop_loss(975) 이하면 None
    lows = [1000, 990, 985, 970, 985, 990, 995, 998, 1000, 1002, 1005, 1003, 1001]
    df = _make_df(lows)
    result = find_limit_entry(df, entry=1000, stop_loss=975)
    assert result is None


def test_find_limit_entry_pivot_above_entry():
    # 모든 low가 entry(1000) 이상이면 None
    lows = [1010, 1005, 1003, 1001, 1003, 1005, 1010, 1015, 1020, 1018, 1015, 1012, 1010]
    df = _make_df(lows)
    result = find_limit_entry(df, entry=1000, stop_loss=975)
    assert result is None


def test_find_limit_entry_insufficient_data():
    # order=2 는 최소 5봉 필요. 4봉이면 None
    df = _make_df([1000, 990, 985, 990])
    result = find_limit_entry(df, entry=1000, stop_loss=975)
    assert result is None


def test_find_limit_entry_none_df():
    result = find_limit_entry(None, entry=1000, stop_loss=975)
    assert result is None


# ──────────── compute_limit_stop ────────────


def test_compute_limit_stop_with_atr():
    # 50,000원 가격대 (tick=100). ATR ≈ 250 → limit_stop ≈ 49000 - 250 = 48750 → 48700
    n = 30
    rng = np.random.default_rng(42)
    lows = (50_000 + rng.normal(0, 200, n)).tolist()
    highs = [v + 500 for v in lows]
    df = _make_df(lows, highs)
    result = compute_limit_stop(limit_entry=49_000, df_30m=df, atr_period=14)
    # ATR 기반 결과는 limit_entry 보다 낮아야 함
    assert result < 49_000
    # KRX 호가 단위(10,000~50,000 → 50원) 적용 확인
    assert result % 50 == 0


def test_compute_limit_stop_atr_fallback():
    # df 가 너무 짧아 ATR 계산 불가 → limit_entry × 0.985 fallback
    df = _make_df([50_000, 49_500])  # 2봉, atr_period=14 미달
    result = compute_limit_stop(limit_entry=49_000, df_30m=df, atr_period=14)
    # 49000 × 0.985 = 48265 → floor_to_tick(50원 단위) = 48250
    assert result == 48_250


def test_compute_limit_stop_none_df():
    result = compute_limit_stop(limit_entry=49_000, df_30m=None)
    # 49000 × 0.985 = 48265 → 48250 (50원 단위)
    assert result == 48_250


# ──────────── populate_limit_fields ────────────


def test_populate_limit_fields_normal():
    n = 30
    rng = np.random.default_rng(42)
    base_lows = (1000 + rng.normal(0, 5, n)).tolist()
    # 마지막 13봉 중 하나에 985 pivot 주입
    base_lows[-7] = 985
    base_lows[-6] = 985  # less_equal 매치
    df = _make_df(base_lows)
    le, ls = populate_limit_fields(df, entry=1000, stop_loss=975)
    assert le is not None
    assert ls is not None
    assert ls < le < 1000


def test_populate_limit_fields_none_when_no_pivot():
    # 모든 low가 entry 이상
    df = _make_df([1010] * 20)
    le, ls = populate_limit_fields(df, entry=1000, stop_loss=975)
    assert le is None
    assert ls is None


def test_populate_limit_fields_none_when_df_none():
    le, ls = populate_limit_fields(None, entry=1000, stop_loss=975)
    assert le is None
    assert ls is None
