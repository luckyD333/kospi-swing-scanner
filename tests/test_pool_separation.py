"""test_pool_separation.py — 풀별 ranking + NOT_APPLICABLE 분기 (PR-B Step 4+5).

D2: ETN/ETF 가 STOCK 풀에서 PER/ROE 가산받는 결함 차단.
applies_to_pools 미매치 priority 는 NOT_APPLICABLE → 가중치 동적 정규화.
"""
from __future__ import annotations

import pandas as pd

from core.decision.aggregator import aggregate_candidates
from core.decision.config import Priority, WeightConfig
from core.strategy_base import Candidate


def _make_cand(ticker: str, score: float = 500.0, **meta) -> Candidate:
    return Candidate(
        ticker=ticker, name=f"name_{ticker}", strategy="dummy",
        signal_date=pd.Timestamp("2026-05-07"), score=score,
        entry_price=100.0, stop_loss=98.0, target_1=102.0, target_2=104.0,
        metadata=dict(meta),
    )


def _stock_etn_cfg() -> WeightConfig:
    """PER (STOCK 한정) + momentum (모든 풀) 으로 동적 정규화 검증."""
    return WeightConfig(
        priorities=[
            Priority(
                "per", 40.0, "lower_better", "PER",
                applies_to_pools=("STOCK",),
            ),
            Priority(
                "momentum_pct", 60.0, "higher_better", "모멘텀",
                applies_to_pools=("STOCK", "ETN_ETF", "OTHER"),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# 풀별 적용 priority 필터링
# ---------------------------------------------------------------------------

def test_stock_pool_uses_all_priorities():
    """STOCK 풀: per + momentum 둘 다 가산 (적용 priority 풀 전체)."""
    cfg = _stock_etn_cfg()
    cands = [
        _make_cand("A", per=10.0, momentum_pct=20.0),
        _make_cand("B", per=20.0, momentum_pct=10.0),
    ]
    ranked = aggregate_candidates(cands, cfg, pool="STOCK")
    by = {r.candidate.ticker: r for r in ranked}
    # per 와 momentum 둘 다 contribution
    assert by["A"].contributions["per"] > 0  # 낮은 PER → 가산 큼
    assert by["A"].contributions["momentum_pct"] > 0
    # 가중치 합 = 100 (정규화 안 일어남)
    assert abs(sum(by["A"].contributions.values()) - by["A"].final_score) < 0.01


def test_etn_etf_pool_excludes_per():
    """ETN_ETF 풀: per 는 NOT_APPLICABLE, momentum 만 가산. 가중치 동적 정규화 (60→100)."""
    cfg = _stock_etn_cfg()
    cands = [
        _make_cand("X", per=999.0, momentum_pct=20.0, product_type="ETN"),
        _make_cand("Y", per=999.0, momentum_pct=10.0, product_type="ETN"),
    ]
    ranked = aggregate_candidates(cands, cfg, pool="ETN_ETF")
    by = {r.candidate.ticker: r for r in ranked}
    # per contribution = 0, momentum 은 정규화된 가중치 (60→100)로 가산
    assert by["X"].contributions["per"] == 0.0
    assert by["X"].normalized_metrics["per_missing_reason"] == "NOT_APPLICABLE"
    # momentum 가중치 정규화: 원래 60 → active_total 60 → scale 100/60 → 100
    # X 는 momentum 1위 → contribution = 1.0 × 100 = 100
    assert by["X"].contributions["momentum_pct"] == 100.0
    assert by["X"].final_score == 100.0


def test_etn_etf_pool_per_value_does_not_affect_ranking():
    """ETN_ETF 풀에서 per 값이 변해도 ranking 영향 없음 (NOT_APPLICABLE 동일 처리)."""
    cfg = _stock_etn_cfg()
    cands_high_per = [
        _make_cand("A", per=999.0, momentum_pct=10.0, product_type="ETN"),
        _make_cand("B", per=1.0,   momentum_pct=20.0, product_type="ETN"),
    ]
    cands_low_per = [
        _make_cand("A", per=1.0,   momentum_pct=10.0, product_type="ETN"),
        _make_cand("B", per=999.0, momentum_pct=20.0, product_type="ETN"),
    ]
    r1 = aggregate_candidates(cands_high_per, cfg, pool="ETN_ETF")
    r2 = aggregate_candidates(cands_low_per, cfg, pool="ETN_ETF")
    # B 가 momentum 높아서 두 케이스 모두 1위
    assert r1[0].candidate.ticker == "B"
    assert r2[0].candidate.ticker == "B"
    # final_score 도 동일
    assert r1[0].final_score == r2[0].final_score


def test_default_pool_is_stock():
    """pool 인자 미지정 → STOCK default (backward compat)."""
    cfg = _stock_etn_cfg()
    cands = [_make_cand("A", per=10.0, momentum_pct=20.0)]
    ranked_default = aggregate_candidates(cands, cfg)
    ranked_explicit = aggregate_candidates(cands, cfg, pool="STOCK")
    assert ranked_default[0].final_score == ranked_explicit[0].final_score


# ---------------------------------------------------------------------------
# NOT_APPLICABLE 메타데이터
# ---------------------------------------------------------------------------

def test_not_applicable_recorded_in_normalized_metrics():
    """제외된 priority 의 missing_reason 은 NOT_APPLICABLE 로 기록."""
    cfg = _stock_etn_cfg()
    cands = [_make_cand("X", per=10.0, momentum_pct=15.0, product_type="ETN")]
    ranked = aggregate_candidates(cands, cfg, pool="ETN_ETF")
    rc = ranked[0]
    assert rc.normalized_metrics["per_missing_reason"] == "NOT_APPLICABLE"
    # NOT_APPLICABLE 은 NEGATIVE_EARNINGS / DATA_MISSING 보다 우선 (풀 결정이 절대)
    # — 가중치 자체가 0 이라 결측 사유 분기는 무관해짐


def test_active_priority_normalization_sums_to_100():
    """동적 정규화: active priorities 의 가중치 합이 정확히 100."""
    cfg = WeightConfig(
        priorities=[
            Priority("a", 30.0, "higher_better", "A", applies_to_pools=("STOCK",)),
            Priority("b", 30.0, "higher_better", "B", applies_to_pools=("STOCK", "ETN_ETF")),
            Priority("c", 40.0, "higher_better", "C", applies_to_pools=("STOCK", "ETN_ETF")),
        ],
    )
    cands = [_make_cand("X", a=1.0, b=1.0, c=1.0, product_type="ETN")]
    ranked = aggregate_candidates(cands, cfg, pool="ETN_ETF")
    rc = ranked[0]
    # a 는 NOT_APPLICABLE, b+c 만 활성 (원래 30+40=70, 정규화 후 100)
    # X 는 b/c 모두 단일 후보 → rank 1.0 → contribution = 가중치 그대로
    # 정규화: b 30 → 30/70×100 ≈ 42.857, c 40 → 40/70×100 ≈ 57.143
    assert rc.contributions["a"] == 0.0
    assert abs(rc.contributions["b"] - 42.857) < 0.01
    assert abs(rc.contributions["c"] - 57.143) < 0.01
    assert abs(rc.final_score - 100.0) < 0.01


def test_pool_with_no_active_priorities_returns_empty():
    """모든 priority 가 풀에 미적용이면 ranking 불가 (빈 리스트)."""
    cfg = WeightConfig(
        priorities=[
            Priority("per", 100.0, "lower_better", "PER", applies_to_pools=("STOCK",)),
        ],
    )
    cands = [_make_cand("X", per=10.0, product_type="REIT")]
    ranked = aggregate_candidates(cands, cfg, pool="OTHER")
    assert ranked == []
