"""
test_core_data_fetch.py — DataClient + OhlcvCache 검증.

가장 중요한 검증:
  - OhlcvCache 가 동일 (ticker, start, end) 호출에 대해 fetch 1회만 수행 (단일 fetch 보장)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from core.cache.ohlcv_disk import OhlcvDiskCache
from core.data_fetch import DataClient, OhlcvCache
from core.data_sources.base import DailyDataSource


class _StubSource(DailyDataSource):
    """fetch 호출 횟수를 기록하는 stub 소스."""
    name = "stub"

    def __init__(self, df_factory):
        self.calls = []
        self._factory = df_factory

    def get_tickers(self, market: str, target_date: str) -> list[str]:
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
    )
    df = client.get_ohlcv("005930", "20260101", "20260418")
    assert not df.empty
    assert succeeding.calls == [("005930", "20260101", "20260418")]


def test_get_ohlcv_with_source_returns_first_success_source():
    """첫 소스 fail, 두 번째 success → (source_name, df) 반환."""
    failing = MagicMock(spec=DailyDataSource)
    failing.name = "failing_source"
    failing.get_ohlcv.side_effect = RuntimeError("boom")

    succeeding = _StubSource(_make_df)
    succeeding.name = "naver"

    client = DataClient(
        ticker_list_sources=[failing],
        ohlcv_sources=[failing, succeeding],
    )
    source, df = client.get_ohlcv_with_source("005930", "20260101", "20260418")
    assert source == "naver"
    assert not df.empty


def test_cache_get_or_fetch_with_source_hit():
    """캐시 hit 시에도 source 정보 반환."""
    stub = _StubSource(_make_df)
    stub.name = "naver"
    cache = OhlcvCache(_make_client(stub))

    source1, df1 = cache.get_or_fetch_with_source("005930", "20260101", "20260418")
    source2, df2 = cache.get_or_fetch_with_source("005930", "20260101", "20260418")

    assert source1 == "naver"
    assert source2 == "naver"  # hit에서도 source 반환
    assert len(stub.calls) == 1  # fetch 1회만
    pd.testing.assert_frame_equal(df1, df2)


def test_cache_get_or_fetch_with_source_miss():
    """캐시 miss 시 fetch 수행 및 source 저장."""
    stub = _StubSource(_make_df)
    stub.name = "fdr"
    cache = OhlcvCache(_make_client(stub))

    source, df = cache.get_or_fetch_with_source("005930", "20260101", "20260418")
    assert source == "fdr"
    assert not df.empty
    assert len(stub.calls) == 1


class _MultiTfStubSource(DailyDataSource):
    """timeframe 별 다른 응답을 주는 stub — disk fix 회귀용."""
    name = "stub_mtf"

    def __init__(self):
        self.calls: list[tuple[str, str, str, str]] = []

    def get_tickers(self, market: str, target_date: str) -> list[str]:
        return ["005930"]

    def get_ticker_name(self, ticker: str) -> str:
        return ticker

    def get_ohlcv(
        self, ticker: str, start: str, end: str, timeframe: str = "1D"
    ) -> pd.DataFrame:
        self.calls.append((ticker, start, end, timeframe))
        if timeframe == "1m":
            base = pd.to_datetime(start[:8])
            return pd.DataFrame(
                {"close": [100.0, 101.0]},
                index=[base + pd.Timedelta(minutes=540),
                       base + pd.Timedelta(minutes=541)],
            )
        return _make_df(ticker, start, end)


def test_disk_cache_passes_timeframe_to_client_for_1m(tmp_path):
    """디스크 캐시 cold path 에서도 timeframe='1m' 이 client 에 전달되어야 함.

    회귀: 이전엔 timeframe 인자가 빠져 1m 디렉토리에 1D 응답이 저장됐음.
    """
    stub = _MultiTfStubSource()
    client = DataClient(ticker_list_sources=[stub], ohlcv_sources=[stub])
    disk = OhlcvDiskCache(tmp_path)
    cache = OhlcvCache(client, disk=disk)

    cache.get_or_fetch("005930", "20260504", "20260504", timeframe="1m")

    assert len(stub.calls) == 1
    _, _, _, tf = stub.calls[0]
    assert tf == "1m"


def test_disk_cache_normalizes_1m_dates(tmp_path):
    """1m 일 때 caller 가 YYYYMMDD 만 줘도 분 단위로 normalize."""
    stub = _MultiTfStubSource()
    client = DataClient(ticker_list_sources=[stub], ohlcv_sources=[stub])
    disk = OhlcvDiskCache(tmp_path)
    cache = OhlcvCache(client, disk=disk)

    cache.get_or_fetch("005930", "20260504", "20260504", timeframe="1m")

    _, start, end, _ = stub.calls[0]
    assert start == "202605040000"
    assert end == "202605042359"


def test_get_ohlcv_with_source_propagates_when_all_sources_fail():
    """
    Step 7: 모든 소스 RuntimeError → 마지막 예외 전파.
    """
    failing1 = MagicMock(spec=DailyDataSource)
    failing1.name = "failing1"
    failing1.get_ohlcv.side_effect = RuntimeError("source1 fail")

    failing2 = MagicMock(spec=DailyDataSource)
    failing2.name = "failing2"
    failing2.get_ohlcv.side_effect = RuntimeError("source2 fail")

    client = DataClient(
        ticker_list_sources=[failing1],
        ohlcv_sources=[failing1, failing2],
    )

    # 마지막 예외 (failing2의 오류) 전파
    with pytest.raises(RuntimeError) as excinfo:
        client.get_ohlcv_with_source("005930", "20260101", "20260418")

    assert "source2 fail" in str(excinfo.value)
