"""
test_core_runner.py — ScanRunner 통합 검증.

핵심 시나리오:
  - 같은 ticker 가 여러 전략에 공유되어도 fetch 1회만 발생 (단일 fetch 보장)
  - 한 전략이 예외 던져도 다른 전략은 정상 수행 (격리)
  - 전략별 결과가 dict 로 반환 + 에러는 RunResult.errors 에 기록
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd
import pytest

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import Candidate, ScanContext


# ============================================================================
# fixtures
# ============================================================================

class _CountingSource(DailyDataSource):
    name = "counting"

    def __init__(self, tickers: List[str], caps: Dict[str, float]):
        self._tickers = tickers
        self._caps = caps
        self.ohlcv_call_count = 0

    def get_tickers(self, market, target_date):
        return list(self._tickers)

    def get_ticker_name(self, ticker):
        return ticker

    def get_ohlcv(self, ticker, start, end):
        self.ohlcv_call_count += 1
        # 30+봉 (runner 의 최소 길이 검증 통과)
        return pd.DataFrame(
            {"open": [100.0]*40, "high": [101.0]*40, "low": [99.0]*40,
             "close": [100.0]*40, "volume": [1_000_000]*40},
            index=pd.date_range("2026-01-01", periods=40, freq="D"),
        )

    def get_market_cap(self, market, target_date):
        rows = {t: {"시가총액": self._caps[t], "종목명": t} for t in self._tickers}
        return pd.DataFrame(rows).T


class _FakeStrategy:
    """결정론적 fake — 모든 ticker 에 동일 score 반환."""

    def __init__(self, name: str, score: float = 0.7, fail: bool = False):
        self.name = name
        self.score = score
        self.fail = fail
        self.calls = 0

    def scan(self, ctx: ScanContext, top_n: int) -> List[Candidate]:
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} boom")
        out = []
        for ticker in ctx.universe[:top_n]:
            out.append(Candidate(
                ticker=ticker,
                name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=pd.Timestamp(ctx.target_date),
                score=self.score,
                entry_price=100.0,
                stop_loss=97.5,
                target_1=103.0,
                target_2=105.0,
            ))
        return out


# ============================================================================
# tests
# ============================================================================

def _make_runner_with_n_tickers(n: int):
    tickers = [f"{i:06d}" for i in range(n)]
    caps = {t: 5_000 * 1e8 for t in tickers}  # 모두 5,000억 — 필터 통과
    src = _CountingSource(tickers, caps)
    client = DataClient(
        ticker_list_sources=[src],
        ohlcv_sources=[src],
        use_krx_for_universe=False,
    )
    runner = ScanRunner(client, RunnerConfig(top_n=10, lookback_days=30))
    return runner, src


def test_single_fetch_shared_across_strategies():
    """3개 전략이 동일 universe 를 받아도 fetch 는 ticker 당 1회."""
    runner, src = _make_runner_with_n_tickers(5)
    strats = [
        _FakeStrategy("s1", score=0.6),
        _FakeStrategy("s2", score=0.7),
        _FakeStrategy("s3", score=0.8),
    ]
    result = runner.run(strats, target_date="20260418")

    # 5종목 × 1회 = 5
    assert src.ohlcv_call_count == 5
    # 3 전략 모두 같은 universe 보였음
    for s in strats:
        assert s.calls == 1
        assert len(result.candidates_by_strategy[s.name]) == 5


def test_strategy_isolation_one_fails_others_succeed():
    runner, src = _make_runner_with_n_tickers(3)
    strats = [
        _FakeStrategy("ok", score=0.5),
        _FakeStrategy("bad", fail=True),
        _FakeStrategy("ok2", score=0.6),
    ]
    result = runner.run(strats, target_date="20260418")

    assert "ok" in result.candidates_by_strategy
    assert "ok2" in result.candidates_by_strategy
    assert "bad" in result.errors
    assert "boom" in result.errors["bad"]


def test_run_result_metadata():
    runner, src = _make_runner_with_n_tickers(4)
    result = runner.run([_FakeStrategy("s")], target_date="20260418")
    assert result.target_date == "20260418"
    assert result.universe_size == 4
    # cache_stats 노출
    assert "fetch_count" in result.cache_stats
    assert result.cache_stats["fetch_count"] == 4


def test_run_no_strategies_returns_empty_dict():
    runner, _ = _make_runner_with_n_tickers(2)
    result = runner.run([], target_date="20260418")
    assert result.candidates_by_strategy == {}
    assert result.errors == {}
