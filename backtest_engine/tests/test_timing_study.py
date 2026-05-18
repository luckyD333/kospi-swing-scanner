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
    build_signal_cohorts,
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


# ── Cohort (전략 조합) ──────────────────────────────────────────────────────


def test_build_signal_cohorts_identifies_same_day_signals():
    date = pd.Timestamp("2026-01-10")
    signals = [
        SignalRecord("strategy_two", "005930", date, 0.8, 70000.0),
        SignalRecord("strategy_three", "005930", date, 0.9, 70000.0),
        SignalRecord("strategy_two", "000660", date, 0.7, 80000.0),
    ]
    cohorts = build_signal_cohorts(signals)
    assert cohorts[("005930", date)] == frozenset({"strategy_two", "strategy_three"})
    assert cohorts[("000660", date)] == frozenset({"strategy_two"})


def _make_cohort_trade(
    strategy: str, cohort: frozenset, pnl: float, hd: int = 1
) -> TimingTrade:
    return TimingTrade(
        strategy=strategy,
        ticker="005930",
        signal_date=pd.Timestamp("2026-01-02"),
        rank_bucket=1,
        entry_window=EntryWindow.MORNING,
        hold_days=hd,
        entry_price=10000.0,
        exit_price=10000.0 * (1 + pnl / 100),
        commission_pct=0.0,
        cohort=cohort,
    )


def test_aggregate_by_cohort_subset_match():
    cohort_234 = frozenset({"strategy_two", "strategy_three", "strategy_four"})
    trades = [
        _make_cohort_trade("strategy_two", cohort_234, 1.0) for _ in range(6)
    ]
    agg = MetricsAggregator()
    df = agg.aggregate_by_cohort(trades)
    combos = set(df["combo"].tolist())
    # query={2,3} 는 cohort {2,3,4} 의 부분집합이므로 포함
    assert "strategy_three+strategy_two" in combos
    # query={2,3,4} 도 정확 매칭으로 포함
    assert "strategy_four+strategy_three+strategy_two" in combos
    # query={2,5} 는 cohort 에 5 없음 → 제외
    assert "strategy_five+strategy_two" not in combos


def test_aggregate_by_cohort_min_sample_guard():
    # strategy_one 미포함 + sample_n=2 → 가드 적용으로 제외
    cohort_23 = frozenset({"strategy_two", "strategy_three"})
    trades = [_make_cohort_trade("strategy_two", cohort_23, 1.0) for _ in range(2)]
    df = MetricsAggregator().aggregate_by_cohort(trades)
    assert df.empty or "strategy_three+strategy_two" not in set(df["combo"].tolist())


def test_aggregate_by_cohort_strategy_one_bypass():
    # strategy_one 포함 combo 는 sample_n=1 이라도 노출
    cohort_12 = frozenset({"strategy_one", "strategy_two"})
    trades = [_make_cohort_trade("strategy_one", cohort_12, 5.0)]
    df = MetricsAggregator().aggregate_by_cohort(trades)
    combos = set(df["combo"].tolist())
    assert "strategy_one+strategy_two" in combos
    row = df[df["combo"] == "strategy_one+strategy_two"].iloc[0]
    assert int(row["sample_n"]) == 1


def test_aggregate_by_cohort_preserves_single_strategy_unchanged():
    # 회귀: cohort 도입이 기본 aggregate() 결과에 영향 없어야 함
    trades = make_trades_fixture()
    df = MetricsAggregator().aggregate(trades)
    assert "avg_return" in df.columns
    assert len(df) > 0
