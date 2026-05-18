"""
core/data_sources/naver.py — 네이버 금융 일봉 + 종목 리스트 소스.

기존 daily_only_scanner.py L693-888에서 추출 (NaverSource).
"""
from __future__ import annotations

import io
import json
import logging
import time

import pandas as pd
import requests

from .base import DailyDataSource

logger = logging.getLogger(__name__)


def naver_detail_url(ticker: str) -> str:
    """ticker → 네이버 종목 상세 페이지 URL (UI 클릭 이동용)."""
    return f"https://stock.naver.com/domestic/stock/{ticker}/price"


def _to_optional_float(value) -> float | None:
    """pd.read_html이 N/A를 NaN으로 파싱한 값을 JSON 호환 None 또는 float로 정규화."""
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_per_raw(raw) -> tuple[float | None, bool]:
    """네이버 sise_market_sum PER raw 셀 → (value, negative_flag).

    pd.read_html 동작 (probe 검증):
      - '—' / '-' (적자 sentinel) → string 그대로 보존
      - 빈 셀 / 'N/A' → NaN
      - 정상 양수 → string '10.5'

    분기 규칙:
      - raw 가 '—' / '-' / 음수 string → (None, True)  적자
      - NaN / 빈 문자열 → (None, False)               단순 누락
      - 정상 양수 string/float → (float, False)        값 있음
    """
    if raw is None or pd.isna(raw):
        return (None, False)
    if isinstance(raw, str):
        s = raw.strip()
        if s == "":
            return (None, False)
        if s in ("—", "-"):
            return (None, True)
        try:
            v = float(s)
            return (None, True) if v < 0 else (v, False)
        except ValueError:
            return (None, False)
    try:
        v = float(raw)
        return (None, True) if v < 0 else (v, False)
    except (TypeError, ValueError):
        return (None, False)


class NaverSource(DailyDataSource):
    """
    네이버 금융 전용 소스. 일봉 OHLCV + 전종목 리스트 모두 지원.

    데이터 경로:
      - 일봉: api.finance.naver.com/siseJson.naver (수정주가)
      - 종목리스트/시총: finance.naver.com/sise/sise_market_sum.naver (페이지 크롤링)
      - 시장 지수: finance.naver.com/sise/sise_index.naver (지수 크롤링)
    """
    name = "naver"
    OHLCV_URL = "https://api.finance.naver.com/siseJson.naver"
    MARKET_SUM_URL = "https://finance.naver.com/sise/sise_market_sum.naver"
    INDEX_URL = "https://finance.naver.com/sise/sise_index.naver"
    ETF_LIST_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
    MOBILE_BASIC_URL = "https://m.stock.naver.com/api/stock/{ticker}/basic"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 시장 코드: KOSPI=0, KOSDAQ=1
    MARKET_CODE = {"KOSPI": 0, "KOSDAQ": 1}

    # 시장 지수 코드
    _INDEX_CODE = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}

    # 타임프레임 → siseJson API 의 timeframe 파라미터 값
    # probe 결과 (Task 2): "minute" 만 인트라데이 지원. "1m"/"30m"/"1h" 토큰은 빈 응답.
    _TF_MAP = {"1D": "day", "1m": "minute"}

    def __init__(self):
        self._ticker_cache: dict[str, dict] = {}   # ticker → {name, market_cap}
        self._market_cached: dict[str, bool] = {}  # market → cached?

    def get_tickers(self, market: str, target_date: str) -> list[str]:
        """
        네이버 시가총액 페이지에서 전종목 크롤링.

        market="ETF"이면 ETF 목록 JSON API를 사용.
        그 외(KOSPI/KOSDAQ)는 sise_market_sum 페이지 크롤링.
        결과는 _ticker_cache에 저장하여 시총/이름 조회에 재사용.
        """
        if market == "ETF":
            return self._get_etf_tickers(top_n=200, sort_by="quant")
        self._crawl_market_sum(market)
        return [t for t, info in self._ticker_cache.items() if info["market"] == market]

    def get_etf_list(self, target_date: str) -> set[str]:
        """네이버 etfItemList API → ETF/ETN itemcode 통합 set (PR-B 분류기용).

        target_date 는 시그니처 호환용 (네이버 API 는 현재 시점만 반환).
        실패 시 빈 set + WARN 로그 — 분류기는 이름 키워드/코드 prefix 만으로 동작 가능.
        """
        try:
            return set(self._get_etf_tickers(top_n=None, sort_by="marketSum"))
        except Exception as e:
            logger.warning(f"ETF 명단 fetch 실패: {e}")
            return set()

    def _get_etf_tickers(
        self, top_n: int | None = None, sort_by: str = "marketSum"
    ) -> list[str]:
        """네이버 ETF 목록 API에서 itemcode 추출. ETN(코드 7xxxxx 또는 종목명 'ETN' 포함) 제외.

        sort_by: 정렬 기준 필드 (기본 'marketSum', 거래량 기준 시 'quant')
        top_n: 상위 N개만 반환 (None이면 전체)
        """
        r = requests.get(
            self.ETF_LIST_URL,
            params={"etfType": 0},
            headers=self.HEADERS,
            timeout=10,
        )
        r.raise_for_status()
        items = r.json()["result"]["etfItemList"]
        items = [
            item for item in items
            if not item["itemcode"].startswith("7")
            and "ETN" not in item.get("itemname", "")
        ]
        items = sorted(items, key=lambda x: x.get(sort_by) or 0, reverse=True)
        if top_n is not None:
            items = items[:top_n]
        return [item["itemcode"] for item in items]

    def get_ticker_name(self, ticker: str) -> str:
        info = self._ticker_cache.get(ticker)
        if info:
            return info["name"]
        return ticker

    def get_market_index(self, market: str, target_date: str) -> dict | None:
        """네이버 sise_index에서 시장 지수 값 + 등락률 수집. 실패 시 None."""
        import re
        from bs4 import BeautifulSoup

        code = self._INDEX_CODE.get(market)
        if not code:
            return None
        try:
            resp = requests.get(
                self.INDEX_URL, params={"code": code}, headers=self.HEADERS, timeout=5
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            now_el = soup.find(id="now_value")
            chg_el = soup.find(id="change_value_and_rate")
            if now_el is None:
                raise ValueError("now_value 요소를 찾을 수 없음")

            close = float(now_el.get_text(strip=True).replace(",", ""))

            chg = 0.0
            if chg_el:
                m = re.search(r"([+-]?\d+\.?\d*)%", chg_el.get_text(strip=True))
                if m:
                    chg = float(m.group(1))

            return {"value": close, "change_pct": chg}
        except Exception as e:
            logger.warning(f"시장 지수 조회 실패 ({market}): {e}")
            return None

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """시가총액 DataFrame 반환 (컬럼: 시가총액, 종목명)"""
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

    def get_fundamentals(self, market: str, target_date: str) -> pd.DataFrame:
        """
        펀더멘털 DataFrame 반환 (인덱스=ticker,
        컬럼=per/per_negative/roe/foreign_pct/market_cap_bil/naver_url).

        결측치는 None (JSON 호환). naver_url은 항상 채워짐 (단순 패턴).
        per_negative 는 PR-A 의 적자 sentinel 플래그 (default False).
        sise_market_sum 페이지 1회 크롤링과 함께 추출되므로 추가 HTTP 비용 0.
        """
        self._crawl_market_sum(market)
        rows = {}
        for ticker, info in self._ticker_cache.items():
            if info["market"] != market:
                continue
            raw_cap = info.get("market_cap") or 0.0
            rows[ticker] = {
                "per": info.get("per"),
                "per_negative": info.get("per_negative", False),
                "roe": info.get("roe"),
                "foreign_pct": info.get("foreign_pct"),
                "market_cap_bil": raw_cap / 1e8 if raw_cap else None,
                "naver_url": naver_detail_url(ticker),
            }
        if not rows:
            return pd.DataFrame(
                columns=["per", "per_negative", "roe", "foreign_pct", "market_cap_bil", "naver_url"]
            )
        df = pd.DataFrame(rows).T
        df.index.name = "티커"
        return df

    def get_macro_indices(self) -> dict[str, dict]:
        """USD/KRW, WTI, 국고채3Y를 네이버 marketindex에서 스크래핑. 실패 항목은 skip."""
        import re
        from bs4 import BeautifulSoup

        result: dict[str, dict] = {}

        # USD/KRW
        try:
            resp = requests.get(
                "https://finance.naver.com/marketindex/exchangeDetail.naver",
                params={"marketindexCd": "FX_USDKRW"},
                headers=self.HEADERS, timeout=5,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            today = soup.find(class_="today")
            if today:
                no_today = today.find(class_="no_today")
                value_text = no_today.get_text(strip=True) if no_today else ""
                value = float(re.sub(r"[^\d.]", "", value_text.replace(",", ""))) if value_text else None
                exday = today.find(class_="no_exday")
                chg_match = re.search(r"([\d.]+)%", exday.get_text()) if exday else None
                change_pct = float(chg_match.group(1)) if chg_match else 0.0
                if today.find("span", class_="ico down") or today.find("i", class_="down"):
                    change_pct = -change_pct
                if value:
                    result["usd_krw"] = {"value": value, "change_pct": change_pct}
        except Exception as e:
            logger.warning(f"USD/KRW 수집 실패: {e}")

        # WTI (최근 거래일 종가)
        try:
            resp = requests.get(
                "https://finance.naver.com/marketindex/worldDailyQuote.naver",
                params={"marketindexCd": "OIL_CL", "fdtc": "2"},
                headers=self.HEADERS, timeout=5,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            tbl = soup.find("table")
            if tbl:
                for row in tbl.find_all("tr")[1:]:
                    cols = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cols) >= 4:
                        try:
                            value = float(cols[1].replace(",", ""))
                            chg_str = cols[3].replace("%", "").replace("+", "").strip()
                            change_pct = float(chg_str)
                            if value > 0:
                                result["wti"] = {"value": value, "change_pct": change_pct}
                                break
                        except ValueError:
                            continue
        except Exception as e:
            logger.warning(f"WTI 수집 실패: {e}")

        # 국고채 3Y (수익률, 전일대비 절대 변화)
        try:
            resp = requests.get(
                "https://finance.naver.com/marketindex/interestDetail.naver",
                params={"marketindexCd": "IRR_OWNBD03Y"},
                headers=self.HEADERS, timeout=5,
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table tr"):
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 2 and cols[0]:
                    try:
                        value = float(cols[0].replace(",", ""))
                        change_abs = float(cols[1].replace(",", ""))
                        if value > 0:
                            result["kr_treasury_3y"] = {"value": value, "change_pct": change_abs}
                            break
                    except ValueError:
                        continue
        except Exception as e:
            logger.warning(f"국고채3Y 수집 실패: {e}")

        return result

    def get_current_quote(self, ticker: str) -> dict | None:
        """네이버 모바일 API로 실시간 현재가·등락률 조회 (delayTime=0).

        Returns:
            {"current_price": int, "change_pct": float} or None on failure
        """
        url = self.MOBILE_BASIC_URL.format(ticker=ticker)
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=5)
            r.raise_for_status()
            d = r.json()
            close_str = d.get("closePrice", "")
            ratio = d.get("fluctuationsRatio")
            if not close_str or ratio is None:
                return None
            price = int(close_str.replace(",", ""))
            # fluctuationsRatio 는 부호 포함 (하락 시 음수). 별도 sign 곱셈 금지 —
            # compareToPreviousPrice.code 로 부호 재계산하면 하락 종목이 양수로 반전됨.
            return {
                "current_price": price,
                "change_pct": round(float(ratio), 2),
            }
        except Exception:
            return None

    def get_ohlcv(
        self, ticker: str, start: str, end: str, timeframe: str = "1D"
    ) -> pd.DataFrame:
        """
        네이버 siseJson API로 OHLCV 조회 (수정주가).

        timeframe:
          - "1D": 일봉 (날짜 포맷 YYYYMMDD)
          - "1m": 1분봉 (날짜 포맷 YYYYMMDDHHMM, 거래없는 분봉은 OHLC=None → dropna)
        """
        if timeframe not in self._TF_MAP:
            raise NotImplementedError(
                f"NaverSource: timeframe={timeframe!r} 미지원. "
                f"지원: {list(self._TF_MAP.keys())}"
            )
        tf_param = self._TF_MAP[timeframe]
        params = {
            "symbol": ticker,
            "requestType": 1,
            "startTime": start,
            "endTime": end,
            "timeframe": tf_param,
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
            "외국인소진율": "foreign_rate",
        })
        date_format = "%Y%m%d%H%M" if timeframe == "1m" else "%Y%m%d"
        df["date"] = pd.to_datetime(df["date"], format=date_format)
        df = df.set_index("date")
        # foreign_rate는 응답에 있을 때만 보존 (1m 응답 보장, 1D는 변동 가능)
        cols = ["open", "high", "low", "close", "volume"]
        if "foreign_rate" in df.columns:
            cols.append("foreign_rate")
        df = df[cols]
        # minute 응답: close 만 있고 OHL 가 null 인 분봉 → 체결가만 채워진 분봉.
        # close 만 dropna 기준으로 두고, OHL null 은 close 로 채움 (네이버 응답 특성).
        df = df.dropna(subset=["close"])
        # fillna 전에 numeric cast — object dtype silent downcast 경고 회피
        for col in cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in ("open", "high", "low"):
            df[col] = df[col].fillna(df["close"])
        # 네이버 분봉 응답은 최신 → 과거 역순. cache.loc[start:end] 슬라이스 안전 보장.
        return df.sort_index().astype(float)

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

            # pd.read_html로 메인 테이블(시총 랭킹) 파싱.
            # flavor='lxml' 명시: 빈 HTML 등에서 html5lib fallback 차단 (불필요 의존성 회피).
            try:
                tables = pd.read_html(io.StringIO(r.text), flavor="lxml")
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

                # PR-A: PER raw text 분기 — 적자 sentinel 식별
                per_value, per_negative = _classify_per_raw(row.get("PER"))
                self._ticker_cache[code] = {
                    "name": name,
                    "market": market,
                    "market_cap": market_cap,
                    # 펀더멘털 (UI 표시 + 의사결정용). N/A → None
                    "per": per_value,
                    "per_negative": per_negative,  # 적자 종목 식별 플래그
                    "roe": _to_optional_float(row.get("ROE")),
                    "foreign_pct": _to_optional_float(row.get("외국인비율")),
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
