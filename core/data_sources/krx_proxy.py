"""
core/data_sources/krx_proxy.py — KRX 공식 Open API proxy 기반 소스 + Circuit Breaker.

기존 daily_only_scanner.py L143-688에서 추출 (CircuitBreakerOpen, CircuitBreaker,
KRXProxySource).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

from .base import DailyDataSource

logger = logging.getLogger(__name__)


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
