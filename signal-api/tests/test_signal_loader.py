import json
import os
from pathlib import Path

from app.services.signal_loader import SignalLoader


SAMPLE = {
    "schema_version": "1.0",
    "generated_at": "2026-05-03T18:16:11+09:00",
    "signals": [
        {
            "ticker": "000020",
            "name": None,
            "name_en": None,
            "strategy": {"id": "s", "label": "S"},
            "trade_plan": {"entry": 1, "stop": 1},
        }
    ],
}


def _write(p: Path, payload: dict):
    p.write_text(json.dumps(payload), encoding="utf-8")


def test_loader_caches_by_ticker(tmp_path):
    p = tmp_path / "s.json"
    _write(p, SAMPLE)
    loader = SignalLoader(p)
    loaded = loader.load()
    assert loaded.by_ticker["000020"]["ticker"] == "000020"


def test_loader_invalidates_on_size_change_same_mtime(tmp_path):
    p = tmp_path / "s.json"
    _write(p, SAMPLE)
    loader = SignalLoader(p)
    first = loader.load()

    # 같은 mtime을 강제로 유지하면서 내용을 바꾼다 → size로 변경 감지되어야 함
    bigger = {**SAMPLE, "extra": "x" * 1000}
    p.write_text(json.dumps(bigger), encoding="utf-8")
    os.utime(p, (first.mtime, first.mtime))

    second = loader.load()
    assert second is not first
    assert second.size != first.size


def test_loader_etag_includes_mtime_and_size(tmp_path):
    p = tmp_path / "s.json"
    _write(p, SAMPLE)
    loader = SignalLoader(p)
    loaded = loader.load()
    assert str(loaded.mtime) in loaded.etag
    assert str(loaded.size) in loaded.etag
