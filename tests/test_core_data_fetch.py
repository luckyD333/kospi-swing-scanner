"""
test_core_data_fetch.py — DataClient + OhlcvCache 검증.

가장 중요한 검증:
  - OhlcvCache 가 동일 (ticker, start, end) 호출에 대해 fetch 1회만 수행 (단일 fetch 보장)
"""
from __future__ import annotations

from typing import List
from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.data_fetch import DataClient, OhlcvCache
from core.data_sources.base import DailyDataSource


class _StubSource(DailyDataSource):
    """fetch 호출 횟수를 기록하는 stub 소스."""
    name = "stub"

    def __init__(self, df_factory):
        self.calls = []
        self._factory = df_factory

    def get_tickers(self, market: str, target_date: str) -> List[str]:
        return ["005930"]

    def get_ticker_name(self, ticker: str) -> str:
        return ticker

    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        self.calls.append((ticker, start, end))
        return self._factory(ticker, start, end)


def _make_df(ticker, start, end):
    return pd.DataFrame(
        {"close": [100.0, 101.0, 102.0]},
        index=pd.date_range(start=pd.to_datetime(start), periods=3, freq="D"),
    )


def _make_client(stub):
    return DataClient(
        ticker_list_sources=[stub],
        ohlcv_sources=[stub],
        use_krx_for_universe=False,
    )


def test_cache_hits_avoid_duplicate_fetch():
    stub = _StubSource(_make_df)
    cache = OhlcvCache(_make_client(stub))

    df1 = cache.get_or_fetch("005930", "20260101", "20260418")
    df2 = cache.get_or_fetch("005930", "20260101", "20260418")
    df3 = cache.get_or_fetch("005930", "20260101", "20260418")

    # 호출 1회만
    assert len(stub.calls) == 1
    assert cache.stats == {"fetch_count": 1, "hit_count": 2, "size": 1}

    # 반환값은 매번 동일 데이터 (사본)
    pd.testing.assert_frame_equal(df1, df2)
    pd.testing.assert_frame_equal(df2, df3)


def test_cache_distinct_keys_trigger_separate_fetch():
    stub = _StubSource(_make_df)
    cache = OhlcvCache(_make_client(stub))

    cache.get_or_fetch("005930", "20260101", "20260418")
    cache.get_or_fetch("035720", "20260101", "20260418")  # 다른 ticker
    cache.get_or_fetch("005930", "20260201", "20260418")  # 다른 start

    assert len(stub.calls) == 3
    assert cache.stats["fetch_count"] == 3
    assert cache.stats["size"] == 3


def test_cache_returns_copy_so_caller_mutation_safe():
    stub = _StubSource(_make_df)
    cache = OhlcvCache(_make_client(stub))

    df1 = cache.get_or_fetch("005930", "20260101", "20260418")
    df1.iloc[0, 0] = 999.99  # 호출자가 mutation
    df2 = cache.get_or_fetch("005930", "20260101", "20260418")

    assert df2.iloc[0, 0] != 999.99  # 캐시 원본은 보존


def test_cache_clear_resets_state():
    stub = _StubSource(_make_df)
    cache = OhlcvCache(_make_client(stub))
    cache.get_or_fetch("005930", "20260101", "20260418")
    cache.clear()
    assert cache.stats == {"fetch_count": 0, "hit_count": 0, "size": 0}


def test_dataclient_fallback_chain():
    """첫 소스 실패해도 두 번째 소스로 fallback 한다."""
    failing = MagicMock(spec=DailyDataSource)
    failing.name = "failing"
    failing.get_ohlcv.side_effect = RuntimeError("boom")

    succeeding = _StubSource(_make_df)
    client = DataClient(
        ticker_list_sources=[failing],
        ohlcv_sources=[failing, succeeding],
        use_krx_for_universe=False,
    )
    df = client.get_ohlcv("005930", "20260101", "20260418")
    assert not df.empty
    assert succeeding.calls == [("005930", "20260101", "20260418")]
