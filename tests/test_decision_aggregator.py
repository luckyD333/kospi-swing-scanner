"""
test_decision_aggregator.py — 후보 통합 + 가중 점수 산출 검증.

Phase 2 의사결정 엔진의 핵심: WeightConfig + 후보 metrics → 정규화 점수 + ranking.
"""
from __future__ import annotations

import pandas as pd

from core.decision.aggregator import RankedCandidate, aggregate_candidates
from core.decision.config import Priority, WeightConfig
from core.strategy_base import Candidate


def _make_cand(ticker: str, score: float = 500.0, **meta) -> Candidate:
    """meta로 metadata 주입 가능."""
    return Candidate(
        ticker=ticker,
        name=f"name_{ticker}",
        strategy="dummy",
        signal_date=pd.Timestamp("2026-05-02"),
        score=score,
        entry_price=100.0,
        stop_loss=98.0,
        target_1=102.0,
        target_2=104.0,
        metadata=dict(meta),
    )


# ---------------------------------------------------------------------------
# 정규화 + 가중 점수 산출
# ---------------------------------------------------------------------------

def test_aggregate_returns_ranked_candidates_sorted_by_final_score():
    """final_score 내림차순 정렬."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 100.0, "lower_better", "저PER"),
        ],
    )
    cands = [
        _make_cand("A", per=10.0),
        _make_cand("B", per=30.0),
        _make_cand("C", per=20.0),
    ]
    ranked = aggregate_candidates(cands, cfg)
    # per 가 낮을수록 좋음 → A 가 1위, B 가 꼴찌
    assert [r.candidate.ticker for r in ranked] == ["A", "C", "B"]
    assert ranked[0].final_score > ranked[-1].final_score


def test_aggregate_weighted_sum_of_normalized_scores():
    """여러 priority 가중 합산."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 50.0, "lower_better", "저PER"),
            Priority("roe", 50.0, "higher_better", "고ROE"),
        ],
    )
    cands = [
        _make_cand("A", per=10.0, roe=20.0),  # 둘 다 최고 → 최고 점수
        _make_cand("B", per=30.0, roe=5.0),   # 둘 다 최악 → 최저 점수
        _make_cand("C", per=20.0, roe=12.5),  # 중간
    ]
    ranked = aggregate_candidates(cands, cfg)
    by_ticker = {r.candidate.ticker: r for r in ranked}
    assert by_ticker["A"].final_score > by_ticker["C"].final_score
    assert by_ticker["C"].final_score > by_ticker["B"].final_score


def test_aggregate_records_per_priority_contribution():
    """RankedCandidate 에 항목별 정규화 점수 + 기여도 보존."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 60.0, "lower_better", "저PER"),
            Priority("roe", 40.0, "higher_better", "고ROE"),
        ],
    )
    cands = [
        _make_cand("A", per=10.0, roe=20.0),
        _make_cand("B", per=30.0, roe=5.0),
    ]
    ranked = aggregate_candidates(cands, cfg)
    top = ranked[0]
    assert "per" in top.contributions
    assert "roe" in top.contributions
    # 기여도 합이 final_score와 일치 (반올림 오차 허용)
    total = sum(top.contributions.values())
    assert abs(total - top.final_score) < 0.01


def test_aggregate_must_have_excludes_failing_candidates():
    """must_have 미충족 후보는 결과에서 제외."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 100.0, "lower_better", "저PER"),
        ],
        must_have=["roe>=10"],
    )
    cands = [
        _make_cand("A", per=10.0, roe=15.0),  # roe 통과
        _make_cand("B", per=20.0, roe=5.0),   # roe 미달 — 탈락
    ]
    ranked = aggregate_candidates(cands, cfg)
    tickers = [r.candidate.ticker for r in ranked]
    assert "A" in tickers
    assert "B" not in tickers


def test_aggregate_handles_missing_metric_as_worst():
    """priority 메트릭이 None 인 후보는 해당 항목 0점 처리."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 100.0, "lower_better", "저PER"),
        ],
    )
    cands = [
        _make_cand("A", per=10.0),
        _make_cand("B", per=None),  # 결측
        _make_cand("C", per=20.0),
    ]
    ranked = aggregate_candidates(cands, cfg)
    # B 는 결측이라 가장 낮은 점수
    by_ticker = {r.candidate.ticker: r for r in ranked}
    assert by_ticker["B"].final_score < by_ticker["A"].final_score
    assert by_ticker["B"].final_score <= by_ticker["C"].final_score


def test_aggregate_uses_score_as_metric_key():
    """priority key='score' → Candidate.score 직접 참조 (metadata 외)."""
    cfg = WeightConfig(
        priorities=[
            Priority("score", 100.0, "higher_better", "전략점수"),
        ],
    )
    cands = [
        _make_cand("A", score=900.0),
        _make_cand("B", score=500.0),
    ]
    ranked = aggregate_candidates(cands, cfg)
    assert ranked[0].candidate.ticker == "A"


def test_aggregate_deterministic():
    """같은 입력 → 같은 출력 (ranking 결정론)."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 50.0, "lower_better", "저PER"),
            Priority("roe", 50.0, "higher_better", "고ROE"),
        ],
    )
    cands = [_make_cand(f"T{i}", per=10.0 + i, roe=20.0 - i) for i in range(5)]
    r1 = aggregate_candidates(cands, cfg)
    r2 = aggregate_candidates(cands, cfg)
    assert [r.candidate.ticker for r in r1] == [r.candidate.ticker for r in r2]
    assert [r.final_score for r in r1] == [r.final_score for r in r2]


def test_aggregate_empty_candidates():
    cfg = WeightConfig(
        priorities=[Priority("per", 100.0, "lower_better", "저PER")],
    )
    assert aggregate_candidates([], cfg) == []


def test_ranked_candidate_dataclass_fields():
    """RankedCandidate 필드 안정성."""
    cand = _make_cand("A", per=10.0)
    cfg = WeightConfig(
        priorities=[Priority("per", 100.0, "lower_better", "저PER")],
    )
    ranked = aggregate_candidates([cand], cfg)
    rc = ranked[0]
    assert isinstance(rc, RankedCandidate)
    assert rc.candidate.ticker == "A"
    assert isinstance(rc.final_score, float)
    assert isinstance(rc.contributions, dict)
    assert "per" in rc.contributions


# ---------------------------------------------------------------------------
# PR #1 metric bridge 통합 (PR #2)
# ---------------------------------------------------------------------------

def test_aggregate_with_rr_ratio_priority():
    """PR #1 metric bridge 의 rr_ratio metadata 를 priority key 로 사용."""
    cfg = WeightConfig(
        priorities=[
            Priority("rr_ratio", 100.0, "higher_better", "손익비"),
        ],
    )
    cands = [
        _make_cand("A", rr_ratio=2.5),  # sweet spot 위
        _make_cand("B", rr_ratio=1.5),  # below
        _make_cand("C", rr_ratio=2.2),  # sweet spot
    ]
    ranked = aggregate_candidates(cands, cfg)
    # rr_ratio 가 큰 A 가 1위
    assert ranked[0].candidate.ticker == "A"
    assert ranked[-1].candidate.ticker == "B"


def test_aggregate_must_have_excludes_by_source_strategy():
    """must_have 의 string DSL 로 특정 전략 후보 배제 (PR #1 source_strategy 활용)."""
    cfg = WeightConfig(
        priorities=[Priority("score", 100.0, "higher_better", "점수")],
        must_have=["source_strategy!=closing_strength_top"],
    )
    cands = [
        _make_cand("A", score=900.0),
        _make_cand("B", score=500.0),
    ]
    cands[0].metadata["source_strategy"] = "gap_up_momentum_top"
    cands[1].metadata["source_strategy"] = "closing_strength_top"
    ranked = aggregate_candidates(cands, cfg)
    tickers = [r.candidate.ticker for r in ranked]
    assert "A" in tickers
    assert "B" not in tickers
