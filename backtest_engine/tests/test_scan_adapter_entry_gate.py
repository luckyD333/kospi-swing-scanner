"""WF 경로의 entry gate 배선.

배경: _build_ctx 가 per_ticker_regime 을 안 채워 entry_gate 의
`if regime is None: return True` 가 전략 7개의 게이트를 전부 무력화했다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_engine.scan_adapter import _build_ctx
from core.decision.per_ticker_regime import build_regime_grid, daily_regime_series


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


def test_grid_를_안_주면_기존처럼_비어_있다():
    data = {"AAA": _합성_일봉(100, 1)}

    ctx = _build_ctx(data["AAA"].index[90], data, market="KOSPI")

    assert ctx.per_ticker_regime == {}
    assert ctx.donchian_1h_by_ticker == {}


def test_grid_를_주면_해당_날짜_라벨이_채워진다():
    data = {"AAA": _합성_일봉(100, 1), "BBB": _합성_일봉(100, 2)}
    grid = build_regime_grid(data)
    d = data["AAA"].index[90]

    ctx = _build_ctx(d, data, market="KOSPI", regime_grid=grid)

    assert ctx.per_ticker_regime["AAA"] == grid["AAA"].loc[d]
    assert ctx.per_ticker_regime["BBB"] == grid["BBB"].loc[d]


def test_주입된_라벨에_룩어헤드가_없다():
    data = {"AAA": _합성_일봉(200, 1)}
    d = data["AAA"].index[120]
    grid = build_regime_grid(data)

    ctx = _build_ctx(d, data, market="KOSPI", regime_grid=grid)

    truncated = daily_regime_series(data["AAA"].loc[:d])
    assert ctx.per_ticker_regime["AAA"] == truncated.iloc[-1]


def test_그_날짜_이전_봉이_없는_종목은_빠진다():
    """regime None → gate 우회. 기존 동작을 유지한다."""
    data = {"AAA": _합성_일봉(100, 1)}
    grid = build_regime_grid(data)
    early = data["AAA"].index[0] - pd.Timedelta(days=5)

    ctx = _build_ctx(early, data, market="KOSPI", regime_grid=grid)

    assert "AAA" not in ctx.per_ticker_regime
