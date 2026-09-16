"""test_naver_market_index.py — m.stock index/basic JSON → {"value", "change_pct"}.

실제 네이버 호출 금지. 구형 sise_index HTML 페이지가 2026-09-10 폐쇄되어 JSON API 로 교체.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.data_sources.naver import NaverSource


def _json(data) -> MagicMock:
    fake = MagicMock()
    fake.json.return_value = data
    fake.raise_for_status = MagicMock()
    return fake


def test_market_index_parses_close_and_signed_ratio():
    """종가는 콤마 제거 후 float, 등락률은 부호를 그대로 보존한다."""
    src = NaverSource()
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_json({"closePrice": "809.97", "fluctuationsRatio": "-0.30"}),
    ) as g:
        out = src.get_market_index("KOSDAQ", "20260916")
    assert out == {"value": 809.97, "change_pct": -0.30}
    assert g.call_args.args[0] == "https://m.stock.naver.com/api/index/KOSDAQ/basic"


def test_market_index_parses_thousands_separator():
    """KOSPI 처럼 천 단위 콤마가 있는 종가도 파싱한다."""
    src = NaverSource()
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_json({"closePrice": "6,693.32", "fluctuationsRatio": "1.00"}),
    ):
        assert src.get_market_index("KOSPI", "20260916") == {
            "value": 6693.32, "change_pct": 1.0,
        }


def test_market_index_unknown_market_returns_none():
    """지원하지 않는 시장은 호출 없이 None."""
    assert NaverSource().get_market_index("NASDAQ", "20260916") is None


def test_market_index_http_error_returns_none():
    """HTTP 실패는 warning 후 None (호출 측이 키를 생략)."""
    src = NaverSource()
    fake = MagicMock()
    fake.raise_for_status.side_effect = RuntimeError("500")
    with patch("core.data_sources.naver.requests.get", return_value=fake):
        assert src.get_market_index("KOSPI", "20260916") is None
