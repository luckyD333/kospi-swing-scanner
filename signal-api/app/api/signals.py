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
    tickers = market.tickers if market else {}
    body = overlay_signals_list(loaded.raw, tickers) if tickers else dict(loaded.raw)
    if market and market.regime:
        body["market_regime"] = market.regime
    if market and market.breadth:
        body["market_breadth"] = market.breadth
    if market and market.axes:
        body["market_axes"] = market.axes
    if market and market.fear_greed:
        body["fear_greed"] = market.fear_greed
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
    snapshot_ticker = market.tickers.get(ticker) if market else None
    body = build_aggregated_signal(entries, snapshot_ticker)
    return JSONResponse(
        content=body,
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )
