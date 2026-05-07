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


def test_aggregate_handles_missing_metric_as_zero():
    """결측(None) 메트릭은 PR-A 정책상 가산 0 — 적자/누락 종목 가산 회피.

    이전에는 0.5 중립이었으나, ETF/적자 종목이 부당 가산받아 P0-1 이슈 유발.
    NOT_APPLICABLE (ETN/ETF) 분기는 PR-B 의 product_type 도입 후 가중치 정규화로 대체.

    higher_better (ROE) 로 검증 — lower_better 에선 valid 최하위가 0 으로 떨어져
    결측(0)과 동률이 되므로 분리 검증 어려움.
    """
    cfg = WeightConfig(
        priorities=[
            Priority("roe", 100.0, "higher_better", "고ROE"),
        ],
    )
    cands = [
        _make_cand("A", roe=20.0),   # 최고 (rank 2/2=1.0)
        _make_cand("B", roe=None),   # 결측 → 0.0 (가산 회피)
        _make_cand("C", roe=10.0),   # valid 최하위 (rank 1/2=0.5)
    ]
    ranked = aggregate_candidates(cands, cfg)
    by_ticker = {r.candidate.ticker: r for r in ranked}
    # B 는 결측(0.0) → C (valid 최하위 0.5) 보다 낮아야 함
    assert by_ticker["B"].final_score < by_ticker["C"].final_score
    # B 의 정규화 점수가 정확히 0.0
    assert by_ticker["B"].normalized_metrics["roe"] == 0.0


def test_aggregate_lower_better_missing_equals_worst():
    """lower_better 에서 결측은 valid 최악(rank=1.0 → 변환 후 0)과 동률 — 의도된 동작.

    lower_better 의 본질적 특성. 결측을 valid 최악보다 더 페널티하려면 별도 sentinel
    필요 — PR-A 범위 외. 결측 사유는 normalized_metrics 의 missing_reason 으로 식별.
    """
    cfg = WeightConfig(
        priorities=[Priority("per", 100.0, "lower_better", "저PER")],
    )
    cands = [
        _make_cand("A", per=10.0),
        _make_cand("B", per=None),
        _make_cand("C", per=20.0),
    ]
    ranked = aggregate_candidates(cands, cfg)
    by_ticker = {r.candidate.ticker: r for r in ranked}
    # A (rank 1/2=0.5 → 1-0.5=0.5) > B (결측=0) == C (rank 2/2=1.0 → 1-1.0=0)
    assert by_ticker["A"].final_score > by_ticker["B"].final_score
    assert by_ticker["B"].final_score == by_ticker["C"].final_score == 0.0
    # 단, B 만 missing_reason 기록
    assert by_ticker["B"].normalized_metrics.get("per_missing_reason") == "DATA_MISSING"
    assert "per_missing_reason" not in by_ticker["C"].normalized_metrics


def test_aggregate_records_missing_reason_data_missing():
    """단순 누락 후보 → metadata 의 '<key>_negative' 플래그 없으면 DATA_MISSING."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 100.0, "lower_better", "저PER"),
        ],
    )
    cands = [
        _make_cand("A", per=10.0),
        _make_cand("B", per=None),  # 단순 누락
    ]
    ranked = aggregate_candidates(cands, cfg)
    by_ticker = {r.candidate.ticker: r for r in ranked}
    assert by_ticker["B"].normalized_metrics.get("per_missing_reason") == "DATA_MISSING"
    # 정상 후보는 missing_reason 미기록
    assert "per_missing_reason" not in by_ticker["A"].normalized_metrics


def test_aggregate_records_missing_reason_negative_earnings():
    """적자 후보 → metadata['per_negative']=True → NEGATIVE_EARNINGS."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 100.0, "lower_better", "저PER"),
        ],
    )
    cands = [
        _make_cand("A", per=10.0),
        _make_cand("B", per=None, per_negative=True),   # 적자
        _make_cand("C", per=None, per_negative=False),  # 단순 누락
    ]
    ranked = aggregate_candidates(cands, cfg)
    by_ticker = {r.candidate.ticker: r for r in ranked}
    assert by_ticker["B"].normalized_metrics.get("per_missing_reason") == "NEGATIVE_EARNINGS"
    assert by_ticker["C"].normalized_metrics.get("per_missing_reason") == "DATA_MISSING"
    # 둘 다 점수는 0 (가산 회피)
    assert by_ticker["B"].normalized_metrics["per"] == 0.0
    assert by_ticker["C"].normalized_metrics["per"] == 0.0


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
