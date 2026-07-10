from __future__ import annotations

import pandas as pd

from core.strategy_performance import (
    STRATEGY_DEFINITIONS,
    build_performance_payload,
    canonical_strategy_key,
)


def _frame(values: list[float], dates: list[str]) -> pd.DataFrame:
    close = pd.Series(values, index=pd.to_datetime(dates), dtype=float)
    return pd.DataFrame({"close": close})


def _signal(strategy_id: str, ticker: str, signal_date: str, rank: int = 1) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "signal_date": f"{signal_date}T00:00:00",
        "strategy": {
            "id": strategy_id,
            "timeframe": "1D",
        },
        "ranking": {"rank": rank},
        "trade_plan": {"entry": 100},
    }


def _snapshot(target_date: str, signals: list[dict], generated_at: str) -> dict:
    return {
        "target_date": target_date,
        "generated_at": generated_at,
        "signals": signals,
    }


def test_canonical_strategy_key_keeps_only_selected_1d_variants():
    assert canonical_strategy_key("strategy_one_d_v2_r1", "1D") == "strategy_one_original"
    assert canonical_strategy_key("strategy_one_d_v2_r2", "1D") == "strategy_one_improved"
    assert canonical_strategy_key("strategy_one_d_v2", "1D") is None
    assert canonical_strategy_key("strategy_one_d_v2_r1", "1h") is None
    assert canonical_strategy_key("strategy_two_cross_sectional_momentum", "1D") == "strategy_two"


def test_build_payload_calculates_next_close_returns_and_strategy_totals():
    dates = ["2026-06-30", "2026-07-01", "2026-07-02"]
    frames = {
        "R1": _frame([100, 101, 100], dates),
        "R2": _frame([100, 99, 100], dates),
    }
    snapshots = [
        _snapshot(
            "2026-06-30",
            [
                _signal("strategy_one_d_v2_r1", "R1", "2026-06-30"),
                _signal("strategy_one_d_v2_r2", "R2", "2026-06-30"),
            ],
            "2026-06-30T16:40:00+09:00",
        ),
    ]

    payload = build_performance_payload(snapshots, frames, retention_months=6)

    assert payload["status"] == "ready"
    assert payload["evaluation"]["cost_pct"] == 0.30
    assert set(payload["totals"]) == set(STRATEGY_DEFINITIONS)

    daily = payload["daily"]
    assert len(daily) == 1
    assert daily[0]["evaluation_date"] == "2026-07-01"

    original = daily[0]["by_strategy"]["strategy_one_original"]
    improved = daily[0]["by_strategy"]["strategy_one_improved"]
    assert original["win_count"] == 1
    assert original["win_rate_pct"] == 100.0
    assert original["signals"][0]["net_return_pct"] == 0.7
    assert improved["loss_count"] == 1
    assert improved["win_rate_pct"] == 0.0
    assert improved["signals"][0]["outcome"] == "LOSS"


def test_old_rows_are_trimmed_relative_to_latest_evaluation_date():
    dates = ["2025-12-01", "2025-12-02", "2026-07-01", "2026-07-02"]
    frames = {
        "OLD": _frame([100, 101, 100, 100], dates),
        "NEW": _frame([100, 100, 100, 101], dates),
    }
    snapshots = [
        _snapshot(
            "2025-12-01",
            [_signal("strategy_two_cross_sectional_momentum", "OLD", "2025-12-01")],
            "2025-12-01T16:40:00+09:00",
        ),
        _snapshot(
            "2026-07-01",
            [_signal("strategy_two_cross_sectional_momentum", "NEW", "2026-07-01")],
            "2026-07-01T16:40:00+09:00",
        ),
    ]

    payload = build_performance_payload(snapshots, frames, retention_months=6)

    assert [row["evaluation_date"] for row in payload["daily"]] == ["2026-07-02"]
    assert payload["window"]["from"] == "2026-01-02"


def test_duplicate_signal_uses_latest_snapshot_without_double_counting():
    dates = ["2026-07-01", "2026-07-02"]
    frames = {"R1": _frame([100, 102], dates)}
    signal = _signal("strategy_one_d_v2_r1", "R1", "2026-07-01", rank=3)
    newer = _signal("strategy_one_d_v2_r1", "R1", "2026-07-01", rank=1)
    snapshots = [
        _snapshot("2026-07-01", [signal], "2026-07-01T16:40:00+09:00"),
        _snapshot("2026-07-01", [newer], "2026-07-01T17:00:00+09:00"),
    ]

    payload = build_performance_payload(snapshots, frames)

    stats = payload["daily"][0]["by_strategy"]["strategy_one_original"]
    assert stats["signal_count"] == 1
    assert stats["signals"][0]["rank"] == 1
