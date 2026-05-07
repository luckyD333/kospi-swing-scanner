"""
strategies/_atr_stop.py — ATR 기반 손절가 계산 헬퍼 (PR-F).

공식:
  stop = max(entry - atr_mult×ATR, support - support_buffer×ATR)
  ATR 결측(None/0) 또는 stop ≥ entry 이면 % fallback.
"""
from __future__ import annotations


def compute_atr_stop(
    entry: float,
    atr: float | None,
    support: float,
    *,
    atr_mult: float,
    support_buffer: float,
    fallback_pct: float,
) -> float:
    """ATR 기반 손절가. 결측 또는 비정상 시 진입가 × (1 - fallback_pct) 반환."""
    if atr is None or atr <= 0:
        return entry * (1 - fallback_pct)
    stop = max(entry - atr_mult * atr, support - support_buffer * atr)
    if stop >= entry:
        return entry * (1 - fallback_pct)
    return stop
