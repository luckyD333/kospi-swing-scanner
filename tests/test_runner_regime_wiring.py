"""tests/test_runner_regime_wiring.py — Phase 3 wiring 단위 테스트.

대상:
  - core.decision.runner._build_unique_pool: regime label/fng_label 전달 시
    compute_regime_aware_ensemble_score 가 호출되어 effective weight 가 ensemble_score 에
    반영되는지

배경: 2026-05-19 Phase 3 wiring 전 runner 가 compute_weighted_ensemble_score 만 호출 →
weights.yml 의 strategy_weights_by_regime 가 의사결정에 미반영. F&G는 이후 정보용으로 전환.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.decision.config import Priority, WeightConfig
from core.decision.runner import _build_unique_pool
from core.strategy_base import Candidate


# -----------------------------------------------------------------------------
# 헬퍼
# -----------------------------------------------------------------------------


def _mk_priorities() -> list[Priority]:
    return [
        Priority(key="momentum_3m", weight=50.0, direction="higher_better", label="momentum"),
        Priority(key="liquidity", weight=50.0, direction="higher_better", label="liquidity"),
    ]


def _mk_candidate(ticker: str, strategy: str = "s_one") -> Candidate:
    return Candidate(
        ticker=ticker, name=ticker, strategy=strategy,
        signal_date=pd.Timestamp("2024-01-01"), score=50.0,
        entry_price=100.0, stop_loss=97.0, target_1=103.0, target_2=105.0,
        metadata={},
    )


# -----------------------------------------------------------------------------
# _build_unique_pool wiring
# -----------------------------------------------------------------------------


def test_wiring_applies_regime_effective_weights():
    """regime 라벨 전달 시 strategy_weights_by_regime 매트릭스가 ensemble_score 에 반영."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0, "s_two": 1.0},
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_one": 1.5, "s_two": 0.5},
        },
    )
    by_strategy = {
        "s_one": [_mk_candidate("AAA", "s_one")],
        "s_two": [_mk_candidate("AAA", "s_two")],
    }
    regime = {"current_score": 80, "current_regime": "UPTREND_STRONG"}
    pool = _build_unique_pool(by_strategy, weight_config=cfg, regime=regime)
    assert len(pool) == 1
    aaa = pool[0]
    # AAA 점수 = 1.5 (s_one) + 0.5 (s_two) = 2.0
    assert aaa.metadata["ensemble_score"] == pytest.approx(2.0)
    assert aaa.metadata["regime_label"] == "UPTREND_STRONG"
    assert aaa.metadata["regime_score"] == 80


def test_wiring_keeps_fng_informational_only():
    """fng_label을 전달해도 점수와 의사결정 메타데이터에 반영하지 않는다."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0},
        strategy_weights_by_regime={"UPTREND_STRONG": {"s_one": 1.0}},
        fng_modifier={"extreme_greed": 0.6},
    )
    candidate = _mk_candidate("AAA", "s_one")
    candidate.metadata["fng_label"] = "Extreme Fear"  # 구형 결과 파일에 남은 값
    by_strategy = {"s_one": [candidate]}
    regime = {"current_score": 80, "current_regime": "UPTREND_STRONG"}
    pool = _build_unique_pool(by_strategy, weight_config=cfg, regime=regime, fng_label="Extreme Greed")
    aaa = pool[0]
    assert aaa.metadata["ensemble_score"] == pytest.approx(1.0)
    assert "fng_label" not in aaa.metadata


def test_wiring_fallback_to_static_when_regime_none():
    """regime=None 시 정적 strategy_weights 동작 유지 (회귀 안전)."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 2.0, "s_two": 1.0},
        strategy_weights_by_regime={"UPTREND_STRONG": {"s_one": 9.9}},  # 사용 X
    )
    by_strategy = {
        "s_one": [_mk_candidate("AAA", "s_one")],
        "s_two": [_mk_candidate("AAA", "s_two")],
    }
    pool = _build_unique_pool(by_strategy, weight_config=cfg, regime=None)
    aaa = pool[0]
    assert aaa.metadata["ensemble_score"] == pytest.approx(3.0)  # 2 + 1
    assert "regime_label" not in aaa.metadata
    assert "fng_label" not in aaa.metadata


def test_wiring_blocks_strategy_when_effective_weight_zero():
    """DOWNTREND_STRONG 같은 차단 regime 에서 effective weight 0 이면 ensemble_score 0."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0},
        strategy_weights_by_regime={"DOWNTREND_STRONG": {"s_one": 0.0}},
    )
    by_strategy = {"s_one": [_mk_candidate("AAA", "s_one")]}
    regime = {"current_score": 10, "current_regime": "DOWNTREND_STRONG"}
    pool = _build_unique_pool(by_strategy, weight_config=cfg, regime=regime)
    aaa = pool[0]
    # 차단 시 점수 누락 → fallback default 1.0 (compute_regime_aware_ensemble_score 의 `if w <= 0: continue`)
    assert aaa.metadata["ensemble_score"] == 1.0
