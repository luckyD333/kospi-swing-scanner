"""
core/data_sources/base.py — 일봉 데이터 소스 추상 인터페이스.

기존 daily_only_scanner.py L51-69에서 추출.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DailyDataSource(ABC):
    """일봉 데이터 소스 인터페이스"""
    name: str = "base"

    @abstractmethod
    def get_tickers(self, market: str, target_date: str) -> list[str]:
        ...

    @abstractmethod
    def get_ticker_name(self, ticker: str) -> str:
        ...

    @abstractmethod
    def get_ohlcv(
        self, ticker: str, start: str, end: str, timeframe: str = "1D"
    ) -> pd.DataFrame:
        """
        OHLCV 시계열 반환. `timeframe`:
          - "1D": 일봉 (모든 소스 지원)
          - "1m": 1분봉 (NaverSource 만 지원, 그 외엔 NotImplementedError 또는 빈 DF)
        """
        ...

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """선택적. 구현 안 하면 빈 DataFrame 반환"""
        return pd.DataFrame()

    def get_fundamentals(self, market: str, target_date: str) -> pd.DataFrame:
        """
        펀더멘털 데이터 (PER/ROE/외국인비율/naver_url) 반환.

        선택적 인터페이스. 구현 안 하면 빈 DataFrame 반환 — 호출 측은 비어 있어도
        동작해야 한다.

        반환 컬럼: per, roe, foreign_pct, naver_url (모두 None 가능, JSON 호환).
        인덱스는 ticker.
        """
        return pd.DataFrame(columns=["per", "roe", "foreign_pct", "naver_url"])

    def get_etf_list(self, target_date: str) -> set[str]:
        """ETF/ETN itemcode 통합 명단. ProductType 분류용 (PR-B).

        선택적 인터페이스. 구현 안 하면 빈 set 반환 — 분류기가 이름 키워드/코드
        prefix 만으로 동작 (UNKNOWN 폴백 빈도 ↑).
        """
        return set()
