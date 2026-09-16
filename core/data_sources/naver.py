"""
core/data_sources/naver.py — 네이버 금융 일봉 + 종목 리스트 소스.

기존 daily_only_scanner.py L693-888에서 추출 (NaverSource).
2026-09-10 구형 HTML 페이지 폐쇄로 종목 리스트 경로를 JSON API 로 교체.
"""
from __future__ import annotations

import json
import logging

import pandas as pd
import requests

from .base import DailyDataSource

logger = logging.getLogger(__name__)


def naver_detail_url(ticker: str) -> str:
    """ticker → 네이버 종목 상세 페이지 URL (UI 클릭 이동용)."""
    return f"https://finance.naver.com/item/main.naver?code={ticker}"


def _to_optional_float(value) -> float | None:
    """pd.read_html이 N/A를 NaN으로 파싱한 값을 JSON 호환 None 또는 float로 정규화."""
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _classify_per_raw(raw) -> tuple[float | None, bool]:
    """네이버 PER raw 값 → (value, negative_flag).

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


def _classify_per(per_raw, eps_raw) -> tuple[float | None, bool]:
    """주식 목록 JSON API 의 PER/EPS → (value, negative_flag).

    API 는 적자 종목의 per 를 null 로 주고 eps 만 음수로 준다. per 값이 있으면
    _classify_per_raw 규칙을 그대로 쓰고, per 가 없을 때만 eps 부호로 적자를 판정한다.
    """
    value, negative = _classify_per_raw(per_raw)
    if value is None and not negative:
        eps = _to_optional_float(eps_raw)
        if eps is not None and eps < 0:
            return (None, True)
    return (value, negative)


class NaverSource(DailyDataSource):
    """
    네이버 금융 전용 소스. 일봉 OHLCV + 전종목 리스트 모두 지원.

    데이터 경로:
      - 일봉: api.finance.naver.com/siseJson.naver (수정주가)
      - 종목리스트/시총/펀더멘털: stock.naver.com 주식 목록 JSON API
      - 시장 지수: finance.naver.com/sise/sise_index.naver (지수 크롤링)

    2026-09-10 네이버가 구형 HTML 페이지(sise_market_sum)를 폐쇄하고 stock.naver.com
    SPA 로 302 리다이렉트를 걸어, 표 파싱 경로를 JSON API 로 교체했다.
    """
    name = "naver"
    OHLCV_URL = "https://api.finance.naver.com/siseJson.naver"
    STOCK_LIST_URL = "https://stock.naver.com/api/domestic/market/stock/default"
    INDEX_URL = "https://m.stock.naver.com/api/index/{code}/basic"
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
        그 외(KOSPI/KOSDAQ)는 주식 목록 JSON API 조회.
        결과는 _ticker_cache에 저장하여 시총/이름 조회에 재사용.
        """
        if market == "ETF":
            items = self._get_etf_items(top_n=200, sort_by="quant")
            return [
                item["itemcode"] for item in items
                if not item["itemcode"].startswith("7")
                and "ETN" not in item.get("itemname", "")
            ]
        self._crawl_market_sum(market)
        return [t for t, info in self._ticker_cache.items() if info["market"] == market]

    def get_etf_list(self, target_date: str) -> set[str]:
        """네이버 etfItemList API → ETF/ETN itemcode 통합 set (PR-B 분류기용).

        target_date 는 시그니처 호환용 (네이버 API 는 현재 시점만 반환).
        실패 시 빈 set + WARN 로그 — 분류기는 이름 키워드/코드 prefix 만으로 동작 가능.
        """
        try:
            return {item["itemcode"] for item in self._get_etf_items(top_n=None, sort_by="marketSum")}
        except Exception as e:
            logger.warning(f"ETF 명단 fetch 실패: {e}")
            return set()

    def _get_etf_items(
        self, top_n: int | None = None, sort_by: str = "marketSum"
    ) -> list[dict]:
        """네이버 ETF 목록 API에서 item dict 목록 반환 (ETN 포함 원본).

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
        items = sorted(items, key=lambda x: x.get(sort_by) or 0, reverse=True)
        if top_n is not None:
            items = items[:top_n]
        return items

    def get_ticker_name(self, ticker: str) -> str:
        info = self._ticker_cache.get(ticker)
        if info:
            return info["name"]
        return ticker

    def get_market_index(self, market: str, target_date: str) -> dict | None:
        """m.stock index/basic JSON 에서 지수 종가 + 등락률 수집. 실패 시 None.

        fluctuationsRatio 는 부호를 포함하므로 (하락 시 음수) 별도 부호 계산을 하지 않는다.
        """
        code = self._INDEX_CODE.get(market)
        if not code:
            return None
        try:
            resp = requests.get(
                self.INDEX_URL.format(code=code), headers=self.HEADERS, timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            close = float(str(data["closePrice"]).replace(",", ""))
            change_pct = float(str(data.get("fluctuationsRatio") or 0).replace(",", ""))
            return {"value": close, "change_pct": round(change_pct, 2)}
        except Exception as e:
            logger.warning(f"시장 지수 조회 실패 ({market}): {e}")
            return None

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """시가총액 DataFrame 반환 (컬럼: 시가총액, 종목명, 거래량)"""
        self._crawl_market_sum(market)
        rows = {}
        for ticker, info in self._ticker_cache.items():
            if info["market"] != market:
                continue
            rows[ticker] = {
                "시가총액": info["market_cap"],  # 원 단위
                "종목명": info["name"],
                "거래량": info["volume"],
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
        주식 목록 JSON API 1회 조회와 함께 추출되므로 추가 HTTP 비용 0.
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
        stock.naver.com 주식 목록 JSON API 로 시장 전종목을 _ticker_cache 에 채운다.

        응답은 배열이고 한 항목이 itemcode / itemname / marketSum(원) / tradeVolume /
        per(null 가능) / eps / roe / frgnHoldRate 를 담는다. KOSPI 945, KOSDAQ 1820 건이
        pageSize=3000 한 페이지에 들어온다 (startIdx 는 offset 이 아니라 0 기반 페이지 번호).

        KOSPI 는 구형 페이지처럼 ETF 가 섞여 있어야 runner 경로(max_etf 30)가 그대로
        동작하므로 etfItemList 항목을 함께 합친다 (per/roe 없음, 시총 억→원 변환).

        0건이면 RuntimeError 를 던진다. 2026-09-10 구형 페이지 폐쇄 당시 "0종목" 이
        INFO 로만 남아 닷새 동안 발견이 늦었던 일을 막기 위한 장치다.
        """
        if self._market_cached.get(market):
            return
        if market not in self.MARKET_CODE:
            raise ValueError(f"unsupported market: {market}. KOSPI/KOSDAQ만 지원")

        logger.info(f"  [네이버] {market} 종목 목록 조회...")
        # 응답 길이가 pageSize 와 같으면 다음 페이지가 있다고 보고 이어 받는다.
        # 서버가 나중에 pageSize 상한을 낮춰도 중형주가 조용히 잘리지 않게 하는 방어.
        items: list[dict] = []
        page_size = 3000
        for page in range(50):  # 안전장치
            r = requests.get(
                self.STOCK_LIST_URL,
                params={
                    "tradeType": "KRX",
                    "marketType": market,
                    "orderType": "marketSum",
                    "startIdx": page,
                    "pageSize": page_size,
                },
                headers=self.HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            chunk = r.json()
            if not isinstance(chunk, list):
                raise RuntimeError(
                    f"네이버 종목 목록 응답 형식 오류: {type(chunk).__name__}"
                )
            items.extend(chunk)
            if len(chunk) < page_size:
                break

        total = 0
        for item in items:
            code = item.get("itemcode")
            if not code:
                continue
            per_value, per_negative = _classify_per(item.get("per"), item.get("eps"))
            volume = _to_optional_float(item.get("tradeVolume"))
            self._ticker_cache[code] = {
                "name": (item.get("itemname") or "").strip(),
                "market": market,
                "market_cap": _to_optional_float(item.get("marketSum")) or 0.0,
                "volume": int(volume) if volume is not None else None,
                # 펀더멘털 (UI 표시 + 의사결정용). 결측은 None
                "per": per_value,
                "per_negative": per_negative,  # 적자 종목 식별 플래그
                "roe": _to_optional_float(item.get("roe")),
                "foreign_pct": _to_optional_float(item.get("frgnHoldRate")),
            }
            total += 1

        if market == "KOSPI":
            try:
                for item in self._get_etf_items():
                    code = item.get("itemcode")
                    if not code or code in self._ticker_cache:
                        continue
                    quant = item.get("quant")
                    self._ticker_cache[code] = {
                        "name": (item.get("itemname") or "").strip(),
                        "market": market,
                        "market_cap": float(item.get("marketSum") or 0) * 100_000_000,
                        "volume": int(quant) if quant is not None else None,
                        "per": None,
                        "per_negative": False,
                        "roe": None,
                        "foreign_pct": None,
                    }
                    total += 1
            except Exception as e:
                logger.warning(f"  [네이버] ETF 목록 합치기 실패, 주식만 사용: {e}")

        if total == 0:
            raise RuntimeError(
                f"네이버 종목 목록 0건 ({market}) — API 응답 형식 변경 가능성"
            )

        self._market_cached[market] = True
        logger.info(f"  [네이버] {market} 종목 목록 완료: {total}종목")
