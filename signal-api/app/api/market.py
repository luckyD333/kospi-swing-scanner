import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..services.market_loader import MarketLoader

logger = logging.getLogger(__name__)
router = APIRouter()

_MARKET_PATH = Path(os.getenv("SIGNAL_API_DATA_DIR", "data")) / "market_snapshot.json"
_loader = MarketLoader(_MARKET_PATH)


@router.get("/market")
async def get_market(request: Request):
    loaded = _loader.load()
    if loaded is None:
        return {"market_indices": {}}
    if request.headers.get("if-none-match") == loaded.etag:
        return Response(status_code=304)
    return JSONResponse(
        content={"market_indices": loaded.indices},
        headers={"ETag": loaded.etag, "Cache-Control": "no-cache"},
    )
