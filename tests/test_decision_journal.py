"""
test_decision_journal.py — Decision Journal markdown 자동 생성 검증.

SKILL.md "Decision Journal 메모" 템플릿 + RankedCandidate 자동 채움.
"""
from __future__ import annotations

import pandas as pd

from core.decision.aggregator import RankedCandidate
from core.decision.config import Priority, WeightConfig
from core.strategy_base import Candidate
from output.decision_journal import (
    format_decision_journal,
    format_ranking_report,
)


def _ranked_with_meta() -> RankedCandidate:
    cand = Candidate(
        ticker="005930",
        name="삼성전자",
        strategy="strategy_two_cross_sectional_momentum",
        signal_date=pd.Timestamp("2026-05-02"),
        score=720.0,
        entry_price=70000.0,
        stop_loss=68250.0,
        target_1=72100.0,
        target_2=73500.0,
        market_cap_bil=350_0000.0,
        volume_20d_avg=20_000_000.0,
        conditions_met={"momentum_top_quartile": True, "volume_above_avg": True},
        metadata={
            "per": 33.59, "roe": 10.85, "foreign_pct": 49.27,
            "naver_url": "https://finance.naver.com/item/main.naver?code=005930",
            "momentum_pct": 0.07,
            "percentile_rank": 0.92,
            "ensemble_count": 2,
            "market": "KOSPI",
        },
    )
    return RankedCandidate(
        candidate=cand,
        final_score=82.5,
        contributions={"per": 16.5, "roe": 25.0, "momentum_pct": 30.0,
                       "ensemble_count": 11.0},
        normalized_metrics={"per": 0.55, "roe": 0.83, "momentum_pct": 1.0,
                            "ensemble_count": 0.55, "max_regret": 1.5},
    )


def _weight_config() -> WeightConfig:
    return WeightConfig(
        priorities=[
            Priority("per", 30.0, "lower_better", "저PER"),
            Priority("roe", 30.0, "higher_better", "고ROE"),
            Priority("momentum_pct", 30.0, "higher_better", "모멘텀"),
            Priority("ensemble_count", 10.0, "higher_better", "다중 전략"),
        ],
        must_have=["per<50"],
    )


# ---------------------------------------------------------------------------
# Decision Journal (단일 후보)
# ---------------------------------------------------------------------------

def test_journal_includes_ticker_name_and_naver_link():
    rc = _ranked_with_meta()
    md = format_decision_journal(rc, _weight_config(), notes="확신 70%")
    assert "005930" in md
    assert "삼성전자" in md
    assert "https://finance.naver.com/item/main.naver?code=005930" in md


def test_journal_includes_fundamentals_section():
    rc = _ranked_with_meta()
    md = format_decision_journal(rc, _weight_config())
    assert "PER" in md
    assert "33.59" in md
    assert "ROE" in md
    assert "10.85" in md
    assert "외국인비율" in md or "외인" in md


def test_journal_includes_signal_section():
    """전략 시그널 (momentum_pct, conditions_met) 자동 채움."""
    rc = _ranked_with_meta()
    md = format_decision_journal(rc, _weight_config())
    assert "momentum_top_quartile" in md or "모멘텀" in md
    assert "전략" in md or "strategy" in md


def test_journal_includes_weights_and_scores():
    """가중치 + 항목별 기여도 표시."""
    rc = _ranked_with_meta()
    md = format_decision_journal(rc, _weight_config())
    assert "82.5" in md   # final_score
    assert "30.0" in md   # 가중치
    # 항목별 기여도 어느 하나는 표시
    assert "30.0" in md or "25.0" in md


def test_journal_target_probabilities_rough_estimate():
    """target_1/target_2 도달 확률 추정값 (R:R 기반) 포함."""
    rc = _ranked_with_meta()
    md = format_decision_journal(rc, _weight_config())
    assert "도달" in md or "확률" in md or "%" in md


def test_journal_has_empty_blanks_for_user_input():
    """감정 상태/확신 수준은 사용자 후속 입력용 빈 칸으로 생성."""
    rc = _ranked_with_meta()
    md = format_decision_journal(rc, _weight_config())
    assert "감정" in md or "확신" in md


def test_journal_appends_user_notes_when_provided():
    """notes 인자 → 메모 영역에 추가."""
    rc = _ranked_with_meta()
    md = format_decision_journal(rc, _weight_config(), notes="중기 보유 의향, 70%")
    assert "중기 보유 의향, 70%" in md


def test_journal_handles_missing_fundamentals():
    """metadata에 펀더멘털 없어도 KeyError 없이 N/A 출력."""
    cand = Candidate(
        ticker="000020", name="동화약품", strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-02"),
        score=600.0,
        entry_price=10000.0, stop_loss=9700.0,
        target_1=10300.0, target_2=10500.0,
        metadata={
            "naver_url": "https://finance.naver.com/item/main.naver?code=000020",
        },
    )
    rc = RankedCandidate(
        candidate=cand, final_score=50.0,
        contributions={}, normalized_metrics={},
    )
    md = format_decision_journal(rc, _weight_config())
    assert "동화약품" in md
    assert "N/A" in md or "-" in md  # 결측 표시


# ---------------------------------------------------------------------------
# Ranking Report (Top N)
# ---------------------------------------------------------------------------

def test_ranking_report_lists_top_n():
    rcs = [_ranked_with_meta() for _ in range(3)]
    # 다른 ticker로 변경
    for i, rc in enumerate(rcs):
        rc.candidate.ticker = f"00593{i}"
        rc.final_score = 80.0 - i * 5
    md = format_ranking_report(rcs, target_date="2026-05-02", top_n=3,
                               weight_config=_weight_config())
    assert "005930" in md
    assert "005931" in md
    assert "005932" in md
    assert "Top 3" in md or "상위 3" in md


def test_ranking_report_truncates_to_top_n():
    rcs = [_ranked_with_meta() for _ in range(5)]
    for i, rc in enumerate(rcs):
        rc.candidate.ticker = f"00593{i}"
        rc.final_score = 80.0 - i * 5
    md = format_ranking_report(rcs, target_date="2026-05-02", top_n=2,
                               weight_config=_weight_config())
    # top_n=2 이므로 005932/3/4는 표시 안 됨
    assert "005930" in md
    assert "005931" in md
    assert "005932" not in md


def test_ranking_report_empty_candidates():
    md = format_ranking_report([], target_date="2026-05-02", top_n=5,
                               weight_config=_weight_config())
    assert "후보 없음" in md or "없어요" in md
