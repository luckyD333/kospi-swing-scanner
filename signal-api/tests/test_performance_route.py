from __future__ import annotations

import json

from httpx import ASGITransport, AsyncClient

from app.main import app
import app.api.performance as performance_module


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_strategy_performance_returns_not_ready_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        performance_module,
        "_PERFORMANCE_PATH",
        tmp_path / "missing.json",
    )

    async with _client() as client:
        response = await client.get("/api/strategy-performance")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "1.1"
    assert body["status"] == "not_ready"
    assert body["archive_summary"] == {
        "discovered_files": 0,
        "loaded_files": 0,
        "failed_files_count": 0,
        "failed_files": [],
    }


async def test_strategy_performance_returns_saved_payload(tmp_path, monkeypatch):
    path = tmp_path / "strategy_performance.json"
    path.write_text(
        json.dumps({
            "schema_version": "1.1",
            "status": "ready",
            "daily": [],
            "totals": {},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(performance_module, "_PERFORMANCE_PATH", path)

    async with _client() as client:
        response = await client.get("/api/strategy-performance")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.headers["cache-control"] == "no-cache"


async def test_strategy_performance_returns_partial_payload_with_http_200(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "strategy_performance.json"
    path.write_text(
        json.dumps({
            "schema_version": "1.1",
            "status": "partial",
            "daily": [],
            "totals": {},
            "archive_summary": {
                "discovered_files": 2,
                "loaded_files": 1,
                "failed_files_count": 1,
                "failed_files": ["signals_2026-07-02.json"],
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(performance_module, "_PERFORMANCE_PATH", path)

    async with _client() as client:
        response = await client.get("/api/strategy-performance")

    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["archive_summary"]["failed_files_count"] == 1


async def test_strategy_performance_returns_503_for_malformed_final_file(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "strategy_performance.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(performance_module, "_PERFORMANCE_PATH", path)

    async with _client() as client:
        response = await client.get("/api/strategy-performance")

    assert response.status_code == 503
    assert response.json() == {"error": "strategy_performance_malformed"}
