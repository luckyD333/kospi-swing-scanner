import json
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


def test_loader_returns_cached_within_ttl(tmp_path):
    """TTL 내에는 동일 instance 반환 (디스크 변경 무시)."""
    p = tmp_path / "s.json"
    _write(p, SAMPLE)
    loader = SignalLoader(p)
    first = loader.load()
    # 디스크는 바꿔도, TTL 내라 같은 캐시 반환
    bigger = {**SAMPLE, "extra": "x" * 1000}
    p.write_text(json.dumps(bigger), encoding="utf-8")
    second = loader.load()
    assert second is first


def test_loader_reloads_after_ttl_expires(tmp_path, monkeypatch):
    """TTL 경과 시 디스크 재로드 → 새 instance."""
    import app.services.signal_loader as sl
    p = tmp_path / "s.json"
    _write(p, SAMPLE)
    loader = SignalLoader(p)
    first = loader.load()
    # TTL 짧게 강제
    monkeypatch.setattr(sl, "_TTL_SECONDS", 0.0)
    bigger = {**SAMPLE, "extra": "x" * 1000}
    p.write_text(json.dumps(bigger), encoding="utf-8")
    second = loader.load()
    assert second is not first
    assert "extra" in second.raw
