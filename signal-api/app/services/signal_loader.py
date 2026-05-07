import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..models.signal import SignalsResponse


# 단순 TTL 메모리 캐시. cron 의 collect_live 가 2분 주기라 동일 cycle.
# 외부 요청과 무관하게 expire 시점에 lazy 로 재로드. mtime/size 비교 race 회피.
_TTL_SECONDS = 120.0


@dataclass
class LoadedSignals:
    raw: dict[str, Any]
    by_ticker: dict[str, dict[str, Any]]
    entries_by_ticker: dict[str, list[dict[str, Any]]]


class SignalLoader:
    def __init__(self, path: Path):
        self._path = path
        self._cache: LoadedSignals | None = None
        self._cache_set_at: float = 0.0
        self._lock = threading.Lock()

    def load(self) -> LoadedSignals:
        with self._lock:
            if not self._path.exists():
                raise FileNotFoundError(self._path)

            now = time.monotonic()
            if self._cache is not None and (now - self._cache_set_at) < _TTL_SECONDS:
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
            entries_by_ticker: dict[str, list[dict[str, Any]]] = {}
            for s in raw.get("signals", []):
                entries_by_ticker.setdefault(s["ticker"], []).append(s)
            self._cache = LoadedSignals(
                raw=raw,
                by_ticker=by_ticker,
                entries_by_ticker=entries_by_ticker,
            )
            self._cache_set_at = now
            return self._cache
