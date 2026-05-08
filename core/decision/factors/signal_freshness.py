"""
core/decision/factors/signal_freshness.py — 신호 freshness factor.

trigger 봉 이후 경과 봉 수에 따른 exponential decay score.
freshness = 0.5 ** (bars_since_trigger / decay_half_life)

설계:
  - bars=0 → 1.0 (즉시 신호)
  - bars=decay_half_life → 0.5 (반감)
  - bars >> decay_half_life → ~0 (매우 오래됨)
  - bars<0 (미래) → 1.0 (fallback 보수적 처리)
"""
from __future__ import annotations


def compute_signal_freshness(
    bars_since_trigger: int,
    decay_half_life: float = 3.0,
) -> float:
    """신호 trigger 봉 이후 경과 봉 수 → 0~1 freshness score (lower_better, exp decay).

    Args:
        bars_since_trigger: trigger 봉으로부터 경과 봉 수 (0=즉시, 1=다음봉, ...)
        decay_half_life: 반감기 (기본값 3.0 봉)

    Returns:
        float: freshness score (0.0 ~ 1.0). 1.0 에 가까울수록 신호가 신선함.
    """
    if bars_since_trigger < 0:
        return 1.0  # 미래 이벤트 — 즉시 처리 (fallback)
    return float(0.5 ** (bars_since_trigger / decay_half_life))
