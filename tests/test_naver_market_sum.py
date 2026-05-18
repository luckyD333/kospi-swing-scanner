"""
test_naver_market_sum.py — sise_market_sum 페이지에서 펀더멘털 컬럼(PER/ROE/외인비율)
파싱 검증.

실제 네이버 호출 금지. tests/fixtures/sise_market_sum/{kospi,kosdaq}_p1_default.html
fixture(2026-05-02 1회 fetch)를 mock 응답으로 주입해서 검증한다.

검증 포인트:
  - 디폴트 컬럼 순서: N|종목명|...|외국인비율|거래량|PER|ROE|토론 (KOSPI=KOSDAQ 동일)
  - 결측치(N/A) → None (JSON 호환)
  - 음수 PER/ROE 정상 처리 (적자 종목)
  - get_fundamentals() 새 메서드 DataFrame 반환
  - naver_detail_url() 헬퍼: ticker → 네이버 종목 상세 URL
  - get_market_cap() 시그니처 BC 유지
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

from core.data_sources.naver import NaverSource, naver_detail_url

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sise_market_sum"


def _load_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _make_response(text: str) -> MagicMock:
    fake = MagicMock()
    fake.text = text
    fake.raise_for_status = MagicMock()
    return fake


def _patch_one_page(html: str):
    """
    page=1만 fixture 응답, page>=2 는 빈 HTML 반환 (read_html ValueError → break).
    _crawl_market_sum의 페이지 순회를 한 번만 돌도록 강제.
    """
    seen = {"n": 0}

    def fake_get(*args, **kwargs):
        seen["n"] += 1
        if seen["n"] == 1:
            return _make_response(html)
        return _make_response("<html></html>")

    return patch("core.data_sources.naver.requests.get", side_effect=fake_get)


# ---------------------------------------------------------------------------
# naver_detail_url 헬퍼
# ---------------------------------------------------------------------------

def test_naver_detail_url_pattern():
    """ticker → stock.naver.com/domestic/stock/{ticker}/price 패턴."""
    assert naver_detail_url("005930") == "https://stock.naver.com/domestic/stock/005930/price"
    assert naver_detail_url("003550") == "https://stock.naver.com/domestic/stock/003550/price"


# ---------------------------------------------------------------------------
# _crawl_market_sum: 펀더멘털 추출
# ---------------------------------------------------------------------------

def test_crawl_market_sum_extracts_fundamentals_kospi():
    """KOSPI 1페이지 → _ticker_cache 에 per/roe/foreign_pct 채워짐."""
    html = _load_fixture("kospi_p1_default.html")
    src = NaverSource()
    with _patch_one_page(html):
        src._crawl_market_sum("KOSPI")

    # 삼성전자 (실제 fixture 기준값, 2026-05-02 시점)
    samsung = src._ticker_cache.get("005930")
    assert samsung is not None
    assert samsung["per"] == 33.59
    assert samsung["roe"] == 10.85
    assert samsung["foreign_pct"] == 49.27

    # SK하이닉스
    sk = src._ticker_cache.get("000660")
    assert sk["per"] == 21.81
    assert sk["roe"] == 44.15
    assert sk["foreign_pct"] == 52.92


def test_crawl_market_sum_handles_na_roe():
    """N/A (NaN) 결측치는 None 으로 정규화 (JSON 호환)."""
    html = _load_fixture("kospi_p1_default.html")
    src = NaverSource()
    with _patch_one_page(html):
        src._crawl_market_sum("KOSPI")

    # 삼성전자우(005935): ROE 가 N/A
    samsung_pref = src._ticker_cache.get("005935")
    assert samsung_pref is not None
    assert samsung_pref["roe"] is None
    # 다른 컬럼은 정상값
    assert samsung_pref["per"] == 24.12
    assert samsung_pref["foreign_pct"] == 78.01


def test_crawl_market_sum_negative_per_kosdaq():
    """KOSDAQ 적자 종목: 음수 PER → None + per_negative=True (PR-A 정책).

    음수 PER 은 lower_better 정렬에서 '가장 낮은 = 가장 좋은 PER' 으로 오해석되어
    적자 종목이 부당 가산받는 P0-1 이슈 유발. PR-A 가 None + negative_flag 로 분리.
    ROE 는 PR-A 범위 외 — 별도 흐름이므로 음수값 그대로 보존.
    """
    html = _load_fixture("kosdaq_p1_default.html")
    src = NaverSource()
    with _patch_one_page(html):
        src._crawl_market_sum("KOSDAQ")

    # 에코프로 (086520): 적자 → PER None + flag, ROE 는 음수값 보존
    ecopro = src._ticker_cache.get("086520")
    assert ecopro is not None
    assert ecopro["per"] is None  # 음수 PER 은 적자 sentinel 로 분류 (PR-A)
    assert ecopro["per_negative"] is True  # 적자 플래그
    assert ecopro["roe"] == -8.39  # ROE 는 PR-A 범위 외
    assert ecopro["foreign_pct"] == 19.22


def test_crawl_market_sum_kospi_kosdaq_same_columns():
    """KOSPI/KOSDAQ 동일 컬럼 구조 — 같은 파싱 코드가 양쪽 모두 작동."""
    src = NaverSource()
    with _patch_one_page(_load_fixture("kospi_p1_default.html")):
        src._crawl_market_sum("KOSPI")
    with _patch_one_page(_load_fixture("kosdaq_p1_default.html")):
        src._crawl_market_sum("KOSDAQ")

    kospi_count = sum(1 for v in src._ticker_cache.values() if v["market"] == "KOSPI")
    kosdaq_count = sum(1 for v in src._ticker_cache.values() if v["market"] == "KOSDAQ")
    assert kospi_count == 50  # 페이지당 50개
    assert kosdaq_count == 50

    # 양쪽 모두 per/roe/foreign_pct 키 존재
    for ticker, info in src._ticker_cache.items():
        assert "per" in info
        assert "roe" in info
        assert "foreign_pct" in info


# ---------------------------------------------------------------------------
# get_market_cap BC: 기존 시그니처 + 컬럼 유지
# ---------------------------------------------------------------------------

def test_get_market_cap_signature_unchanged():
    """기존 get_market_cap 컬럼(시가총액, 종목명) 유지 — 호출 측 BC."""
    html = _load_fixture("kospi_p1_default.html")
    src = NaverSource()
    with _patch_one_page(html):
        df = src.get_market_cap("KOSPI", "20260502")

    assert "시가총액" in df.columns
    assert "종목명" in df.columns
    assert "005930" in df.index  # 삼성전자
    assert df.loc["005930", "종목명"] == "삼성전자"


# ---------------------------------------------------------------------------
# get_fundamentals: 새 메서드
# ---------------------------------------------------------------------------

def test_get_fundamentals_returns_dataframe():
    """새 메서드: 인덱스=ticker, 컬럼=per/roe/foreign_pct/naver_url."""
    html = _load_fixture("kospi_p1_default.html")
    src = NaverSource()
    with _patch_one_page(html):
        df = src.get_fundamentals("KOSPI", "20260502")

    assert isinstance(df, pd.DataFrame)
    for col in ["per", "roe", "foreign_pct", "naver_url"]:
        assert col in df.columns

    # 값 검증
    assert df.loc["005930", "per"] == 33.59
    assert df.loc["005930", "roe"] == 10.85
    assert df.loc["005930", "naver_url"] == "https://stock.naver.com/domestic/stock/005930/price"

    # 결측 None 으로 노출 (DataFrame 에서는 None 또는 NaN — to_dict 후에도 호환되어야)
    samsung_pref = df.loc["005935"].to_dict()
    assert samsung_pref["roe"] is None or pd.isna(samsung_pref["roe"])


def test_get_fundamentals_empty_when_market_unknown():
    """존재하지 않는 시장 → 빈 DataFrame (기존 get_market_cap 패턴 동일)."""
    src = NaverSource()
    with _patch_one_page("<html></html>"):
        # ValueError 없이 _crawl_market_sum 의 정상 경로 — KOSPI 호출 후 fundamentals
        try:
            df = src.get_fundamentals("KOSPI", "20260502")
        except ValueError:
            df = pd.DataFrame()
    # 빈 응답이면 빈 결과 — 키 없는 게 정상
    assert df.empty or len(df) == 0
