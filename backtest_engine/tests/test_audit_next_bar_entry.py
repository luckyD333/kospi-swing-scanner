"""
test_audit_next_bar_entry.py — 감사 F1 후속: next_bar_entry 옵션 (제안 테스트 T-1).

same-bar(시그널 봉 close 체결) vs next-bar(다음 봉 open 체결) 진입 타이밍 검증.
결정론·무네트워크 (ScenarioBuilder 합성 데이터).

설계 노트: next-bar 모드의 체결은 루프에서 청산 체크보다 먼저 처리 — 진입 봉부터
bars_held=1 로 모니터링되어 same-bar 모드와 청산 체크 스케줄이 동일. 두 모드의
차이는 체결 가격·시점(시그널 봉 close vs 다음 봉 open)만으로 격리된다.
"""
import pandas as pd

from backtest_engine.engine import BacktestConfig, BacktestEngine
from backtest_engine.scenarios import ScenarioBuilder
from backtest_engine.strategy import StrategyD, StrategyDConfig


def _run(df: pd.DataFrame, next_bar_entry: bool):
    strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
    config = BacktestConfig(next_bar_entry=next_bar_entry)
    return BacktestEngine(strategy, config).run_single(df, ticker="TEST")


def test_same_bar_vs_next_bar_entry_gap():
    """T-1: same-bar 는 시그널 봉 close, next-bar 는 다음 봉 open 에 체결."""
    df = ScenarioBuilder.perfect_double_bottom(seed=42).df

    same = _run(df, next_bar_entry=False)
    nxt = _run(df, next_bar_entry=True)

    assert same.total_trades == 1
    assert nxt.total_trades == 1

    t_same = same.trades[0]
    t_next = nxt.trades[0]

    # same-bar: 시그널 봉 close 체결
    assert t_same.entry_price == float(df.loc[t_same.entry_time, "close"])

    # next-bar: 시그널 직후 봉 open 체결
    same_idx = df.index.get_loc(t_same.entry_time)
    assert t_next.entry_time == df.index[same_idx + 1]
    assert t_next.entry_price == float(df.loc[t_next.entry_time, "open"])


def test_next_bar_signal_on_last_bar_is_not_filled():
    """마지막 봉 시그널은 next-bar 모드에서 체결 봉이 없어 미체결 (look-ahead 차단)."""
    df = ScenarioBuilder.perfect_double_bottom(seed=42).df.iloc[:33]  # 진입봉이 마지막

    same = _run(df, next_bar_entry=False)
    nxt = _run(df, next_bar_entry=True)

    assert same.total_trades == 1  # same-bar 는 시그널 봉에서 체결 (강제청산 포함)
    assert nxt.total_trades == 0


def test_next_bar_default_off_preserves_existing_behavior():
    """기본값 next_bar_entry=False — 기존 same-bar 동작과 동일 (하위 호환)."""
    df = ScenarioBuilder.perfect_double_bottom(seed=42).df

    strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
    default_result = BacktestEngine(strategy).run_single(df, ticker="TEST")
    explicit_same = _run(df, next_bar_entry=False)

    assert default_result.total_trades == explicit_same.total_trades == 1
    assert default_result.trades[0].entry_price == explicit_same.trades[0].entry_price
