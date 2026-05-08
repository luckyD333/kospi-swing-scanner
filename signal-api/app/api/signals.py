import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..services.signal_loader import SignalLoader
from ..services.market_loader import MarketLoader
from ..services.join import (
    aggregate_entries_for_ticker,
    overlay_signals_list,
)

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


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/signals")
async def get_signals(strategy: str | None = None):
    """
    Query parameter:
      - strategy: 전략 id 필터 (예: "all" → strategy.id=="all" entry 만 반환).
        대소문자 무시. None 이면 전체.
    """
    loaded = _load_or_raise()
    market = _market_loader.load()
    tickers = market.tickers if market else {}
    body = overlay_signals_list(loaded.raw, tickers) if tickers else dict(loaded.raw)
    # Task 8: schema_version 필드 추가 (카탈로그는 2.0으로 고정)
    body["schema_version"] = "2.0"
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
    return JSONResponse(content=body, headers={"Cache-Control": "no-cache"})


@router.get("/signals/{ticker}")
async def get_signal(ticker: str):
    loaded = _load_or_raise()
    entries = loaded.entries_by_ticker.get(ticker)
    if not entries:
        raise HTTPException(404, detail={"error": "ticker_not_found", "ticker": ticker})
    # Task 8: multi-strategy aggregate 응답 (schema_version 2.0)
    market = _market_loader.load()
    snapshot_ticker = market.tickers.get(ticker) if market else None
    body = aggregate_entries_for_ticker(entries, ticker, snapshot_ticker)
    return JSONResponse(content=body, headers={"Cache-Control": "no-cache"})
