"""
core/data_sources/base.py — 일봉 데이터 소스 추상 인터페이스.

기존 daily_only_scanner.py L51-69에서 추출.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

import pandas as pd


class DailyDataSource(ABC):
    """일봉 데이터 소스 인터페이스"""
    name: str = "base"

    @abstractmethod
    def get_tickers(self, market: str, target_date: str) -> List[str]:
        ...

    @abstractmethod
    def get_ticker_name(self, ticker: str) -> str:
        ...

    @abstractmethod
    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        ...

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """선택적. 구현 안 하면 빈 DataFrame 반환"""
        return pd.DataFrame()
