"""ATR + score percentile 기반 trade_plan(stop/target_1/target_2) 산식 통합 helper.

설계 (plan: trade-plan-pricing-redesign Phase 2):
  - stop = entry - k_adj × ATR_14
  - k_adj = base_k_stop × (1.3 - 0.6 × score_percentile)
    · score 0.5 → 1.0× base (중립), 1.0 → 0.7× (자신감, stop tight), 0.0 → 1.3× (보수)
  - target_1 = entry + r_target_1 × R  (R = entry - stop)
  - target_2 = entry + r_target_2 × R

전략별 base k/r 은 STRATEGY_PARAMS 단일 module constant 에서 lookup. r1/r2/_d_v2/_1h/_30m
등 variant 는 resolve_base_strategy_id() 의 regex 로 base 5 키에 매핑.

운영 retune: STRATEGY_PARAMS 의 base_k_stop 값을 walk-forward 결과로 직접 수정.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TradePlanParams:
    """전략별 stop/target 산식 base 파라미터.

    base_k_stop: ATR multiplier (stop 까지 거리). score_pct 동적 ±30% 조정.
    r_target_1: target_1 의 R 비율 (R = entry - stop). 기본 1.0 (1R).
    r_target_2: target_2 의 R 비율. 전략별 reward 욕심에 따라 차등.
    """
    base_k_stop: float
    r_target_1: float = 1.0
    r_target_2: float = 2.0


@dataclass(frozen=True)
class TradePlanResult:
    """compute_trade_plan() 산출물."""
    stop: float
    target_1: float
    target_2: float
    risk: float       # entry - stop (양수)
    k_used: float     # 최종 적용 k_adj (UI 표시·디버그용)
    atr_14: float


# 단일 위치 base k/r 테이블 — retune 시 여기 5 줄만 수정.
# base_k_stop 은 경험치 초기값 (백테스트 근거 없음). 운영 1주 후 walk-forward retune 예정.
STRATEGY_PARAMS: dict[str, TradePlanParams] = {
    "strategy_five":  TradePlanParams(base_k_stop=1.5, r_target_1=1.0, r_target_2=3.0),
    "strategy_three": TradePlanParams(base_k_stop=1.8, r_target_1=1.0, r_target_2=2.5),
    "strategy_four":  TradePlanParams(base_k_stop=1.8, r_target_1=1.0, r_target_2=2.5),
    "strategy_one":   TradePlanParams(base_k_stop=1.6, r_target_1=1.0, r_target_2=3.0),
    "strategy_two":   TradePlanParams(base_k_stop=2.0, r_target_1=1.0, r_target_2=2.0),
}

# REGISTRY 의 strategy_id (예: strategy_one_d_v2_r1, strategy_two_30m,
# strategy_five_bull_flag_1h) 에서 base 5 키 (strategy_one ~ strategy_five) 추출.
_BASE_STRATEGY_RE = re.compile(r"^(strategy_(?:one|two|three|four|five))(?:_.*)?$")


def resolve_base_strategy_id(strategy_id: str) -> str:
    """REGISTRY full strategy_id → base 5 키 (strategy_one/two/three/four/five).

    예:
      strategy_one_d_v2_r1 → strategy_one
      strategy_two_30m → strategy_two
      strategy_five_bull_flag_1h → strategy_five

    매칭 실패 시 KeyError (REGISTRY 와 STRATEGY_PARAMS 동기 깨짐 신호).
    """
    if not strategy_id:
        raise KeyError("empty strategy_id")
    m = _BASE_STRATEGY_RE.match(strategy_id)
    if not m:
        raise KeyError(f"unknown strategy_id (no base match): {strategy_id}")
    return m.group(1)


def compute_trade_plan(
    *,
    entry: float,
    atr_14: float,
    strategy_id: str,
    score_percentile: float,
    support_floor: float | None = None,
) -> TradePlanResult:
    """ATR + score 기반 stop/target_1/target_2 산정.

    Args:
      entry: 진입가 (>0)
      atr_14: ATR(14) — 종목 변동성 단위
      strategy_id: REGISTRY 의 full id (resolver 가 base 5 키로 매핑)
      score_percentile: 0~1 신호 강도 percentile (intra-strategy). clamp 됨.
      support_floor: 차트 지지선 (있으면 max(stop, support_floor) 로 stop 의 최저점 보장)

    Returns:
      TradePlanResult — UI/Candidate 빌더가 그대로 stop/target_1/target_2 사용.
    """
    if entry <= 0:
        raise ValueError(f"entry must be > 0, got {entry}")
    if atr_14 <= 0:
        raise ValueError(f"atr_14 must be > 0, got {atr_14}")
    if support_floor is not None and support_floor >= entry:
        # support_floor 가 진입가 이상이면 strategy 코드의 logic bug.
        # silent 보정하면 후속 retune 시 신호 왜곡 → 명시적으로 raise.
        raise ValueError(
            f"support_floor ({support_floor}) must be < entry ({entry}); "
            f"strategy_id={strategy_id}"
        )

    base = resolve_base_strategy_id(strategy_id)
    params = STRATEGY_PARAMS[base]

    # score clamp [0, 1]
    s = max(0.0, min(1.0, score_percentile))
    k_adj = params.base_k_stop * (1.3 - 0.6 * s)

    stop = entry - k_adj * atr_14
    if support_floor is not None and support_floor > stop:
        stop = support_floor
    if stop >= entry:
        # k_adj × atr_14 가 entry 이상 (저가주 + 큰 ATR) — 최소 risk 1×ATR fallback.
        stop = entry - atr_14

    risk = entry - stop
    target_1 = entry + params.r_target_1 * risk
    target_2 = entry + params.r_target_2 * risk

    return TradePlanResult(
        stop=stop,
        target_1=target_1,
        target_2=target_2,
        risk=risk,
        k_used=k_adj,
        atr_14=atr_14,
    )
