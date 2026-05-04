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
    # /api/market 과 /api/signals 의 join 둘 다 같은 market_file 을 보도록 patch
    monkeypatch.setattr(market_module, "_loader", MarketLoader(market_file))
    monkeypatch.setattr(signals_module, "_market_loader", MarketLoader(market_file))


@pytest.fixture
def with_no_market(tmp_path, monkeypatch):
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(market_module, "_loader", MarketLoader(missing))
    monkeypatch.setattr(signals_module, "_market_loader", MarketLoader(missing))


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
    assert "python cli.py" in r.json()["detail"]["hint"]
    assert "--format signals_ui" in r.json()["detail"]["hint"]
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


# ── Phase E: signals + market join ────────────────────────────────────────────

async def test_signals_overlays_latest_fundamentals(with_signals, with_market):
    """signals.json 의 fundamentals 가 null 이어도 market_snapshot.tickers 의
    latest fundamentals 로 응답 시 override (옵션 B)."""
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    sig = next(s for s in r.json()["signals"] if s["ticker"] == "006340")
    # SAMPLE_SIGNALS 는 fundamentals=null 이지만 SAMPLE_MARKET 의 tickers["006340"]
    # 가 per=151.77 등 latest 보유. 응답 시 override 되어야 함.
    assert sig["fundamentals"]["per"] == 151.77
    assert sig["fundamentals"]["high_52w"] == 18560
    assert sig["flow"]["foreign_ratio_pct"] == 5.51


async def test_signals_no_market_passthrough(with_signals, with_no_market):
    """market_snapshot.json 없으면 signals.json 그대로 응답 (graceful fallback)."""
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    sig = next(s for s in r.json()["signals"] if s["ticker"] == "006340")
    assert sig["fundamentals"]["per"] is None  # signals.json 원본 그대로


async def test_signals_ticker_uses_snapshot_rsi_by_tf_first(
    signals_multi_tf_file, monkeypatch, with_market,
):
    """snapshot.tickers[ticker].rsi_by_tf 가 있으면 그게 우선 (ticker 의 indicator).

    SAMPLE_MARKET 에 rsi_by_tf={1D:60.0, 1h:50.0, 30m:45.0}, signals entries 는
    rsi_14={1D:65.5, 1h:72.3, 30m:58.1}. 응답은 snapshot 값 우선.
    """
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_multi_tf_file))
    async with _make_client() as c:
        r = await c.get("/api/signals/006340")
    assert r.status_code == 200
    body = r.json()
    tp = body["trade_plan"]
    assert tp["rsi_1d"] == 60.0
    assert tp["rsi_1h"] == 50.0
    assert tp["rsi_30m"] == 45.0
    # base entry = highest score (1h, score 90.0)
    assert body["strategy"]["timeframe"] == "1h"


async def test_signals_ticker_falls_back_to_entries_rsi(
    signals_multi_tf_file, monkeypatch, with_no_market,
):
    """snapshot 자체가 없으면 entries 의 rsi_14 로 분배 (fallback)."""
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_multi_tf_file))
    async with _make_client() as c:
        r = await c.get("/api/signals/006340")
    assert r.status_code == 200
    tp = r.json()["trade_plan"]
    assert tp["rsi_1d"] == 65.5
    assert tp["rsi_1h"] == 72.3
    assert tp["rsi_30m"] == 58.1


async def test_signals_ticker_snapshot_rsi_when_only_one_strategy_candidate(
    with_signals, with_market,
):
    """ticker 가 1D strategy 만 후보여도 snapshot.rsi_by_tf 로 1h/30m 표시."""
    async with _make_client() as c:
        r = await c.get("/api/signals/006340")
    assert r.status_code == 200
    tp = r.json()["trade_plan"]
    # SAMPLE_SIGNALS 의 006340 는 1D strategy 1개만 후보. 그래도 snapshot 의
    # rsi_by_tf 가 1h/30m 채워줘야 함.
    assert tp["rsi_1d"] == 60.0
    assert tp["rsi_1h"] == 50.0
    assert tp["rsi_30m"] == 45.0


async def test_signals_ticker_overlays_fundamentals(
    signals_multi_tf_file, monkeypatch, with_market,
):
    """단일 ticker 응답도 market 의 latest fundamentals 로 override."""
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_multi_tf_file))
    async with _make_client() as c:
        r = await c.get("/api/signals/006340")
    assert r.status_code == 200
    body = r.json()
    assert body["fundamentals"]["per"] == 151.77
    assert body["flow"]["foreign_ratio_pct"] == 5.51


async def test_signals_strategy_all_filters_to_merged_entries(
    signals_with_all_file, monkeypatch, with_no_market,
):
    """GET /signals?strategy=all → strategy.id=='all' entry 만 반환."""
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_with_all_file))
    async with _make_client() as c:
        r = await c.get("/api/signals", params={"strategy": "all"})
    assert r.status_code == 200
    body = r.json()
    assert all(s["strategy"]["id"] == "all" for s in body["signals"])
    assert len(body["signals"]) == 1


# ── market_breadth / market_axes join ─────────────────────────────────────────

async def test_signals_overlays_market_breadth_and_axes(
    signals_file, market_file, tmp_path, monkeypatch,
):
    """market_snapshot 에 market_breadth/market_axes 있으면 응답에 포함."""
    import json as _json
    base = _json.loads(market_file.read_text(encoding="utf-8"))
    base["market_breadth"] = {"1d": {"up_ratio": 0.62, "above_ma20_ratio": 0.45, "avg_atr_pct": 1.2, "top_volume_return_avg": 0.003}}
    base["market_axes"] = {"1d": {"trend_score": 24, "volatility_regime": "MID"}}
    mf = tmp_path / "market_with_axes.json"
    mf.write_text(_json.dumps(base), encoding="utf-8")
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_file))
    monkeypatch.setattr(signals_module, "_market_loader", MarketLoader(mf))

    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    body = r.json()
    assert "market_breadth" in body
    assert body["market_breadth"]["1d"]["up_ratio"] == 0.62
    assert "market_axes" in body
    assert body["market_axes"]["1d"]["trend_score"] == 24
    assert body["market_axes"]["1d"]["volatility_regime"] == "MID"


async def test_signals_no_breadth_when_market_missing(with_signals, with_no_market):
    """market_snapshot 없으면 market_breadth/market_axes 키 없음."""
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    body = r.json()
    assert "market_breadth" not in body
    assert "market_axes" not in body


async def test_signals_overlays_fear_greed(
    signals_file, market_file, tmp_path, monkeypatch,
):
    """market_snapshot 에 fear_greed 있으면 /api/signals 응답에 포함."""
    import json as _json
    base = _json.loads(market_file.read_text(encoding="utf-8"))
    base["fear_greed"] = {
        "score": 72.4,
        "label": "Greed",
        "components": {"momentum": 80.1, "breadth": 65.0, "volatility": 72.1},
        "history": [
            {"date": "2026-04-01", "score": 50.0},
            {"date": "2026-04-02", "score": 55.0},
        ],
    }
    mf = tmp_path / "market_with_fear_greed.json"
    mf.write_text(_json.dumps(base), encoding="utf-8")
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_file))
    monkeypatch.setattr(signals_module, "_market_loader", MarketLoader(mf))

    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    body = r.json()
    assert "fear_greed" in body
    assert body["fear_greed"]["score"] == 72.4
    assert body["fear_greed"]["label"] == "Greed"
    assert set(body["fear_greed"]["components"]) == {"momentum", "breadth", "volatility"}
    assert len(body["fear_greed"]["history"]) == 2


async def test_signals_no_fear_greed_when_market_missing(with_signals, with_no_market):
    """market_snapshot 없으면 fear_greed 키 없음."""
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    assert "fear_greed" not in r.json()


async def test_signals_no_strategy_query_returns_all_entries(
    signals_with_all_file, monkeypatch, with_no_market,
):
    """쿼리 없으면 모든 entry (strategy='all' 포함) 반환."""
    monkeypatch.setattr(signals_module, "_loader", SignalLoader(signals_with_all_file))
    async with _make_client() as c:
        r = await c.get("/api/signals")
    assert r.status_code == 200
    ids = {s["strategy"]["id"] for s in r.json()["signals"]}
    assert "all" in ids
    assert "strategy_one_d_v2" in ids


async def test_signals_etag_changes_when_market_changes(
    with_signals, market_file, monkeypatch,
):
    """market 파일이 갱신되면 ETag 도 바뀌어야 함 (signals 는 그대로여도)."""
    from app.services.market_loader import MarketLoader
    import app.api.signals as signals_module_local
    monkeypatch.setattr(signals_module_local, "_market_loader", MarketLoader(market_file))
    async with _make_client() as c:
        r1 = await c.get("/api/signals")
        etag1 = r1.headers["ETag"]
    # market 파일 갱신 (touch)
    import time
    time.sleep(0.01)
    market_file.write_text(market_file.read_text() + " ", encoding="utf-8")
    async with _make_client() as c:
        r2 = await c.get("/api/signals")
        etag2 = r2.headers["ETag"]
    assert etag1 != etag2
