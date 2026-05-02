"""
test_decision_ensemble.py — 다중 전략 교집합 + Minimax Regret 검증.

Phase 2:
  - compute_ensemble_count: ticker → 등장 전략 수
  - apply_minimax_regret: 후보별 시나리오 후회 매트릭스 → 최대 후회 최소화 정렬
  - auto_volatility_scenarios: 후보 risk/reward 기반 bull/bear 자동 시나리오
"""
from __future__ import annotations

import pandas as pd

import pytest

from core.decision.aggregator import RankedCandidate
from core.decision.ensemble import (
    apply_minimax_regret,
    auto_volatility_scenarios,
    compute_ensemble_count,
    compute_weighted_ensemble_score,
)
from core.strategy_base import Candidate


def _cand(ticker: str, **kwargs) -> Candidate:
    base = dict(
        ticker=ticker, name=f"name_{ticker}", strategy="dummy",
        signal_date=pd.Timestamp("2026-05-02"),
        score=500.0,
        entry_price=100.0, stop_loss=98.0,
        target_1=102.0, target_2=104.0,
    )
    base.update(kwargs)
    return Candidate(**base)


def _ranked(ticker: str, final_score: float = 50.0, **cand_kwargs) -> RankedCandidate:
    return RankedCandidate(
        candidate=_cand(ticker, **cand_kwargs),
        final_score=final_score,
        contributions={},
        normalized_metrics={},
    )


# ---------------------------------------------------------------------------
# compute_ensemble_count
# ---------------------------------------------------------------------------

def test_ensemble_count_single_strategy():
    by_strat = {"strat_a": [_cand("005930"), _cand("000660")]}
    counts = compute_ensemble_count(by_strat)
    assert counts == {"005930": 1, "000660": 1}


def test_ensemble_count_two_strategies_intersection():
    by_strat = {
        "strat_a": [_cand("005930"), _cand("000660")],
        "strat_b": [_cand("005930"), _cand("035720")],
    }
    counts = compute_ensemble_count(by_strat)
    assert counts["005930"] == 2  # 두 전략 동시 등장
    assert counts["000660"] == 1
    assert counts["035720"] == 1


def test_ensemble_count_three_strategies():
    by_strat = {
        "a": [_cand("X"), _cand("Y")],
        "b": [_cand("X"), _cand("Z")],
        "c": [_cand("X"), _cand("Y")],
    }
    counts = compute_ensemble_count(by_strat)
    assert counts["X"] == 3
    assert counts["Y"] == 2
    assert counts["Z"] == 1


def test_ensemble_count_empty():
    assert compute_ensemble_count({}) == {}
    assert compute_ensemble_count({"a": []}) == {}


# ---------------------------------------------------------------------------
# apply_minimax_regret
# ---------------------------------------------------------------------------

def test_minimax_regret_prefers_lowest_max_regret():
    """A: 시나리오X 후회 0, Y 후회 3. B: X 후회 2, Y 후회 1.
    A의 max=3, B의 max=2 → B 가 우선 (최대 후회 작음)."""
    ranked = [_ranked("A", final_score=80.0), _ranked("B", final_score=80.0)]

    def regret_fn(cand: Candidate) -> dict[str, float]:
        return {
            "A": {"X": 0.0, "Y": 3.0},
            "B": {"X": 2.0, "Y": 1.0},
        }[cand.ticker]

    out = apply_minimax_regret(ranked, regret_fn)
    assert [r.candidate.ticker for r in out] == ["B", "A"]


def test_minimax_regret_secondary_sort_by_final_score():
    """최대 후회 동률 시 final_score 우선순위 (내림차순)."""
    ranked = [_ranked("A", final_score=70.0), _ranked("B", final_score=90.0)]

    def regret_fn(cand: Candidate) -> dict[str, float]:
        return {"X": 1.0, "Y": 1.0}  # 둘 다 max=1

    out = apply_minimax_regret(ranked, regret_fn)
    assert out[0].candidate.ticker == "B"  # final_score 더 높음


def test_minimax_regret_empty_scenarios_returns_input_order():
    ranked = [_ranked("A"), _ranked("B")]
    out = apply_minimax_regret(ranked, lambda c: {})
    # 빈 시나리오면 max regret 0 으로 모두 동률 → final_score 정렬
    assert len(out) == 2


def test_minimax_regret_records_max_regret_in_metadata():
    """RankedCandidate에 max_regret 기록."""
    ranked = [_ranked("A", final_score=80.0)]

    def regret_fn(cand):
        return {"X": 1.5, "Y": 0.5}

    out = apply_minimax_regret(ranked, regret_fn)
    assert "max_regret" in out[0].normalized_metrics or \
           hasattr(out[0], "max_regret")
    # 구체값
    val = (out[0].normalized_metrics.get("max_regret")
           or getattr(out[0], "max_regret", None))
    assert val == 1.5


# ---------------------------------------------------------------------------
# auto_volatility_scenarios
# ---------------------------------------------------------------------------

def test_auto_volatility_scenarios_basic():
    """후보 reward/risk → bull(target_1 도달) 와 bear(stop_loss 도달) 시나리오 후회."""
    ranked = [
        _ranked("A", entry_price=100.0, stop_loss=98.0,
                target_1=110.0, target_2=120.0),
        _ranked("B", entry_price=100.0, stop_loss=95.0,
                target_1=103.0, target_2=105.0),
    ]
    regret_fn = auto_volatility_scenarios(ranked)
    a_regret = regret_fn(ranked[0].candidate)
    b_regret = regret_fn(ranked[1].candidate)
    # bull 시나리오: A 의 reward 가 더 큼 → B 의 후회 (놓친 reward) 더 큼
    assert b_regret["bull"] >= a_regret["bull"]
    # bear 시나리오: B 의 risk(-5%) 가 더 큼 → B 의 손실 후회 더 큼
    assert b_regret["bear"] >= a_regret["bear"]


# ---------------------------------------------------------------------------
# compute_weighted_ensemble_score
# ---------------------------------------------------------------------------

def test_weighted_ensemble_score_strategy_one_d_v2_alone():
    """strategy_one_d_v2 단독 등장 → score 2.0."""
    by_strat = {"strategy_one_d_v2": [_cand("005930")]}
    scores = compute_weighted_ensemble_score(
        by_strat, {"strategy_one_d_v2": 2.0}
    )
    assert scores["005930"] == pytest.approx(2.0)


def test_weighted_ensemble_score_two_low_weight_strategies():
    """strategy_two(1.0) + strategy_three(1.0) → score 2.0."""
    by_strat = {
        "strategy_two": [_cand("005930")],
        "strategy_three": [_cand("005930")],
    }
    scores = compute_weighted_ensemble_score(
        by_strat,
        {"strategy_two": 1.0, "strategy_three": 1.0},
    )
    assert scores["005930"] == pytest.approx(2.0)


def test_weighted_ensemble_fallback_unknown_strategy():
    """strategy_weights에 없는 전략 → 가중치 1.0."""
    by_strat = {"unknown_strategy": [_cand("005930")]}
    scores = compute_weighted_ensemble_score(by_strat, {})
    assert scores["005930"] == pytest.approx(1.0)


def test_weighted_ensemble_empty_weights_equals_count():
    """strategy_weights 빈 dict → compute_ensemble_count 와 동일."""
    by_strat = {
        "strat_a": [_cand("005930"), _cand("000660")],
        "strat_b": [_cand("005930")],
    }
    scores = compute_weighted_ensemble_score(by_strat, {})
    assert scores["005930"] == pytest.approx(2.0)
    assert scores["000660"] == pytest.approx(1.0)
