"""
Task 7: ScanContext + ScanRunner + StrategyOneDv2 multi-tf 통합.

검증:
  - REGISTRY 에 4 변형 등록 (strategy_one_{d,w,1h,30m}_v2)
  - StrategyOneDv2(timeframe=) 파라미터화 — name/timeframe 자동 매핑
  - ScanRunner.run(timeframes=["1D","1W"]) 가 (strategy, tf) 키로 결과 분리
  - ScanContext.ohlcv_by_tf 자동 동기화 (legacy ohlcv → 1D)
"""
from __future__ import annotations


import pandas as pd

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import ScanContext
from strategies import REGISTRY
from strategies.strategy_one_d_v2 import StrategyOneDv2


class _StubSource(DailyDataSource):
    name = "stub"

    def __init__(self, tickers: list[str], caps: dict[str, float]):
        self._tickers = tickers
        self._caps = caps

    def get_tickers(self, market, target_date):
        return list(self._tickers)

    def get_ticker_name(self, ticker):
        return f"종목{ticker}"

    def get_ohlcv(self, ticker, start, end, timeframe="1D"):
        if timeframe == "1D":
            idx = pd.date_range("2026-01-01", periods=120, freq="B")
        elif timeframe == "1m":
            idx = pd.date_range("2026-04-23 09:00", periods=2000, freq="1min")
        else:
            raise NotImplementedError(f"stub: timeframe={timeframe}")
        return pd.DataFrame(
            {
                "open": [100.0] * len(idx),
                "high": [101.0] * len(idx),
                "low": [99.0] * len(idx),
                "close": [100.0] * len(idx),
                "volume": [1_000_000] * len(idx),
            },
            index=idx,
        )

    def get_market_cap(self, market, target_date):
        rows = {t: {"시가총액": self._caps[t], "종목명": f"종목{t}"} for t in self._tickers}
        return pd.DataFrame(rows).T


# ---------------------------------------------------------------- REGISTRY


def test_registry_has_four_strategy_one_variants():
    for name in [
        "strategy_one_d_v2",
        "strategy_one_w_v2",
        "strategy_one_1h_v2",
        "strategy_one_30m_v2",
    ]:
        assert name in REGISTRY, f"missing: {name}"


def test_registry_factory_returns_correct_timeframe():
    inst = REGISTRY["strategy_one_w_v2"]()
    assert inst.timeframe == "1W"
    assert inst.name == "strategy_one_w_v2"


def test_registry_d_v2_default_legacy():
    inst = REGISTRY["strategy_one_d_v2"]()
    assert inst.timeframe == "1D"
    assert inst.name == "strategy_one_d_v2"


# ---------------------------------------------------------------- StrategyOneDv2 param


def test_strategy_one_dv2_unsupported_timeframe_raises():
    import pytest
    with pytest.raises(ValueError, match="unsupported timeframe"):
        StrategyOneDv2(timeframe="5s")


# ---------------------------------------------------------------- ScanContext sync


def test_scan_context_legacy_ohlcv_auto_mirrors_to_1D():
    ohlcv_1d = {"005930": pd.DataFrame()}
    ctx = ScanContext(
        target_date="20260430",
        universe=("005930",),
        ohlcv=ohlcv_1d,
        names={},
        market_caps={},
        market="KOSPI",
    )
    assert "1D" in ctx.ohlcv_by_tf
    assert ctx.ohlcv_by_tf["1D"] is ohlcv_1d


def test_scan_context_ohlcv_by_tf_auto_mirrors_to_legacy():
    ohlcv_1d = {"005930": pd.DataFrame()}
    ctx = ScanContext(
        target_date="20260430",
        universe=("005930",),
        ohlcv={},
        names={},
        market_caps={},
        market="KOSPI",
        ohlcv_by_tf={"1D": ohlcv_1d, "1W": {}},
    )
    assert ctx.ohlcv is ohlcv_1d


# ---------------------------------------------------------------- Runner multi-tf


def _make_client():
    tickers = ["005930", "000660"]
    caps = {t: 5_000 * 1e8 for t in tickers}  # 5,000억
    src = _StubSource(tickers, caps)
    return DataClient(
        ticker_list_sources=[src],
        ohlcv_sources=[src],
    )


def test_runner_scans_1D_and_1W(tmp_path):
    cfg = RunnerConfig(
        market="KOSPI",
        timeframes=["1D", "1W"],
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        min_market_cap_bil=10.0,
        max_market_cap_bil=1_000_000.0,
        min_daily_volume=10_000,
        lookback_days=60,
    )
    runner = ScanRunner(_make_client(), cfg)
    result = runner.run(
        [REGISTRY["strategy_one_d_v2"](), REGISTRY["strategy_one_w_v2"]()],
        target_date="20260430",
    )
    # 두 (strategy, tf) 키가 결과 dict 에 존재 (후보 0개여도 키는 있음)
    assert ("strategy_one_d_v2", "1D") in result.candidates_by_strategy_tf
    assert ("strategy_one_w_v2", "1W") in result.candidates_by_strategy_tf
    # legacy alias 도 1D 결과 포함
    assert "strategy_one_d_v2" in result.candidates_by_strategy
    # per-tf size funnel
    assert result.funnel_stats["per_tf_size"]["1D"] >= 0
    assert result.funnel_stats["per_tf_size"]["1W"] >= 0


def test_runner_scans_30m_with_minute_resample(tmp_path):
    cfg = RunnerConfig(
        market="KOSPI",
        timeframes=["30m"],
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        min_market_cap_bil=10.0,
        max_market_cap_bil=1_000_000.0,
        min_daily_volume=10_000,
    )
    runner = ScanRunner(_make_client(), cfg)
    result = runner.run([REGISTRY["strategy_one_30m_v2"]()], target_date="20260430")
    assert ("strategy_one_30m_v2", "30m") in result.candidates_by_strategy_tf
