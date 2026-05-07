"""
core/decision/multi_timeframe.py — 멀티 TF RSI 역할 분리 헬퍼 (PR-I).

역할:
  1D  → 추세 게이트 (StrategyD rsi_oversold 조건에서 이미 처리)
  1h  → 진입 트리거 정밀도 (score 가산 1회)
  30m → 과열 감지 (RSI 80+ 시 페널티)

동시 과열/과매도:
  모든 유효 TF 가 동시에 RSI > 80 이거나 RSI < 20 이면 confirmation × 0.85.
"""
from __future__ import annotations

_OVERBOUGHT = 80.0
_OVERSOLD = 20.0
_PENALTY = 0.85


def compute_multi_tf_penalty(rsi_by_tf: dict[str, float | None]) -> float:
    """동시 과열/과매도 감지 시 0.85, 그 외 1.0.

    Args:
        rsi_by_tf: TF 이름 → RSI 값 (None 은 데이터 미보유).
                   유효값이 2개 미만이면 페널티 없음.
    """
    values = [v for v in rsi_by_tf.values() if v is not None]
    if len(values) < 2:
        return 1.0
    if all(v > _OVERBOUGHT for v in values):
        return _PENALTY
    if all(v < _OVERSOLD for v in values):
        return _PENALTY
    return 1.0
