"""
test_core_universe.py — UniverseFilter / build_universe 검증 (Naver 단일 소스).

snapshot 테스트가 통합 검증을 하므로 여기선 단위 케이스 중심.
"""
from __future__ import annotations


import pandas as pd

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.universe import UniverseFilter, build_universe


class _MockSource(DailyDataSource):
    """네이버 스타일 mock — 시총 lookup 만 제공."""
    name = "mock"

    def __init__(self, tickers: list[str], cap_lookup: dict[str, float], names: dict[str, str]):
        self._tickers = tickers
        self._caps = cap_lookup
        self._names = names

    def get_tickers(self, market, target_date):
        return list(self._tickers)

    def get_ticker_name(self, ticker):
        return self._names.get(ticker, ticker)

    def get_ohlcv(self, ticker, start, end):
        return pd.DataFrame()

    def get_market_cap(self, market, target_date):
        rows = {
            t: {"시가총액": self._caps[t], "종목명": self._names[t]}
            for t in self._tickers
        }
        return pd.DataFrame(rows).T


def _client_with_mock(mock):
    return DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
    )


def test_build_universe_filters_by_market_cap():
    mock = _MockSource(
        tickers=["A", "B", "C", "D"],
        cap_lookup={
            "A": 1_000 * 1e8,        # 1,000억 — too small
            "B": 5_000 * 1e8,        # 5,000억 — pass
            "C": 25_000 * 1e8,       # 2.5조 — pass
            "D": 50_000 * 1e8,       # 5조 — too big
        },
        names={"A": "에이", "B": "비", "C": "씨", "D": "디"},
    )
    client = _client_with_mock(mock)
    res = build_universe(
        client, "20260418",
        UniverseFilter(min_market_cap_bil=2000, max_market_cap_bil=30000, market="KOSPI"),
    )
    assert sorted(res.tickers) == ["B", "C"]
    assert res.cap_lookup["B"] == 5_000 * 1e8


def test_build_universe_no_cap_data_returns_all_tickers():
    """시총 lookup 자체가 비면 필터 없이 전종목 통과."""
    class _NoCap(_MockSource):
        def get_market_cap(self, market, target_date):
            return pd.DataFrame()

    mock = _NoCap(
        tickers=["A", "B"],
        cap_lookup={},
        names={"A": "에이", "B": "비"},
    )
    client = _client_with_mock(mock)
    res = build_universe(
        client, "20260418",
        UniverseFilter(min_market_cap_bil=2000, max_market_cap_bil=30000),
    )
    assert sorted(res.tickers) == ["A", "B"]
    assert res.cap_lookup == {}


def test_build_universe_inclusive_boundaries():
    """경계값 정확히 포함 (≤ ≤)"""
    mock = _MockSource(
        tickers=["MIN", "MAX"],
        cap_lookup={"MIN": 2_000 * 1e8, "MAX": 30_000 * 1e8},
        names={"MIN": "민", "MAX": "맥스"},
    )
    client = _client_with_mock(mock)
    res = build_universe(
        client, "20260418",
        UniverseFilter(min_market_cap_bil=2000, max_market_cap_bil=30000),
    )
    assert sorted(res.tickers) == ["MAX", "MIN"]


def test_build_universe_applies_top_n_cap_limit():
    """cap range 통과 종목 12개 중 max_universe_size=5 시 시총 상위 5개만 반환."""
    tickers = [f"T{i:02d}" for i in range(12)]
    cap_lookup = {t: 5_000 * 1e8 for t in tickers}
    names = {t: t for t in tickers}

    mock = _MockSource(tickers=tickers, cap_lookup=cap_lookup, names=names)
    client = _client_with_mock(mock)
    res = build_universe(
        client, "20260418",
        UniverseFilter(
            min_market_cap_bil=2000,
            max_market_cap_bil=30000,
            max_universe_size=5,
        ),
    )
    assert len(res.tickers) == 5
    assert res.pre_cap_limit_size == 12


def test_build_universe_no_limit_when_below_threshold():
    """통과 종목 8개 < limit 500 → 그대로 8개 반환."""
    tickers = [f"T{i:02d}" for i in range(8)]
    cap_lookup = {tickers[i]: 5_000 * 1e8 for i in range(8)}
    names = {t: t for t in tickers}

    mock = _MockSource(tickers=tickers, cap_lookup=cap_lookup, names=names)
    client = _client_with_mock(mock)
    res = build_universe(
        client, "20260418",
        UniverseFilter(
            min_market_cap_bil=2000,
            max_market_cap_bil=30000,
            max_universe_size=500,
        ),
    )
    assert len(res.tickers) == 8
    assert res.pre_cap_limit_size == 8


def test_build_universe_skips_when_no_cap_lookup():
    """시총 lookup 실패 시 cap limit 우회."""
    class _NoCap(_MockSource):
        def get_market_cap(self, market, target_date):
            return pd.DataFrame()

    tickers = ["A", "B", "C"]
    mock = _NoCap(tickers=tickers, cap_lookup={}, names={t: t for t in tickers})
    client = _client_with_mock(mock)
    res = build_universe(
        client, "20260418",
        UniverseFilter(
            min_market_cap_bil=2000,
            max_market_cap_bil=30000,
            max_universe_size=1,
        ),
    )
    # cap_lookup 없으면 limit 우회 → 전종목 반환
    assert len(res.tickers) == 3
    assert res.pre_cap_limit_size == 0


def test_cap_limit_when_cap_lookup_empty():
    """cap_lookup={} + max_universe_size 지정 → 우회 + warning."""
    tickers = ["A", "B"]

    class _NoCap(_MockSource):
        def get_market_cap(self, market, target_date):
            return pd.DataFrame()

    mock = _NoCap(tickers=tickers, cap_lookup={}, names={t: t for t in tickers})
    client = _client_with_mock(mock)
    res = build_universe(
        client, "20260418",
        UniverseFilter(
            min_market_cap_bil=2000,
            max_market_cap_bil=30000,
            max_universe_size=100,
        ),
    )
    assert len(res.tickers) == 2
    assert res.pre_cap_limit_size == 0
