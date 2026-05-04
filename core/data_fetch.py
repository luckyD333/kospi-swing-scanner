"""
core/data_fetch.py — 일봉/분봉 데이터 fetch + 메모리/디스크 캐시 (Naver 단일 소스).

설계 결정:
  - 데이터 소스: 네이버 금융만 사용 (sise_market_sum + siseJson API).
  - 메모리 캐시: per-run dict (in-process). 같은 (ticker, tf, start, end) 키 재요청 시 fetch 생략.
  - 디스크 캐시 (opt-in via `disk=`): `.cache/ohlcv/{tf}/{ticker}.parquet` 영속화.
    warm 캐시면 last_cached+1 ~ end 만 incremental gap fetch.
  - 디스크 캐시 default OFF — `OhlcvCache(client)` 만 호출하면 기존 메모리 동작 그대로.
"""
from __future__ import annotations

import logging

import pandas as pd

from .cache.ohlcv_disk import OhlcvDiskCache
from .data_sources.base import DailyDataSource
from .data_sources.naver import NaverSource

logger = logging.getLogger(__name__)


class DataClient:
    """
    네이버 단일 소스로 일봉/분봉 데이터 공급.

    역할 분담:
      - 종목 리스트 (유니버스): 네이버 sise_market_sum 크롤링
      - 추정 시총: 네이버 시총 페이지 (크롤링 raw 값)
      - 과거 OHLCV (1D/1m): 네이버 siseJson (수정주가, 1회 호출로 N일)

    `ticker_list_sources` / `ohlcv_sources` 인자는 테스트용 주입 hook.
    Production 사용에서는 default(네이버 단일)을 그대로 사용.
    """

    def __init__(
        self,
        ticker_list_sources: list[DailyDataSource] | None = None,
        ohlcv_sources: list[DailyDataSource] | None = None,
    ):
        # NaverSource 인스턴스 공유 (크롤링 결과 캐시 공유)
        naver = NaverSource()
        self.ticker_list_sources = ticker_list_sources or [naver]
        self.ohlcv_sources = ohlcv_sources or [naver]

    def get_tickers(self, market: str, target_date: str) -> list[str]:
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

    def get_fundamentals(self, market: str, target_date: str) -> pd.DataFrame:
        """펀더멘털 (PER/ROE/외인비율/naver_url) DataFrame. 미지원 source는 빈 결과."""
        for src in self.ticker_list_sources:
            try:
                df = src.get_fundamentals(market, target_date)
                if not df.empty:
                    return df
            except Exception:
                continue
        return pd.DataFrame(columns=["per", "roe", "foreign_pct", "naver_url"])

    def get_ticker_name(self, ticker: str) -> str:
        for src in self.ticker_list_sources:
            try:
                name = src.get_ticker_name(ticker)
                if name and name != ticker:
                    return name
            except Exception:
                continue
        return ticker

    def get_ohlcv(
        self, ticker: str, start: str, end: str, timeframe: str = "1D"
    ) -> pd.DataFrame:
        last_err = None
        for src in self.ohlcv_sources:
            try:
                df = self._call_ohlcv(src, ticker, start, end, timeframe)
                if not df.empty:
                    return df
            except NotImplementedError:
                # 이 소스가 timeframe 미지원 → 다음 소스로
                continue
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        return pd.DataFrame()

    def get_ohlcv_with_source(
        self, ticker: str, start: str, end: str, timeframe: str = "1D"
    ) -> tuple[str, pd.DataFrame]:
        """OHLCV 및 소스명을 함께 반환. fallback 체인에서 성공한 소스명 포함."""
        last_err = None
        for src in self.ohlcv_sources:
            try:
                df = self._call_ohlcv(src, ticker, start, end, timeframe)
                if not df.empty:
                    return (src.name, df)
            except NotImplementedError:
                continue
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        return ("", pd.DataFrame())

    @staticmethod
    def _call_ohlcv(
        src: DailyDataSource, ticker: str, start: str, end: str, timeframe: str
    ) -> pd.DataFrame:
        """Source 가 timeframe kwarg 미지원이어도 backward-compat 호출."""
        try:
            return src.get_ohlcv(ticker, start, end, timeframe=timeframe)
        except TypeError:
            # legacy source 가 timeframe 인자 미지원 → 1D 만 가능
            if timeframe != "1D":
                raise NotImplementedError(
                    f"{src.name}: legacy source, timeframe={timeframe!r} 미지원"
                )
            return src.get_ohlcv(ticker, start, end)


class OhlcvCache:
    """
    Memory + (선택) 디스크 캐시. (ticker, timeframe, start, end) 키 재요청 시 fetch 1회만.

    `disk=` 미주입 시: 기존 per-run 메모리 dict 동작 (회귀 보호).
    `disk=OhlcvDiskCache(...)` 주입 시:
      - cold: 전체 [start,end] fetch → 디스크 저장
      - warm: 디스크에 (ticker,tf) 파일 존재 → last_cached+1 ~ end 만 incremental fetch + append
    """

    def __init__(
        self,
        client: DataClient,
        disk: OhlcvDiskCache | None = None,
    ):
        self._client = client
        self._disk = disk
        self._cache: dict[tuple[str, str, str, str], pd.DataFrame] = {}
        self._source_cache: dict[tuple[str, str, str, str], str] = {}
        self._fetch_count = 0
        self._hit_count = 0

    def get_or_fetch(
        self,
        ticker: str,
        start: str,
        end: str,
        timeframe: str = "1D",
    ) -> pd.DataFrame:
        """
        캐시 hit 시 사본 반환(원본 보호), miss 시 fetch 후 저장.

        반환되는 DataFrame 은 매번 새 사본이라 호출자가 수정해도 캐시 보존.
        """
        key = (ticker, timeframe, start, end)
        cached = self._cache.get(key)
        if cached is not None:
            self._hit_count += 1
            return cached.copy()

        df = self._fetch_with_disk(ticker, start, end, timeframe)
        self._cache[key] = df
        self._fetch_count += 1
        return df.copy()

    def get_or_fetch_with_source(
        self,
        ticker: str,
        start: str,
        end: str,
        timeframe: str = "1D",
    ) -> tuple[str, pd.DataFrame]:
        """
        캐시 hit 시 사본과 소스명을 함께 반환, miss 시 fetch 후 저장.
        소스명도 함께 캐시하여 hit 시 소스 정보 유지.
        """
        key = (ticker, timeframe, start, end)
        cached = self._cache.get(key)
        if cached is not None:
            self._hit_count += 1
            source = self._source_cache.get(key, "unknown")
            return (source, cached.copy())

        if self._disk is None:
            source, df = self._client.get_ohlcv_with_source(ticker, start, end)
        else:
            df = self._fetch_with_disk(ticker, start, end, timeframe)
            source = "disk" if not df.empty else "unknown"
        self._cache[key] = df
        self._source_cache[key] = source
        self._fetch_count += 1
        return (source, df.copy())

    def _fetch_with_disk(
        self, ticker: str, start: str, end: str, timeframe: str
    ) -> pd.DataFrame:
        """디스크 hit 이면 incremental, miss 이면 full fetch + 디스크 저장.

        timeframe 은 client/디스크 양쪽에 일관되게 전달. 1m timeframe 일 때는
        gap_start 를 분 단위로 계산해 분봉 raw 가 분 단위 incremental 로 누적.
        caller 가 YYYYMMDD 로만 줘도 1m 의 경우 자동 normalize.
        """
        if timeframe == "1m":
            if len(start) == 8:
                start = f"{start}0000"
            if len(end) == 8:
                end = f"{end}2359"
        if self._disk is None:
            return self._client.get_ohlcv(ticker, start, end, timeframe=timeframe)

        cached_disk = self._disk.read(ticker, timeframe)
        if cached_disk.empty:
            df = self._client.get_ohlcv(ticker, start, end, timeframe=timeframe)
            self._disk.write(ticker, timeframe, df)
            return df

        # warm: gap 만 fetch
        last = cached_disk.index.max()
        if timeframe == "1m":
            gap_start_dt = last + pd.Timedelta(minutes=1)
            gap_start = gap_start_dt.strftime("%Y%m%d%H%M")
        else:
            gap_start_dt = last + pd.Timedelta(days=1)
            gap_start = gap_start_dt.strftime("%Y%m%d")
        if gap_start <= end:
            new = self._client.get_ohlcv(
                ticker, gap_start, end, timeframe=timeframe
            )
            if not new.empty:
                cached_disk = self._disk.append(ticker, timeframe, new)
        # 요청 [start,end] 범위로 슬라이스
        return cached_disk.loc[start:end]

    @property
    def stats(self) -> dict[str, int]:
        return {
            "fetch_count": self._fetch_count,
            "hit_count": self._hit_count,
            "size": len(self._cache),
        }

    def clear(self) -> None:
        self._cache.clear()
        self._fetch_count = 0
        self._hit_count = 0
