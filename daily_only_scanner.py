"""
daily_only_scanner.py — 일봉만으로 KOSPI 전종목 Strategy D v2 스크리닝

특징:
  - KIS API 불필요 (완전 무료)
  - pykrx → FDR → 네이버 3단계 fallback
  - Strategy D v2 백테스트 엔진 재사용
  - Phase 1 전종목 스캔 + Phase 2 상세 분석 + 최종 매수 리스트 출력

실행:
    python daily_only_scanner.py                # 당일 기준 스캔
    python daily_only_scanner.py --date 20260418 # 특정일 기준
    python daily_only_scanner.py --top 20        # 상위 20개만

의존성:
    pip install pykrx finance-datareader pandas numpy scipy ta
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import requests

# Strategy D v2 백테스트 엔진 (이전에 작성한 모듈)
from backtest_engine.strategy import StrategyD, StrategyDConfig
from backtest_engine.detectors import DoubleBottomSimple, DoubleBottomFractal, DoubleBottomProminence
from backtest_engine.screener import ScreenerHit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# 데이터 소스 추상화 (Fallback 체인)
# ============================================================================

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


# ── 1차 소스: pykrx ────────────────────────────────────────────────

class PykrxSource(DailyDataSource):
    name = "pykrx"

    def get_tickers(self, market: str, target_date: str) -> List[str]:
        from pykrx import stock
        return stock.get_market_ticker_list(target_date, market=market)

    def get_ticker_name(self, ticker: str) -> str:
        from pykrx import stock
        return stock.get_market_ticker_name(ticker)

    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        from pykrx import stock
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
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


# ── 2차 소스: FinanceDataReader ────────────────────────────────────

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


# ── 4차 소스: KRX Proxy (공식 데이터, 유니버스/검증용) ────────────────


class CircuitBreakerOpen(RuntimeError):
    """Circuit breaker가 열려 있어 요청 거부됨"""
    pass


class CircuitBreaker:
    """
    연속 오류 발생 시 요청을 중단시키는 안전장치.

    동작:
      - consecutive_failures ≥ failure_threshold → OPEN (요청 전부 차단)
      - OPEN 상태에서 recovery_timeout 초 경과 → HALF_OPEN (1회 시도 허용)
      - HALF_OPEN 요청 성공 → CLOSED (정상 복귀), 실패 → 다시 OPEN

    스킬 문서 요구사항:
      "딜레이 또는 오류가 발생해 데이터를 전부 가져오지 못한다면 동작을 멈추도록"
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_sec: float = 30.0,
        fatal_status_codes: Tuple[int, ...] = (502, 503),
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self.fatal_status_codes = fatal_status_codes

        self.state = self.STATE_CLOSED
        self.consecutive_failures = 0
        self.last_failure_time: Optional[float] = None
        self.last_fatal_status: Optional[int] = None

    def before_request(self):
        """요청 전 호출. OPEN 상태면 CircuitBreakerOpen 발생"""
        if self.state == self.STATE_OPEN:
            # recovery timeout 경과?
            if (
                self.last_failure_time
                and time.time() - self.last_failure_time > self.recovery_timeout_sec
            ):
                self.state = self.STATE_HALF_OPEN
                logger.info(f"  [CircuitBreaker] HALF_OPEN — 복구 시도")
            else:
                raise CircuitBreakerOpen(
                    f"Circuit breaker OPEN — {self.consecutive_failures}회 연속 실패 "
                    f"(마지막 status: {self.last_fatal_status}). "
                    f"{self.recovery_timeout_sec}초 후 자동 복구 시도."
                )

    def on_success(self):
        """요청 성공 시 호출 — 카운터 리셋"""
        if self.state == self.STATE_HALF_OPEN:
            logger.info(f"  [CircuitBreaker] CLOSED — 복구 완료")
        self.state = self.STATE_CLOSED
        self.consecutive_failures = 0
        self.last_failure_time = None

    def on_failure(self, status_code: Optional[int] = None):
        """요청 실패 시 호출"""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if status_code is not None:
            self.last_fatal_status = status_code

        # Fatal status (502/503): 임계값 무시하고 즉시 OPEN
        if status_code in self.fatal_status_codes:
            logger.error(
                f"  [CircuitBreaker] OPEN (즉시) — status={status_code} "
                f"(upstream/proxy 장애)"
            )
            self.state = self.STATE_OPEN
        elif self.consecutive_failures >= self.failure_threshold:
            logger.error(
                f"  [CircuitBreaker] OPEN — {self.consecutive_failures}회 연속 실패"
            )
            self.state = self.STATE_OPEN


class KRXProxySource(DailyDataSource):
    """
    KRX 공식 Open API proxy 서버 기반 소스.

    - 기본 경로: https://k-skill-proxy.nomadamas.org
    - 환경변수 KSKILL_PROXY_BASE_URL로 override 가능
    - 사용자 KRX_API_KEY 불필요 (proxy 서버에서 관리)

    엔드포인트:
      - /v1/korean-stock/search       → {"items": [...], "query": {...}, "proxy": {...}}
      - /v1/korean-stock/base-info    → {"item": {...}, "query": {...}, "proxy": {...}}
      - /v1/korean-stock/trade-info   → {"item": {...}, "query": {...}, "proxy": {...}}

    안전장치:
      - CircuitBreaker: 5회 연속 실패 or 502/503 1회 → 즉시 중단
      - retry with exponential backoff: 429, 5xx 일시 장애 대응
      - timeout (15초) per request
    """
    name = "krx_proxy"
    DEFAULT_BASE_URL = "https://k-skill-proxy.nomadamas.org"
    API_PREFIX = "/v1/korean-stock"
    HEADERS = {"User-Agent": "daily-only-scanner/1.0"}
    REQUEST_TIMEOUT = 15

    # Retry 설정
    MAX_RETRIES = 2
    RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
    BACKOFF_BASE_SEC = 0.5  # 1차 retry 0.5s, 2차 1s, 3차 2s (exponential)

    def __init__(
        self,
        base_url: Optional[str] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        import os
        env_base = os.environ.get("KSKILL_PROXY_BASE_URL")
        self.base_url = (base_url or env_base or self.DEFAULT_BASE_URL).rstrip("/")
        self.api_base = f"{self.base_url}{self.API_PREFIX}"
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        # 유니버스 캐시: {market: {ticker: {name, market_cap, ...}}}
        self._universe_cache: Dict[str, Dict[str, Dict]] = {}
        # 최근 영업일 캐시 (휴장일 재시도 방지)
        self._resolved_bas_dd: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # HTTP helper (retry + circuit breaker 통합)
    # ------------------------------------------------------------------

    def _request(
        self,
        endpoint: str,
        params: Dict[str, str],
    ) -> Tuple[Optional[Dict], Optional[int]]:
        """
        GET 요청 with retry + circuit breaker.

        Returns:
            (response_json, status_code) — 실패 시 (None, status)

        Raises:
            CircuitBreakerOpen — circuit이 OPEN이면 즉시 발생
            requests.RequestException — 재시도 다 소진된 경우
        """
        self.circuit_breaker.before_request()

        url = f"{self.api_base}{endpoint}"
        last_exc: Optional[Exception] = None
        last_status: Optional[int] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                r = requests.get(
                    url,
                    params=params,
                    headers=self.HEADERS,
                    timeout=self.REQUEST_TIMEOUT,
                )
                last_status = r.status_code

                # 404는 정상적인 "찾을 수 없음" (not_found), 재시도 안 함
                if r.status_code == 404:
                    self.circuit_breaker.on_success()  # 서버는 살아 있음
                    return None, 404

                # 400은 입력 오류 — 재시도 의미 없음
                if r.status_code == 400:
                    self.circuit_breaker.on_success()  # 서버는 살아 있음
                    raise ValueError(
                        f"[KRX Proxy] 400 Bad Request: {endpoint} params={params}"
                    )

                # 502/503 → 서버 측 장애. circuit breaker 즉시 OPEN
                if r.status_code in (502, 503):
                    self.circuit_breaker.on_failure(r.status_code)
                    raise requests.HTTPError(
                        f"{r.status_code} from {endpoint}: "
                        f"{'KRX upstream 전체 실패 (502)' if r.status_code == 502 else 'proxy 서버 API 키 문제 (503)'}"
                    )

                # 일시 장애 (429, 500, 504): 재시도
                if r.status_code in self.RETRY_STATUS_CODES:
                    if attempt < self.MAX_RETRIES:
                        backoff = self.BACKOFF_BASE_SEC * (2 ** attempt)
                        logger.debug(
                            f"  [KRX Proxy] {r.status_code} {endpoint}, "
                            f"재시도 {attempt+1}/{self.MAX_RETRIES} ({backoff}s 대기)"
                        )
                        time.sleep(backoff)
                        continue
                    # 재시도 모두 소진
                    self.circuit_breaker.on_failure(r.status_code)
                    r.raise_for_status()

                # 2xx 성공
                r.raise_for_status()
                data = r.json()
                self.circuit_breaker.on_success()
                return data, r.status_code

            except CircuitBreakerOpen:
                raise  # 상위로 전파

            except (requests.Timeout, requests.ConnectionError) as e:
                last_exc = e
                if attempt < self.MAX_RETRIES:
                    backoff = self.BACKOFF_BASE_SEC * (2 ** attempt)
                    logger.debug(
                        f"  [KRX Proxy] 네트워크 오류 {endpoint}: {e}, "
                        f"재시도 {attempt+1}/{self.MAX_RETRIES}"
                    )
                    time.sleep(backoff)
                    continue
                self.circuit_breaker.on_failure()
                raise

            except requests.HTTPError as e:
                last_exc = e
                # 여기 도달한 경우는 위에서 raise 된 5xx 계열
                raise

        # 여기 도달하면 재시도 소진
        self.circuit_breaker.on_failure(last_status)
        if last_exc:
            raise last_exc
        raise RuntimeError(f"[KRX Proxy] 재시도 {self.MAX_RETRIES}회 모두 실패")

    # ------------------------------------------------------------------
    # Public endpoints (실제 스킬 스펙 반영)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        bas_dd: Optional[str] = None,
        limit: int = 10,
    ) -> Tuple[List[Dict], Dict]:
        """
        /search: 종목명 검색.

        Response 스펙:
            {"items": [{"market", "code", "standard_code", "name",
                        "short_name", "english_name", "listed_at"}, ...],
             "query": {...},
             "proxy": {"name", "cache": {...},
                       "upstream": {"degraded": bool, "failed_markets": [...]}}}

        Returns:
            (items, proxy_meta) — degraded 여부 등은 proxy_meta에서 확인
        """
        params: Dict[str, str] = {"q": query, "limit": str(min(limit, 20))}
        if bas_dd:
            params["bas_dd"] = bas_dd

        data, status = self._request("/search", params)
        if data is None:
            return [], {}

        items = data.get("items", [])
        proxy_meta = data.get("proxy", {})
        if proxy_meta.get("upstream", {}).get("degraded"):
            failed = proxy_meta["upstream"].get("failed_markets", [])
            logger.warning(
                f"  [KRX Proxy] search degraded: failed_markets={failed}"
            )
        return items, proxy_meta

    def get_base_info(
        self,
        market: str,
        code: str,
        bas_dd: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        /base-info: 종목 기본정보.

        Response 스펙:
            {"item": {"market", "code", "standard_code", "name", "short_name",
                      "english_name", "security_group", "section_type",
                      "stock_certificate_type", "par_value", "listed_shares"},
             "query": {...}, "proxy": {...}}

        주의: market_cap 필드 없음 (trade-info에만 있음).
              시가총액이 필요하면 get_trade_info() 사용.

        Returns:
            item dict or None (not_found)
        """
        if market not in ("KOSPI", "KOSDAQ", "KONEX"):
            raise ValueError(f"invalid market: {market}")

        params: Dict[str, str] = {"market": market, "code": code}
        if bas_dd:
            params["bas_dd"] = bas_dd

        data, status = self._request("/base-info", params)
        if data is None:
            return None
        return data.get("item")

    def get_trade_info(
        self,
        market: str,
        code: str,
        bas_dd: str,
    ) -> Optional[Dict]:
        """
        /trade-info: 특정 날짜 1일치 매매정보.

        Response 스펙:
            {"item": {"market", "code", "standard_code", "base_date", "name",
                      "close_price", "change_price", "fluctuation_rate",
                      "open_price", "high_price", "low_price",
                      "trading_volume", "trading_value", "market_cap"},
             "query": {...}, "proxy": {...}}

        Returns:
            item dict or None (not_found — 휴장일 가능성)
        """
        if market not in ("KOSPI", "KOSDAQ", "KONEX"):
            raise ValueError(f"invalid market: {market}")

        params: Dict[str, str] = {"market": market, "code": code, "bas_dd": bas_dd}

        data, status = self._request("/trade-info", params)
        if data is None:
            return None
        return data.get("item")

    def get_trade_info_with_fallback(
        self,
        market: str,
        code: str,
        bas_dd: str,
        max_lookback_days: int = 10,
    ) -> Optional[Dict]:
        """
        get_trade_info + 휴장일 처리.

        bas_dd에 데이터 없으면 최근 영업일로 최대 max_lookback_days일 소급.
        """
        current_dt = datetime.strptime(bas_dd, "%Y%m%d")
        for i in range(max_lookback_days):
            check_dd = current_dt.strftime("%Y%m%d")
            # 주말 skip
            if current_dt.weekday() >= 5:
                current_dt -= timedelta(days=1)
                continue

            data = self.get_trade_info(market=market, code=code, bas_dd=check_dd)
            if data:
                return data

            current_dt -= timedelta(days=1)
        return None

    # ------------------------------------------------------------------
    # DailyDataSource 인터페이스 구현
    # ------------------------------------------------------------------

    def get_tickers(self, market: str, target_date: str) -> List[str]:
        """KRX Proxy는 전종목 리스트 엔드포인트 미제공."""
        raise NotImplementedError(
            "KRX Proxy는 전종목 리스트 엔드포인트 미제공. "
            "다른 소스(네이버/FDR)에서 ticker 목록 확보 후 "
            "enrich_with_trade_info()로 시총/이름을 공식 데이터로 보강하세요."
        )

    def get_ticker_name(self, ticker: str) -> str:
        """search API로 종목명 조회"""
        try:
            items, _ = self.search(query=ticker, limit=1)
            if items:
                return items[0].get("name", ticker)
        except Exception:
            pass
        return ticker

    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """
        과거 N일 OHLCV는 네이버 API가 훨씬 효율적.
        5일 초과 요청은 RuntimeError로 네이버 사용 유도.
        """
        start_dt = datetime.strptime(start, "%Y%m%d")
        end_dt = datetime.strptime(end, "%Y%m%d")
        days = (end_dt - start_dt).days + 1

        if days > 5:
            raise RuntimeError(
                f"KRXProxySource.get_ohlcv: 요청 기간 {days}일 > 5일 한도. "
                f"장기 시계열은 네이버 siseJson API를 사용하세요."
            )

        # 시장 명시 필요하므로 NOT 간단 구현. 상위 레벨에서 보통 호출 안 함.
        raise NotImplementedError(
            "KRX Proxy get_ohlcv는 market 인자 필요. "
            "get_trade_info(market, code, bas_dd)를 직접 사용하세요."
        )

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """enrich_with_trade_info() 호출 후에만 값 반환"""
        cache = self._universe_cache.get(market, {})
        if not cache:
            return pd.DataFrame()
        rows = {
            ticker: {
                "시가총액": info.get("market_cap", 0),
                "종목명": info.get("name", ticker),
            }
            for ticker, info in cache.items()
        }
        df = pd.DataFrame(rows).T
        df.index.name = "티커"
        return df

    # ------------------------------------------------------------------
    # 유니버스 보강 (공식 데이터)
    # ------------------------------------------------------------------

    def enrich_with_trade_info(
        self,
        tickers: List[str],
        market: str,
        bas_dd: str,
        rate_limit_sec: float = 0.1,
        progress_every: int = 100,
        fail_threshold_pct: float = 0.5,
    ) -> Dict[str, Dict]:
        """
        ticker 리스트에 KRX 공식 시총/종가를 보강.

        `trade-info`에서 market_cap 추출 (base-info에는 market_cap 없음).

        안전장치:
          1) CircuitBreaker가 OPEN되면 즉시 중단 (nnn-502/503 연속 시)
          2) 실패율 > fail_threshold_pct면 중간에 중단 (데이터 부족)
          3) 사용자 Ctrl+C 대응 (KeyboardInterrupt 즉시 전파)

        Args:
            tickers: 보강할 종목코드 리스트
            market: "KOSPI" | "KOSDAQ" | "KONEX"
            bas_dd: 기준일 YYYYMMDD (자동 휴장일 fallback 포함)
            rate_limit_sec: 각 요청 간 대기 시간
            progress_every: N개마다 진행상황 로그
            fail_threshold_pct: 실패율 한계 (0.5 = 50% 실패하면 중단)

        Returns:
            {ticker: {"name", "market_cap", "close_price", "listed_shares", ...}}

        Raises:
            RuntimeError: CircuitBreaker OPEN 또는 실패율 초과로 중단
        """
        if not tickers:
            return {}

        result: Dict[str, Dict] = {}
        failed = 0
        not_found = 0
        circuit_broke = False

        logger.info(
            f"  [KRX Proxy] 보강 시작: {len(tickers)}종목 @ {bas_dd} ({market})"
        )

        for i, ticker in enumerate(tickers):
            try:
                data = self.get_trade_info_with_fallback(
                    market=market, code=ticker, bas_dd=bas_dd,
                )
                if data:
                    result[ticker] = {
                        "name": data.get("name", ticker),
                        "market_cap": float(data.get("market_cap", 0) or 0),
                        "close_price": float(data.get("close_price", 0) or 0),
                        "trading_volume": int(data.get("trading_volume", 0) or 0),
                        "base_date": data.get("base_date", bas_dd),
                    }
                else:
                    not_found += 1

            except CircuitBreakerOpen as e:
                logger.error(
                    f"  [KRX Proxy] Circuit breaker OPEN 감지, 중단 "
                    f"(진행 {i}/{len(tickers)}): {e}"
                )
                circuit_broke = True
                break

            except KeyboardInterrupt:
                logger.warning("  [KRX Proxy] 사용자 중단 (Ctrl+C)")
                raise

            except ValueError as e:
                # 400 Bad Request — 입력 오류, 계속 진행 (이 ticker만 skip)
                logger.debug(f"  [KRX Proxy] {ticker} 400 오류: {e}")
                failed += 1

            except Exception as e:
                failed += 1
                if failed <= 3:
                    logger.debug(f"  [KRX Proxy] {ticker} 실패: {e}")

            # 진행 상황 로그
            if (i + 1) % progress_every == 0:
                logger.info(
                    f"  [KRX Proxy] 보강: {i+1}/{len(tickers)} "
                    f"(hit {len(result)}, not_found {not_found}, fail {failed})"
                )

            # 실패율 체크 (최소 progress_every개는 모아봐야)
            processed = i + 1
            if processed >= progress_every:
                fail_rate = failed / processed
                if fail_rate > fail_threshold_pct:
                    logger.error(
                        f"  [KRX Proxy] 실패율 {fail_rate:.1%} > "
                        f"{fail_threshold_pct:.0%}, 중단"
                    )
                    raise RuntimeError(
                        f"KRX Proxy 실패율 한계 초과: {failed}/{processed}"
                    )

            if rate_limit_sec > 0:
                time.sleep(rate_limit_sec)

        if circuit_broke:
            raise RuntimeError(
                f"KRX Proxy 연속 장애로 중단. "
                f"수집 {len(result)}/{len(tickers)}. "
                f"잠시 후 재시도하거나 --no-krx 옵션을 사용하세요."
            )

        logger.info(
            f"  [KRX Proxy] 보강 완료: hit {len(result)}, "
            f"not_found {not_found}, fail {failed} / 총 {len(tickers)}"
        )
        self._universe_cache[market] = result
        return result

    # 구버전 이름과의 호환성 alias
    enrich_with_base_info = enrich_with_trade_info


# ── 네이버 금융: 일봉 + 종목리스트 (KRX Proxy 없을 때 주력) ─────────────

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


# ── 통합 클라이언트 (Fallback 체인) ─────────────────────────────────

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


# ============================================================================
# 일봉 전용 스크리너
# ============================================================================

@dataclass
class ScanConfig:
    """일봉 스크리너 설정"""
    market: str = "KOSPI"                  # "KOSPI", "KOSDAQ", "KRX"
    min_market_cap_bil: float = 2000.0      # 최소 시총 2천억
    max_market_cap_bil: float = 30000.0     # 최대 시총 3조
    min_daily_volume: int = 100_000         # 일 최소 거래량
    lookback_days: int = 90                 # 지표 계산용 과거 기간
    top_n: int = 20                          # 최종 출력 상위 N개
    detector_name: str = "simple"            # "simple" / "fractal" / "prominence"


@dataclass
class ScanCandidate:
    """스크리닝 결과 단일 종목"""
    ticker: str
    name: str
    market: str
    current_price: float
    market_cap_bil: float
    volume_20d_avg: float
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    confidence: float
    conditions_met: Dict[str, bool]

    @property
    def risk_pct(self) -> float:
        return (self.entry_price - self.stop_loss) / self.entry_price * 100

    @property
    def reward_pct_t1(self) -> float:
        return (self.target_1 - self.entry_price) / self.entry_price * 100

    @property
    def reward_pct_t2(self) -> float:
        return (self.target_2 - self.entry_price) / self.entry_price * 100


class DailyOnlyScanner:
    """
    일봉 전용 KOSPI/KOSDAQ 스크리너.

    Phase 1: 유니버스 필터 (시총, 거래량)
    Phase 2: Strategy D v2 진입 조건 체크
    Phase 3: confidence 순 정렬 및 매수/손절/익절 가격 출력
    """

    def __init__(
        self,
        client: Optional[DataClient] = None,
        config: Optional[ScanConfig] = None,
    ):
        self.client = client or DataClient()
        self.config = config or ScanConfig()

    def _build_strategy(self) -> StrategyD:
        det_map = {
            "simple": DoubleBottomSimple(),
            "fractal": DoubleBottomFractal(),
            "prominence": DoubleBottomProminence(prominence_pct=0.015),
        }
        detector = det_map.get(self.config.detector_name, DoubleBottomSimple())
        return StrategyD(
            config=StrategyDConfig(min_lookback_bars=25),  # BB 20 + 여유 5
            double_bottom_detector=detector,
        )

    def scan(self, target_date: Optional[str] = None) -> List[ScanCandidate]:
        """전종목 일봉 스캔"""
        if target_date is None:
            target_date = self._latest_business_day()

        end_str = target_date
        start_dt = datetime.strptime(target_date, "%Y%m%d") - timedelta(
            days=self.config.lookback_days + 30
        )
        start_str = start_dt.strftime("%Y%m%d")

        logger.info(f"🔍 스캔 시작: {self.config.market} @ {target_date}")

        # Phase 1: 유니버스 필터
        tickers = self._filter_universe(target_date)
        logger.info(f"📊 Phase 1 유니버스: {len(tickers)}종목")

        # Phase 2: Strategy D 진입 조건 체크
        candidates = []
        strategy = self._build_strategy()
        failed = 0

        for i, ticker in enumerate(tickers):
            if (i + 1) % 50 == 0:
                logger.info(f"  진행: {i+1}/{len(tickers)} (hits: {len(candidates)})")

            try:
                df = self.client.get_ohlcv(ticker, start_str, end_str)
                if len(df) < 30:
                    continue

                # 거래량 필터
                avg_volume = float(df["volume"].tail(20).mean())
                if avg_volume < self.config.min_daily_volume:
                    continue

                # Strategy D 진입 체크
                prepared = strategy.prepare(df)
                last_idx = len(prepared) - 1
                signal = strategy.check_entry(prepared, last_idx, ticker=ticker)

                if signal is not None:
                    name = self.client.get_ticker_name(ticker)
                    cap_bil = self._get_cap_for_ticker(ticker, target_date)

                    candidate = ScanCandidate(
                        ticker=ticker,
                        name=name,
                        market=self.config.market,
                        current_price=float(df["close"].iloc[-1]),
                        market_cap_bil=cap_bil,
                        volume_20d_avg=avg_volume,
                        entry_price=signal.entry_price,
                        stop_loss=signal.stop_loss,
                        target_1=signal.target_1,
                        target_2=signal.target_2,
                        confidence=signal.confidence,
                        conditions_met=signal.conditions_met,
                    )
                    candidates.append(candidate)

            except Exception as e:
                failed += 1
                if failed <= 3:
                    logger.debug(f"  {ticker} 분석 실패: {e}")

        logger.info(
            f"✅ Phase 2 완료: 시그널 {len(candidates)}개, 실패 {failed}개"
        )

        # confidence 내림차순 정렬
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[: self.config.top_n]

    # ------------------------------------------------------------------
    # 내부 helpers
    # ------------------------------------------------------------------

    def _filter_universe(self, target_date: str) -> List[str]:
        """
        시가총액 기준 유니버스 필터.

        우선순위:
          1) KRX Proxy 공식 시총 보강 (use_krx_for_universe=True)
          2) 실패 시 1차 소스(네이버/pykrx) 시총 사용
          3) strict_mode=True면 KRX 실패 시 전체 중단 (fallback 안 함)
        """
        all_tickers = self.client.get_tickers(self.config.market, target_date)

        cap_lookup: Dict[str, float] = {}

        # 1) KRX Proxy로 공식 시총 보강 시도
        if self.client.use_krx_for_universe:
            logger.info(
                f"  [KRX Proxy] 공식 시총 보강 중... ({len(all_tickers)}종목)"
            )
            try:
                enriched = self.client.krx_proxy.enrich_with_trade_info(
                    tickers=all_tickers,
                    market=self.config.market,
                    bas_dd=target_date,
                )
                cap_lookup = {
                    ticker: info["market_cap"]
                    for ticker, info in enriched.items()
                    if info.get("market_cap", 0) > 0
                }
                self._name_lookup = {
                    ticker: info["name"] for ticker, info in enriched.items()
                }
                logger.info(
                    f"  [KRX Proxy] 보강 성공: {len(cap_lookup)}종목 "
                    f"(실패/미수집 {len(all_tickers) - len(cap_lookup)}개)"
                )
            except (CircuitBreakerOpen, RuntimeError) as e:
                # Circuit breaker 또는 실패율 초과
                if self.client.strict_mode:
                    logger.error(
                        f"  [KRX Proxy] 보강 실패 + strict_mode → 스캔 전체 중단: {e}"
                    )
                    raise RuntimeError(
                        f"KRX Proxy 데이터 수집 불완전. "
                        f"strict_mode=True이므로 중단. 원인: {e}"
                    )
                logger.warning(
                    f"  [KRX Proxy] 보강 실패, fallback 진행: {e}"
                )
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.warning(
                    f"  [KRX Proxy] 예상 외 오류, fallback 진행: {e}"
                )

        # 2) fallback: 1차 소스 시총 사용
        if not cap_lookup:
            cap_df = self.client.get_market_cap(self.config.market, target_date)
            if not cap_df.empty and "시가총액" in cap_df.columns:
                cap_lookup = cap_df["시가총액"].to_dict()

        if not cap_lookup:
            logger.warning("  시가총액 조회 실패. 필터 없이 전종목 진행.")
            self._cap_lookup = {}
            return all_tickers

        self._cap_lookup = cap_lookup

        # 억 단위로 변환해서 범위 필터
        filtered = [
            t for t in all_tickers
            if self.config.min_market_cap_bil
            <= cap_lookup.get(t, 0) / 100_000_000
            <= self.config.max_market_cap_bil
        ]
        return filtered

    def _get_cap_for_ticker(self, ticker: str, target_date: str) -> float:
        """억 단위"""
        cap_won = getattr(self, "_cap_lookup", {}).get(ticker, 0)
        return float(cap_won) / 100_000_000

    def _latest_business_day(self) -> str:
        """최근 영업일 (주말/장 시작 전 고려)"""
        today = date.today()
        now = datetime.now()
        # 장 마감(15:30) 이전이면 전일 기준
        if now.hour < 16:
            today -= timedelta(days=1)
        while today.weekday() >= 5:  # 주말
            today -= timedelta(days=1)
        return today.strftime("%Y%m%d")


# ============================================================================
# 출력 포맷터
# ============================================================================

def print_results(candidates: List[ScanCandidate], target_date: str):
    if not candidates:
        print("\n  ⚠️  진입 조건 충족 종목 없음\n")
        return

    print("\n" + "=" * 90)
    print(f"  🎯 {target_date} 장 마감 기준 — 매수 후보 {len(candidates)}개")
    print("=" * 90)

    # 요약 테이블
    print()
    print(f"  {'순위':>4}  {'종목코드':<8}  {'종목명':<15}  {'현재가':>10}  "
          f"{'시총(억)':>10}  {'Conf':>5}  {'손절':>8}  {'목표1':>8}  {'목표2':>8}")
    print("  " + "─" * 86)

    for i, c in enumerate(candidates, 1):
        print(
            f"  {i:>4}  {c.ticker:<8}  {c.name[:15]:<15}  {c.current_price:>10,.0f}  "
            f"{c.market_cap_bil:>10,.0f}  {c.confidence:>5.2f}  "
            f"{-c.risk_pct:>7.2f}%  +{c.reward_pct_t1:>6.2f}%  +{c.reward_pct_t2:>6.2f}%"
        )

    # 상세 정보
    print()
    print("─" * 90)
    print("  📋 상세 매수 정보 (상위 5개)")
    print("─" * 90)

    for i, c in enumerate(candidates[:5], 1):
        print(f"\n  ────── #{i}  [{c.ticker}] {c.name}  ──────")
        print(f"     시총               : {c.market_cap_bil:>12,.0f} 억원")
        print(f"     20일 평균 거래량    : {c.volume_20d_avg:>12,.0f} 주")
        print(f"     Confidence          : {c.confidence:>12.1%}")
        print(f"     ")
        print(f"     💰 진입가 (매수)    : {c.entry_price:>12,.0f} 원")
        print(f"     🛑 손절가           : {c.stop_loss:>12,.0f} 원 ({-c.risk_pct:+.2f}%)")
        print(f"     🎯 1차 목표 (익절)  : {c.target_1:>12,.0f} 원 (+{c.reward_pct_t1:.2f}%)")
        print(f"     🎯 2차 목표 (익절)  : {c.target_2:>12,.0f} 원 (+{c.reward_pct_t2:.2f}%)")
        print(f"     ⏰ 최대 보유        : 3 거래일 (미도달 시 시간 손절)")
        conds = [k for k, v in c.conditions_met.items() if v]
        print(f"     ✓ 충족 조건 ({len(conds)}): {', '.join(conds[:6])}{'...' if len(conds) > 6 else ''}")

    print("\n" + "=" * 90 + "\n")


def save_json(candidates: List[ScanCandidate], target_date: str, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"scan_{target_date}_{datetime.now().strftime('%H%M')}.json"
    filepath = output_dir / filename

    data = {
        "scan_time": datetime.now().isoformat(),
        "target_date": target_date,
        "count": len(candidates),
        "candidates": [asdict(c) for c in candidates],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 결과 저장: {filepath}")
    return filepath


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="일봉 전용 KOSPI/KOSDAQ Strategy D v2 스크리너"
    )
    parser.add_argument("--market", default="KOSPI", choices=["KOSPI", "KOSDAQ", "KRX"])
    parser.add_argument("--date", help="기준일 (YYYYMMDD). 미지정 시 최근 영업일")
    parser.add_argument("--top", type=int, default=20, help="상위 N개 (기본 20)")
    parser.add_argument("--detector", default="simple",
                        choices=["simple", "fractal", "prominence"])
    parser.add_argument("--min-cap", type=float, default=2000.0,
                        help="최소 시총 (억, 기본 2000)")
    parser.add_argument("--max-cap", type=float, default=30000.0,
                        help="최대 시총 (억, 기본 30000)")
    parser.add_argument("--output-dir", default="scan_results")
    parser.add_argument("--no-save", action="store_true", help="JSON 저장 안 함")
    parser.add_argument(
        "--no-krx", action="store_true",
        help="KRX 공식 Proxy 보강 비활성화 (네이버/pykrx만 사용)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="엄격 모드: KRX Proxy 데이터가 불완전하면 스캔 전체 중단 "
             "(Circuit Breaker OPEN 또는 실패율 50%% 초과 시)",
    )
    args = parser.parse_args()

    if args.date:
        try:
            datetime.strptime(args.date, "%Y%m%d")
        except ValueError:
            parser.error(f"--date 형식 오류: '{args.date}' (YYYYMMDD 형식 필요, 예: 20260418)")

    config = ScanConfig(
        market=args.market,
        min_market_cap_bil=args.min_cap,
        max_market_cap_bil=args.max_cap,
        top_n=args.top,
        detector_name=args.detector,
    )

    client = DataClient(
        use_krx_for_universe=not args.no_krx,
        strict_mode=args.strict,
    )
    scanner = DailyOnlyScanner(client=client, config=config)

    target = args.date or scanner._latest_business_day()
    candidates = scanner.scan(target_date=target)

    print_results(candidates, target)

    if not args.no_save and candidates:
        save_json(candidates, target, Path(args.output_dir))


if __name__ == "__main__":
    main()
