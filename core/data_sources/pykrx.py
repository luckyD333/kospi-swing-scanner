"""
core/data_sources/pykrx.py — pykrx 기반 일봉 데이터 소스.

기존 daily_only_scanner.py L74-102에서 추출.
"""
from __future__ import annotations


import pandas as pd

from .base import DailyDataSource


class PykrxSource(DailyDataSource):
    name = "pykrx"

    def get_tickers(self, market: str, target_date: str) -> list[str]:
        from pykrx import stock
        if market == "ETF":
            return stock.get_etf_ticker_list(target_date)
        return stock.get_market_ticker_list(target_date, market=market)

    def get_ticker_name(self, ticker: str) -> str:
        from pykrx import stock
        return stock.get_market_ticker_name(ticker)

    def get_ohlcv(
        self, ticker: str, start: str, end: str, timeframe: str = "1D"
    ) -> pd.DataFrame:
        if timeframe != "1D":
            raise NotImplementedError(
                f"PykrxSource: timeframe={timeframe!r} 미지원 (일봉만)"
            )
        from pykrx import stock
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        if df is None or df.empty:
            df = stock.get_etf_ohlcv_by_date(start, end, ticker)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "시가": "open", "고가": "high", "저가": "low",
            "종가": "close", "거래량": "volume",
        })
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        from pykrx import stock
        df = stock.get_market_cap_by_ticker(target_date, market=market)
        if df is None or df.empty:
            return pd.DataFrame()
        return df
