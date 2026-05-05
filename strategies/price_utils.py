"""strategies/price_utils.py — KRX 호가 단위 기반 가격 반올림 + 30m limit_entry 유틸리티."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


def _tick_size(price: float) -> int:
    """한국거래소(KRX) 공식 호가 단위 반환."""
    if price <= 1_000:
        return 1
    elif price <= 5_000:
        return 5
    elif price <= 10_000:
        return 10
    elif price <= 50_000:
        return 50
    elif price <= 100_000:
        return 100
    elif price <= 500_000:
        return 500
    else:
        return 1_000


def round_to_tick(price: float) -> int:
    """KRX 호가 단위로 반올림 (0.5 이상 올림). 진입가·목표가에 사용."""
    tick = _tick_size(price)
    return int(math.floor(price / tick + 0.5) * tick)


def floor_to_tick(price: float) -> int:
    """KRX 호가 단위로 내림. 손절가에 사용 (보수적 방향 — 더 낮게)."""
    tick = _tick_size(price)
    return int(math.floor(price / tick) * tick)


def find_limit_entry(
    df_30m: pd.DataFrame | None,
    entry: int,
    stop_loss: int,
    lookback_bars: int = 13,
    order: int = 2,
) -> int | None:
    """30m swing low 중 (stop_loss, entry) 배타 범위 내 최고 pivot. 없으면 None.

    반환값 보장:
      - None 이거나, stop_loss < value < entry
      - round_to_tick 적용된 정수

    한국장 1거래일 = 30m × 13봉. order=2 는 최소 5봉 필요.
    """
    if df_30m is None or len(df_30m) < order * 2 + 1:
        return None

    n = min(len(df_30m), lookback_bars + order * 2)
    lows = df_30m["low"].iloc[-n:].to_numpy(dtype=float)

    pivot_indices = argrelextrema(lows, np.less_equal, order=order)[0]
    if len(pivot_indices) == 0:
        return None

    pivot_values = lows[pivot_indices]
    valid = pivot_values[(pivot_values > stop_loss) & (pivot_values < entry)]
    if len(valid) == 0:
        return None

    return round_to_tick(float(valid.max()))


def compute_limit_stop(
    limit_entry: int,
    df_30m: pd.DataFrame | None,
    atr_period: int = 14,
) -> int:
    """limit_entry - 1×ATR_30m. ATR 미계산 시 limit_entry × 0.985 fallback."""
    if df_30m is not None and len(df_30m) >= atr_period:
        from core.indicators import calc_atr

        atr_series = calc_atr(
            df_30m["high"], df_30m["low"], df_30m["close"], period=atr_period
        )
        atr = atr_series.iloc[-1]
        if not pd.isna(atr) and atr > 0:
            return floor_to_tick(limit_entry - float(atr))
    return floor_to_tick(limit_entry * 0.985)


def populate_limit_fields(
    df_30m: pd.DataFrame | None,
    entry: int,
    stop_loss: int,
) -> tuple[int | None, int | None]:
    """5전략 공통 헬퍼. (limit_entry, limit_stop) 반환.

    `find_limit_entry` 가 (stop_loss, entry) 범위를 보장하므로 limit_entry
    자체 범위 검증은 불필요. limit_stop 만 추가 검증:
      - ATR fallback 결과가 limit_entry 이상이거나 0 이하면 무효 → 양쪽 None
    """
    limit_entry = find_limit_entry(df_30m, entry, stop_loss)
    if limit_entry is None:
        return None, None

    limit_stop = compute_limit_stop(limit_entry, df_30m)
    if limit_stop >= limit_entry or limit_stop <= 0:
        return None, None

    return limit_entry, limit_stop
