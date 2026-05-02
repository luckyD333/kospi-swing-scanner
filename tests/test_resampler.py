"""
Task 5: resample_to (1D→1W, 1m→30m/1h).

검증:
  - 일봉 10개 (2주) → 주봉 2개, close 가 금요일 close
  - 분봉 120개 (2시간) → 30m 4개
  - 미지원 timeframe ValueError
  - 빈 DataFrame 입력은 빈 DataFrame 반환
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.cache.resampler import resample_to


def test_daily_to_weekly_friday_close():
    # 2026-04-13(월) ~ 2026-04-24(금): 10영업일 = 2주
    idx = pd.date_range("2026-04-13", "2026-04-24", freq="B")
    df = pd.DataFrame(
        {
            "open": list(range(10)),
            "high": list(range(10)),
            "low": list(range(10)),
            "close": list(range(10)),
            "volume": [100] * 10,
        },
        index=idx,
    )
    w = resample_to(df, "1W")
    assert len(w) == 2
    # 첫 주 close = 4 (월=0, 금=4)
    assert w["close"].iloc[0] == 4
    # high = 그 주 최대
    assert w["high"].iloc[0] == 4
    # 둘째 주 close = 9
    assert w["close"].iloc[1] == 9


def test_minute_to_30m():
    # 09:00 ~ 10:59 (120 분봉)
    idx = pd.date_range("2026-04-30 09:00", periods=120, freq="1min")
    df = pd.DataFrame(
        {
            "open": [1.0] * 120,
            "high": [2.0] * 120,
            "low": [0.5] * 120,
            "close": [1.5] * 120,
            "volume": [10] * 120,
        },
        index=idx,
    )
    out = resample_to(df, "30m")
    assert len(out) == 4
    assert out["high"].iloc[0] == 2.0
    assert out["volume"].iloc[0] == 300  # 30 * 10


def test_minute_to_1h():
    idx = pd.date_range("2026-04-30 09:00", periods=120, freq="1min")
    df = pd.DataFrame(
        {
            "open": [1.0] * 120,
            "high": [2.0] * 120,
            "low": [0.5] * 120,
            "close": [1.5] * 120,
            "volume": [10] * 120,
        },
        index=idx,
    )
    out = resample_to(df, "1h")
    assert len(out) == 2
    assert out["volume"].iloc[0] == 600  # 60 * 10


def test_unsupported_raises():
    with pytest.raises(ValueError, match="unsupported timeframe"):
        resample_to(pd.DataFrame(), "5s")


def test_empty_input_returns_empty():
    assert resample_to(pd.DataFrame(), "1W").empty
