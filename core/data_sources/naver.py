"""
core/data_sources/naver.py — 네이버 금융 일봉 + 종목 리스트 소스.

기존 daily_only_scanner.py L693-888에서 추출 (NaverSource).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Dict, List

import pandas as pd
import requests

from .base import DailyDataSource

logger = logging.getLogger(__name__)


class NaverSource(DailyDataSource):
    """
    네이버 금융 전용 소스. 일봉 OHLCV + 전종목 리스트 모두 지원.

    데이터 경로:
      - 일봉: api.finance.naver.com/siseJson.naver (수정주가)
      - 종목리스트/시총: finance.naver.com/sise/sise_market_sum.naver (페이지 크롤링)
    """
    name = "naver"
    OHLCV_URL = "https://api.finance.naver.com/siseJson.naver"
    MARKET_SUM_URL = "https://finance.naver.com/sise/sise_market_sum.naver"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 시장 코드: KOSPI=0, KOSDAQ=1
    MARKET_CODE = {"KOSPI": 0, "KOSDAQ": 1}

    def __init__(self):
        self._ticker_cache: Dict[str, Dict] = {}   # ticker → {name, market_cap}
        self._market_cached: Dict[str, bool] = {}  # market → cached?

    def get_tickers(self, market: str, target_date: str) -> List[str]:
        """
        네이버 시가총액 페이지에서 전종목 크롤링.

        페이지 1부터 마지막 페이지까지 순회하며 pd.read_html로 파싱.
        결과는 _ticker_cache에 저장하여 시총/이름 조회에 재사용.
        """
        self._crawl_market_sum(market)
        return [t for t, info in self._ticker_cache.items() if info["market"] == market]

    def get_ticker_name(self, ticker: str) -> str:
        info = self._ticker_cache.get(ticker)
        if info:
            return info["name"]
        return ticker

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """pykrx 호환 형식으로 시가총액 DataFrame 반환"""
        self._crawl_market_sum(market)
        rows = {}
        for ticker, info in self._ticker_cache.items():
            if info["market"] != market:
                continue
            rows[ticker] = {
                "시가총액": info["market_cap"],  # 원 단위
                "종목명": info["name"],
            }
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).T
        df.index.name = "티커"
        return df

    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """네이버 siseJson API로 일봉 (수정주가) 조회"""
        params = {
            "symbol": ticker,
            "requestType": 1,
            "startTime": start,
            "endTime": end,
            "timeframe": "day",
        }
        r = requests.get(self.OHLCV_URL, params=params,
                         headers=self.HEADERS, timeout=10)
        r.raise_for_status()
        text = r.text.strip().replace("'", '"')
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"  [네이버] OHLCV JSON 파싱 실패 ({e})")
            return pd.DataFrame()
        if len(raw) < 2:
            return pd.DataFrame()

        cols = raw[0]
        rows = raw[1:]
        df = pd.DataFrame(rows, columns=cols)
        df = df.rename(columns={
            "날짜": "date", "시가": "open", "고가": "high",
            "저가": "low", "종가": "close", "거래량": "volume",
        })
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df = df.set_index("date")
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    # ------------------------------------------------------------------
    # 전종목 리스트 크롤링 (내부 helper)
    # ------------------------------------------------------------------

    def _crawl_market_sum(self, market: str):
        """
        sise_market_sum 페이지를 페이지 단위로 순회.

        페이지 구조:
          https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1

          - sosok=0: KOSPI, sosok=1: KOSDAQ
          - 각 페이지에 ~50개 종목, KOSPI는 대략 20페이지 이내
          - pd.read_html()로 테이블 파싱
        """
        if self._market_cached.get(market):
            return
        if market not in self.MARKET_CODE:
            raise ValueError(f"unsupported market: {market}. KOSPI/KOSDAQ만 지원")

        sosok = self.MARKET_CODE[market]
        from bs4 import BeautifulSoup

        logger.info(f"  [네이버] {market} 전종목 크롤링 시작...")

        page = 1
        total = 0
        while True:
            url = f"{self.MARKET_SUM_URL}?sosok={sosok}&page={page}"
            try:
                r = requests.get(url, headers=self.HEADERS, timeout=10)
                r.raise_for_status()
            except Exception as e:
                logger.warning(f"  page {page} 실패: {e}")
                break

            # pd.read_html로 메인 테이블(시총 랭킹) 파싱
            try:
                tables = pd.read_html(r.text)
                # 시총 테이블은 보통 index=1 (or 2). "N" 컬럼(순번) 있는 것 선택
                df = None
                for t in tables:
                    cols = list(t.columns)
                    if "종목명" in cols and "현재가" in cols and "시가총액" in cols:
                        df = t.dropna(subset=["종목명"])
                        break
                if df is None or df.empty:
                    break
            except ValueError:
                break

            # 각 행에서 종목코드 추출 (테이블에는 이름만 있어서 a 태그에서 파싱)
            soup = BeautifulSoup(r.text, "html.parser")
            code_pairs = []
            for a in soup.select("table.type_2 a.tltle"):
                href = a.get("href", "")
                if "code=" in href:
                    code = href.split("code=")[-1].split("&")[0]
                    code_pairs.append((code, a.text.strip()))

            if not code_pairs:
                break

            # DataFrame 행과 code_pairs 매칭
            # (테이블 순서와 a 태그 순서가 일치)
            if len(code_pairs) != len(df):
                logger.warning(
                    f"  [네이버] page {page}: code_pairs({len(code_pairs)}) != "
                    f"df rows({len(df)}), 이 페이지 skip"
                )
                page += 1
                continue
            for (code, name), (_, row) in zip(code_pairs, df.iterrows()):
                try:
                    market_cap = self._parse_market_cap(row.get("시가총액"))
                except Exception:
                    market_cap = 0.0

                self._ticker_cache[code] = {
                    "name": name,
                    "market": market,
                    "market_cap": market_cap,
                }
                total += 1

            # 마지막 페이지 확인: 다음 페이지 링크 있는지
            has_next = bool(soup.select_one("td.pgRR a"))
            # 또는 페이지가 10페이지 넘어도 신규 종목이 안 추가되면 stop
            if not has_next and page > 1:
                break
            if len(code_pairs) < 10:  # 페이지당 50개 기준, 많이 적으면 마지막
                break
            page += 1
            if page > 50:  # 안전장치
                break
            time.sleep(0.2)  # 네이버 rate limit 고려

        self._market_cached[market] = True
        logger.info(f"  [네이버] {market} 크롤링 완료: {total}종목")

    @staticmethod
    def _parse_market_cap(raw) -> float:
        """네이버 시가총액 문자열 → 원 단위 float"""
        if pd.isna(raw):
            return 0.0
        s = str(raw).replace(",", "").strip()
        # 네이버는 "억" 단위로 표시 (예: "3,500,000" = 350조)
        try:
            return float(s) * 100_000_000  # 억 → 원
        except ValueError:
            return 0.0
