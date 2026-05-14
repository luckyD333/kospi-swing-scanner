"""
test_regret_scorer.py — 비대칭 후회 점수 + 랭킹 검증.

"안 사면 가장 후회 남을 종목" 식별을 위한 4축 가중합:
  bull_reward(+) · ensemble(+) · max_drawdown(-) · dist_to_stop(+)
"""
from __future__ import annotations

import pandas as pd

from core.decision.aggregator import RankedCandidate
from core.decision.regret_scorer import (
    DEFAULT_WEIGHTS,
    RegretWeights,
    compute_regret_scores,
)
from core.strategy_base import Candidate


def _make_ranked(
    ticker: str,
    *,
    reward_pct_t2: float = 5.0,
    risk_pct: float = 3.0,
    final_score: float = 50.0,
    current_offset_from_stop: float = 5.0,
) -> RankedCandidate:
    """간이 RankedCandidate 빌더. entry=100, target/stop을 reward/risk로 환산."""
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
    )
    return RankedCandidate(candidate=cand, final_score=final_score)


# ---------------------------------------------------------------------------
# 핵심 로직
# ---------------------------------------------------------------------------

def test_bull_heavy_candidate_has_higher_regret_than_risk_heavy():
    """큰 상승 + 작은 리스크 = 안 사면 후회 큰 종목."""
    bull = _make_ranked("BULL", reward_pct_t2=15.0, risk_pct=2.0)
    risk = _make_ranked("RISKY", reward_pct_t2=3.0, risk_pct=8.0)
    out = compute_regret_scores([bull, risk])
    assert out[0].candidate.ticker == "BULL"
    assert out[1].candidate.ticker == "RISKY"
    assert (
        out[0].normalized_metrics["regret_score"]
        > out[1].normalized_metrics["regret_score"]
    )


def test_ensemble_scores_param_ignored():
    """ensemble_scores 매개변수는 하위호환용으로 무시됨 (신규 4축에서 제거)."""
    a = _make_ranked("A", reward_pct_t2=5.0, risk_pct=3.0)
    b = _make_ranked("B", reward_pct_t2=5.0, risk_pct=3.0)
    # ensemble_scores를 전달해도 점수에 영향 없음 (reward/risk/dist가 동일)
    out = compute_regret_scores(
        [a, b],
        ensemble_scores={"A": 3.0, "B": 1.0},
    )
    # reward/risk/dist가 동일 → 점수도 동일
    assert (
        out[0].normalized_metrics["regret_score"]
        == out[1].normalized_metrics["regret_score"]
    )


def test_rank_assignment_is_one_based_and_total_set():
    """rank 1..n + total = n."""
    cands = [
        _make_ranked("A", reward_pct_t2=10.0),
        _make_ranked("B", reward_pct_t2=5.0),
        _make_ranked("C", reward_pct_t2=2.0),
    ]
    out = compute_regret_scores(cands)
    ranks = [r.normalized_metrics["regret_rank"] for r in out]
    totals = [r.normalized_metrics["regret_total"] for r in out]
    assert ranks == [1, 2, 3]
    assert totals == [3, 3, 3]


def test_single_candidate_has_zero_score_rank_one():
    only = _make_ranked("ONLY")
    out = compute_regret_scores([only])
    assert len(out) == 1
    assert out[0].normalized_metrics["regret_score"] == 0.0
    assert out[0].normalized_metrics["regret_rank"] == 1
    assert out[0].normalized_metrics["regret_total"] == 1


def test_empty_input_returns_empty():
    assert compute_regret_scores([]) == []


def test_tie_breaks_by_final_score_then_ticker():
    """regret_score 동률 시 final_score 큰 순, 그 후 ticker 알파벳."""
    a = _make_ranked("B", reward_pct_t2=5.0, risk_pct=3.0, final_score=80.0)
    b = _make_ranked("A", reward_pct_t2=5.0, risk_pct=3.0, final_score=80.0)
    c = _make_ranked("C", reward_pct_t2=5.0, risk_pct=3.0, final_score=20.0)
    out = compute_regret_scores([a, b, c])
    tickers = [r.candidate.ticker for r in out]
    # C 는 final_score 작음 → 가장 마지막
    assert tickers[-1] == "C"
    # A 가 B 보다 앞 (final_score 동률 → 알파벳)
    assert tickers.index("A") < tickers.index("B")


def test_deterministic_output():
    """같은 입력 → 같은 출력."""
    es = {"T0": 2.0, "T1": 1.0, "T2": 1.5, "T3": 1.0, "T4": 1.0}
    cands1 = [_make_ranked(f"T{i}", reward_pct_t2=10.0 - i) for i in range(5)]
    cands2 = [_make_ranked(f"T{i}", reward_pct_t2=10.0 - i) for i in range(5)]
    r1 = compute_regret_scores(cands1, ensemble_scores=es)
    r2 = compute_regret_scores(cands2, ensemble_scores=es)
    assert [r.candidate.ticker for r in r1] == [r.candidate.ticker for r in r2]
    assert (
        [r.normalized_metrics["regret_score"] for r in r1]
        == [r.normalized_metrics["regret_score"] for r in r2]
    )


def test_score_is_in_zero_to_hundred_range():
    cands = [
        _make_ranked(f"T{i}", reward_pct_t2=1.0 + i * 2.0) for i in range(5)
    ]
    out = compute_regret_scores(cands)
    for rc in out:
        s = rc.normalized_metrics["regret_score"]
        assert 0.0 <= s <= 100.0


# ---------------------------------------------------------------------------
# Weights 노출
# ---------------------------------------------------------------------------

def test_default_weights_constants():
    """KOSDAQ Rank 1 4 factor 가중치 (OOS 검증 2026-05-15, scripts/optimize_market_separate.py)."""
    assert DEFAULT_WEIGHTS.bull_reward == 0.04
    assert DEFAULT_WEIGHTS.max_drawdown == 0.61
    assert DEFAULT_WEIGHTS.dist_to_stop == 0.31
    assert DEFAULT_WEIGHTS.signal_freshness == 0.04
    # ensemble factor 는 없음
    assert not hasattr(DEFAULT_WEIGHTS, "ensemble")


def test_custom_weights_override():
    """weight=1.0 만 주면 해당 축이 ranking 결정."""
    bull = _make_ranked("BULL", reward_pct_t2=15.0, risk_pct=8.0)
    safe = _make_ranked("SAFE", reward_pct_t2=3.0, risk_pct=2.0)

    # bull_reward 만 → BULL 1위 (reward 큼)
    weights_bull = RegretWeights(
        bull_reward=1.0, max_drawdown=0.0, dist_to_stop=0.0, signal_freshness=0.0,
    )
    out_bull = compute_regret_scores([bull, safe], weights=weights_bull)
    assert out_bull[0].candidate.ticker == "BULL"

    # max_drawdown 만 → SAFE 1위 (risk 작음)
    weights_dd = RegretWeights(
        bull_reward=0.0, max_drawdown=1.0, dist_to_stop=0.0, signal_freshness=0.0,
    )
    out_dd = compute_regret_scores([bull, safe], weights=weights_dd)
    assert out_dd[0].candidate.ticker == "SAFE"


# ---------------------------------------------------------------------------
# 4축 breakdown (UI factor breakdown 노출용)
# ---------------------------------------------------------------------------

def test_compute_regret_scores_stores_4_axis_breakdown():
    """신규 4축 개별 percentile rank 가 normalized_metrics 에 0~1 범위로 저장된다."""
    cands = [
        _make_ranked("A", reward_pct_t2=10.0, risk_pct=2.0),
        _make_ranked("B", reward_pct_t2=5.0, risk_pct=5.0),
        _make_ranked("C", reward_pct_t2=2.0, risk_pct=8.0),
    ]
    out = compute_regret_scores(cands)
    for rc in out:
        nm = rc.normalized_metrics
        assert "regret_bull_reward" in nm
        assert "regret_max_drawdown" in nm
        assert "regret_dist_to_stop" in nm
        assert "regret_signal_freshness" in nm
        # ensemble factor 는 없음
        assert "regret_ensemble" not in nm
        for k in ("regret_bull_reward", "regret_max_drawdown", "regret_dist_to_stop", "regret_signal_freshness"):
            assert 0.0 <= nm[k] <= 1.0, f"{rc.candidate.ticker}.{k}={nm[k]} out of [0,1]"


def test_4_axis_sum_equals_regret_score():
    """신규 4축 가중합 × 100 == regret_score (소수점 4자리 허용 오차).

    UI 의 contribution = weight × normalized 가 합산 regret_score 와 일치하려면
    max_drawdown 은 dd_norm(반전 후) 을 저장해야 한다.
    """
    cands = [
        _make_ranked(f"T{i}", reward_pct_t2=1.0 + i * 2.0, risk_pct=1.0 + i * 0.7)
        for i in range(5)
    ]
    out = compute_regret_scores(cands)
    w = DEFAULT_WEIGHTS
    for rc in out:
        nm = rc.normalized_metrics
        recomputed = (
            w.bull_reward  * nm["regret_bull_reward"]
            + w.max_drawdown * nm["regret_max_drawdown"]
            + w.dist_to_stop * nm["regret_dist_to_stop"]
            + w.signal_freshness * nm["regret_signal_freshness"]
        ) * 100.0
        assert abs(recomputed - nm["regret_score"]) < 0.01, (
            f"{rc.candidate.ticker}: recomputed={recomputed:.4f}, "
            f"stored={nm['regret_score']:.4f}"
        )


# ---------------------------------------------------------------------------
# composite_score: 3-score 합성 랭킹 + TF 배율
# ---------------------------------------------------------------------------

def _make_ranked_with_strategy(
    ticker: str,
    strategy_id: str,
    *,
    reward_pct_t2: float = 5.0,
    risk_pct: float = 3.0,
    final_score: float = 50.0,
) -> RankedCandidate:
    """timeframe 테스트용 — strategy_id 로 TF 배율 결정."""
    entry = 100.0
    stop_loss = entry - risk_pct
    target_2 = entry + reward_pct_t2
    target_1 = entry + reward_pct_t2 / 2
    cand = Candidate(
        ticker=ticker,
        name=f"name_{ticker}",
        strategy=strategy_id,
        signal_date=pd.Timestamp("2026-05-04"),
        score=500.0,
        entry_price=entry,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        current_price=entry,
        metadata={"bars_since_trigger": 0},
    )
    return RankedCandidate(candidate=cand, final_score=final_score)


def test_composite_score_lower_for_intraday():
    """1h 신호는 1D 신호보다 composite_score가 낮아야 함 (같은 조건에서 TF 배율 차이)."""
    rc_1d = _make_ranked_with_strategy("A", "strategy_one_d_v2")
    rc_1h = _make_ranked_with_strategy("B", "strategy_one_1h_v2")
    results = {r.candidate.ticker: r for r in compute_regret_scores([rc_1d, rc_1h])}
    score_1d = results["A"].normalized_metrics["composite_score"]
    score_1h = results["B"].normalized_metrics["composite_score"]
    assert score_1d > score_1h, f"1D({score_1d}) should > 1h({score_1h})"


def test_composite_uses_all_three_scores():
    """composite_score 가 regret_score + final_score + signal_rank 모두 반영함.

    KOSDAQ Rank 1 설정 (opp=0.20, pot=0.23, sig=0.57 + bull_reward=0.04):
    bull_reward 가중치가 0.04 로 낮아 reward 차이의 영향 미미.
    A: reward 낮음 + final_score=90, B: reward 높음 + final_score=10
    → high-final_score A 가 우선 (pot 23% > reward 차이 영향).
    """
    rc_a = _make_ranked("A", reward_pct_t2=2.0, final_score=90.0)
    rc_b = _make_ranked("B", reward_pct_t2=8.0, final_score=10.0)
    results = {r.candidate.ticker: r for r in compute_regret_scores([rc_a, rc_b])}
    assert "composite_score" in results["A"].normalized_metrics
    assert "composite_score" in results["B"].normalized_metrics
    # KOSDAQ Rank 1: bull_reward 가중치 작아 final_score 차이가 dominant → A > B
    assert (
        results["A"].normalized_metrics["composite_score"]
        > results["B"].normalized_metrics["composite_score"]
    ), (
        f"A({results['A'].normalized_metrics['composite_score']:.2f}) "
        f"should > B({results['B'].normalized_metrics['composite_score']:.2f})"
    )
