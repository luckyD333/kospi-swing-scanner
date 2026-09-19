"""전 종목 regime grid 선계산과 asof 조회."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.decision.per_ticker_regime import (
    REGIME_LABELS,
    build_regime_grid,
    daily_regime_series,
    regime_at,
)


def _합성_일봉(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.linspace(0.0, 20.0, n) + rng.normal(0.0, 1.5, n).cumsum()
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


def test_종목마다_시계열이_하나씩_생긴다():
    data = {"AAA": _합성_일봉(100, 1), "BBB": _합성_일봉(100, 2)}

    grid = build_regime_grid(data)

    assert set(grid) == {"AAA", "BBB"}
    assert list(grid["AAA"]) == list(daily_regime_series(data["AAA"]))


def test_해당_날짜의_라벨을_돌려준다():
    data = {"AAA": _합성_일봉(100, 1)}
    grid = build_regime_grid(data)
    d = data["AAA"].index[90]

    assert regime_at(grid, "AAA", d) == grid["AAA"].loc[d]
    assert regime_at(grid, "AAA", d) in REGIME_LABELS


def test_그_날_봉이_없으면_직전_봉_라벨을_쓴다():
    """실운영의 "가장 최근 봉" 동작과 맞춘다."""
    data = {"AAA": _합성_일봉(100, 1)}
    grid = build_regime_grid(data)
    last = data["AAA"].index[-1]

    assert regime_at(grid, "AAA", last + pd.Timedelta(days=10)) == grid["AAA"].iloc[-1]


def test_첫_봉보다_이전이면_None_이다():
    data = {"AAA": _합성_일봉(100, 1)}
    grid = build_regime_grid(data)
    first = data["AAA"].index[0]

    assert regime_at(grid, "AAA", first - pd.Timedelta(days=1)) is None


def test_모르는_종목이면_None_이다():
    grid = build_regime_grid({"AAA": _합성_일봉(100, 1)})

    assert regime_at(grid, "ZZZ", pd.Timestamp("2025-03-03")) is None
