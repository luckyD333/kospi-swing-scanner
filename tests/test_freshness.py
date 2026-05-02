"""Task 3: freshness.py 신선도 검증."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from core.cache.freshness import check_freshness


def _write_manifest(tmp_path: Path, collected_at: datetime) -> None:
    m = tmp_path / "manifest.json"
    m.write_text(
        json.dumps({
            "collected_at": collected_at.isoformat(),
            "market": "KOSPI",
            "tickers": [],
            "base_tfs": ["1D"],
            "target_date": "20260430",
        })
    )


def test_fresh_manifest(tmp_path):
    _write_manifest(tmp_path, datetime.now() - timedelta(hours=1))
    result = check_freshness(tmp_path, stale_hours=8)
    assert result.ok is True
    assert result.stale_hours < 2


def test_stale_manifest(tmp_path):
    _write_manifest(tmp_path, datetime.now() - timedelta(hours=25))
    result = check_freshness(tmp_path, stale_hours=8)
    assert result.ok is False
    assert "stale" in result.message.lower()


def test_missing_manifest(tmp_path):
    result = check_freshness(tmp_path, stale_hours=8)
    assert result.ok is False
    assert "manifest" in result.message.lower()


def test_stale_hours_boundary(tmp_path):
    _write_manifest(tmp_path, datetime.now() - timedelta(hours=7, minutes=59))
    assert check_freshness(tmp_path, stale_hours=8).ok is True

    _write_manifest(tmp_path, datetime.now() - timedelta(hours=8, minutes=1))
    assert check_freshness(tmp_path, stale_hours=8).ok is False
