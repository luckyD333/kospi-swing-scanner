"""
core/decision/order_type_classifier.py — 진입가 vs 현재가 → 주문 타입 의도 분류.

PR-C (P1-1): 돌파 신호(진입가 > 현재가)인 종목이 '지정가' 라벨로 출력되어
즉시 체결되는 P1-1 결함 차단.

* 본 모듈은 출력 라벨/필드만 다룬다 (스크리너 only — 실제 발주 클라이언트 없음).
* 매핑 규칙:
    entry > current × 1.005   → BREAKOUT  (역지정가)
    entry < current × 0.995   → PULLBACK  (지정가)
    그 외 (≈ 현재가)            → IMMEDIATE (시장가/즉시 지정가)
"""
from __future__ import annotations

from enum import Enum


class OrderTypeIntent(str, Enum):
    """주문 타입 의도 — 발주 시 실제 라벨 매핑의 source-of-truth."""
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    IMMEDIATE = "IMMEDIATE"


_BREAKOUT_THR = 1.005
_PULLBACK_THR = 0.995


_KOREAN_LABEL: dict[OrderTypeIntent, str] = {
    OrderTypeIntent.BREAKOUT: "역지정가",
    OrderTypeIntent.PULLBACK: "지정가",
    OrderTypeIntent.IMMEDIATE: "시장가",
}


def classify(
    entry: float, current: float,
    *, breakout_thr: float = _BREAKOUT_THR, pullback_thr: float = _PULLBACK_THR,
) -> OrderTypeIntent:
    """진입가·현재가 비율 기반 의도 분류.

    current ≤ 0 (이상 데이터) → IMMEDIATE 폴백 (분류 회피).
    """
    if current <= 0:
        return OrderTypeIntent.IMMEDIATE
    ratio = entry / current
    if ratio > breakout_thr:
        return OrderTypeIntent.BREAKOUT
    if ratio < pullback_thr:
        return OrderTypeIntent.PULLBACK
    return OrderTypeIntent.IMMEDIATE


def korean_label(intent: OrderTypeIntent) -> str:
    """OrderTypeIntent → 한국어 UI 라벨."""
    return _KOREAN_LABEL.get(intent, "지정가")
