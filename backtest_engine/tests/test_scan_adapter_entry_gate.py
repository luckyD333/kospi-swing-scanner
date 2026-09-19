"""WF 경로의 entry gate 배선.

배경: _build_ctx 가 per_ticker_regime 을 안 채워 entry_gate 의
`if regime is None: return True` 가 전략 7개의 게이트를 전부 무력화했다.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from backtest_engine.scan_adapter import (
    ScanBarConfig,
    ScanPnlConfig,
    _build_ctx,
    make_scan_bartracker_scorer,
    make_scan_pnl_scorer,
)
from core.decision.per_ticker_regime import build_regime_grid, daily_regime_series
from core.strategy_base import Candidate, ScanContext


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


class _국면_기록기:
    """scan() 마다 ctx.per_ticker_regime 을 찍어 두고 후보는 0건 반환."""

    name = "_spy"

    def __init__(self) -> None:
        self.seen: list[dict] = []

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        self.seen.append(dict(ctx.per_ticker_regime))
        return []


def test_기본값은_국면을_채운다():
    spy = _국면_기록기()
    data = {"AAA": _합성_일봉(120, 1)}
    scorer = make_scan_pnl_scorer(lambda _p: spy, ScanPnlConfig(top_n=1))
    d = data["AAA"].index[110]

    scorer(data, {}, d, d)

    assert spy.seen and spy.seen[0].get("AAA") is not None


def test_게이트를_끄면_국면이_비어_있다():
    spy = _국면_기록기()
    data = {"AAA": _합성_일봉(120, 1)}
    scorer = make_scan_pnl_scorer(
        lambda _p: spy, ScanPnlConfig(top_n=1, apply_entry_gate=False)
    )
    d = data["AAA"].index[110]

    scorer(data, {}, d, d)

    assert spy.seen == [{}]


def test_bartracker_도_기본값이_국면을_채운다():
    spy = _국면_기록기()
    data = {"AAA": _합성_일봉(120, 1)}
    scorer = make_scan_bartracker_scorer(lambda _p: spy, ScanBarConfig(top_n=1))
    d = data["AAA"].index[110]

    scorer(data, {}, d, d)

    assert spy.seen and spy.seen[0].get("AAA") is not None


def test_국면은_lookback_buffer_와_무관하게_전체_이력으로_계산한다():
    """buffer=0 이면 슬라이스 워밍업이 0봉이라, 슬라이스 기반이었다면 라벨이 어긋난다."""
    spy = _국면_기록기()
    data = {"AAA": _합성_일봉(200, 1)}
    d = data["AAA"].index[180]
    scorer = make_scan_pnl_scorer(
        lambda _p: spy, ScanPnlConfig(top_n=1, lookback_buffer_days=0)
    )

    scorer(data, {}, d, d)

    expected = daily_regime_series(data["AAA"]).loc[d]
    assert spy.seen[0]["AAA"] == expected


def test_grid_는_파라미터를_바꿔도_한_번만_만든다():
    """walk_forward 는 같은 ohlcv_data 로 파라미터만 바꿔 수백 번 부른다."""
    import backtest_engine.scan_adapter as sa

    calls = {"n": 0}
    original = sa.build_regime_grid

    def 세는_래퍼(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    sa.build_regime_grid = 세는_래퍼
    try:
        data = {"AAA": _합성_일봉(120, 1)}
        scorer = make_scan_pnl_scorer(lambda _p: _국면_기록기(), ScanPnlConfig(top_n=1))
        d = data["AAA"].index[110]
        for i in range(5):
            scorer(data, {"x": i}, d, d)
    finally:
        sa.build_regime_grid = original

    assert calls["n"] == 1


def test_1h_부재_경고는_grid_를_만들_때만_남긴다(caplog):
    """파라미터를 5번 바꿔도 grid 는 한 번만 만들어지므로 경고도 한 번이다."""
    data = {"AAA": _합성_일봉(120, 1)}
    scorer = make_scan_pnl_scorer(lambda _p: _국면_기록기(), ScanPnlConfig(top_n=1))
    d = data["AAA"].index[110]

    with caplog.at_level(logging.WARNING, logger="backtest_engine.scan_adapter"):
        for i in range(5):
            scorer(data, {"x": i}, d, d)

    hits = [r for r in caplog.records if "setup_score" in r.getMessage()]
    assert len(hits) == 1


def test_1h_부재_경고를_한_번만_남긴다(caplog):
    data = {"AAA": _합성_일봉(120, 1)}
    scorer = make_scan_pnl_scorer(lambda _p: _국면_기록기(), ScanPnlConfig(top_n=1))
    d = data["AAA"].index[110]

    with caplog.at_level(logging.WARNING, logger="backtest_engine.scan_adapter"):
        scorer(data, {}, d, d)

    hits = [r for r in caplog.records if "setup_score" in r.getMessage()]
    assert len(hits) == 1


def test_게이트를_끄면_경고도_없다(caplog):
    data = {"AAA": _합성_일봉(120, 1)}
    scorer = make_scan_pnl_scorer(
        lambda _p: _국면_기록기(), ScanPnlConfig(top_n=1, apply_entry_gate=False)
    )
    d = data["AAA"].index[110]

    with caplog.at_level(logging.WARNING, logger="backtest_engine.scan_adapter"):
        scorer(data, {}, d, d)

    assert [r for r in caplog.records if "setup_score" in r.getMessage()] == []


def test_통계에_setup_score_부재를_남긴다():
    data = {"AAA": _합성_일봉(120, 1)}
    scorer = make_scan_bartracker_scorer(
        lambda _p: _국면_기록기(), ScanBarConfig(top_n=1, emit_stats=True)
    )
    d = data["AAA"].index[110]

    scorer(data, {}, d, d)

    assert scorer.last_stats["setup_score_unavailable"] is True
