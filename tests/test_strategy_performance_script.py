from __future__ import annotations

import json

import pandas as pd

from core.cache.ohlcv_disk import OhlcvDiskCache
from scripts.aggregate_strategy_performance import update_performance_file


def _signal(ticker: str, date: str) -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "signal_date": f"{date}T00:00:00",
        "strategy": {
            "id": "strategy_one_d_v2_r1",
            "timeframe": "1D",
        },
        "ranking": {"rank": 1},
        "trade_plan": {"entry": 100},
    }


def test_update_performance_file_is_idempotent(tmp_path):
    data_dir = tmp_path / "data"
    archive_dir = data_dir / "archive"
    archive_dir.mkdir(parents=True)
    cache_root = tmp_path / "cache"

    (archive_dir / "signals_2026-07-01.json").write_text(
        json.dumps({
            "target_date": "2026-07-01",
            "generated_at": "2026-07-01T16:40:00+09:00",
            "signals": [_signal("AAA", "2026-07-01")],
        }),
        encoding="utf-8",
    )
    OhlcvDiskCache(cache_root).write(
        "AAA",
        "1D",
        pd.DataFrame(
            {"close": [100.0, 102.0]},
            index=pd.to_datetime(["2026-07-01", "2026-07-02"]),
        ),
    )

    output = data_dir / "strategy_performance.json"
    first = update_performance_file(data_dir, cache_root, output)
    second = update_performance_file(data_dir, cache_root, output)

    assert first["daily"] == second["daily"]
    assert first["totals"] == second["totals"]
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "ready"


def test_update_without_archive_returns_not_ready(tmp_path):
    output = tmp_path / "data" / "strategy_performance.json"

    payload = update_performance_file(
        tmp_path / "data",
        tmp_path / "cache",
        output,
    )

    assert payload["status"] == "not_ready"
    assert output.exists()
