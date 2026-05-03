import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..models.signal import SignalsResponse


@dataclass
class LoadedSignals:
    raw: dict[str, Any]
    etag: str
    mtime: float
    size: int
    by_ticker: dict[str, dict[str, Any]]


class SignalLoader:
    def __init__(self, path: Path):
        self._path = path
        self._cache: LoadedSignals | None = None
        self._lock = threading.Lock()

    def load(self) -> LoadedSignals:
        with self._lock:
            if not self._path.exists():
                raise FileNotFoundError(self._path)

            stat = self._path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            # (mtime,size) 페어로 비교: 같은 초에 atomic rename 두 번 발생해도 size로 변경 감지
            if self._cache and self._cache.mtime == mtime and self._cache.size == size:
                return self._cache

            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ValueError("malformed") from e

            try:
                SignalsResponse.model_validate(raw)
            except ValidationError as e:
                raise ValueError("schema_invalid") from e

            by_ticker = {s["ticker"]: s for s in raw.get("signals", [])}
            self._cache = LoadedSignals(
                raw=raw,
                etag=f'"{mtime}-{size}"',
                mtime=mtime,
                size=size,
                by_ticker=by_ticker,
            )
            return self._cache
