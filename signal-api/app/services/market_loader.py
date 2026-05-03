import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LoadedMarket:
    indices: dict[str, Any]
    etag: str
    mtime: float
    size: int


class MarketLoader:
    """SignalLoader와 동일한 (mtime,size) 캐시 패턴.

    market_snapshot.json은 schema 검증을 강제하지 않고
    market_indices만 추출해 반환한다.
    """

    def __init__(self, path: Path):
        self._path = path
        self._cache: LoadedMarket | None = None
        self._lock = threading.Lock()

    def load(self) -> LoadedMarket | None:
        with self._lock:
            if not self._path.exists():
                self._cache = None
                return None

            stat = self._path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            if self._cache and self._cache.mtime == mtime and self._cache.size == size:
                return self._cache

            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                # market은 graceful degradation 정책 — 손상돼도 None 반환
                return None

            indices = data.get("market_indices", {})
            self._cache = LoadedMarket(
                indices=indices,
                etag=f'"{mtime}-{size}"',
                mtime=mtime,
                size=size,
            )
            return self._cache
