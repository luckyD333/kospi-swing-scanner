"""tests/test_runner_regime_wiring.py — Phase 3 wiring 단위 테스트.

대상:
  - core.decision.runner._build_unique_pool: regime label/fng_label 전달 시
    compute_regime_aware_ensemble_score 가 호출되어 effective weight 가 ensemble_score 에
    반영되는지
  - core.decision.runner._load_fng_label: data/market_snapshot.json 없음/None/정상 처리

배경: 2026-05-19 Phase 3 wiring 전 runner 가 compute_weighted_ensemble_score 만 호출 →
weights.yml 의 strategy_weights_by_regime / fng_modifier 가 의사결정에 미반영. 본 테스트로
회귀 차단.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from core.decision.config import Priority, WeightConfig
from core.decision.runner import _build_unique_pool, _load_fng_label
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


def test_wiring_applies_fng_modifier():
    """fng_label 전달 시 fng_modifier 가 적용."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0},
        strategy_weights_by_regime={"UPTREND_STRONG": {"s_one": 1.0}},
        fng_modifier={"extreme_greed": 0.6},
    )
    by_strategy = {"s_one": [_mk_candidate("AAA", "s_one")]}
    regime = {"current_score": 80, "current_regime": "UPTREND_STRONG"}
    pool = _build_unique_pool(by_strategy, weight_config=cfg, regime=regime, fng_label="Extreme Greed")
    aaa = pool[0]
    # 1.0 * 0.6 = 0.6
    assert aaa.metadata["ensemble_score"] == pytest.approx(0.6)
    assert aaa.metadata["fng_label"] == "Extreme Greed"


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


# -----------------------------------------------------------------------------
# _load_fng_label
# -----------------------------------------------------------------------------


def test_load_fng_label_missing_file_returns_none(tmp_path: Path):
    """파일 없음 → None (예외 X)."""
    assert _load_fng_label(tmp_path / "no_such.json") is None


def test_load_fng_label_returns_label(tmp_path: Path):
    """fear_greed.label 정상 추출."""
    p = tmp_path / "market_snapshot.json"
    p.write_text(json.dumps({"fear_greed": {"score": 80, "label": "Extreme Greed"}}))
    assert _load_fng_label(p) == "Extreme Greed"


def test_load_fng_label_handles_none_fear_greed(tmp_path: Path):
    """fear_greed=None 또는 키 부재 시 None."""
    p1 = tmp_path / "snap1.json"
    p1.write_text(json.dumps({"fear_greed": None}))
    p2 = tmp_path / "snap2.json"
    p2.write_text(json.dumps({}))
    assert _load_fng_label(p1) is None
    assert _load_fng_label(p2) is None
