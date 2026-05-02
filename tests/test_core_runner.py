"""
test_core_runner.py — ScanRunner 통합 검증.

핵심 시나리오:
  - 같은 ticker 가 여러 전략에 공유되어도 fetch 1회만 발생 (단일 fetch 보장)
  - 한 전략이 예외 던져도 다른 전략은 정상 수행 (격리)
  - 전략별 결과가 dict 로 반환 + 에러는 RunResult.errors 에 기록
"""
from __future__ import annotations


import pandas as pd

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.runner import RunnerConfig, RunResult, ScanRunner
from core.strategy_base import Candidate, ScanContext

# ============================================================================
# fixtures
# ============================================================================

class _CountingSource(DailyDataSource):
    name = "counting"

    def __init__(self, tickers: list[str], caps: dict[str, float]):
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

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
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


def test_funnel_stats_default_values():
    """RunResult의 funnel_stats 초기값은 빈 dict."""
    result = RunResult(target_date="20260418", universe_size=0)
    assert result.funnel_stats == {}


def test_run_records_funnel_counts():
    """fetch 성공/실패/short_bars 카운트 검증."""
    class _PartialSource(DailyDataSource):
        """일부 ticker는 성공, 일부는 empty 반환."""
        name = "partial"

        def __init__(self):
            self.calls = 0

        def get_tickers(self, market, target_date):
            return ["OK1", "EMPTY", "SHORT", "OK2"]

        def get_ticker_name(self, ticker):
            return ticker

        def get_ohlcv(self, ticker, start, end):
            self.calls += 1
            if ticker == "OK1" or ticker == "OK2":
                return pd.DataFrame(
                    {"close": [100.0]*40},
                    index=pd.date_range("2026-01-01", periods=40, freq="D"),
                )
            elif ticker == "EMPTY":
                return pd.DataFrame()
            elif ticker == "SHORT":
                return pd.DataFrame(
                    {"close": [100.0]*20},
                    index=pd.date_range("2026-01-01", periods=20, freq="D"),
                )
            return pd.DataFrame()

        def get_market_cap(self, market, target_date):
            caps = {t: 5_000 * 1e8 for t in ["OK1", "EMPTY", "SHORT", "OK2"]}
            return pd.DataFrame(
                {t: {"시가총액": caps[t], "종목명": t} for t in caps}
            ).T

    src = _PartialSource()
    client = DataClient(
        ticker_list_sources=[src],
        ohlcv_sources=[src],
    )
    runner = ScanRunner(client, RunnerConfig(top_n=10))
    result = runner.run([_FakeStrategy("s")], target_date="20260418")

    assert result.funnel_stats["fetch_success"] == 2
    assert result.funnel_stats["fetch_failed"] == 1  # empty
    assert result.funnel_stats["short_bars"] == 1
    assert result.funnel_stats["universe_size"] == 4


def test_run_distinguishes_empty_vs_short_bars():
    """empty df와 short df가 다른 카운터로 들어가는지 검증."""
    class _MixedSource(DailyDataSource):
        name = "mixed"

        def get_tickers(self, market, target_date):
            return ["EMPTY", "SHORT25"]

        def get_ticker_name(self, ticker):
            return ticker

        def get_ohlcv(self, ticker, start, end):
            if ticker == "EMPTY":
                return pd.DataFrame()
            else:  # SHORT25
                return pd.DataFrame(
                    {"close": [100.0]*25},
                    index=pd.date_range("2026-01-01", periods=25, freq="D"),
                )

        def get_market_cap(self, market, target_date):
            return pd.DataFrame(
                {
                    "EMPTY": {"시가총액": 5_000 * 1e8, "종목명": "EMPTY"},
                    "SHORT25": {"시가총액": 5_000 * 1e8, "종목명": "SHORT25"},
                }
            ).T

    src = _MixedSource()
    client = DataClient(
        ticker_list_sources=[src],
        ohlcv_sources=[src],
    )
    runner = ScanRunner(client, RunnerConfig(top_n=10))
    result = runner.run([_FakeStrategy("s")], target_date="20260418")

    assert result.funnel_stats["fetch_failed"] == 1  # empty
    assert result.funnel_stats["short_bars"] == 1
    assert result.funnel_stats["fetch_success"] == 0


def test_run_records_exception_types():
    """Exception 타입별 카운트 기록."""
    class _ExceptionSource(DailyDataSource):
        name = "exception"

        def get_tickers(self, market, target_date):
            return ["TIMEOUT", "CONNECTION"]

        def get_ticker_name(self, ticker):
            return ticker

        def get_ohlcv(self, ticker, start, end):
            if ticker == "TIMEOUT":
                raise TimeoutError("timeout")
            else:
                raise ConnectionError("conn")

        def get_market_cap(self, market, target_date):
            return pd.DataFrame(
                {
                    "TIMEOUT": {"시가총액": 5_000 * 1e8, "종목명": "TIMEOUT"},
                    "CONNECTION": {"시가총액": 5_000 * 1e8, "종목명": "CONNECTION"},
                }
            ).T

    src = _ExceptionSource()
    client = DataClient(
        ticker_list_sources=[src],
        ohlcv_sources=[src],
    )
    runner = ScanRunner(client, RunnerConfig(top_n=10))
    result = runner.run([_FakeStrategy("s")], target_date="20260418")

    # fetch_exceptions는 Counter를 dict로 변환해서 저장
    assert result.funnel_stats["fetch_exceptions"]["TimeoutError"] == 1
    assert result.funnel_stats["fetch_exceptions"]["ConnectionError"] == 1
    assert result.funnel_stats["fetch_failed"] == 2


def test_run_records_source_counts():
    """OHLCV 소스별 응답 분포 기록 — 1차 소스 8개, 2차 소스 2개."""

    class _MultiSourceProvider(DailyDataSource):
        """ticker 리스트와 시총만 제공."""
        name = "multi_provider"

        def get_tickers(self, market, target_date):
            return [f"T{i:02d}" for i in range(10)]

        def get_ticker_name(self, ticker):
            return ticker

        def get_ohlcv(self, ticker, start, end):
            return pd.DataFrame(
                {"close": [100.0]*40},
                index=pd.date_range("2026-01-01", periods=40, freq="D"),
            )

        def get_market_cap(self, market, target_date):
            tickers = [f"T{i:02d}" for i in range(10)]
            return pd.DataFrame(
                {t: {"시가총액": 5_000 * 1e8, "종목명": t} for t in tickers}
            ).T

    class _PrimarySource(DailyDataSource):
        name = "primary"

        def get_tickers(self, market, target_date):
            return []

        def get_ticker_name(self, ticker):
            return ticker

        def get_ohlcv(self, ticker, start, end):
            # T00~T07만 응답 (8개)
            if int(ticker[1:]) < 8:
                return pd.DataFrame(
                    {"close": [100.0]*40},
                    index=pd.date_range("2026-01-01", periods=40, freq="D"),
                )
            return pd.DataFrame()

        def get_market_cap(self, market, target_date):
            return pd.DataFrame()

    class _SecondarySource(DailyDataSource):
        name = "secondary"

        def get_tickers(self, market, target_date):
            return []

        def get_ticker_name(self, ticker):
            return ticker

        def get_ohlcv(self, ticker, start, end):
            # T08~T09만 응답 (2개)
            if int(ticker[1:]) >= 8:
                return pd.DataFrame(
                    {"close": [100.0]*40},
                    index=pd.date_range("2026-01-01", periods=40, freq="D"),
                )
            return pd.DataFrame()

        def get_market_cap(self, market, target_date):
            return pd.DataFrame()

    provider = _MultiSourceProvider()
    client = DataClient(
        ticker_list_sources=[provider],
        ohlcv_sources=[_PrimarySource(), _SecondarySource()],  # fallback chain
    )
    runner = ScanRunner(client, RunnerConfig(top_n=10))
    result = runner.run([_FakeStrategy("s")], target_date="20260418")

    assert result.funnel_stats["source_counts"]["primary"] == 8
    assert result.funnel_stats["source_counts"]["secondary"] == 2
