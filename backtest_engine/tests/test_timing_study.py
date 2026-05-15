import numpy as np
import pandas as pd
import pytest


# ── Task 1 ──────────────────────────────────────────────────────────────────

from backtest_engine.timing_study import (
    EntryWindow,
    MetricsAggregator,
    TimingStudyConfig,
    TimingStudyEngine,
    TimingStudyResult,
    TimingTrade,
)


def test_timing_trade_pnl_pct():
    trade = TimingTrade(
        strategy="strategy_one",
        ticker="005930",
        signal_date=pd.Timestamp("2026-01-02"),
        rank_bucket=1,
        entry_window=EntryWindow.MORNING,
        hold_days=1,
        entry_price=70000.0,
        exit_price=71400.0,
        commission_pct=0.0025,
    )
    expected = (71400 / 70000 - 1) * 100 - 0.25
    assert abs(trade.pnl_pct - expected) < 0.01


def test_config_defaults():
    cfg = TimingStudyConfig()
    assert EntryWindow.MORNING in cfg.entry_windows
    assert EntryWindow.AFTERNOON in cfg.entry_windows
    assert 0 in cfg.hold_periods and 3 in cfg.hold_periods


# ── Task 2 ──────────────────────────────────────────────────────────────────

from backtest_engine.historical_signals import HistoricalSignalGenerator, SignalRecord


def make_ohlcv(n: int = 60, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 10000 + np.cumsum(rng.standard_normal(n) * 100)
    return pd.DataFrame(
        {
            "open": close * 0.995,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(100_000, 1_000_000, n),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="B"),
    )


def test_signal_generator_returns_list():
    ohlcv_map = {"005930": make_ohlcv(60), "000660": make_ohlcv(60, seed=7)}
    gen = HistoricalSignalGenerator(min_lookback=25)
    signals = gen.extract("strategy_three", ohlcv_map)
    assert isinstance(signals, list)
    for s in signals:
        assert isinstance(s, SignalRecord)
        assert 0.0 <= s.score <= 1.0
        assert s.entry_price > 0


# ── Task 3 ──────────────────────────────────────────────────────────────────


def test_entry_price_morning():
    engine = TimingStudyEngine()
    bar = pd.Series({"open": 10000.0, "close": 10500.0})
    assert engine.calc_entry_price(bar, EntryWindow.MORNING) == 10000.0


def test_entry_price_afternoon():
    engine = TimingStudyEngine()
    bar = pd.Series({"open": 10000.0, "close": 10500.0})
    price = engine.calc_entry_price(bar, EntryWindow.AFTERNOON)
    assert abs(price - 10400.0) < 1.0


def test_exit_price_same_day():
    engine = TimingStudyEngine()
    df = pd.DataFrame(
        {"close": [10500, 10600, 10700, 10800]},
        index=pd.date_range("2026-01-02", periods=4, freq="B"),
    )
    assert engine.calc_exit_price(df, pd.Timestamp("2026-01-02"), hold_days=0) == 10500.0


def test_exit_price_two_days():
    engine = TimingStudyEngine()
    df = pd.DataFrame(
        {"close": [10500, 10600, 10700, 10800]},
        index=pd.date_range("2026-01-02", periods=4, freq="B"),
    )
    assert engine.calc_exit_price(df, pd.Timestamp("2026-01-02"), hold_days=2) == 10700.0


# ── Task 4 ──────────────────────────────────────────────────────────────────


def make_trades_fixture() -> list[TimingTrade]:
    trades = []
    for win, pnl in [
        (EntryWindow.MORNING, 2.0),
        (EntryWindow.MORNING, -1.0),
        (EntryWindow.AFTERNOON, 3.0),
        (EntryWindow.AFTERNOON, -0.5),
    ]:
        trades.append(
            TimingTrade(
                strategy="strategy_one",
                ticker="005930",
                signal_date=pd.Timestamp("2026-01-02"),
                rank_bucket=1,
                entry_window=win,
                hold_days=1,
                entry_price=10000.0,
                exit_price=10000.0 * (1 + pnl / 100),
                commission_pct=0.0,
            )
        )
    return trades


def test_aggregator_shape():
    agg = MetricsAggregator()
    df = agg.aggregate(make_trades_fixture())
    assert "avg_return" in df.columns
    assert "win_rate" in df.columns
    assert "sample_n" in df.columns


def test_aggregator_win_rate():
    agg = MetricsAggregator()
    df = agg.aggregate(make_trades_fixture())
    row = df[(df["entry_window"] == EntryWindow.MORNING) & (df["hold_days"] == 1)]
    assert row["win_rate"].iloc[0] == pytest.approx(0.5)
