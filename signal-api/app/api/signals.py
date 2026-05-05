import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ..services.signal_loader import SignalLoader
from ..services.market_loader import MarketLoader
from ..services.join import build_aggregated_signal, overlay_signals_list

logger = logging.getLogger(__name__)
router = APIRouter()

_DATA_DIR = Path(os.getenv("SIGNAL_API_DATA_DIR", "data"))
_DATA_PATH = _DATA_DIR / "signals.json"
_MARKET_PATH = _DATA_DIR / "market_snapshot.json"
_loader = SignalLoader(_DATA_PATH)
_market_loader = MarketLoader(_MARKET_PATH)

# Join 결과 캐시 — etag 변경 시 자동 무효화
# 키: combined ETag (signals.json mtime+size + market_snapshot.json mtime+size)
# 무효화: 어느 한 파일이라도 갱신되면 _maybe_invalidate()가 전체 캐시 초기화
# 스레드 안전성: async def 핸들러 내 critical section에 await 없음 →
#   asyncio 단일 이벤트 루프에서 원자적 실행 보장. uvicorn --workers N (멀티 프로세스) 시
#   프로세스별 독립 캐시 — 공유 캐시 없이도 각 워커가 독립적으로 캐시 유지.
_cache_etag: str | None = None
_cached_base_body: dict | None = None   # /api/signals 기본 body (strategy 필터 전)
_cached_tickers: dict[str, dict] = {}  # ticker → /api/signals/{ticker} body


def _maybe_invalidate(etag: str) -> None:
    global _cache_etag, _cached_base_body, _cached_tickers
    if _cache_etag != etag:
        _cache_etag = etag
        _cached_base_body = None
        _cached_tickers = {}


def _load_or_raise():
    try:
        return _loader.load()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "signals_not_generated",
                "hint": (
                    "Run Job B: python cli.py --strategy all --cache-root .cache "
                    "--output-dir data --format signals_ui"
                ),
            },
            headers={"Retry-After": "3600"},
        )
    except ValueError as e:
        msg = str(e)
        if "malformed" in msg:
            logger.error("signals.json 손상: %s", e)
            raise HTTPException(503, detail={"error": "signals_malformed"})
        logger.error("signals.json 스키마 불일치: %s", e)
        raise HTTPException(503, detail={"error": "signals_schema_invalid"})


def _combined_etag(signals_etag: str, market_etag: str | None) -> str:
    """signals + market 두 파일 mtime 합쳐 ETag 생성. market 없으면 signals 만."""
    if market_etag is None:
        return signals_etag
    # signals_etag = '"<mt>-<sz>"' 형식. 뒤에 market mtime/size 합산.
    return f'{signals_etag.rstrip(chr(34))}-{market_etag.strip(chr(34))}"'


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/signals")
async def get_signals(request: Request, strategy: str | None = None):
    """
    Query parameter:
      - strategy: 전략 id 필터 (예: "all" → strategy.id=="all" entry 만 반환).
        대소문자 무시. None 이면 전체.
    """
    loaded = _load_or_raise()
    market = _market_loader.load()
    market_etag = market.etag if market else None
    etag = _combined_etag(loaded.etag, market_etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    global _cached_base_body
    _maybe_invalidate(etag)
    if _cached_base_body is None:
        tickers = market.tickers if market else {}
        _cached_base_body = overlay_signals_list(loaded.raw, tickers) if tickers else dict(loaded.raw)
        if market and market.regime:
            _cached_base_body["market_regime"] = market.regime
        if market and market.breadth:
            _cached_base_body["market_breadth"] = market.breadth
        if market and market.axes:
            _cached_base_body["market_axes"] = market.axes
        if market and market.fear_greed:
            _cached_base_body["fear_greed"] = market.fear_greed
    body = _cached_base_body
    if strategy:
        target = strategy.lower()
        body = {
            **body,
            "signals": [
                s for s in body.get("signals", [])
                if ((s.get("strategy") or {}).get("id", "")).lower() == target
            ],
        }
    return JSONResponse(
        content=body,
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )


@router.get("/signals/{ticker}")
async def get_signal(ticker: str, request: Request):
    loaded = _load_or_raise()
    entries = loaded.entries_by_ticker.get(ticker)
    if not entries:
        raise HTTPException(404, detail={"error": "ticker_not_found", "ticker": ticker})
    market = _market_loader.load()
    market_etag = market.etag if market else None
    etag = _combined_etag(loaded.etag, market_etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    _maybe_invalidate(etag)
    if ticker not in _cached_tickers:
        snapshot_ticker = market.tickers.get(ticker) if market else None
        _cached_tickers[ticker] = build_aggregated_signal(entries, snapshot_ticker)
    body = _cached_tickers[ticker]
    return JSONResponse(
        content=body,
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )
