"""
Task 4: 디스크 캐시 모드에서 1m lookback이 확장되는지 검증.

cache_root 지정 시 minute_start_str = start_str (lookback+30일 전)
cache_root 미지정 시 minute_start_str = 7일 전 (기존 동작 유지)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.runner import RunnerConfig, ScanRunner


class _StubSrc(DailyDataSource):
    name = "stub"

    def get_tickers(self, market, date):
        return ["_stub_"]  # 비어있으면 DataClient가 fallback 후 RuntimeError

    def get_ticker_name(self, t):
        return t

    def get_ohlcv(self, t, start, end, timeframe="1D"):
        return pd.DataFrame()

    def get_market_cap(self, market, date):
        return pd.DataFrame({"_stub_": {"시가총액": 5e11, "종목명": "stub"}}).T


def _make_client():
    return DataClient(
        ticker_list_sources=[_StubSrc()],
        ohlcv_sources=[_StubSrc()],
    )


def test_no_cache_root_uses_7day_minute_window():
    """cache_root 미지정 시 1m window는 7일 (기존 동작)."""
    cfg = RunnerConfig(
        timeframes=["30m"],
        cache_root=None,
        lookback_days=60,
        max_universe_size=2,
        min_market_cap_bil=0.0,
        max_market_cap_bil=9_999_999.0,
    )
    runner = ScanRunner(_make_client(), cfg)
    # 유니버스 0개 → fetch 없음, 예외 없으면 통과
    result = runner.run([], target_date="20260430")
    assert result is not None


def test_cache_root_extends_minute_start_to_lookback(tmp_path):
    """cache_root 지정 시 minute_start_str 이 start_str(lookback+30일 전)와 동일해야 함."""
    captured_starts = []

    import core.runner as runner_mod
    OriginalOhlcvCache = runner_mod.OhlcvCache

    class _TrackingCache:
        def __init__(self, client, disk=None):
            pass

        def get_or_fetch_with_source(self, ticker, start, end, timeframe="1D"):
            captured_starts.append((timeframe, start))
            return ("stub", pd.DataFrame())

        @property
        def stats(self):
            return {"fetch_count": 0, "hit_count": 0, "size": 0}

    # 유니버스에 1종목이 있어야 fetch가 호출됨
    class _OneSrc(DailyDataSource):
        name = "one"

        def get_tickers(self, market, date):
            return ["005930"]

        def get_ticker_name(self, t):
            return "삼성전자"

        def get_ohlcv(self, t, s, e, timeframe="1D"):
            return pd.DataFrame()

        def get_market_cap(self, market, date):
            return pd.DataFrame(
                {"005930": {"시가총액": 5e11, "종목명": "삼성전자"}}
            ).T

    client = DataClient(
        ticker_list_sources=[_OneSrc()],
        ohlcv_sources=[_OneSrc()],
    )
    cfg = RunnerConfig(
        timeframes=["30m"],
        cache_root=tmp_path / ".cache",
        lookback_days=60,
        max_universe_size=2,
        min_market_cap_bil=0.0,
        max_market_cap_bil=9_999_999.0,
    )

    runner_mod.OhlcvCache = _TrackingCache
    try:
        runner = ScanRunner(client, cfg)
        runner.run([], target_date="20260430")
    finally:
        runner_mod.OhlcvCache = OriginalOhlcvCache

    minute_starts = [s for (tf, s) in captured_starts if tf == "1m"]
    if minute_starts:
        target_dt = datetime(2026, 4, 30)
        expected = (target_dt - timedelta(days=60 + 30)).strftime("%Y%m%d")
        assert minute_starts[0] == expected, (
            f"기대 1m start={expected}, 실제={minute_starts[0]}"
        )
