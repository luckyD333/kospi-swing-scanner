from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_DATA_DIR = Path(os.getenv("SIGNAL_API_DATA_DIR", "data"))
_PERFORMANCE_PATH = _DATA_DIR / "strategy_performance.json"


def _not_ready_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "status": "not_ready",
        "updated_at": None,
        "window": {"from": None, "to": None},
        "evaluation": {
            "timeframe": "1D",
            "basis": "signal_close_to_next_close",
            "horizon_bars": 1,
            "cost_pct": 0.30,
        },
        "strategies": {},
        "daily": [],
        "totals": {},
        "archive_summary": {
            "discovered_files": 0,
            "loaded_files": 0,
            "failed_files_count": 0,
            "failed_files": [],
        },
    }


@router.get("/strategy-performance")
async def get_strategy_performance() -> JSONResponse:
    """최근 rolling 전략 성과를 반환한다.

    성과 파일은 선택적 운영 artifact이므로 아직 생성되지 않은 경우에도
    signal API 자체를 실패시키지 않고 ``not_ready`` payload를 반환한다.
    """
    if not _PERFORMANCE_PATH.exists():
        body = _not_ready_payload()
    else:
        try:
            body = json.loads(_PERFORMANCE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return JSONResponse(
                status_code=503,
                content={"error": "strategy_performance_malformed"},
            )
    return JSONResponse(content=body, headers={"Cache-Control": "no-cache"})
