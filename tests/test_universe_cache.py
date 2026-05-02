"""Task 2: UniverseCache 저장/로드 검증."""
from __future__ import annotations

from core.cache.universe_cache import UniverseCache


def test_save_and_load_roundtrip(tmp_path):
    cache = UniverseCache(tmp_path)
    cache.save(
        market="KOSPI",
        date="20260430",
        tickers=["005930", "000660"],
        cap_lookup={"005930": 500_000_000_000.0, "000660": 200_000_000_000.0},
        name_lookup={"005930": "삼성전자", "000660": "SK하이닉스"},
    )
    loaded = cache.load(market="KOSPI", date="20260430")
    assert loaded["tickers"] == ["005930", "000660"]
    assert loaded["cap_lookup"]["005930"] == 500_000_000_000.0
    assert loaded["name_lookup"]["005930"] == "삼성전자"


def test_load_missing_returns_none(tmp_path):
    cache = UniverseCache(tmp_path)
    assert cache.load(market="KOSPI", date="20260430") is None


def test_latest_returns_most_recent(tmp_path):
    cache = UniverseCache(tmp_path)
    cache.save("KOSPI", "20260428", ["A"], {}, {})
    cache.save("KOSPI", "20260430", ["B"], {}, {})
    loaded = cache.latest(market="KOSPI")
    assert loaded["tickers"] == ["B"]


def test_latest_returns_none_when_empty(tmp_path):
    cache = UniverseCache(tmp_path)
    assert cache.latest(market="KOSPI") is None
