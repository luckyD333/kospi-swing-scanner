"""backtest_engine/tests/test_walk_forward.py — Walk-Forward framework 단위 테스트.

테스트 전략:
  - 합성 scorer 로 framework 동작 격리 (실제 백테스트 엔진 의존 X)
  - 윈도우 생성, 파라미터 안정성, OOS decay, verdict 등 핵심 산출물 검증
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtest_engine.walk_forward import (
    WalkForwardConfig,
    WFReport,
    WFWindow,
    _generate_windows,
    _iter_param_combinations,
    compute_sharpe,
    run_walk_forward,
)


# -----------------------------------------------------------------------------
# 헬퍼: 윈도우 생성 검증
# -----------------------------------------------------------------------------


def test_generate_windows_basic_sequence():
    cfg = WalkForwardConfig(
        train_days=90,
        test_days=30,
        step_days=30,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    windows = list(_generate_windows(cfg))
    assert len(windows) >= 7
    assert windows[0][0] == pd.Timestamp("2024-01-01")
    train_start, train_end, test_start, test_end = windows[0]
    assert (train_end - train_start).days == 89
    assert (test_start - train_end).days == 1
    assert (test_end - test_start).days == 29


def test_generate_windows_stop_when_test_exceeds_end():
    cfg = WalkForwardConfig(
        train_days=10,
        test_days=10,
        step_days=10,
        start_date="2024-01-01",
        end_date="2024-01-30",
    )
    windows = list(_generate_windows(cfg))
    assert len(windows) == 2
    assert windows[-1][3] <= pd.Timestamp("2024-01-30")


def test_generate_windows_step_smaller_than_train():
    cfg = WalkForwardConfig(
        train_days=30,
        test_days=10,
        step_days=10,
        start_date="2024-01-01",
        end_date="2024-04-30",
    )
    windows = list(_generate_windows(cfg))
    assert windows[1][0] - windows[0][0] == pd.Timedelta(days=10)


# -----------------------------------------------------------------------------
# 헬퍼: 파라미터 조합
# -----------------------------------------------------------------------------


def test_iter_param_combinations_cartesian():
    grid = {"a": [1, 2], "b": [10, 20, 30]}
    combos = list(_iter_param_combinations(grid))
    assert len(combos) == 6
    assert len({tuple(sorted(c.items())) for c in combos}) == 6


def test_iter_param_combinations_empty_grid():
    combos = list(_iter_param_combinations({}))
    assert combos == [{}]


# -----------------------------------------------------------------------------
# 헬퍼: Sharpe
# -----------------------------------------------------------------------------


def test_compute_sharpe_positive_drift():
    rng = np.random.default_rng(42)
    daily = 0.001 + rng.normal(0, 0.01, size=252)
    equity = (1 + pd.Series(daily)).cumprod() * 1000
    sharpe = compute_sharpe(equity)
    assert sharpe > 0
    assert not math.isnan(sharpe)


def test_compute_sharpe_zero_variance_returns_nan():
    equity = pd.Series([1000.0, 1000.0, 1000.0])
    assert math.isnan(compute_sharpe(equity))


def test_compute_sharpe_too_short_returns_nan():
    assert math.isnan(compute_sharpe(pd.Series([1000.0])))


# -----------------------------------------------------------------------------
# WFReport: 안정성·decay 계산
# -----------------------------------------------------------------------------


def _mk_window(
    best_params: dict,
    train_metric: float,
    test_metric: float,
    *,
    train_trades: int = 20,
    test_trades: int = 7,
) -> WFWindow:
    return WFWindow(
        train_start=pd.Timestamp("2024-01-01"),
        train_end=pd.Timestamp("2024-03-30"),
        test_start=pd.Timestamp("2024-03-31"),
        test_end=pd.Timestamp("2024-04-29"),
        best_params=best_params,
        train_metric=train_metric,
        test_metric=test_metric,
        train_trades=train_trades,
        test_trades=test_trades,
    )


def test_stability_score_constant_params_is_zero():
    report = WFReport(
        strategy_name="test",
        param_grid={"lookback": [20, 30, 40]},
        windows=[
            _mk_window({"lookback": 30}, 1.0, 0.9),
            _mk_window({"lookback": 30}, 1.1, 1.0),
            _mk_window({"lookback": 30}, 0.9, 0.8),
        ],
    )
    cv = report.param_stability_score["lookback"]
    assert cv == 0.0
    assert report.passed_stability


def test_stability_score_varying_params_is_high():
    report = WFReport(
        strategy_name="test",
        param_grid={"lookback": [10, 20, 30, 40, 50]},
        windows=[
            _mk_window({"lookback": 10}, 1.0, 0.9),
            _mk_window({"lookback": 30}, 1.0, 0.9),
            _mk_window({"lookback": 50}, 1.0, 0.9),
        ],
    )
    cv = report.param_stability_score["lookback"]
    assert cv > 0.30
    assert not report.passed_stability


def test_stability_score_handles_boolean_param():
    stable_report = WFReport(
        strategy_name="test",
        param_grid={"strict": [True, False]},
        windows=[
            _mk_window({"strict": True}, 1.0, 0.9),
            _mk_window({"strict": True}, 1.0, 0.9),
            _mk_window({"strict": True}, 1.0, 0.9),
        ],
    )
    assert stable_report.param_stability_score["strict"] == 0.0

    flipping = WFReport(
        strategy_name="test",
        param_grid={"strict": [True, False]},
        windows=[
            _mk_window({"strict": True}, 1.0, 0.9),
            _mk_window({"strict": False}, 1.0, 0.9),
            _mk_window({"strict": True}, 1.0, 0.9),
        ],
    )
    assert flipping.param_stability_score["strict"] > 0.0


def test_oos_decay_zero_when_train_equals_test():
    report = WFReport(
        strategy_name="test",
        param_grid={"x": [1]},
        windows=[
            _mk_window({"x": 1}, 1.0, 1.0),
            _mk_window({"x": 1}, 1.0, 1.0),
        ],
    )
    assert report.oos_metric_decay == 0.0
    assert report.passed_decay


def test_oos_decay_positive_when_test_lower():
    report = WFReport(
        strategy_name="test",
        param_grid={"x": [1]},
        windows=[
            _mk_window({"x": 1}, 1.0, 0.4),
            _mk_window({"x": 1}, 1.0, 0.4),
        ],
    )
    assert report.oos_metric_decay == pytest.approx(0.6)
    assert not report.passed_decay


def test_oos_decay_nan_when_no_windows():
    report = WFReport(strategy_name="test", param_grid={}, windows=[])
    assert math.isnan(report.oos_metric_decay)
    assert not report.passed_decay


def test_verdict_combinations():
    r_pass = WFReport(
        strategy_name="t",
        param_grid={"x": [1]},
        windows=[_mk_window({"x": 1}, 1.0, 0.9)] * 3,
    )
    assert r_pass.verdict == "PASS"

    r_unstable = WFReport(
        strategy_name="t",
        param_grid={"x": [1, 2, 3]},
        windows=[
            _mk_window({"x": 1}, 1.0, 0.9),
            _mk_window({"x": 3}, 1.0, 0.9),
        ],
    )
    assert "unstable" in r_unstable.verdict

    r_decayed = WFReport(
        strategy_name="t",
        param_grid={"x": [1]},
        windows=[_mk_window({"x": 1}, 1.0, 0.2)] * 3,
    )
    assert "OOS decay" in r_decayed.verdict


# -----------------------------------------------------------------------------
# End-to-end: run_walk_forward
# -----------------------------------------------------------------------------


def _make_constant_scorer(metric: float, n_trades: int):
    def _score_fn(ohlcv, params, start, end):
        return metric, n_trades
    return _score_fn


def test_run_walk_forward_picks_first_param_when_metric_constant():
    cfg = WalkForwardConfig(
        train_days=30,
        test_days=10,
        step_days=10,
        start_date="2024-01-01",
        end_date="2024-04-30",
    )
    report = run_walk_forward(
        strategy_name="test",
        evaluator=_make_constant_scorer(metric=1.0, n_trades=20),
        param_grid={"lookback": [10, 20, 30]},
        ohlcv_data={},
        config=cfg,
    )
    assert len(report.windows) >= 3
    first_param = report.windows[0].best_params
    assert all(w.best_params == first_param for w in report.windows)
    assert report.param_stability_score["lookback"] == 0.0
    assert report.verdict == "PASS"


def test_run_walk_forward_skips_window_when_below_min_trades():
    cfg = WalkForwardConfig(
        train_days=30,
        test_days=10,
        step_days=10,
        start_date="2024-01-01",
        end_date="2024-04-30",
        min_trades_for_metric=10,
    )
    report = run_walk_forward(
        strategy_name="test",
        evaluator=_make_constant_scorer(metric=1.0, n_trades=2),
        param_grid={"x": [1]},
        ohlcv_data={},
        config=cfg,
    )
    assert report.windows == []


def test_run_walk_forward_evaluator_exception_is_skipped():
    def _flaky(ohlcv, params, start, end):
        if params["x"] == 1:
            raise RuntimeError("boom")
        return 0.5, 20
    cfg = WalkForwardConfig(
        train_days=30,
        test_days=10,
        step_days=10,
        start_date="2024-01-01",
        end_date="2024-02-29",
    )
    report = run_walk_forward(
        strategy_name="test",
        evaluator=_flaky,
        param_grid={"x": [1, 2]},
        ohlcv_data={},
        config=cfg,
    )
    assert all(w.best_params["x"] == 2 for w in report.windows)


def test_run_walk_forward_regime_changing_scorer_shows_param_drift():
    midpoint = pd.Timestamp("2024-03-01")

    def _regime_scorer(ohlcv, params, start, end):
        center = start + (end - start) / 2
        if center < midpoint:
            return (1.0 if params["lookback"] == 10 else 0.3), 20
        return (1.0 if params["lookback"] == 30 else 0.3), 20

    cfg = WalkForwardConfig(
        train_days=20,
        test_days=10,
        step_days=15,
        start_date="2024-01-01",
        end_date="2024-06-30",
    )
    report = run_walk_forward(
        strategy_name="regime_test",
        evaluator=_regime_scorer,
        param_grid={"lookback": [10, 20, 30]},
        ohlcv_data={},
        config=cfg,
    )
    lookbacks = [w.best_params["lookback"] for w in report.windows]
    assert min(lookbacks) == 10
    assert max(lookbacks) == 30
    assert report.param_stability_score["lookback"] > 0.30
    assert not report.passed_stability


def test_run_walk_forward_summary_serializable():
    import json
    cfg = WalkForwardConfig(
        train_days=30, test_days=10, step_days=10,
        start_date="2024-01-01", end_date="2024-02-29",
    )
    report = run_walk_forward(
        strategy_name="test",
        evaluator=_make_constant_scorer(metric=1.0, n_trades=20),
        param_grid={"x": [1]},
        ohlcv_data={},
        config=cfg,
    )
    serialized = json.dumps(report.summary())
    assert "strategy_name" in serialized
    assert "param_stability_score" in serialized
