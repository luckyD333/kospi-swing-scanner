"""
tests/test_summary_format.py — Summary 포맷팅 테스트.
"""

from core.runner import RunResult
from output.formatters import format_run_summary, format_run_summary_json


def test_summary_renders_funnel_block():
    """기본 funnel 블록 렌더링."""
    result = RunResult(
        target_date="2026-04-30",
        universe_size=500,
        candidates_by_strategy={
            "strategy_one_d_v2": [],
        },
        errors={},
        funnel_stats={
            "universe_size": 500,
            "pre_cap_limit_size": 712,
            "universe_cap_limit": 500,
            "fetch_success": 475,
            "fetch_failed": 25,
            "short_bars": 18,
            "fetch_exceptions": {"TimeoutError": 4, "ConnectionError": 3},
            "source_counts": {"naver": 475},
        },
    )
    summary = format_run_summary(result, "KOSPI")

    # 핵심 라인 확인
    assert "📊 Scan Summary" in summary
    assert "2026-04-30" in summary
    assert "KOSPI" in summary
    assert "712 → top 500 적용 → 500 종목" in summary
    assert "475 종목" in summary
    assert "fetch 실패" in summary
    assert "7" in summary  # 4 + 3 exceptions
    assert "naver 475" in summary


def test_summary_handles_zero_universe():
    """유니버스 0 시 ZeroDivisionError 없음."""
    result = RunResult(
        target_date="2026-04-30",
        universe_size=0,
        funnel_stats={
            "universe_size": 0,
            "pre_cap_limit_size": 0,
            "universe_cap_limit": 500,
            "fetch_success": 0,
            "fetch_failed": 0,
            "short_bars": 0,
            "fetch_exceptions": {},
            "source_counts": {},
        },
    )
    summary = format_run_summary(result, "KOSPI")

    # 정상 렌더링, ZeroDivisionError 없음
    assert "📊 Scan Summary" in summary
    assert "0 종목" in summary


def test_summary_handles_no_strategies():
    """전략 결과 비어있어도 정상."""
    result = RunResult(
        target_date="2026-04-30",
        universe_size=100,
        candidates_by_strategy={},
        errors={},
        funnel_stats={
            "universe_size": 100,
            "pre_cap_limit_size": 100,
            "universe_cap_limit": 0,
            "fetch_success": 80,
            "fetch_failed": 20,
            "short_bars": 0,
            "fetch_exceptions": {},
            "source_counts": {"naver": 80},
        },
    )
    summary = format_run_summary(result, "KOSPI")

    assert "📊 Scan Summary" in summary
    assert "전략별 결과" in summary


def test_summary_handles_empty_funnel_dict():
    """빈 funnel_stats={} 안전 처리."""
    result = RunResult(
        target_date="2026-04-30",
        universe_size=100,
        funnel_stats={},  # 빈 dict (legacy/raw default)
    )
    summary = format_run_summary(result, "KOSPI")

    # 정상 렌더링, KeyError 없음
    assert "[funnel 미수집]" in summary or "Scan Summary" in summary


def test_summary_json_includes_funnel_and_strategies():
    """JSON 포맷에 funnel + strategies 포함."""
    result = RunResult(
        target_date="2026-04-30",
        universe_size=100,
        candidates_by_strategy={
            "strategy_one_d_v2": [],
        },
        errors={"strategy_two_cs_momentum": "KeyError('rsi')"},
        funnel_stats={
            "universe_size": 100,
            "fetch_success": 80,
            "fetch_failed": 20,
        },
    )
    summary_dict = format_run_summary_json(result, "KOSPI")

    assert isinstance(summary_dict, dict)
    assert "funnel" in summary_dict or "universe_size" in summary_dict
    assert "strategies" in summary_dict or "strategy_one_d_v2" in str(summary_dict)
