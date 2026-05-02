"""manifest.json 기반 캐시 신선도 검증."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class FreshnessResult:
    ok: bool
    stale_hours: float
    message: str


def check_freshness(cache_root: Path, stale_hours: float = 8.0) -> FreshnessResult:
    manifest_path = Path(cache_root) / "manifest.json"
    if not manifest_path.exists():
        return FreshnessResult(
            ok=False,
            stale_hours=float("inf"),
            message=f"manifest.json 없음: {manifest_path}",
        )
    try:
        data = json.loads(manifest_path.read_text())
        collected_at = datetime.fromisoformat(data["collected_at"])
    except Exception as e:
        return FreshnessResult(
            ok=False,
            stale_hours=float("inf"),
            message=f"manifest.json 파싱 실패: {e}",
        )

    elapsed = (datetime.now() - collected_at).total_seconds() / 3600
    if elapsed > stale_hours:
        return FreshnessResult(
            ok=False,
            stale_hours=elapsed,
            message=f"캐시 stale: {elapsed:.1f}시간 경과 (허용 {stale_hours}시간)",
        )
    return FreshnessResult(ok=True, stale_hours=elapsed, message="캐시 신선")
