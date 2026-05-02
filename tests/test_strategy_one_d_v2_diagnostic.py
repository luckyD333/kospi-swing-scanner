"""
Task 1: strategy_one_d_v2 무후보 분류 진단.

후보가 0개일 때 funnel_stats 를 보고 다음 4 분류 중 하나로 판정한다:
  - NORMAL_NO_SIGNAL: 정상 작동 후 시그널 없음 (5조건 AND 미충족)
  - UNIVERSE_TOO_SMALL: 유니버스 자체가 작음 (시총 필터 과다)
  - FETCH_FAILURE: 네트워크/API 장애로 fetch 실패율 과다
  - (이상 3) 조건별 일관 탈락은 condition_failures Counter 수치 검토로 식별
"""
from __future__ import annotations

from core.runner import RunResult, _classify_zero_candidate


def test_classify_zero_candidate_normal():
    r = RunResult(
        target_date="20260430",
        universe_size=200,
        funnel_stats={
            "fetch_success": 150,
            "short_bars": 5,
            "fetch_failed": 10,
            "condition_failures": {"double_bottom": 120, "engulfing": 30},
        },
    )
    assert _classify_zero_candidate(r) == "NORMAL_NO_SIGNAL"


def test_classify_zero_candidate_universe_too_small():
    r = RunResult(
        target_date="20260430",
        universe_size=200,
        funnel_stats={
            "fetch_success": 40,
            "short_bars": 5,
            "fetch_failed": 10,
            "condition_failures": {},
        },
    )
    assert _classify_zero_candidate(r) == "UNIVERSE_TOO_SMALL"


def test_classify_zero_candidate_fetch_failure():
    r = RunResult(
        target_date="20260430",
        universe_size=200,
        funnel_stats={
            "fetch_success": 50,
            "short_bars": 5,
            "fetch_failed": 150,
            "condition_failures": {},
        },
    )
    assert _classify_zero_candidate(r) == "FETCH_FAILURE"
