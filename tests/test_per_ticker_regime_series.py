"""종목별 regime 시계열의 동치·무룩어헤드 고정.

daily_regime_series(df).iloc[i] 는 compute_donchian(df.iloc[:i+1]) → daily_regime 과
반드시 같아야 한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.decision.donchian import compute_donchian
from core.decision.per_ticker_regime import (
    REGIME_LABELS,
    daily_regime,
    daily_regime_series,
)


def _합성_일봉(n: int = 160, seed: int = 7) -> pd.DataFrame:
    """상승 추세에 랜덤워크를 얹는다. 7개 국면이 고루 나오도록 진폭을 크게 잡는다."""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.linspace(0.0, 25.0, n) + rng.normal(0.0, 1.5, n).cumsum()
    close = np.maximum(close, 5.0)
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.full(n, 1_000_000, dtype=float),
        },
        index=idx,
    )


def test_시계열의_인덱스와_라벨이_유효하다():
    df = _합성_일봉()
    s = daily_regime_series(df)

    assert isinstance(s, pd.Series)
    assert list(s.index) == list(df.index)
    assert set(s.unique()) <= set(REGIME_LABELS)


def test_봉마다_compute_donchian_결과와_일치한다():
    df = _합성_일봉()
    s = daily_regime_series(df)

    for i in range(len(df)):
        frame = compute_donchian(df.iloc[: i + 1], timeframe="1d")
        expected = "MIXED" if frame is None else daily_regime(frame)
        assert s.iloc[i] == expected, f"{i}번째 봉({df.index[i]}) 불일치"


def test_뒤에_봉을_더_붙여도_앞쪽_라벨은_그대로다():
    """무룩어헤드 고정 — 미래 봉이 과거 라벨을 바꾸면 안 된다."""
    df = _합성_일봉(200)
    cut = 150

    full = daily_regime_series(df)
    prefix = daily_regime_series(df.iloc[:cut])

    assert list(prefix) == list(full.iloc[:cut])


def test_이력이_짧으면_전부_MIXED_다():
    """period+1 미만이면 compute_donchian 이 None 을 준다."""
    df = _합성_일봉(10)

    assert list(daily_regime_series(df)) == ["MIXED"] * 10
