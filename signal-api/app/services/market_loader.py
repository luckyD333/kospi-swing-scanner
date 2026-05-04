import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LoadedMarket:
    indices: dict[str, Any]
    tickers: dict[str, Any]  # ticker_id → TickerSnapshot dict (fundamentals/flow/external_links 등)
    regime: dict[str, Any] | None  # timeframe_scores ({"1d": {...}, "1h": {...}})
    breadth: dict[str, Any] | None  # timeframe → breadth metrics
    axes: dict[str, Any] | None    # timeframe → {trend_score, volatility_regime}
    fear_greed: dict[str, Any] | None  # {score, label, components, history}
    etag: str
    mtime: float
    size: int


class MarketLoader:
    """SignalLoader와 동일한 (mtime,size) 캐시 패턴.

    market_snapshot.json 에서 market_indices + tickers 를 추출해 반환.
    /api/market 은 indices 만 응답, /api/signals join 은 tickers 도 사용.
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
            tickers = data.get("tickers", {})
            regime = data.get("market_regime")
            breadth = data.get("market_breadth")
            axes = data.get("market_axes")
            fear_greed = data.get("fear_greed")
            self._cache = LoadedMarket(
                indices=indices,
                tickers=tickers,
                regime=regime,
                breadth=breadth,
                axes=axes,
                fear_greed=fear_greed,
                etag=f'"{mtime}-{size}"',
                mtime=mtime,
                size=size,
            )
            return self._cache
