"""
test_runner_fundamentals_injection.py — Step 3 검증.

ScanContext에 fundamentals 필드 추가 + runner.py 사후 주입 패턴 검증.
전략 코드 무수정 원칙(CLAUDE.md): runner가 후보 metadata에 일괄 주입.

검증:
  - ScanContext.fundamentals 필드 존재 + 기본 빈 dict
  - DataClient.get_fundamentals 위임 (source 의 메서드 호출)
  - runner.run() 후 모든 후보의 metadata에 per/roe/foreign_pct/naver_url 키 존재
  - get_fundamentals 빈 응답이어도 naver_url은 항상 채워짐 (ticker 기반 패턴)
"""
from __future__ import annotations

import pandas as pd

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.data_sources.naver import naver_detail_url
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import Candidate, ScanContext


# ---------------------------------------------------------------------------
# ScanContext 필드 검증
# ---------------------------------------------------------------------------

def test_scan_context_has_fundamentals_field():
    """ScanContext.fundamentals: dict[ticker, dict] 필드 존재, 기본 빈 dict."""
    ctx = ScanContext(
        target_date="20260502",
        universe=("005930",),
        ohlcv={},
        names={"005930": "삼성전자"},
        market_caps={"005930": 1.0e12},
        market="KOSPI",
    )
    assert hasattr(ctx, "fundamentals")
    assert ctx.fundamentals == {}


def test_scan_context_accepts_fundamentals():
    """fundamentals 인자로 ticker별 dict 주입 가능."""
    funds = {
        "005930": {"per": 33.59, "roe": 10.85, "foreign_pct": 49.27,
                   "naver_url": naver_detail_url("005930")},
    }
    ctx = ScanContext(
        target_date="20260502",
        universe=("005930",),
        ohlcv={},
        names={"005930": "삼성전자"},
        market_caps={"005930": 1.0e12},
        market="KOSPI",
        fundamentals=funds,
    )
    assert ctx.fundamentals["005930"]["per"] == 33.59


# ---------------------------------------------------------------------------
# Runner 사후 주입 — Mock source with fundamentals
# ---------------------------------------------------------------------------

class _FundamentalsAwareSource(DailyDataSource):
    """get_fundamentals를 구현한 mock source."""
    name = "mock_funda"

    def __init__(self, tickers: list[str], caps: dict[str, float],
                 funds: dict[str, dict] | None = None):
        self._tickers = tickers
        self._caps = caps
        self._funds = funds or {}

    def get_tickers(self, market, target_date):
        return list(self._tickers)

    def get_ticker_name(self, ticker):
        return ticker

    def get_ohlcv(self, ticker, start, end, timeframe="1D"):
        return pd.DataFrame(
            {"open": [100.0] * 40, "high": [101.0] * 40, "low": [99.0] * 40,
             "close": [100.0] * 40, "volume": [1_000_000] * 40},
            index=pd.date_range("2026-01-01", periods=40, freq="D"),
        )

    def get_market_cap(self, market, target_date):
        rows = {t: {"시가총액": self._caps[t], "종목명": t} for t in self._tickers}
        return pd.DataFrame(rows).T

    def get_fundamentals(self, market, target_date):
        if not self._funds:
            return pd.DataFrame(columns=["per", "roe", "foreign_pct", "naver_url"])
        rows = {}
        for t, f in self._funds.items():
            rows[t] = {
                "per": f.get("per"),
                "roe": f.get("roe"),
                "foreign_pct": f.get("foreign_pct"),
                "naver_url": naver_detail_url(t),
            }
        return pd.DataFrame(rows).T


class _AlwaysCandidateStrategy:
    """모든 universe ticker에 대해 후보 1개씩 반환하는 더미 전략."""
    name = "dummy_alpha"
    timeframe = "1D"

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        out = []
        for ticker in ctx.universe[:top_n]:
            out.append(Candidate(
                ticker=ticker,
                name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=pd.Timestamp("2026-05-02"),
                score=500.0,
                entry_price=100.0,
                stop_loss=98.0,
                target_1=102.0,
                target_2=104.0,
            ))
        return out


def _build_runner(source) -> ScanRunner:
    client = DataClient(ticker_list_sources=[source], ohlcv_sources=[source])
    return ScanRunner(client, RunnerConfig(
        market="KOSPI",
        min_market_cap_bil=10.0,
        max_market_cap_bil=1_000_000.0,
        min_daily_volume=0,
        top_n=10,
    ))


def test_runner_injects_fundamentals_into_candidate_metadata():
    """get_fundamentals 데이터가 후보 metadata에 사후 주입된다."""
    tickers = ["005930", "000660"]
    caps = {"005930": 5e12, "000660": 1e12}
    funds = {
        "005930": {"per": 33.59, "roe": 10.85, "foreign_pct": 49.27},
        "000660": {"per": 21.81, "roe": 44.15, "foreign_pct": 52.92},
    }
    source = _FundamentalsAwareSource(tickers, caps, funds)
    runner = _build_runner(source)
    result = runner.run([_AlwaysCandidateStrategy()], target_date="20260502")

    candidates = result.candidates_by_strategy["dummy_alpha"]
    assert len(candidates) == 2

    by_ticker = {c.ticker: c for c in candidates}

    assert by_ticker["005930"].metadata["per"] == 33.59
    assert by_ticker["005930"].metadata["roe"] == 10.85
    assert by_ticker["005930"].metadata["foreign_pct"] == 49.27
    assert by_ticker["005930"].metadata["naver_url"] == \
        "https://finance.naver.com/item/main.naver?code=005930"

    assert by_ticker["000660"].metadata["per"] == 21.81
    assert by_ticker["000660"].metadata["naver_url"] == \
        "https://finance.naver.com/item/main.naver?code=000660"


def test_runner_injects_naver_url_even_when_fundamentals_empty():
    """get_fundamentals가 빈 결과를 반환해도 naver_url은 ticker 기반 패턴으로 채워진다.

    UI 일관성: 모든 후보가 같은 metadata 키 셋을 가져야 함.
    """
    tickers = ["005930"]
    caps = {"005930": 5e12}
    source = _FundamentalsAwareSource(tickers, caps, funds=None)  # 빈 fundamentals
    runner = _build_runner(source)
    result = runner.run([_AlwaysCandidateStrategy()], target_date="20260502")

    cand = result.candidates_by_strategy["dummy_alpha"][0]
    assert cand.metadata["naver_url"] == \
        "https://finance.naver.com/item/main.naver?code=005930"
    # per/roe/foreign_pct 키도 일관성 위해 존재해야 함 (값은 None)
    assert "per" in cand.metadata
    assert "roe" in cand.metadata
    assert "foreign_pct" in cand.metadata
    assert cand.metadata["per"] is None
    assert cand.metadata["roe"] is None
    assert cand.metadata["foreign_pct"] is None


def test_runner_does_not_modify_candidate_strategy_specific_metadata():
    """전략이 metadata에 자체 키를 넣었다면 보존되어야 한다 (사후 주입은 update만)."""

    class _StrategyWithCustomMeta:
        name = "with_meta"
        timeframe = "1D"

        def scan(self, ctx, top_n):
            ticker = ctx.universe[0]
            return [Candidate(
                ticker=ticker,
                name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=pd.Timestamp("2026-05-02"),
                score=500.0,
                entry_price=100.0, stop_loss=98.0,
                target_1=102.0, target_2=104.0,
                metadata={"custom_key": "custom_value", "momentum_pct": 7.5},
            )]

    funds = {"005930": {"per": 33.59, "roe": 10.85, "foreign_pct": 49.27}}
    source = _FundamentalsAwareSource(["005930"], {"005930": 5e12}, funds)
    runner = _build_runner(source)
    result = runner.run([_StrategyWithCustomMeta()], target_date="20260502")

    cand = result.candidates_by_strategy["with_meta"][0]
    # 전략 고유 키 보존
    assert cand.metadata["custom_key"] == "custom_value"
    assert cand.metadata["momentum_pct"] == 7.5
    # 사후 주입 키도 추가됨
    assert cand.metadata["per"] == 33.59


# ---------------------------------------------------------------------------
# DataClient 위임 검증
# ---------------------------------------------------------------------------

def test_data_client_delegates_get_fundamentals():
    """DataClient.get_fundamentals → ticker_list_sources 첫 번째 source의 동명 메서드."""
    funds = {"005930": {"per": 33.59, "roe": 10.85, "foreign_pct": 49.27}}
    source = _FundamentalsAwareSource(["005930"], {"005930": 5e12}, funds)
    client = DataClient(ticker_list_sources=[source], ohlcv_sources=[source])

    df = client.get_fundamentals("KOSPI", "20260502")
    assert "per" in df.columns
    assert df.loc["005930", "per"] == 33.59
    assert df.loc["005930", "naver_url"] == \
        "https://finance.naver.com/item/main.naver?code=005930"


def test_data_client_get_fundamentals_empty_when_source_lacks():
    """source 가 get_fundamentals 미지원 → 빈 DataFrame (BC: base 클래스 기본 구현)."""
    class _MinimalSource(DailyDataSource):
        name = "minimal"

        def get_tickers(self, market, target_date):
            return ["005930"]

        def get_ticker_name(self, ticker):
            return ticker

        def get_ohlcv(self, ticker, start, end, timeframe="1D"):
            return pd.DataFrame()

    client = DataClient(ticker_list_sources=[_MinimalSource()],
                        ohlcv_sources=[_MinimalSource()])
    df = client.get_fundamentals("KOSPI", "20260502")
    assert df.empty or len(df) == 0
