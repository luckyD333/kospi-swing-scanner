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
    assert response.json()["status"] == "not_ready"


async def test_strategy_performance_returns_saved_payload(tmp_path, monkeypatch):
    path = tmp_path / "strategy_performance.json"
    path.write_text(
        json.dumps({
            "schema_version": "1.0",
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
