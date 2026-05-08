"""
core/cache/close_resolver.py — strategy 가 entry 산출 시 사용할 close 인덱스 결정.

1D 의 마지막 row 가 incomplete 봉 (manifest.collected_at < 15:30 KST) 이면
어제 row (-2) 로 fallback. row 가 1개뿐이면 -1.
"""
from __future__ import annotations

import pandas as pd

from core.cache.incomplete_bar import is_today_bar_complete


def resolve_close_index(df: pd.DataFrame, fetched_at_iso: str | None) -> int:
    """incomplete-bar 가드. df.iloc[index] 로 close_now 를 뽑을 인덱스 반환.

    Args:
        df: 1D OHLCV DataFrame (index = datetime).
        fetched_at_iso: manifest.collected_at 또는 호출자 now() ISO.
                        None / 미지정 → 가드 비활성 (legacy/test 환경 호환).

    Returns:
        -1: 가드 비활성 (fetched_at None) 또는 마지막 row 가 confirmed close 또는 row 1개.
        -2: 마지막 row 가 incomplete bar 이고 직전 row 사용 가능.
    """
    if fetched_at_iso is None or len(df) < 2:
        return -1
    last_date_str = df.index[-1].strftime("%Y-%m-%d")
    if is_today_bar_complete(last_date_str, fetched_at_iso):
        return -1
    return -2
