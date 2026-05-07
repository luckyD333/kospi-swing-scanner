import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# 단순 TTL 메모리 캐시. cron 의 collect_live 가 2분 주기라 동일 cycle.
# 외부 요청과 무관하게 expire 시점에 lazy 로 재로드. mtime/size 비교 race 회피.
_TTL_SECONDS = 120.0


@dataclass
class LoadedMarket:
    indices: dict[str, Any]
    tickers: dict[str, Any]  # ticker_id → TickerSnapshot dict (fundamentals/flow/external_links 등)
    regime: dict[str, Any] | None  # timeframe_scores ({"1d": {...}, "1h": {...}})
    breadth: dict[str, Any] | None  # timeframe → breadth metrics
    axes: dict[str, Any] | None    # timeframe → {trend_score, volatility_regime}
    fear_greed: dict[str, Any] | None  # {score, label, components, history}


class MarketLoader:
    """SignalLoader 와 동일한 TTL 캐시 패턴.

    market_snapshot.json 에서 market_indices + tickers 를 추출해 반환.
    /api/market 은 indices 만 응답, /api/signals join 은 tickers 도 사용.
    """

    def __init__(self, path: Path):
        self._path = path
        self._cache: LoadedMarket | None = None
        self._cache_set_at: float = 0.0
        self._lock = threading.Lock()

    def load(self) -> LoadedMarket | None:
        with self._lock:
            if not self._path.exists():
                self._cache = None
                self._cache_set_at = 0.0
                return None

            now = time.monotonic()
            if self._cache is not None and (now - self._cache_set_at) < _TTL_SECONDS:
                return self._cache

            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                # market 은 graceful degradation 정책 — 손상돼도 None 반환
                return None

            self._cache = LoadedMarket(
                indices=data.get("market_indices", {}),
                tickers=data.get("tickers", {}),
                regime=data.get("market_regime"),
                breadth=data.get("market_breadth"),
                axes=data.get("market_axes"),
                fear_greed=data.get("fear_greed"),
            )
            self._cache_set_at = now
            return self._cache
