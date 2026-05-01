"""
tests/test_etf_source.py — ETF 데이터 소스 단위 테스트.
"""
from __future__ import annotations

import pandas as pd
from unittest.mock import patch

from core.data_sources.pykrx import PykrxSource


def _make_ohlcv_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "시가": [10000],
            "고가": [10100],
            "저가": [9900],
            "종가": [10050],
            "거래량": [500000],
        },
        index=pd.to_datetime(["2026-05-01"]),
    )


def test_get_tickers_etf_uses_etf_api():
    mock_etf_tickers = ["379800", "069500", "152100"]
    with patch("pykrx.stock.get_etf_ticker_list", return_value=mock_etf_tickers) as mock_fn:
        src = PykrxSource()
        result = src.get_tickers("ETF", "20260501")
    mock_fn.assert_called_once_with("20260501")
    assert result == mock_etf_tickers


def test_get_ohlcv_etf_fallback_when_stock_api_empty():
    empty_df = pd.DataFrame()
    etf_df = _make_ohlcv_df()
    with (
        patch("pykrx.stock.get_market_ohlcv_by_date", return_value=empty_df),
        patch("pykrx.stock.get_etf_ohlcv_by_date", return_value=etf_df) as mock_etf,
    ):
        src = PykrxSource()
        result = src.get_ohlcv("379800", "20260401", "20260501")
    mock_etf.assert_called_once_with("20260401", "20260501", "379800")
    assert not result.empty
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
