"""
test_regret_scorer_new_factors.py — 신규 4축 regret_scorer 검증.

신규 4 factor (ensemble 제거, signal_freshness 추가):
  bull_reward (40%) + max_drawdown (20%) + dist_to_stop (15%) + signal_freshness (25%)
"""
from __future__ import annotations

import pandas as pd

from core.decision.aggregator import RankedCandidate
from core.decision.regret_scorer import (
    DEFAULT_WEIGHTS,
    compute_regret_scores,
)
from core.strategy_base import Candidate


def _make_ranked_with_metadata(
    ticker: str,
    *,
    reward_pct_t2: float = 5.0,
    risk_pct: float = 3.0,
    final_score: float = 50.0,
    current_offset_from_stop: float = 5.0,
    bars_since_trigger: int = 0,
) -> RankedCandidate:
    """간이 RankedCandidate 빌더 (metadata 포함)."""
    assert reward_pct_t2 > 0.5, "fixture requires reward_pct_t2 > 0.5"
    assert risk_pct > 0, "fixture requires risk_pct > 0"
    entry = 100.0
    stop_loss = entry - risk_pct
    target_2 = entry + reward_pct_t2
    target_1 = entry + reward_pct_t2 / 2
    current_price = stop_loss + current_offset_from_stop
    cand = Candidate(
        ticker=ticker,
        name=f"name_{ticker}",
        strategy="dummy",
        signal_date=pd.Timestamp("2026-05-04"),
        score=500.0,
        entry_price=entry,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        current_price=current_price,
        metadata={"bars_since_trigger": bars_since_trigger},
    )
    return RankedCandidate(candidate=cand, final_score=final_score)


def test_default_weights_has_four_factors_no_ensemble():
    """DEFAULT_WEIGHTS 는 4 factor: bull_reward / max_drawdown / dist_to_stop / signal_freshness.

    rr_focus 설정 (OOS 검증 2026-04-15~05-07, scripts/backtest_ranking_oos.py):
      signal_freshness=0.0 (live scan bars=0 고정 → 변별력 없음)
      dist_to_stop=0.30 강화, bull_reward=0.55.
    """
    w = DEFAULT_WEIGHTS
    assert w.bull_reward == 0.55
    assert w.max_drawdown == 0.15
    assert w.dist_to_stop == 0.30
    assert w.signal_freshness == 0.00
    assert abs((w.bull_reward + w.max_drawdown + w.dist_to_stop + w.signal_freshness) - 1.0) < 0.001


def test_regret_scorer_no_ensemble_factor():
    """regret_scorer 가 ensemble factor 를 호출하지 않음 (metric 없음)."""
    cands = [
        _make_ranked_with_metadata("A", reward_pct_t2=10.0),
        _make_ranked_with_metadata("B", reward_pct_t2=5.0),
    ]
    out = compute_regret_scores(cands)
    for rc in out:
        nm = rc.normalized_metrics
        # 신규 4 factor만 있어야 함
        assert "regret_bull_reward" in nm
        assert "regret_max_drawdown" in nm
        assert "regret_dist_to_stop" in nm
        assert "regret_signal_freshness" in nm
        # ensemble factor 는 없어야 함
        assert "regret_ensemble" not in nm


def test_regret_score_with_signal_freshness():
    """signal_freshness 가중치 0.0 → bars_since_trigger 값이 달라도 regret_score 동일.

    rr_focus 에서 freshness 가중치를 0.0으로 낮춘 후 동작 확인.
    다른 조건이 동일하면 FRESH/STALE 은 동점 (변별 불가 == 의도된 동작).
    """
    fresh = _make_ranked_with_metadata(
        "FRESH", reward_pct_t2=5.0, bars_since_trigger=0
    )
    stale = _make_ranked_with_metadata(
        "STALE", reward_pct_t2=5.0, bars_since_trigger=10
    )
    out = compute_regret_scores([fresh, stale])
    # freshness 가중치 0 → regret_score 동일 (변별력 없음)
    assert abs(
        out[0].normalized_metrics["regret_score"]
        - out[1].normalized_metrics["regret_score"]
    ) < 0.01


def test_signal_freshness_metric_is_in_range():
    """signal_freshness metric 은 0~1 범위."""
    cands = [
        _make_ranked_with_metadata("A", bars_since_trigger=0),
        _make_ranked_with_metadata("B", bars_since_trigger=5),
    ]
    out = compute_regret_scores(cands)
    for rc in out:
        fresh_val = rc.normalized_metrics["regret_signal_freshness"]
        assert 0.0 <= fresh_val <= 1.0


def test_four_factors_sum_equals_regret_score():
    """4축 가중합 × 100 == regret_score."""
    cands = [
        _make_ranked_with_metadata(f"T{i}", reward_pct_t2=1.0 + i * 2.0, bars_since_trigger=i)
        for i in range(3)
    ]
    out = compute_regret_scores(cands)
    w = DEFAULT_WEIGHTS
    for rc in out:
        nm = rc.normalized_metrics
        recomputed = (
            w.bull_reward * nm["regret_bull_reward"]
            + w.max_drawdown * nm["regret_max_drawdown"]
            + w.dist_to_stop * nm["regret_dist_to_stop"]
            + w.signal_freshness * nm["regret_signal_freshness"]
        ) * 100.0
        assert abs(recomputed - nm["regret_score"]) < 0.01, (
            f"{rc.candidate.ticker}: recomputed={recomputed:.4f}, "
            f"stored={nm['regret_score']:.4f}"
        )


def test_regret_score_still_zero_to_hundred():
    """regret_score 는 여전히 0~100 범위."""
    cands = [
        _make_ranked_with_metadata(f"T{i}", reward_pct_t2=1.0 + i * 2.0)
        for i in range(5)
    ]
    out = compute_regret_scores(cands)
    for rc in out:
        s = rc.normalized_metrics["regret_score"]
        assert 0.0 <= s <= 100.0


def test_single_candidate_still_zero_score():
    """single candidate 는 여전히 score=0."""
    only = _make_ranked_with_metadata("ONLY")
    out = compute_regret_scores([only])
    assert out[0].normalized_metrics["regret_score"] == 0.0
