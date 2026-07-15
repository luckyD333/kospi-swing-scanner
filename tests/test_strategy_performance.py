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

    assert payload["schema_version"] == "1.1"
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
    assert original["avg_net_return_pct"] == 0.7
    assert "signals" not in original
    assert improved["loss_count"] == 1
    assert improved["win_rate_pct"] == 0.0


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
    assert payload["window"]["from"] == "2026-07-02"


def test_duplicate_signal_uses_first_snapshot_without_double_counting():
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
    assert stats["avg_net_return_pct"] == 1.7


def test_repeated_signal_is_evaluated_from_first_exposure_date():
    dates = ["2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03"]
    frames = {"R1": _frame([100, 200, 110, 121], dates)}
    first = _signal("strategy_one_d_v2_r1", "R1", "2026-06-30", rank=3)
    repeated = _signal("strategy_one_d_v2_r1", "R1", "2026-06-30", rank=1)
    snapshots = [
        _snapshot("2026-07-02", [first], "2026-07-02T16:40:00+09:00"),
        _snapshot("2026-07-03", [repeated], "2026-07-03T16:40:00+09:00"),
    ]

    payload = build_performance_payload(snapshots, frames)

    assert [row["evaluation_date"] for row in payload["daily"]] == ["2026-07-03"]
    stats = payload["daily"][0]["by_strategy"]["strategy_one_original"]
    assert stats["signal_count"] == 1
    assert stats["avg_net_return_pct"] == 9.7


def test_legacy_weekend_snapshot_uses_previous_and_next_trading_bars():
    frames = {
        "R1": _frame(
            [100, 103],
            ["2026-04-30", "2026-05-04"],
        )
    }
    signal = _signal("strategy_one_d_v2_r1", "R1", "2026-04-30")
    signal["signal_date"] = None
    snapshots = [
        _snapshot(None, [signal], "2026-05-03T16:40:00+09:00"),
    ]

    payload = build_performance_payload(snapshots, frames)

    assert payload["daily"][0]["evaluation_date"] == "2026-05-04"
    assert payload["totals"]["strategy_one_original"]["avg_net_return_pct"] == 2.7


def test_snapshot_date_falls_back_to_strict_archive_filename():
    frames = {"R1": _frame([100, 101], ["2026-07-03", "2026-07-06"])}
    snapshot = _snapshot(
        None,
        [_signal("strategy_one_d_v2_r1", "R1", "2026-07-01")],
        None,
    )
    snapshot["source_file"] = "signals_2026-07-05.json"

    payload = build_performance_payload([snapshot], frames)

    assert payload["daily"][0]["evaluation_date"] == "2026-07-06"
    assert payload["totals"]["strategy_one_original"]["avg_net_return_pct"] == 0.7


def test_nonfinite_or_nonpositive_closes_are_not_evaluated():
    dates = ["2026-07-01", "2026-07-02"]
    snapshots = [
        _snapshot(
            "2026-07-01",
            [
                _signal("strategy_one_d_v2_r1", "NAN", "2026-07-01"),
                _signal("strategy_one_d_v2_r1", "ZERO", "2026-07-01"),
            ],
            "2026-07-01T16:40:00+09:00",
        )
    ]
    frames = {
        "NAN": _frame([100, float("nan")], dates),
        "ZERO": _frame([100, 0], dates),
    }

    payload = build_performance_payload(snapshots, frames)

    assert payload["status"] == "not_ready"
    assert payload["daily"] == []
