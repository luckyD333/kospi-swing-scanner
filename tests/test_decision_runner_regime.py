"""tests/test_decision_runner_regime.py — _build_unique_pool 의 regime metadata 주입 회귀."""
from __future__ import annotations

import pandas as pd

from core.decision.config import Priority, WeightConfig
from core.decision.runner import _build_unique_pool
from core.strategy_base import Candidate


def _mk_weight_config() -> WeightConfig:
    """검증 통과용 최소 WeightConfig — 정적 strategy_weights 동작 (regime 매트릭스 없음)."""
    return WeightConfig(
        priorities=[
            Priority(key="rr_ratio", weight=100.0,
                     direction="higher_better", label="RR"),
        ],
        must_have=[],
        strategy_weights={},
    )


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

    pool = _build_unique_pool(by_strategy, weight_config=_mk_weight_config(), regime=regime)

    assert len(pool) == 2
    for cand in pool:
        assert cand.metadata["regime_score"] == 85
        assert cand.metadata["regime_label"] == "BULL"


def test_build_unique_pool_without_regime_omits_keys():
    """regime=None 시 후보 metadata 에 regime_* 키 미주입 (기존 동작 유지)."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
    }
    pool = _build_unique_pool(by_strategy, weight_config=_mk_weight_config(), regime=None)

    assert "regime_score" not in pool[0].metadata
    assert "regime_label" not in pool[0].metadata


def test_build_unique_pool_handles_partial_regime_dict():
    """current_regime 키 부재 시 score 기반으로 label 도출."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
    }
    regime = {"current_score": 25}

    pool = _build_unique_pool(by_strategy, weight_config=_mk_weight_config(), regime=regime)

    assert pool[0].metadata["regime_score"] == 25
    # regime_label 은 score 기반으로 derive: 25 < 30 → BEAR
    assert pool[0].metadata["regime_label"] == "BEAR"


def test_run_decide_ranking_passes_regime_from_cache_root(tmp_path, monkeypatch):
    """cache_root 인자로 regime_analysis.json 로드해 후보에 주입."""
    from core.decision import runner as r

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    (cache_root / "regime_analysis.json").write_text(
        '{"current_score": 80, "current_regime": "BULL", "history": [], '
        '"bull_state_mean_return": 0.01, "bear_state_mean_return": -0.01, '
        '"n_tickers": 100, "n_days": 30}'
    )
    scan_root = tmp_path / "scan"
    scan_root.mkdir()

    captured: dict = {}

    def fake_pool(by_strategy, weight_config=None, regime=None, fng_label=None):
        captured["regime"] = regime
        captured["fng_label"] = fng_label
        return []

    monkeypatch.setattr(r, "load_candidates_from_manifest", lambda _p: {})
    monkeypatch.setattr(r, "_build_unique_pool", fake_pool)
    monkeypatch.setattr(r, "aggregate_candidates", lambda _p, _c: [])

    cfg = _mk_weight_config()
    r.run_decide_ranking(
        scan_root=scan_root,
        target_date="20260503",
        top_n=5,
        weight_config=cfg,
        cache_root=cache_root,
    )

    assert captured["regime"] is not None
    assert captured["regime"]["current_score"] == 80
    assert captured["regime"]["current_regime"] == "BULL"
