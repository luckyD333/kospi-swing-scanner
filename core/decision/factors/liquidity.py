"""
core/decision/factors/liquidity.py — 유동성 점수 factor.

유동성 = log(market_cap + 1) × log(20D 평균 거래대금 + 1)

설계:
  - None 입력 → 0.0 (sentinel, aggregator 의 percentile rank 에서 유도)
  - 0 이하 입력 → 0.0
  - cross-sectional rank 변환은 aggregator 담당 (기존 직교 패턴)
"""
from __future__ import annotations

import math


def compute_liquidity_score(
    market_cap_krw: float | None,
    avg_turnover_20d_krw: float | None,
) -> float:
    """log(market_cap) × log(20D 평균 거래대금) raw 점수 계산.

    Args:
        market_cap_krw: 시가총액 (원). None 또는 <= 0 시 0.0 반환.
        avg_turnover_20d_krw: 20일 평균 거래대금 (원). None 또는 <= 0 시 0.0 반환.

    Returns:
        float: raw 유동성 점수 (0 이상). cross-sectional percentile rank 는
               aggregator 가 담당.
    """
    if not market_cap_krw or not avg_turnover_20d_krw:
        return 0.0
    if market_cap_krw <= 0 or avg_turnover_20d_krw <= 0:
        return 0.0
    return math.log(market_cap_krw + 1) * math.log(avg_turnover_20d_krw + 1)
