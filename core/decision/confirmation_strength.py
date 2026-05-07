"""
core/decision/confirmation_strength.py — 평균 회귀 confirmation 등급 (PR-H).

등급 기준:
  STRONG : RSI < rsi_strong AND (BB 하단 터치 OR 장악형 양봉) → 배율 1.0
  MEDIUM : rsi_strong ≤ RSI < rsi_medium AND BB AND 장악형 양봉   → 배율 0.7
  WEAK   : 그 외 (단일 트리거 또는 RSI 부재)                       → 배율 0.3
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConfirmationLevel(str, Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"


@dataclass(frozen=True)
class ConfirmationThresholds:
    rsi_strong: float = 35.0   # RSI < rsi_strong → STRONG 후보
    rsi_medium: float = 45.0   # rsi_strong ≤ RSI < rsi_medium → MEDIUM 후보
    scale_medium: float = 0.7
    scale_weak: float = 0.3


_SCALE: dict[ConfirmationLevel, float] = {
    ConfirmationLevel.STRONG: 1.0,
    ConfirmationLevel.MEDIUM: 0.7,
    ConfirmationLevel.WEAK: 0.3,
}

_BB_KEY = "bb_lower_breach"
_ENGULF_KEY = "bullish_engulfing"


def evaluate(
    triggers: set[str],
    rsi: float | None,
    *,
    thresholds: ConfirmationThresholds | None = None,
) -> tuple[ConfirmationLevel, float]:
    """confirmation 등급·점수 배율 반환.

    Args:
        triggers: 발화된 조건 키 집합 (signal.conditions_met 의 True 키)
        rsi: 진입봉 RSI(14) 값. None 이면 WEAK 처리.

    Returns:
        (ConfirmationLevel, scale_factor)
    """
    thr = thresholds or ConfirmationThresholds()
    has_bb = _BB_KEY in triggers
    has_engulf = _ENGULF_KEY in triggers

    if rsi is not None and rsi < thr.rsi_strong and (has_bb or has_engulf):
        level = ConfirmationLevel.STRONG
    elif (
        rsi is not None
        and thr.rsi_strong <= rsi < thr.rsi_medium
        and has_bb
        and has_engulf
    ):
        level = ConfirmationLevel.MEDIUM
    else:
        level = ConfirmationLevel.WEAK

    return level, _SCALE[level]
