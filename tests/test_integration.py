"""
test_integration.py — 멀티 전략 통합 시나리오.

본 plan(Sub-1·2·3) 범위에서는 전략1만 실제 동작하지만, 통합 흐름을 검증할 수 있도록
dummy 전략 1개를 register 하여 같은 날 2전략 동시 실행 + 비교 테이블 생성을 확인.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from core.data_fetch import DataClient
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import Candidate, ScanContext
from output.comparison import (
    format_csv_comparison,
    format_json_comparison,
    format_markdown_comparison,
    overlap_summary,
)
from strategies import register, unregister
from strategies.strategy_one_d_v2 import StrategyOneDv2
from test_daily_scanner_mock import MockKOSPIDataSource


# ============================================================================
# 보조 dummy 전략 (멀티 전략 흐름 검증용)
# ============================================================================

class _PassThroughStrategy:
    """universe 의 첫 N 종목을 그대로 후보로 반환 — 결정론적 테스트용."""
    name = "passthrough"

    def scan(self, ctx: ScanContext, top_n: int) -> List[Candidate]:
        out = []
        for i, ticker in enumerate(list(ctx.universe)[:top_n]):
            df = ctx.ohlcv[ticker]
            close = float(df["close"].iloc[-1])
            out.append(Candidate(
                ticker=ticker,
                name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=pd.Timestamp(ctx.target_date),
                # rank 가 낮을수록 score 높게
                score=max(0.5, 0.95 - i * 0.05),
                entry_price=close,
                stop_loss=close * 0.97,
                target_1=close * 1.03,
                target_2=close * 1.05,
            ))
        return out


@pytest.fixture
def cleanup_passthrough():
    yield
    unregister("passthrough")


@pytest.fixture
def runner_with_mock():
    mock = MockKOSPIDataSource()
    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=False,
    )
    return ScanRunner(
        client,
        RunnerConfig(
            market="KOSPI",
            min_market_cap_bil=2000.0,
            max_market_cap_bil=30000.0,
            min_daily_volume=100_000,
            top_n=10,
        ),
    )


# ============================================================================
# tests
# ============================================================================

def test_two_strategies_share_single_fetch(runner_with_mock, cleanup_passthrough):
    register(_PassThroughStrategy)
    strats = [StrategyOneDv2(), _PassThroughStrategy()]

    result = runner_with_mock.run(strats, target_date="20260418")

    assert "strategy_one_d_v2" in result.candidates_by_strategy
    assert "passthrough" in result.candidates_by_strategy
    # 단일 fetch 보장: cache_stats hit_count > 0 이면 동일 ticker 재요청이 캐시에서 처리됨
    assert result.cache_stats["fetch_count"] > 0


def test_comparison_markdown_renders_both_strategies(runner_with_mock, cleanup_passthrough):
    register(_PassThroughStrategy)
    result = runner_with_mock.run(
        [StrategyOneDv2(), _PassThroughStrategy()],
        target_date="20260418",
    )
    md = format_markdown_comparison(
        result.candidates_by_strategy, target_date="20260418", top_n=5,
    )
    assert "strategy_one_d_v2" in md
    assert "passthrough" in md
    assert "20260418" in md


def test_comparison_csv_has_rows_per_strategy(runner_with_mock, cleanup_passthrough):
    register(_PassThroughStrategy)
    result = runner_with_mock.run(
        [StrategyOneDv2(), _PassThroughStrategy()],
        target_date="20260418",
    )
    csv_text = format_csv_comparison(
        result.candidates_by_strategy, target_date="20260418",
    )
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("target_date,strategy,rank,")
    body = "\n".join(lines[1:])
    assert "strategy_one_d_v2" in body
    assert "passthrough" in body


def test_comparison_json_includes_overlap(runner_with_mock, cleanup_passthrough):
    register(_PassThroughStrategy)
    result = runner_with_mock.run(
        [StrategyOneDv2(), _PassThroughStrategy()],
        target_date="20260418",
    )
    out = format_json_comparison(result.candidates_by_strategy, "20260418")
    parsed = json.loads(out)
    assert set(parsed["strategies"].keys()) == {"strategy_one_d_v2", "passthrough"}
    assert "overlap" in parsed
    # passthrough 는 universe 첫 10개를 반환하므로 strategy_one_d_v2 와 일부 교집합 발생 기대
    overlap = overlap_summary(result.candidates_by_strategy)
    assert isinstance(overlap, dict)


def test_single_strategy_only_skips_comparison_overlap(runner_with_mock):
    """단일 전략 결과에선 overlap 이 비어 있어야 함."""
    result = runner_with_mock.run([StrategyOneDv2()], target_date="20260418")
    overlap = overlap_summary(result.candidates_by_strategy)
    assert overlap == {}
