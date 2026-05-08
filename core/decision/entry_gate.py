"""
core/decision/entry_gate.py — 전략별 entry gate 정책 매트릭스.

7×5 매트릭스: 7개 regime × 5개 전략 = 35개 정책 셀.

정책 액션:
  - "allow": 진입 허용
  - "allow_strong_only": setup_score ≥ 60 일 때만 진입
  - "block": 진입 차단

위계 원칙:
  - 1d regime은 환경 게이트 (Yes/No)
  - 1h setup_score는 메타 정보 (품질 점수)
  - 30m은 실행 가격 산출 (Task 5d)

Calibration (Phase 2):
  - STRONG_SETUP_THRESHOLD = 60 (adjust via weights.yml or CLI flag)
"""
from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

GateAction = Literal["allow", "allow_strong_only", "block"]

# 전략별 entry gate 정책 (7×5 매트릭스)
ENTRY_GATE_POLICY: dict[str, dict[str, GateAction]] = {
    "strategy_one": {  # 평균 회귀 (RSI+BB+쌍바닥+장악형)
        "UPTREND_STRONG": "allow_strong_only",  # 풀백만 (high setup)
        "UPTREND_WEAK": "allow",
        "RANGE_TIGHT": "allow_strong_only",
        "RANGE": "allow",
        "DOWNTREND_WEAK": "allow_strong_only",  # 강한 셋업만
        "DOWNTREND_STRONG": "block",  # 모든 매수 차단
        "MIXED": "allow_strong_only",  # 보수
    },
    "strategy_two": {  # 모멘텀 (cross-sectional)
        "UPTREND_STRONG": "allow",
        "UPTREND_WEAK": "allow",
        "RANGE_TIGHT": "allow",
        "RANGE": "block",  # 횡보장 회피
        "DOWNTREND_WEAK": "block",
        "DOWNTREND_STRONG": "block",
        "MIXED": "block",
    },
    "strategy_three": {  # Donchian 추세 추종
        "UPTREND_STRONG": "allow",
        "UPTREND_WEAK": "allow",
        "RANGE_TIGHT": "allow",  # 돌파 대기 (에너지 응축 → 큰 변동 임박)
        "RANGE": "block",
        "DOWNTREND_WEAK": "block",
        "DOWNTREND_STRONG": "block",
        "MIXED": "block",
    },
    "strategy_four": {  # Pullback MA (추세 추종)
        "UPTREND_STRONG": "allow",
        "UPTREND_WEAK": "allow",
        "RANGE_TIGHT": "allow_strong_only",  # 돌파 대기, 품질 확인
        "RANGE": "block",
        "DOWNTREND_WEAK": "block",
        "DOWNTREND_STRONG": "block",
        "MIXED": "block",
    },
    "strategy_five": {  # Bull Flag (추세 추종)
        "UPTREND_STRONG": "allow",
        "UPTREND_WEAK": "allow",
        "RANGE_TIGHT": "allow",
        "RANGE": "block",
        "DOWNTREND_WEAK": "block",
        "DOWNTREND_STRONG": "block",
        "MIXED": "block",
    },
}

# Strong setup quality threshold (경계값 캘리브레이션)
STRONG_SETUP_THRESHOLD = 60


def is_strategy_allowed(
    strategy_family: str,
    regime: str,
    setup_score: int | None = None,
) -> bool:
    """전략·regime·setup_score 조합으로 entry gate 판정.

    Args:
        strategy_family: "strategy_one_d_v2" / "strategy_two_1h" / ...
                         (정규화됨: "strategy_one", "strategy_two", ... → prefix match)
        regime: daily_regime() 결과 (7단계 중 1개)
        setup_score: 1h setup quality score (선택, allow_strong_only 판정용)

    Returns:
        True: entry 허용
        False: entry 차단
    """
    # regime 미설정 (legacy fixture / 단위 테스트) → gate 우회
    if regime is None:
        return True

    family = _normalize_family(strategy_family)
    action = ENTRY_GATE_POLICY.get(family, {}).get(regime, "block")

    if action == "allow":
        return True
    if action == "block":
        return False
    # allow_strong_only
    return setup_score is not None and setup_score >= STRONG_SETUP_THRESHOLD


def _normalize_family(strategy_id: str) -> str:
    """전략 ID → family 정규화.

    Examples:
        - strategy_one_d_v2 → strategy_one
        - strategy_one_w_v2 → strategy_one
        - strategy_two_1h → strategy_two
        - strategy_three_30m_v2 → strategy_three
        - strategy_four_pullback_ma_1h → strategy_four
        - strategy_five_bull_flag_30m → strategy_five
    """
    for family in (
        "strategy_one",
        "strategy_two",
        "strategy_three",
        "strategy_four",
        "strategy_five",
    ):
        if strategy_id.startswith(family):
            return family
    # 미정의 전략 → block 처리됨. 새 전략 추가 시 ENTRY_GATE_POLICY에 등록 필요.
    logger.warning("entry_gate: 미등록 전략 '%s' → block 처리됨. ENTRY_GATE_POLICY에 추가하세요.", strategy_id)
    return strategy_id
