"""strategies/price_utils.py — KRX 호가 단위 기반 가격 반올림 유틸리티."""
from __future__ import annotations

import math


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
