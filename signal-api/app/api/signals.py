import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ..services.signal_loader import SignalLoader

logger = logging.getLogger(__name__)
router = APIRouter()

_DATA_PATH = Path(os.getenv("SIGNAL_API_DATA_DIR", "data")) / "signals.json"
_loader = SignalLoader(_DATA_PATH)


def _load_or_raise():
    try:
        return _loader.load()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "signals_not_generated",
                "hint": "Run Job B: python scripts/collect.py --format signals_ui",
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


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/signals")
async def get_signals(request: Request):
    loaded = _load_or_raise()
    if request.headers.get("if-none-match") == loaded.etag:
        return Response(status_code=304)
    return JSONResponse(
        content=loaded.raw,
        headers={"ETag": loaded.etag, "Cache-Control": "no-cache"},
    )


@router.get("/signals/{ticker}")
async def get_signal(ticker: str, request: Request):
    loaded = _load_or_raise()
    if request.headers.get("if-none-match") == loaded.etag:
        return Response(status_code=304)
    signal = loaded.by_ticker.get(ticker)
    if signal is None:
        raise HTTPException(404, detail={"error": "ticker_not_found", "ticker": ticker})
    return JSONResponse(
        content=signal,
        headers={"ETag": loaded.etag, "Cache-Control": "no-cache"},
    )
