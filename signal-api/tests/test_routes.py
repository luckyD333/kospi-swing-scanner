import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
import app.api.signals as signals_module
import app.api.market as market_module
from app.services.signal_loader import SignalLoader
from app.services.market_loader import MarketLoader


def _make_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def with_signals(signals_file, monkeypatch):
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_file))


@pytest.fixture
def with_no_signals(tmp_path, monkeypatch):
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(tmp_path / "missing.json"))


@pytest.fixture
def with_market(market_file, monkeypatch):
    monkeypatch.setattr(market_module, "_loader", MarketLoader(market_file))


@pytest.fixture
def with_no_market(tmp_path, monkeypatch):
    monkeypatch.setattr(market_module, "_loader", MarketLoader(tmp_path / "missing.json"))


# ── health ────────────────────────────────────────────────────────────────────

async def test_health_returns_200(with_signals):
    async with _make_client() as c:
        r = await c.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── /api/signals ──────────────────────────────────────────────────────────────

async def test_signals_returns_200_when_file_exists(with_signals):
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    assert r.json()["schema_version"] == "1.0"
    assert "ETag" in r.headers


async def test_signals_returns_503_when_file_missing(with_no_signals):
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "signals_not_generated"
    assert r.headers.get("retry-after") == "3600"


async def test_signals_returns_503_on_malformed_json(tmp_path, monkeypatch):
    bad = tmp_path / "signals.json"
    bad.write_text("{ not valid json }", encoding="utf-8")
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(bad))
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "signals_malformed"


async def test_signals_304_on_matching_etag(with_signals):
    async with _make_client() as c:
        r1 = await c.get("/api/signals")
        etag = r1.headers["ETag"]
        r2 = await c.get("/api/signals", headers={"If-None-Match": etag})
    assert r2.status_code == 304


# ── /api/signals/{ticker} ─────────────────────────────────────────────────────

async def test_signals_ticker_returns_signal(with_signals):
    async with _make_client() as c:
        r = await c.get("/api/signals/006340")
    assert r.status_code == 200
    assert r.json()["ticker"] == "006340"
    assert "ETag" in r.headers


async def test_signals_ticker_returns_404_for_unknown(with_signals):
    async with _make_client() as c:
        r = await c.get("/api/signals/UNKNOWN")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "ticker_not_found"


# ── /api/market ───────────────────────────────────────────────────────────────

async def test_market_returns_empty_when_file_missing(with_no_market):
    async with _make_client() as c:
        r = await c.get("/api/market")
    assert r.status_code == 200
    assert r.json() == {"market_indices": {}}


async def test_market_returns_indices_only(with_market):
    async with _make_client() as c:
        r = await c.get("/api/market")
    assert r.status_code == 200
    data = r.json()
    assert "market_indices" in data
    assert "tickers" not in data
    assert "kospi" in data["market_indices"]


async def test_market_etag_round_trip(with_market):
    async with _make_client() as c:
        r1 = await c.get("/api/market")
        etag = r1.headers["ETag"]
        r2 = await c.get("/api/market", headers={"If-None-Match": etag})
    assert r2.status_code == 304
