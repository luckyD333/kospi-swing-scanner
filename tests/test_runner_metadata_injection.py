"""tests/test_runner_metadata_injection.py — Step 1 TDD.

runner.py 가 candidate.metadata 에 per_ticker_regime + atr_bucket 을 주입하는지 검증.
holding_recommender 가 modifier lookup 시 이 두 키를 읽으므로, 누락되면 modifier 가
항상 미적용되는 결함이 발생함.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import Candidate, ScanContext


class _DiverseAtrSource(DailyDataSource):
    """ticker 별 변동성이 다른 OHLCV 를 반환 — ATR 분위수 분포 형성용."""

    name = "diverse_atr"

    def __init__(self, tickers: list[str], caps: dict[str, float],
                 noise_scale: dict[str, float]):
        self._tickers = tickers
        self._caps = caps
        # noise_scale[ticker] = 일일 가격 변동 폭 (close 기준 %)
        self._noise = noise_scale

    def get_tickers(self, market, target_date):
        return list(self._tickers)

    def get_ticker_name(self, ticker):
        return ticker

    def get_ohlcv(self, ticker, start, end):
        # 60봉 — ATR(14) + Donchian(20) 모두 충분
        n = 60
        scale = self._noise.get(ticker, 0.01)
        rng = np.random.default_rng(seed=hash(ticker) & 0xFFFFFFFF)
        base = 100.0
        closes = base * (1 + rng.normal(0, scale, n).cumsum() * 0.1)
        closes = np.clip(closes, 50.0, 200.0)
        highs = closes * (1 + np.abs(rng.normal(0, scale, n)))
        lows = closes * (1 - np.abs(rng.normal(0, scale, n)))
        return pd.DataFrame(
            {"open": closes, "high": highs, "low": lows,
             "close": closes, "volume": [1_000_000] * n},
            index=pd.date_range("2026-01-01", periods=n, freq="D"),
        )

    def get_market_cap(self, market, target_date):
        rows = {t: {"시가총액": self._caps[t], "종목명": t} for t in self._tickers}
        return pd.DataFrame(rows).T


class _FakeStrategy:
    """모든 universe ticker 를 후보로 반환."""

    name = "fake_strategy"
    timeframe = "1D"

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        out = []
        for ticker in ctx.universe[:top_n]:
            out.append(Candidate(
                ticker=ticker, name=ctx.names.get(ticker, ticker),
                strategy=self.name,
                signal_date=pd.Timestamp(ctx.target_date),
                score=0.7, entry_price=100.0, stop_loss=97.5,
                target_1=103.0, target_2=105.0,
            ))
        return out


def _make_runner():
    # 변동성 LOW/MID/HIGH 분포 형성 — bucket_atr 가 p33/p67 분기 가능하도록
    tickers = [f"{i:06d}" for i in range(6)]
    caps = {t: 5_000 * 1e8 for t in tickers}
    noise = {
        tickers[0]: 0.005, tickers[1]: 0.008,  # LOW
        tickers[2]: 0.015, tickers[3]: 0.018,  # MID
        tickers[4]: 0.030, tickers[5]: 0.035,  # HIGH
    }
    src = _DiverseAtrSource(tickers, caps, noise)
    client = DataClient(ticker_list_sources=[src], ohlcv_sources=[src])
    runner = ScanRunner(client, RunnerConfig(top_n=10, lookback_days=60))
    return runner, src, tickers


def test_metadata_per_ticker_regime_injected():
    """candidate.metadata 에 per_ticker_regime 키가 비-None 값으로 주입된다."""
    runner, _, _ = _make_runner()
    result = runner.run([_FakeStrategy()], target_date="20260301")
    candidates = result.candidates_by_strategy["fake_strategy"]
    assert candidates, "후보 없음 — fixture 점검"
    for cand in candidates:
        assert "per_ticker_regime" in cand.metadata, (
            f"per_ticker_regime 키 누락: {cand.metadata.keys()}"
        )
        regime = cand.metadata["per_ticker_regime"]
        assert isinstance(regime, str)
        assert regime in {
            "UPTREND_STRONG", "UPTREND_WEAK", "RANGE_TIGHT", "RANGE",
            "DOWNTREND_WEAK", "DOWNTREND_STRONG", "MIXED",
        }


def test_metadata_atr_bucket_injected():
    """candidate.metadata 에 atr_bucket 키가 LOW/MID/HIGH 중 하나로 주입된다."""
    runner, _, _ = _make_runner()
    result = runner.run([_FakeStrategy()], target_date="20260301")
    candidates = result.candidates_by_strategy["fake_strategy"]
    assert candidates
    buckets = set()
    for cand in candidates:
        assert "atr_bucket" in cand.metadata, (
            f"atr_bucket 키 누락: {cand.metadata.keys()}"
        )
        bucket = cand.metadata["atr_bucket"]
        assert bucket in {"LOW", "MID", "HIGH"}
        buckets.add(bucket)
    # 변동성 분포가 다양하므로 최소 2개 bucket 출현 기대 (회귀 방지)
    assert len(buckets) >= 2, f"bucket 분포가 단조로움: {buckets}"
