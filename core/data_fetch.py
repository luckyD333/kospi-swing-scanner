"""
core/data_fetch.py — 일봉 데이터 fetch + 메모리 캐시.

기존 daily_only_scanner.py L893-977 의 DataClient 를 그대로 추출하고,
멀티 전략 공유용 OhlcvCache 를 추가한다.

설계 결정:
  - 캐시는 per-run 메모리 dict (in-process)
  - 같은 ticker(start, end) 키가 다시 들어오면 fetch 생략 → 단일 fetch 보장
  - disk cache 는 별도 plan
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .data_sources.base import DailyDataSource
from .data_sources.fdr import FDRSource
from .data_sources.krx_proxy import KRXProxySource
from .data_sources.naver import NaverSource
from .data_sources.pykrx import PykrxSource

logger = logging.getLogger(__name__)


class DataClient:
    """
    Fallback 체인으로 일봉 데이터 안정 공급.

    역할 분담:
      - 종목 리스트 (유니버스): 네이버 sise_market_sum → pykrx → FDR
      - 유니버스 시총 보강 (선택): KRX Proxy trade-info (공식 데이터)
      - 과거 일봉 OHLCV (지표 계산용): 네이버 siseJson (수정주가, 1회 호출로 N일)
      - 당일 검증 (선택): KRX Proxy trade-info (공식 종가/거래량)

    strict_mode=True일 때:
      - KRX Proxy에서 Circuit Breaker OPEN 또는 실패율 초과 → 스캔 전체 중단
      - 데이터 불완전한 상태로 진입 시그널 내지 않음 (실전 안전)
    strict_mode=False (기본):
      - KRX 실패 시 네이버/pykrx로 fallback (개발/테스트 편의)
    """

    def __init__(
        self,
        ticker_list_sources: Optional[List[DailyDataSource]] = None,
        ohlcv_sources: Optional[List[DailyDataSource]] = None,
        krx_proxy: Optional[KRXProxySource] = None,
        use_krx_for_universe: bool = True,
        strict_mode: bool = False,
    ):
        # NaverSource 인스턴스 공유 (크롤링 결과 캐시 공유)
        naver = NaverSource()

        # 종목 리스트: 네이버 주력 (수정주가 + 무료 + 인증 불필요)
        self.ticker_list_sources = ticker_list_sources or [
            naver, PykrxSource(), FDRSource(),
        ]
        # OHLCV 시계열: 네이버 주력 (한 번 호출로 N일치)
        self.ohlcv_sources = ohlcv_sources or [
            naver, PykrxSource(), FDRSource(),
        ]

        # KRX Proxy: 공식 데이터 보강용
        self.krx_proxy = krx_proxy or KRXProxySource()
        self.use_krx_for_universe = use_krx_for_universe
        self.strict_mode = strict_mode

    def get_tickers(self, market: str, target_date: str) -> List[str]:
        for src in self.ticker_list_sources:
            try:
                tickers = src.get_tickers(market, target_date)
                if tickers:
                    logger.info(f"  종목 리스트 소스: {src.name} ({len(tickers)}개)")
                    return tickers
            except Exception as e:
                logger.warning(f"  {src.name} 실패: {e}")
        raise RuntimeError("모든 종목 리스트 소스 실패")

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        for src in self.ticker_list_sources:
            try:
                df = src.get_market_cap(market, target_date)
                if not df.empty:
                    return df
            except Exception:
                continue
        return pd.DataFrame()

    def get_ticker_name(self, ticker: str) -> str:
        for src in self.ticker_list_sources:
            try:
                name = src.get_ticker_name(ticker)
                if name and name != ticker:
                    return name
            except Exception:
                continue
        return ticker

    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        last_err = None
        for src in self.ohlcv_sources:
            try:
                df = src.get_ohlcv(ticker, start, end)
                if not df.empty:
                    return df
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        return pd.DataFrame()


class OhlcvCache:
    """
    Per-run 메모리 캐시. 같은 (ticker, start, end) 조합은 fetch 1회만 수행.

    멀티 전략 실행 시 각 전략이 동일 OHLCV를 요구해도 fetch 호출은 1회로 제한된다
    ("단일 fetch 후 메모리 공유" 제약 충족).

    주의: 단일 ScanRunner.run() 안에서만 유효. 새 인스턴스를 생성하면 캐시는 비어 있다.
    """

    def __init__(self, client: DataClient):
        self._client = client
        self._cache: Dict[Tuple[str, str, str], pd.DataFrame] = {}
        self._fetch_count = 0
        self._hit_count = 0

    def get_or_fetch(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        캐시 hit 시 사본 반환(원본 보호), miss 시 fetch 후 저장.

        반환되는 DataFrame 은 매번 새 사본이라 호출자가 수정해도 캐시 보존.
        """
        key = (ticker, start, end)
        cached = self._cache.get(key)
        if cached is not None:
            self._hit_count += 1
            return cached.copy()

        df = self._client.get_ohlcv(ticker, start, end)
        self._cache[key] = df
        self._fetch_count += 1
        return df.copy()

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "fetch_count": self._fetch_count,
            "hit_count": self._hit_count,
            "size": len(self._cache),
        }

    def clear(self) -> None:
        self._cache.clear()
        self._fetch_count = 0
        self._hit_count = 0
