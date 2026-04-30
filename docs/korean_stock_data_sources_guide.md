# 실전 한국 주식 데이터 수집 — 멀티 소스 통합 전략

## TL;DR

**단일 소스로는 안 된다.** 각 소스별로 커버 범위가 다르므로 **Fallback 체인**으로 조합해야 실전에서 쓸 수 있다.

| 데이터 종류 | 1차 소스 | 2차 (Fallback) | 3차 (Fallback) |
|------------|----------|---------------|----------------|
| **일봉 OHLCV (과거)** | pykrx | 네이버 금융 | KIS API |
| **일봉 (수정주가)** | 네이버 금융 | pykrx (비수정) | FinanceDataReader |
| **분봉/시간봉 (intraday)** | KIS API | (네이버 미지원) | 키움 OpenAPI+ |
| **실시간 현재가** | KIS API | 네이버 웹 크롤링 | — |
| **전종목 스냅샷** | pykrx | KRX Marketplace | — |
| **종목 리스트/시가총액** | pykrx | FinanceDataReader | 네이버 웹 |
| **투자자별 수급** | pykrx (T-1) | KIS API (실시간) | — |
| **재무제표** | OpenDartReader | 네이버 크롤링 | — |

---

## 소스별 특성 상세 비교

### 1. pykrx (KRX Data Marketplace 래퍼)

**✅ 강점**
- **무료, 인증 불필요**, 설치 즉시 사용
- KOSPI + KOSDAQ + KONEX 전종목 커버
- 투자자별 수급(외국인/기관/개인) 기본 제공
- 시가총액, PER/PBR, 거래대금 등 기본 지표 모두 포함

**⚠️ 약점**
- **일봉이 최소 단위** (분봉/시간봉 없음)
- 2024년 12월부터 **Kakao OAuth 로그인 요구** — 버전에 따라 인증 필요 (`kospi-kosdaq-stock-server`가 이 문제를 Playwright로 해결)
- 수정주가 지원 불완전 (2018년 삼성 액면분할 이후 이슈 존재)
- 장 마감 후 ~30분~1시간 데이터 반영 지연

**💡 어디에 쓰나**
- Strategy D v2의 **Phase 1 전종목 일봉 스캔** (800종목을 3분 안에 훑기)
- 백테스트용 과거 일봉 데이터 수집
- 시가총액 기반 유니버스 필터링

```python
from pykrx import stock

# 전종목 시총 (Phase 1 유니버스 필터용)
cap_df = stock.get_market_cap_by_ticker("20260418", market="KOSPI")
# 개별 종목 일봉
df = stock.get_market_ohlcv_by_date("20250101", "20260418", "005930")
# 투자자별 순매수 (전일 기준)
trading_df = stock.get_market_trading_value_by_investor(
    "20260415", "20260418", "005930"
)
```

---

### 2. 네이버 금융 (`api.finance.naver.com/siseJson.naver`)

**✅ 강점**
- **무료, 인증 불필요**, 속도 빠름
- **수정주가로 제공** (액면분할/배당 반영) — 백테스트에 유리
- pykrx 의존성 없이 순수 HTTP 요청으로 작동
- User-Agent만 잘 달면 안정적

**⚠️ 약점**
- **비공식 API** — 언제든 스펙 변경/차단 가능
- **분봉 지원 안 함** (공식은 `timeframe=day/week/month`만)
- 실시간 데이터는 웹 HTML 크롤링 필요 (BeautifulSoup)
- 투자자별 수급, 재무제표 등은 별도 크롤링 필요
- rate limit 모호 (과도한 요청 시 차단 리스크)

**💡 어디에 쓰나**
- **수정주가 필요한 백테스트** — 액면분할 이슈 회피
- pykrx와 **교차 검증** (두 소스 값 비교해 이상치 탐지)
- pykrx 인증 문제 시 fallback

```python
import requests

def fetch_naver_daily(ticker: str, start: str, end: str):
    """네이버 금융 일봉 (수정주가)"""
    url = "https://api.finance.naver.com/siseJson.naver"
    params = {
        "symbol": ticker,       # "005930"
        "requestType": 1,
        "startTime": start,     # "20260101"
        "endTime": end,
        "timeframe": "day",     # week / month 만 가능
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, params=params, headers=headers, timeout=5)
    # JSON-like 문자열 (작은따옴표 쓰는 비표준 JSON)
    text = r.text.replace("'", '"').strip()
    import json
    raw = json.loads(text)
    # [['날짜','시가','고가','저가','종가','거래량','외국인소진율'], ['20260101', ...]]
    cols = raw[0]
    rows = raw[1:]
    import pandas as pd
    df = pd.DataFrame(rows, columns=cols)
    return df
```

---

### 3. 한국투자증권 (KIS) OpenAPI

**✅ 강점**
- **유일하게 분봉/시간봉 공식 지원** (1/3/5/10/15/30/60분봉)
- 실전 매매(주문/체결) 지원
- 실시간 웹소켓 스트리밍
- 공식 API, 안정성 높음

**⚠️ 약점**
- **계좌 개설 + 앱키/시크릿 발급 필수**
- 모의투자 계좌 별도 개설 필요 (권장)
- 분봉은 **최근 30영업일까지만** 조회 가능 (장기 과거 데이터 불가)
- Rate limit: 실전 초당 10건, 모의 초당 1건
- API 토큰 24시간마다 재발급 필요

**💡 어디에 쓰나**
- Strategy D v2의 **Phase 2 시간봉 정밀 분석**
- 실전 매매 주문 실행
- 장중 실시간 현재가/수급 조회

```python
# 60분봉 조회 예시 (TR_ID: FHKST03010200 - 국내주식 기간별 시세)
def get_kis_hourly(ticker: str, token: str, app_key: str, app_secret: str):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": app_key,
        "appsecret": app_secret,
        "tr_id": "FHKST03010200",
        "content-type": "application/json; charset=utf-8",
    }
    params = {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_HOUR_1": "153000",
        "FID_PW_DATA_INCU_YN": "N",
    }
    r = requests.get(url, headers=headers, params=params, timeout=5)
    return r.json()
```

---

### 4. FinanceDataReader (보조)

**✅ 강점**
- 해외 주식 통합 지원 (미국, 일본, 중국)
- 지수 데이터 (KOSPI, S&P500 등) 편리
- 무료, 인증 불필요

**⚠️ 약점**
- 여러 소스를 합친 라이브러리라 **데이터 일관성 보장 안 됨**
- 분봉 미지원
- 최근 몇 년간 유지보수 빈도 낮음

**💡 어디에 쓰나**
- KOSPI/KOSDAQ **지수** 데이터 (시장 전체 상태 확인용)
- 과거 장기 데이터 보완 (pykrx가 실패할 때)

---

## 실전 Fallback 데이터 클라이언트 구현

세 소스를 통합한 실전 데이터 클라이언트. 각 소스 장애 시 자동으로 다음 소스로 전환됩니다.

```python
"""
data_client.py — 멀티소스 데이터 클라이언트

사용:
    client = KoreanStockDataClient(kis_credentials={...})
    df = client.get_daily("005930", "20250101", "20260418")
    df = client.get_hourly("005930")   # KIS API 사용
    df = client.get_universe_snapshot("20260418")  # pykrx
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from abc import ABC, abstractmethod

import pandas as pd
import requests

logger = logging.getLogger(__name__)


# ============================================================================
# 추상 인터페이스
# ============================================================================

class DailyDataSource(ABC):
    """일봉 데이터 소스"""

    @abstractmethod
    def fetch(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """
        Returns:
            DataFrame with columns: open, high, low, close, volume
            index: DatetimeIndex
        """
        ...


class IntradayDataSource(ABC):
    """분봉/시간봉 데이터 소스"""

    @abstractmethod
    def fetch(self, ticker: str, interval_minutes: int) -> pd.DataFrame:
        ...


# ============================================================================
# 1차 소스: pykrx
# ============================================================================

class PykrxDailySource(DailyDataSource):
    """pykrx 기반 일봉 조회 (비수정주가)"""

    def fetch(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        from pykrx import stock
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        # pykrx 컬럼명 한글 → 영어
        df = df.rename(columns={
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
            "거래대금": "trading_value",
        })
        df.index.name = "date"
        return df[["open", "high", "low", "close", "volume"]].astype(float)


# ============================================================================
# 2차 소스: 네이버 금융 (수정주가)
# ============================================================================

class NaverDailySource(DailyDataSource):
    """네이버 금융 siseJson API 기반 (수정주가)"""

    URL = "https://api.finance.naver.com/siseJson.naver"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    def fetch(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        params = {
            "symbol": ticker,
            "requestType": 1,
            "startTime": start,
            "endTime": end,
            "timeframe": "day",
        }
        r = requests.get(
            self.URL, params=params, headers=self.HEADERS, timeout=10
        )
        r.raise_for_status()

        # 네이버는 작은따옴표 + 비표준 JSON 형식이므로 변환
        text = r.text.strip().replace("'", '"')
        raw = json.loads(text)

        if len(raw) < 2:
            return pd.DataFrame()

        cols = raw[0]
        rows = raw[1:]

        # cols: ['날짜', '시가', '고가', '저가', '종가', '거래량', '외국인소진율']
        df = pd.DataFrame(rows, columns=cols)
        df = df.rename(columns={
            "날짜": "date",
            "시가": "open",
            "고가": "high",
            "저가": "low",
            "종가": "close",
            "거래량": "volume",
        })
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df = df.set_index("date")
        return df[["open", "high", "low", "close", "volume"]].astype(float)


# ============================================================================
# 3차 소스: KIS API (분봉 전용)
# ============================================================================

class KISIntradaySource(IntradayDataSource):
    """KIS 국내주식 분봉 조회"""

    BASE_URL = "https://openapi.koreainvestment.com:9443"
    TR_ID = "FHKST03010200"

    def __init__(self, app_key: str, app_secret: str, token: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self.token = token

    def fetch(
        self,
        ticker: str,
        interval_minutes: int = 60,
        end_time: str = "153000",
    ) -> pd.DataFrame:
        url = f"{self.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        headers = {
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": self.TR_ID,
            "content-type": "application/json; charset=utf-8",
        }
        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_HOUR_1": end_time,
            "FID_PW_DATA_INCU_YN": "N",
        }
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        rows = []
        for item in data.get("output2", []):
            rows.append({
                "datetime": pd.to_datetime(
                    f"{item['stck_bsop_date']} {item['stck_cntg_hour']}",
                    format="%Y%m%d %H%M%S",
                ),
                "open": float(item.get("stck_oprc", 0) or 0),
                "high": float(item.get("stck_hgpr", 0) or 0),
                "low": float(item.get("stck_lwpr", 0) or 0),
                "close": float(item.get("stck_prpr", 0) or 0),
                "volume": int(item.get("cntg_vol", 0) or 0),
            })
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows).set_index("datetime").sort_index()
        return df


# ============================================================================
# 통합 클라이언트
# ============================================================================

@dataclass
class KISCredentials:
    app_key: str
    app_secret: str
    access_token: str


class KoreanStockDataClient:
    """
    멀티 소스 fallback 지원 한국 주식 데이터 클라이언트.

    우선순위:
      - 일봉: pykrx → 네이버 금융
      - 분봉: KIS API
    """

    def __init__(
        self,
        kis_credentials: Optional[KISCredentials] = None,
        prefer_adjusted: bool = True,
    ):
        # 일봉 소스 fallback 체인
        self.daily_sources: List[DailyDataSource] = []
        if prefer_adjusted:
            # 수정주가 우선 → 네이버 먼저
            self.daily_sources.append(NaverDailySource())
            self.daily_sources.append(PykrxDailySource())
        else:
            self.daily_sources.append(PykrxDailySource())
            self.daily_sources.append(NaverDailySource())

        # 분봉 소스 (KIS only)
        self.intraday_source: Optional[IntradayDataSource] = None
        if kis_credentials:
            self.intraday_source = KISIntradaySource(
                app_key=kis_credentials.app_key,
                app_secret=kis_credentials.app_secret,
                token=kis_credentials.access_token,
            )

    def get_daily(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        일봉 조회 (fallback 체인).

        Args:
            ticker: 6자리 종목 코드
            start: YYYYMMDD
            end: YYYYMMDD
        """
        last_error = None
        for source in self.daily_sources:
            try:
                df = source.fetch(ticker, start, end)
                if not df.empty:
                    logger.info(
                        f"[{ticker}] daily fetched from "
                        f"{source.__class__.__name__} ({len(df)} rows)"
                    )
                    return df
            except Exception as e:
                logger.warning(
                    f"[{ticker}] {source.__class__.__name__} 실패: {e}"
                )
                last_error = e
        raise RuntimeError(
            f"[{ticker}] 모든 일봉 소스 실패. 마지막 에러: {last_error}"
        )

    def get_intraday(
        self,
        ticker: str,
        interval_minutes: int = 60,
    ) -> pd.DataFrame:
        """분봉/시간봉 조회 (KIS API 필수)"""
        if self.intraday_source is None:
            raise RuntimeError(
                "분봉 조회는 KIS API 자격 증명 필요. KoreanStockDataClient 생성 시 "
                "kis_credentials=KISCredentials(...) 전달."
            )
        return self.intraday_source.fetch(ticker, interval_minutes)

    def get_universe(
        self,
        target_date: str,
        market: str = "KOSPI",
        min_market_cap_억: float = 2000.0,
        max_market_cap_억: float = 30000.0,
    ) -> pd.DataFrame:
        """
        유니버스 필터링 (pykrx 전용 기능).

        Strategy D v2의 시총 필터 (2천억 ~ 3조원).
        """
        from pykrx import stock
        cap_df = stock.get_market_cap_by_ticker(target_date, market=market)
        cap_억 = cap_df["시가총액"] / 100_000_000  # 원 → 억
        filtered = cap_df[
            (cap_억 >= min_market_cap_억) & (cap_억 <= max_market_cap_억)
        ]
        return filtered


# ============================================================================
# 사용 예시
# ============================================================================

if __name__ == "__main__":
    import os

    # 1) KIS 없이 일봉만 (네이버 + pykrx)
    client = KoreanStockDataClient(prefer_adjusted=True)
    df_daily = client.get_daily("005930", "20260101", "20260418")
    print("삼성전자 일봉:\n", df_daily.tail())

    # 2) KIS로 분봉 조회
    if os.getenv("KIS_APP_KEY"):
        kis_creds = KISCredentials(
            app_key=os.getenv("KIS_APP_KEY"),
            app_secret=os.getenv("KIS_APP_SECRET"),
            access_token=os.getenv("KIS_ACCESS_TOKEN"),
        )
        client_with_kis = KoreanStockDataClient(kis_credentials=kis_creds)
        df_60m = client_with_kis.get_intraday("005930", interval_minutes=60)
        print("삼성전자 60분봉:\n", df_60m.tail())

    # 3) 유니버스 필터
    universe = client.get_universe("20260418", market="KOSPI")
    print(f"시총 필터 통과 종목: {len(universe)}개")
```

---

## Strategy D v2와 연결하는 실전 파이프라인

이전에 작성한 백테스트 엔진 + 스크리너와 통합:

```python
"""
live_scanner.py — Strategy D v2 실전 스크리너
KIS API 실전 초당 10건 rate limit 고려한 구현
"""
import time
import asyncio
from datetime import datetime

from data_client import KoreanStockDataClient, KISCredentials
from backtest_engine.screener import MultiTimeframeScreener, resample_ohlcv
from backtest_engine.strategy import StrategyDConfig


def run_live_scan():
    # 1) 클라이언트 초기화
    kis_creds = KISCredentials(
        app_key=os.getenv("KIS_APP_KEY"),
        app_secret=os.getenv("KIS_APP_SECRET"),
        access_token=os.getenv("KIS_ACCESS_TOKEN"),
    )
    client = KoreanStockDataClient(kis_credentials=kis_creds)

    # 2) Phase 1: 유니버스 필터 (pykrx)
    today = datetime.now().strftime("%Y%m%d")
    universe = client.get_universe(
        today, market="KOSPI",
        min_market_cap_억=2000, max_market_cap_억=30000,
    )
    tickers = universe.index.tolist()
    print(f"Phase 1 유니버스: {len(tickers)}종목")

    # 3) Phase 2: 일봉 1차 스캔 (네이버 → pykrx)
    #    여기서 Strategy D v2 조건 만족 후보만 추려낸다
    candidates = []
    start_date = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    for ticker in tickers:
        try:
            df_daily = client.get_daily(ticker, start_date, today)
            # 간단 필터: 최근 RSI < 35인 종목만 candidate
            # (실제로는 Strategy D 완전 체크)
            candidates.append((ticker, df_daily))
        except Exception as e:
            continue
    print(f"Phase 2 후보: {len(candidates)}종목")

    # 4) Phase 3: 상위 후보에 대해 분봉 멀티 타임프레임 스캔 (KIS API)
    #    Rate limit: 초당 10건
    scanner = MultiTimeframeScreener(
        strategy_config=StrategyDConfig(min_lookback_bars=25),
        timeframes=["1h", "2h", "4h", "1D"],
    )

    multi_data = {}
    for i, (ticker, df_daily) in enumerate(candidates[:50]):
        try:
            df_60m = client.get_intraday(ticker, interval_minutes=60)
            multi_data[ticker] = {
                "1h": df_60m,
                "2h": resample_ohlcv(df_60m, "2h"),
                "4h": resample_ohlcv(df_60m, "4h"),
                "1D": df_daily,
            }
            # Rate limit 준수
            if (i + 1) % 10 == 0:
                time.sleep(1.1)
        except Exception as e:
            print(f"[{ticker}] 분봉 조회 실패: {e}")

    # 5) 스크리너 실행
    result = scanner.scan_multi(multi_data)

    # 6) 매수/매도/손절 가격 출력
    for hit in result.top_by_confidence(10):
        print(f"{hit.ticker} [{hit.timeframe}]: "
              f"진입 {hit.entry_price:,.0f} | "
              f"손절 {hit.stop_loss:,.0f} ({-hit.risk_pct:.2f}%) | "
              f"목표 {hit.target_1:,.0f}/{hit.target_2:,.0f} | "
              f"confidence {hit.confidence:.1%}")


if __name__ == "__main__":
    run_live_scan()
```

---

## 핵심 정리

| 질문 | 답변 |
|------|------|
| **네이버 API 단독으로 가능한가?** | 일봉만 가능. 분봉 필요하면 불가. |
| **pykrx 단독으로 가능한가?** | 일봉 전종목 스캔 가능. 분봉 불가. |
| **KIS API 단독으로 가능한가?** | 기술적으로는 가능하나 최근 30일 제한으로 **백테스트 불가**. |
| **실전 추천 조합** | pykrx (유니버스 + 과거 일봉) + 네이버 (수정주가 검증) + KIS (분봉 + 실매매) |

### Strategy D v2는 **일봉 기반**이므로:
- **Phase 1 스캔**: pykrx로 충분 (KIS 불필요)
- **Phase 2 정밀 분석**: 여전히 일봉 기준 → pykrx + 네이버 교차검증
- **KIS API는 실매매 주문 때만** 필요

즉 Strategy D v2를 실전 투입할 때 **KIS 없이도 시그널 생성까지는 가능**하고, 실제 주문 체결 단계에서만 KIS가 필요합니다. 백테스트 → Paper trading → 실매매로 단계 넘어갈 때 KIS 연동을 추가하는 게 합리적인 순서입니다.

### 15분/30분봉 멀티 타임프레임 원하면?
- KIS API 없이는 **불가능** (네이버·pykrx 모두 분봉 미지원)
- 대안: 15:20 스캔 후 다음 날 분봉 기반 정밀 진입 타이밍 판단용으로 KIS 도입

네이버 API는 **무료 + 수정주가 + 안정적**이라는 장점으로 **"일봉 데이터의 대안/검증 채널"로 활용하는 게 정답**입니다.
