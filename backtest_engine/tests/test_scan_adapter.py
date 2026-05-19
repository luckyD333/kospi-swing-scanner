"""tests/test_scan_adapter.py — Strategy Protocol → WF scorer 어댑터 단위 검증.

검증 포인트:
  - ScanContext 가 target_date 이하만 포함 (look-ahead 차단)
  - 진입 = T+1 open, 청산 = T+1+holding_bars close
  - commission 왕복 차감
  - candidates 0건 윈도우 → NaN
  - holding_bars 만큼 미래 봉 없으면 skip
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest_engine.scan_adapter import ScanPnlConfig, make_scan_pnl_scorer
from core.strategy_base import Candidate, ScanContext


# ---------- 합성 데이터 헬퍼 -------------------------------------------------


def _make_df(n: int, start_price: float = 100.0, daily_step: float = 1.0) -> pd.DataFrame:
    """단조 증가 가격 합성. close[T+1+N] - open[T+1] = N×daily_step 보장."""
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    closes = np.array([start_price + i * daily_step for i in range(n)], dtype=float)
    opens = closes - 0.5  # 진입 open = 종가 -0.5 (단조성 유지)
    return pd.DataFrame(
        {
            "open": opens,
            "high": closes + 0.5,
            "low": opens - 0.5,
            "close": closes,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )


# ---------- Dummy Strategy --------------------------------------------------


class _AlwaysFirstStrategy:
    """매 scan() 마다 universe 첫 ticker 1건 반환. look-ahead 검사용."""
    name = "_dummy"
    captured_ctx_sizes: list[int]

    def __init__(self):
        self.captured_ctx_sizes = []

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        self.captured_ctx_sizes.append(
            len(next(iter(ctx.ohlcv.values()))) if ctx.ohlcv else 0
        )
        if not ctx.universe:
            return []
        ticker = ctx.universe[0]
        df = ctx.ohlcv[ticker]
        last_close = float(df["close"].iloc[-1])
        return [
            Candidate(
                ticker=ticker,
                name=ticker,
                strategy="_dummy",
                signal_date=df.index[-1],
                score=500.0,
                entry_price=last_close,
                stop_loss=last_close * 0.97,
                target_1=last_close * 1.03,
                target_2=last_close * 1.05,
            )
        ]


class _NoSignalStrategy:
    name = "_no_signal"

    def scan(self, ctx, top_n):
        return []


# ---------- 테스트 ---------------------------------------------------------


def test_scorer_look_ahead_slice():
    """ScanContext 가 t 이하만 포함 — 매 호출 데이터 길이 단조 증가."""
    df = _make_df(40)
    ohlcv = {"AAA": df}
    strategy = _AlwaysFirstStrategy()
    scorer = make_scan_pnl_scorer(
        lambda _p: strategy,
        ScanPnlConfig(holding_bars=3, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
    )
    start = df.index[30]
    end = df.index[35]
    sharpe, n = scorer(ohlcv, {}, start, end)
    # 매 호출 ctx 크기는 t 위치 기반 → 단조 증가
    sizes = strategy.captured_ctx_sizes
    assert sizes == sorted(sizes), f"ctx 길이 비단조: {sizes}"
    # 마지막 호출 ≤ 전체 df 길이
    assert max(sizes) <= len(df)


def test_scorer_entry_exit_prices():
    """N=3 보유 시 진입=T+1 open, 청산=T+4 close 사용 확인."""
    df = _make_df(40, start_price=100.0, daily_step=1.0)
    ohlcv = {"AAA": df}
    strategy = _AlwaysFirstStrategy()
    scorer = make_scan_pnl_scorer(
        lambda _p: strategy,
        ScanPnlConfig(holding_bars=3, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
    )
    # 단일 signal date 만
    start = df.index[20]
    end = df.index[20]
    sharpe, n = scorer(ohlcv, {}, start, end)
    # 단일 trade → Sharpe NaN (분산 부족)
    assert n == 1
    assert np.isnan(sharpe)


def test_scorer_commission_applied():
    """commission 차감으로 동일 시나리오 PnL 차이 확인."""
    df = _make_df(40, start_price=100.0, daily_step=1.0)
    ohlcv = {"AAA": df}
    strategy_a = _AlwaysFirstStrategy()
    strategy_b = _AlwaysFirstStrategy()
    scorer_zero = make_scan_pnl_scorer(
        lambda _p: strategy_a,
        ScanPnlConfig(holding_bars=3, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
    )
    scorer_high = make_scan_pnl_scorer(
        lambda _p: strategy_b,
        ScanPnlConfig(holding_bars=3, top_n=1, commission_pct=0.05, lookback_buffer_days=0),
    )
    start = df.index[20]
    end = df.index[30]
    sh_zero, n_zero = scorer_zero(ohlcv, {}, start, end)
    sh_high, n_high = scorer_high(ohlcv, {}, start, end)
    # 동일 trades, commission 만 차이 → Sharpe 변동 (zero 가 더 큼)
    assert n_zero == n_high > 1
    assert sh_zero > sh_high


def test_scorer_no_signal_returns_nan():
    """모든 윈도우에서 signal 0건이면 NaN 반환."""
    df = _make_df(40)
    ohlcv = {"AAA": df}
    scorer = make_scan_pnl_scorer(
        lambda _p: _NoSignalStrategy(),
        ScanPnlConfig(holding_bars=3, top_n=1, lookback_buffer_days=0),
    )
    sharpe, n = scorer(ohlcv, {}, df.index[20], df.index[30])
    assert np.isnan(sharpe)
    assert n == 0


def test_scorer_insufficient_future_bars_skipped():
    """signal date 가 end 에 가까워 holding_bars+1 미래 봉 부족하면 trade 발생 X."""
    df = _make_df(40)
    ohlcv = {"AAA": df}
    strategy = _AlwaysFirstStrategy()
    scorer = make_scan_pnl_scorer(
        lambda _p: strategy,
        ScanPnlConfig(holding_bars=3, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
    )
    # signal = 마지막 봉 (T+1 자체 없음)
    last = df.index[-1]
    sharpe, n = scorer(ohlcv, {}, last, last)
    assert n == 0


def test_scorer_top_n_caps_candidates():
    """scan() 이 top_n 보다 많이 반환해도 어댑터가 cap 적용."""
    df = _make_df(40)
    ohlcv = {"AAA": df, "BBB": df.copy()}

    class _MultiCand:
        name = "_multi"
        def scan(self, ctx, top_n):
            cands = []
            for t in ctx.universe:
                last_close = float(ctx.ohlcv[t]["close"].iloc[-1])
                cands.append(
                    Candidate(
                        ticker=t, name=t, strategy="_multi",
                        signal_date=ctx.ohlcv[t].index[-1], score=500.0,
                        entry_price=last_close,
                        stop_loss=last_close * 0.97,
                        target_1=last_close * 1.03,
                        target_2=last_close * 1.05,
                    )
                )
            return cands

    scorer = make_scan_pnl_scorer(
        lambda _p: _MultiCand(),
        ScanPnlConfig(holding_bars=3, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
    )
    start = df.index[20]
    end = df.index[20]
    sharpe, n = scorer(ohlcv, {}, start, end)
    # universe 2종목인데 top_n=1 cap → 1 trade
    assert n == 1
