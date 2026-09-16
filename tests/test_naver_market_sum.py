"""
test_naver_market_sum.py — stock.naver.com 주식 목록 JSON API 파싱 검증.

실제 네이버 호출 금지. 2026-09-16 실제 응답 형태를 축약한 dict 를 mock 으로 주입한다.

검증 포인트:
  - 응답 항목 → _ticker_cache (name/market/market_cap(원)/volume/per/per_negative/roe/foreign_pct)
  - per null + eps 음수 → 적자 sentinel (PR-A 정책 유지)
  - KOSPI 는 etfItemList 항목을 합쳐 구형 페이지의 ETF 혼입 동작 유지
  - 0건 응답은 조용히 넘어가지 않고 RuntimeError
  - get_market_cap / get_fundamentals 컬럼 BC 유지
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.data_sources.naver import NaverSource, naver_detail_url

_STOCKS_KOSPI = [
    {"itemcode": "005930", "itemname": "삼성전자", "marketSum": "1477646918000000",
     "tradeVolume": "6392554", "per": "11.34", "eps": "22292.0", "roe": "10.85",
     "frgnHoldRate": "46.56"},
    {"itemcode": "005935", "itemname": "삼성전자우", "marketSum": "60000000000000",
     "tradeVolume": "500000", "per": "9.1", "eps": "22292.0", "roe": None,
     "frgnHoldRate": "78.01"},
    {"itemcode": "373220", "itemname": "LG에너지솔루션", "marketSum": "86814000000000",
     "tradeVolume": "191319", "per": None, "eps": "-7193.0", "roe": "-5.19",
     "frgnHoldRate": "5.52"},
]
_STOCKS_KOSDAQ = [
    {"itemcode": "086520", "itemname": "에코프로", "marketSum": "12000000000000",
     "tradeVolume": "300000", "per": None, "eps": "-1000.0", "roe": "-8.39",
     "frgnHoldRate": "19.22"},
]
_ETF_RESPONSE = {"result": {"etfItemList": [
    {"itemcode": "069500", "itemname": "KODEX 200", "marketSum": 247029, "quant": 14406930},
]}}


def _json_response(data) -> MagicMock:
    fake = MagicMock()
    fake.json.return_value = data
    fake.raise_for_status = MagicMock()
    return fake


def _patch_requests(stocks, etf=_ETF_RESPONSE):
    """stock/default 요청엔 stocks 배열, etfItemList 요청엔 etf dict 를 돌려준다."""
    def fake_get(url, *args, **kwargs):
        if "etfItemList" in url:
            return _json_response(etf)
        return _json_response(stocks)
    return patch("core.data_sources.naver.requests.get", side_effect=fake_get)


# ---------------------------------------------------------------------------
# naver_detail_url 헬퍼
# ---------------------------------------------------------------------------

def test_naver_detail_url_pattern():
    """ticker → finance.naver.com/item/main.naver?code={ticker} 패턴."""
    assert naver_detail_url("005930") == "https://finance.naver.com/item/main.naver?code=005930"


# ---------------------------------------------------------------------------
# _crawl_market_sum: JSON 응답 → _ticker_cache
# ---------------------------------------------------------------------------

def test_crawl_kospi_fills_cache_from_json():
    """주식 API 항목 → per/roe/foreign_pct/market_cap(원)/volume 이 캐시에 채워진다."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSPI):
        src._crawl_market_sum("KOSPI")
    s = src._ticker_cache["005930"]
    assert s["name"] == "삼성전자"
    assert s["market"] == "KOSPI"
    assert s["market_cap"] == 1477646918000000.0
    assert s["volume"] == 6392554
    assert s["per"] == 11.34 and s["per_negative"] is False
    assert s["roe"] == 10.85
    assert s["foreign_pct"] == 46.56


def test_crawl_handles_null_roe():
    """null ROE → None (JSON 호환)."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSPI):
        src._crawl_market_sum("KOSPI")
    assert src._ticker_cache["005935"]["roe"] is None


def test_crawl_negative_eps_sets_per_negative():
    """per null + eps 음수 → per None, per_negative True, roe 음수 보존 (PR-A 정책)."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSDAQ):
        src._crawl_market_sum("KOSDAQ")
    e = src._ticker_cache["086520"]
    assert e["per"] is None and e["per_negative"] is True
    assert e["roe"] == -8.39
    assert e["foreign_pct"] == 19.22


def test_crawl_kospi_merges_etf_list():
    """KOSPI 는 etfItemList 항목을 합쳐 기존(ETF 혼입) 동작을 유지한다. 시총 억→원."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSPI):
        src._crawl_market_sum("KOSPI")
    etf = src._ticker_cache["069500"]
    assert etf["market"] == "KOSPI"
    assert etf["name"] == "KODEX 200"
    assert etf["market_cap"] == 247029 * 100_000_000
    assert etf["volume"] == 14406930
    assert etf["per"] is None and etf["per_negative"] is False


def test_crawl_kosdaq_does_not_merge_etf():
    """KOSDAQ 은 ETF 를 합치지 않는다 (중복 등록 방지)."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSDAQ):
        src._crawl_market_sum("KOSDAQ")
    assert "069500" not in src._ticker_cache


def test_crawl_etf_failure_keeps_stocks():
    """etfItemList 실패는 warning 만 남기고 주식은 유지된다."""
    src = NaverSource()

    def fake_get(url, *args, **kwargs):
        if "etfItemList" in url:
            raise RuntimeError("boom")
        return _json_response(_STOCKS_KOSPI)

    with patch("core.data_sources.naver.requests.get", side_effect=fake_get):
        src._crawl_market_sum("KOSPI")
    assert "005930" in src._ticker_cache


def test_crawl_empty_response_raises():
    """0건이면 조용히 넘어가지 않고 RuntimeError (9/11~9/16 조용한 실패 재발 방지)."""
    src = NaverSource()
    with _patch_requests([], etf={"result": {"etfItemList": []}}):
        with pytest.raises(RuntimeError):
            src._crawl_market_sum("KOSPI")


def test_crawl_calls_stock_default_api_once_per_market():
    """시장별 1회만 fetch (캐시 히트 시 재호출 없음)."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSDAQ) as mock_get:
        src._crawl_market_sum("KOSDAQ")
        src._crawl_market_sum("KOSDAQ")  # 캐시 히트
    stock_calls = [c for c in mock_get.call_args_list if "stock/default" in c.args[0]]
    assert len(stock_calls) == 1
    params = stock_calls[0].kwargs["params"]
    assert params["marketType"] == "KOSDAQ"
    assert params["startIdx"] == 0
    assert params["pageSize"] >= 3000


def test_crawl_follows_pages_when_response_is_full():
    """응답 길이가 pageSize 와 같으면 startIdx 를 올려 다음 페이지를 이어 받는다."""
    src = NaverSource()
    full_page = [dict(_STOCKS_KOSDAQ[0], itemcode=f"{i:06d}") for i in range(3000)]

    def fake_get(url, *args, **kwargs):
        if "etfItemList" in url:
            return _json_response({"result": {"etfItemList": []}})
        page = kwargs["params"]["startIdx"]
        return _json_response(full_page if page == 0 else _STOCKS_KOSDAQ)

    with patch("core.data_sources.naver.requests.get", side_effect=fake_get) as mock_get:
        src._crawl_market_sum("KOSDAQ")
    assert len(src._ticker_cache) == 3001
    assert [c.kwargs["params"]["startIdx"] for c in mock_get.call_args_list] == [0, 1]


# ---------------------------------------------------------------------------
# get_market_cap BC: 기존 시그니처 + 컬럼 유지
# ---------------------------------------------------------------------------

def test_get_market_cap_signature_unchanged():
    """기존 get_market_cap 컬럼(시가총액, 종목명, 거래량) 유지 — 호출 측 BC."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSPI):
        df = src.get_market_cap("KOSPI", "20260916")
    for col in ("시가총액", "종목명", "거래량"):
        assert col in df.columns
    assert df.loc["005930", "종목명"] == "삼성전자"
    assert df.loc["005930", "거래량"] == 6392554


# ---------------------------------------------------------------------------
# get_fundamentals
# ---------------------------------------------------------------------------

def test_get_fundamentals_returns_dataframe():
    """인덱스=ticker, 컬럼=per/per_negative/roe/foreign_pct/market_cap_bil/naver_url."""
    src = NaverSource()
    with _patch_requests(_STOCKS_KOSPI):
        df = src.get_fundamentals("KOSPI", "20260916")
    assert isinstance(df, pd.DataFrame)
    for col in ["per", "per_negative", "roe", "foreign_pct", "market_cap_bil", "naver_url"]:
        assert col in df.columns
    assert df.loc["005930", "per"] == 11.34
    assert df.loc["005930", "market_cap_bil"] == pytest.approx(14776469.18)
    assert df.loc["005930", "naver_url"] == "https://finance.naver.com/item/main.naver?code=005930"
    pref = df.loc["005935"].to_dict()
    assert pref["roe"] is None or pd.isna(pref["roe"])
