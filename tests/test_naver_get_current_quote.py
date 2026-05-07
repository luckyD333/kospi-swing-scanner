"""NaverSource.get_current_quote 부호 처리 회귀 테스트.

회귀 사례: 016610(DB증권) — 네이버 모바일 API 가 fluctuationsRatio=-1.99 (하락)
반환했는데 get_current_quote 가 +1.99 로 반전. 원인: code='5'(하락) 일 때
sign=-1 곱해서 음수×음수=양수 가 됨. fluctuationsRatio 자체에 부호가 이미
포함되므로 sign 곱셈 자체가 불필요.
"""
from unittest.mock import patch

from core.data_sources.naver import NaverSource


def _mock_response(payload: dict):
    class _R:
        def raise_for_status(self):
            pass
        def json(self):
            return payload
    return _R()


def test_get_current_quote_falling_stock_keeps_negative_sign():
    """하락 종목: fluctuationsRatio=-1.99, code='5' → change_pct=-1.99."""
    payload = {
        "closePrice": "15,300",
        "fluctuationsRatio": -1.99,
        "compareToPreviousPrice": {"code": "5", "text": "하락", "name": "FALLING"},
    }
    src = NaverSource()
    with patch("core.data_sources.naver.requests.get", return_value=_mock_response(payload)):
        q = src.get_current_quote("016610")
    assert q == {"current_price": 15300, "change_pct": -1.99}


def test_get_current_quote_rising_stock_keeps_positive_sign():
    """상승 종목: fluctuationsRatio=2.05, code='2' → change_pct=2.05."""
    payload = {
        "closePrice": "15,290",
        "fluctuationsRatio": 2.05,
        "compareToPreviousPrice": {"code": "2", "text": "상승", "name": "RISING"},
    }
    src = NaverSource()
    with patch("core.data_sources.naver.requests.get", return_value=_mock_response(payload)):
        q = src.get_current_quote("000000")
    assert q == {"current_price": 15290, "change_pct": 2.05}


def test_get_current_quote_lower_limit_keeps_negative_sign():
    """하한가: fluctuationsRatio=-29.85, code='4' → change_pct=-29.85."""
    payload = {
        "closePrice": "7,000",
        "fluctuationsRatio": -29.85,
        "compareToPreviousPrice": {"code": "4", "text": "하한가", "name": "LOWER_LIMIT"},
    }
    src = NaverSource()
    with patch("core.data_sources.naver.requests.get", return_value=_mock_response(payload)):
        q = src.get_current_quote("999999")
    assert q == {"current_price": 7000, "change_pct": -29.85}


def test_get_current_quote_flat_returns_zero():
    """보합: fluctuationsRatio=0, code='3' → change_pct=0.0."""
    payload = {
        "closePrice": "10,000",
        "fluctuationsRatio": 0,
        "compareToPreviousPrice": {"code": "3", "text": "보합", "name": "FLAT"},
    }
    src = NaverSource()
    with patch("core.data_sources.naver.requests.get", return_value=_mock_response(payload)):
        q = src.get_current_quote("111111")
    assert q == {"current_price": 10000, "change_pct": 0.0}
