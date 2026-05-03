"""
test_naver_etf.py — NaverSource.get_tickers("ETF") 검증.

실제 네이버 호출 금지. ETF 목록 JSON API 응답을 mock으로 주입.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.data_sources.naver import NaverSource

_FAKE_ETF_RESPONSE = {
    "resultCode": "success",
    "result": {
        "etfItemList": [
            {"itemcode": "069500", "itemname": "KODEX 200", "etfTabCode": 1, "marketSum": 10000, "quant": 500},
            {"itemcode": "360750", "itemname": "TIGER 미국S&P500", "etfTabCode": 1, "marketSum": 5000, "quant": 3000},
            {"itemcode": "396500", "itemname": "TIGER 반도체TOP10", "etfTabCode": 2, "marketSum": 3000, "quant": 1000},
        ]
    },
}


def _make_json_response(data: dict) -> MagicMock:
    fake = MagicMock()
    fake.json.return_value = data
    fake.raise_for_status = MagicMock()
    return fake


def test_get_tickers_etf_returns_itemcodes():
    """get_tickers('ETF') → 거래량 내림차순 itemcode 목록 반환."""
    src = NaverSource()
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_make_json_response(_FAKE_ETF_RESPONSE),
    ):
        tickers = src.get_tickers("ETF", "20260503")

    # quant 내림차순: 360750(3000) > 396500(1000) > 069500(500)
    assert tickers == ["360750", "396500", "069500"]


def test_get_tickers_etf_calls_correct_url():
    """ETF_LIST_URL에 etfType=0 파라미터로 호출한다."""
    src = NaverSource()
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_make_json_response(_FAKE_ETF_RESPONSE),
    ) as mock_get:
        src.get_tickers("ETF", "20260503")

    call_kwargs = mock_get.call_args
    assert call_kwargs[0][0] == NaverSource.ETF_LIST_URL
    assert call_kwargs[1]["params"] == {"etfType": 0}


def test_get_tickers_etf_empty_list():
    """빈 ETF 목록 응답 → 빈 리스트 반환."""
    src = NaverSource()
    empty_response = {"resultCode": "success", "result": {"etfItemList": []}}
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_make_json_response(empty_response),
    ):
        tickers = src.get_tickers("ETF", "20260503")

    assert tickers == []


def test_get_tickers_etf_sorted_by_volume():
    """응답 순서와 무관하게 quant(거래량) 내림차순 정렬 후 반환."""
    src = NaverSource()
    unsorted_response = {
        "resultCode": "success",
        "result": {
            "etfItemList": [
                {"itemcode": "C", "quant": 100},
                {"itemcode": "A", "quant": 9000},
                {"itemcode": "B", "quant": 500},
            ]
        },
    }
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_make_json_response(unsorted_response),
    ):
        tickers = src.get_tickers("ETF", "20260503")

    assert tickers == ["A", "B", "C"]


def test_get_tickers_etf_top200_limit():
    """get_tickers('ETF')는 거래량 상위 200개만 반환한다."""
    src = NaverSource()
    items = [
        {"itemcode": str(i).zfill(6), "quant": 1000 - i}
        for i in range(400)
    ]
    response = {"resultCode": "success", "result": {"etfItemList": items}}
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_make_json_response(response),
    ):
        tickers = src.get_tickers("ETF", "20260503")

    assert len(tickers) == 200
    assert tickers[0] == "000000"  # quant 최대값
