"""
Task 5: cli.py --cache-root 인자 검증.

검증:
  - --cache-root 지정 시 RunnerConfig.cache_root 설정
  - stale 캐시(25시간 경과) 시 WARNING 로그 출력
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.runner import RunResult


def _setup_manifest(tmp_path: Path, hours_ago: float = 1.0) -> None:
    manifest = {
        "collected_at": (datetime.now() - timedelta(hours=hours_ago)).isoformat(),
        "market": "KOSPI",
        "target_date": "20260430",
        "tickers": ["005930"],
        "base_tfs": ["1D"],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))


def _fake_runner_class(captured: dict):
    class _FakeRunner:
        def __init__(self, client, config):
            captured["cache_root"] = config.cache_root

        def run(self, strategies, target_date=None):
            return RunResult(
                target_date="20260430",
                universe_size=0,
                candidates_by_strategy={},
                candidates_by_strategy_tf={},
            )

    return _FakeRunner


def test_cache_root_arg_sets_runner_config(tmp_path):
    _setup_manifest(tmp_path)
    captured = {}

    with patch("cli.ScanRunner", _fake_runner_class(captured)), \
         patch("cli.DataClient", MagicMock()), \
         patch("cli.formatters.format_run_summary", return_value=""), \
         patch("cli.formatters.format_run_summary_json", return_value={}):
        from cli import main
        main(["--cache-root", str(tmp_path), "--date", "20260430"])

    assert captured["cache_root"] == tmp_path


def test_cache_root_freshness_warning_when_stale(tmp_path, caplog):
    _setup_manifest(tmp_path, hours_ago=25.0)
    captured = {}

    with patch("cli.ScanRunner", _fake_runner_class(captured)), \
         patch("cli.DataClient", MagicMock()), \
         patch("cli.formatters.format_run_summary", return_value=""), \
         patch("cli.formatters.format_run_summary_json", return_value={}), \
         caplog.at_level(logging.WARNING):
        from cli import main
        main(["--cache-root", str(tmp_path), "--date", "20260430"])

    assert any("stale" in r.message.lower() for r in caplog.records)


def test_no_cache_root_does_not_warn(tmp_path, caplog):
    captured = {}

    with patch("cli.ScanRunner", _fake_runner_class(captured)), \
         patch("cli.DataClient", MagicMock()), \
         patch("cli.formatters.format_run_summary", return_value=""), \
         patch("cli.formatters.format_run_summary_json", return_value={}), \
         caplog.at_level(logging.WARNING):
        from cli import main
        main(["--date", "20260430"])

    assert captured["cache_root"] is None
    assert not any("stale" in r.message.lower() for r in caplog.records)
