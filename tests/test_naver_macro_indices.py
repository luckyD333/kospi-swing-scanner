"""test_naver_macro_indices.py — productDetail JSON → usd_krw / wti / kr_treasury_3y.

실제 네이버 호출 금지. 구형 marketindex HTML 페이지가 2026-09-10 폐쇄되어 JSON API 로 교체.
국고채3Y 는 기존 의미를 유지해 change_pct 자리에 절대 변화량(fluctuations)을 담는다.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from core.data_sources.naver import NaverSource


def _detail(close: str, ratio: str, fluct: str) -> MagicMock:
    fake = MagicMock()
    fake.json.return_value = {
        "isSuccess": True,
        "result": {"closePrice": close, "fluctuationsRatio": ratio, "fluctuations": fluct},
    }
    fake.raise_for_status = MagicMock()
    return fake


def test_macro_indices_parses_three_products():
    """환율·WTI 는 등락률, 국고채는 절대 변화량을 change_pct 로 담는다."""
    def fake_get(url, params=None, **kwargs):
        return {
            "FX_USDKRW": _detail("1,367.40", "0.27", "3.70"),
            "CLcv1": _detail("104.92", "-0.86", "-0.91"),
            "KR3YT=RR": _detail("4.0570", "-1.05", "-0.0430"),
        }[params["reutersCode"]]

    with patch("core.data_sources.naver.requests.get", side_effect=fake_get):
        out = NaverSource().get_macro_indices()

    assert out["usd_krw"] == {"value": 1367.40, "change_pct": 0.27}
    assert out["wti"] == {"value": 104.92, "change_pct": -0.86}
    assert out["kr_treasury_3y"] == {"value": 4.057, "change_pct": -0.043}


def test_macro_indices_skips_failed_item():
    """한 항목이 실패해도 나머지는 수집한다."""
    def fake_get(url, params=None, **kwargs):
        if params["reutersCode"] == "CLcv1":
            raise RuntimeError("timeout")
        return _detail("1.0", "0.0", "0.0")

    with patch("core.data_sources.naver.requests.get", side_effect=fake_get):
        out = NaverSource().get_macro_indices()

    assert "wti" not in out
    assert {"usd_krw", "kr_treasury_3y"} <= set(out)


def test_macro_indices_skips_unsuccessful_payload():
    """isSuccess=false 는 값으로 취급하지 않는다."""
    fake = MagicMock()
    fake.json.return_value = {"isSuccess": False, "result": {}}
    fake.raise_for_status = MagicMock()
    with patch("core.data_sources.naver.requests.get", return_value=fake):
        assert NaverSource().get_macro_indices() == {}
