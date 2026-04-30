"""
core/data_sources/fdr.py — FinanceDataReader 기반 fallback 소스.

기존 daily_only_scanner.py L107-140에서 추출.
"""
from __future__ import annotations

from typing import List

import pandas as pd

from .base import DailyDataSource


class FDRSource(DailyDataSource):
    name = "FinanceDataReader"

    def get_tickers(self, market: str, target_date: str) -> List[str]:
        import FinanceDataReader as fdr
        df = fdr.StockListing(market)
        return df["Code"].tolist()

    def get_ticker_name(self, ticker: str) -> str:
        import FinanceDataReader as fdr
        # KOSPI 전체에서 찾기 (캐시 권장)
        try:
            df = fdr.StockListing("KRX")  # KOSPI+KOSDAQ
            row = df[df["Code"] == ticker]
            if not row.empty:
                return row.iloc[0]["Name"]
        except Exception:
            pass
        return ticker

    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        import FinanceDataReader as fdr
        # FDR은 YYYY-MM-DD 형식 선호
        start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
        end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
        df = fdr.DataReader(ticker, start_fmt, end_fmt)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Volume": "volume",
        })
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume"]].astype(float)
