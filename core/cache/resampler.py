"""
core/cache/resampler.py — 타임프레임 리샘플링 헬퍼.

- 1D → 1W (W-FRI 종가): 한국 증시 주봉 컨벤션 (토·일 미장)
- 1m → 30m / 1h / 2h / 4h: 인트라데이 집계
- 미지원 타임프레임은 ValueError
"""
from __future__ import annotations

import pandas as pd

_FREQ_MAP = {
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1D": "1D",
    "1W": "W-FRI",
}


def resample_to(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """OHLCV DataFrame 을 target_tf 봉으로 집계 (open=first/high=max/low=min/close=last/volume=sum)."""
    if target_tf not in _FREQ_MAP:
        raise ValueError(f"unsupported timeframe: {target_tf}")
    if df.empty:
        return df
    out = (
        df.resample(_FREQ_MAP[target_tf])
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    return out
