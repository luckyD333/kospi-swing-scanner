"""tests/test_decision_runner_regime.py — _build_unique_pool 의 regime metadata 주입 회귀."""
from __future__ import annotations

import pandas as pd

from core.decision.runner import _build_unique_pool
from core.strategy_base import Candidate


def _mk_candidate(ticker: str, strategy: str, score: float = 100.0) -> Candidate:
    return Candidate(
        ticker=ticker,
        name=ticker,
        strategy=strategy,
        signal_date=pd.Timestamp("2026-05-03"),
        score=score,
        entry_price=10000.0,
        stop_loss=9700.0,
        target_1=10300.0,
        target_2=10500.0,
        current_price=10000.0,
        market_cap_bil=100.0,
        volume_20d_avg=100_000.0,
        conditions_met={},
        metadata={"source_strategy": strategy},
    )


def test_build_unique_pool_injects_regime_score_and_label():
    """regime 인자 전달 시 모든 후보 metadata 에 regime_score / regime_label 주입."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
        "strategy_two_*": [_mk_candidate("000660", "strategy_two_*")],
    }
    regime = {"current_score": 85, "current_regime": "BULL"}

    pool = _build_unique_pool(by_strategy, regime=regime)

    assert len(pool) == 2
    for cand in pool:
        assert cand.metadata["regime_score"] == 85
        assert cand.metadata["regime_label"] == "BULL"


def test_build_unique_pool_without_regime_omits_keys():
    """regime=None 시 후보 metadata 에 regime_* 키 미주입 (기존 동작 유지)."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
    }
    pool = _build_unique_pool(by_strategy, regime=None)

    assert "regime_score" not in pool[0].metadata
    assert "regime_label" not in pool[0].metadata


def test_build_unique_pool_handles_partial_regime_dict():
    """current_regime 키 부재 시 score 기반으로 label 도출."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
    }
    regime = {"current_score": 25}

    pool = _build_unique_pool(by_strategy, regime=regime)

    assert pool[0].metadata["regime_score"] == 25
    # regime_label 은 score 기반으로 derive: 25 < 30 → BEAR
    assert pool[0].metadata["regime_label"] == "BEAR"
