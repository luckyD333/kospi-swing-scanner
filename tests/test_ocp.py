"""
test_ocp.py — Open-Closed Principle 검증.

신규 전략 추가가 기존 코드 수정 0줄로 가능한지 확인:
  - register() 호출만으로 REGISTRY 에 노출
  - ScanRunner 가 등록된 전략을 그대로 실행 가능
  - unregister 로 정리 가능
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import Candidate, ScanContext
from strategies import REGISTRY, available, register, unregister

# ============================================================================
# Dummy strategy — 본 파일 외 어디에도 변경 없이 등록만으로 동작해야 함
# ============================================================================

class DummyConstantStrategy:
    """모든 ticker 에 고정 score 0.42 부여하는 토이 전략."""
    name = "dummy_constant"

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        out = []
        for ticker in list(ctx.universe)[:top_n]:
            out.append(Candidate(
                ticker=ticker,
                name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=pd.Timestamp(ctx.target_date),
                score=0.42,
                entry_price=100.0,
                stop_loss=98.0,
                target_1=103.0,
                target_2=105.0,
            ))
        return out


# ============================================================================
# Mock universe (network-free)
# ============================================================================

class _StubSource(DailyDataSource):
    name = "ocp_stub"

    def get_tickers(self, market, target_date):
        return ["AAA", "BBB", "CCC"]

    def get_ticker_name(self, ticker):
        return f"name_{ticker}"

    def get_ohlcv(self, ticker, start, end):
        return pd.DataFrame(
            {"open": [10.0]*40, "high": [11.0]*40, "low": [9.0]*40,
             "close": [10.0]*40, "volume": [200_000]*40},
            index=pd.date_range("2026-01-01", periods=40, freq="D"),
        )

    def get_market_cap(self, market, target_date):
        rows = {t: {"시가총액": 5_000 * 1e8, "종목명": f"name_{t}"}
                for t in ["AAA", "BBB", "CCC"]}
        return pd.DataFrame(rows).T


# ============================================================================
# tests
# ============================================================================

@pytest.fixture
def cleanup_dummy():
    """테스트 격리: dummy 등록 → 실행 → 해제."""
    yield
    unregister("dummy_constant")


def test_register_makes_strategy_available(cleanup_dummy):
    assert "dummy_constant" not in available()
    register(DummyConstantStrategy)
    assert "dummy_constant" in available()
    assert REGISTRY["dummy_constant"] is DummyConstantStrategy


def test_runner_executes_registered_dummy_strategy(cleanup_dummy):
    register(DummyConstantStrategy)

    src = _StubSource()
    client = DataClient(
        ticker_list_sources=[src], ohlcv_sources=[src],
    )
    runner = ScanRunner(client, RunnerConfig(top_n=10, lookback_days=30))

    cls = REGISTRY["dummy_constant"]
    result = runner.run([cls()], target_date="20260418")

    assert "dummy_constant" in result.candidates_by_strategy
    out = result.candidates_by_strategy["dummy_constant"]
    assert {c.ticker for c in out} == {"AAA", "BBB", "CCC"}
    assert all(c.score == pytest.approx(0.42) for c in out)


def test_strategy_one_still_present_after_dummy_register(cleanup_dummy):
    """기존 전략은 신규 등록에 영향받지 않음."""
    register(DummyConstantStrategy)
    assert "strategy_one_d_v2" in available()


def test_register_rejects_invalid_class():
    class NoName:
        def scan(self, ctx, top_n):
            return []

    with pytest.raises(ValueError):
        register(NoName)


def test_register_rejects_missing_scan():
    class NoScan:
        name = "no_scan"

    with pytest.raises(ValueError):
        register(NoScan)


def test_unregister_removes_strategy():
    register(DummyConstantStrategy)
    assert "dummy_constant" in available()
    unregister("dummy_constant")
    assert "dummy_constant" not in available()
