"""
core/cache/ohlcv_disk.py — parquet 영속 캐시.

(ticker, timeframe) → DataFrame 매핑을 `<root>/<tf>/<ticker>.parquet` 파일로 저장.
손상 파일은 `.corrupted` 로 격리하고 빈 DataFrame 반환 (다음 실행에 정상화).
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class OhlcvDiskCache:
    """parquet 기반 (ticker, timeframe) → DataFrame 영속 캐시."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, ticker: str, tf: str) -> Path:
        d = self.root / tf
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{ticker}.parquet"

    def read(self, ticker: str, tf: str) -> pd.DataFrame:
        p = self._path(ticker, tf)
        if not p.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(p)
        except Exception as e:
            logger.warning(f"캐시 손상 ({ticker}/{tf}): {e} → .corrupted 로 격리")
            shutil.move(str(p), str(p) + ".corrupted")
            return pd.DataFrame()

    def write(self, ticker: str, tf: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        df.to_parquet(self._path(ticker, tf))

    def has_cache(self, ticker: str, tf: str) -> bool:
        return self._path(ticker, tf).exists()

    def clear(self, ticker: str, tf: str) -> None:
        """단일 (ticker, tf) parquet 파일 삭제. 없으면 no-op (force-refetch용)."""
        p = self._path(ticker, tf)
        try:
            p.unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"캐시 삭제 실패 ({ticker}/{tf}): {e}")

    def append(self, ticker: str, tf: str, df_new: pd.DataFrame) -> pd.DataFrame:
        existing = self.read(ticker, tf)
        if existing.empty:
            self.write(ticker, tf, df_new)
            return df_new.sort_index()
        merged = pd.concat([existing, df_new])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        self.write(ticker, tf, merged)
        return merged
