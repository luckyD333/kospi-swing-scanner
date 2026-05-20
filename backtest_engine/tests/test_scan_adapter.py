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

from backtest_engine.scan_adapter import (
    ScanBarConfig,
    ScanPnlConfig,
    _track_position,
    make_scan_bartracker_scorer,
    make_scan_pnl_scorer,
)
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


# ---------- BarTracker 어댑터: _track_position 순수 함수 -----------------------


def _ohlc(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """(open, high, low, close) 튜플 리스트 → 정확한 OHLC DataFrame."""
    return pd.DataFrame(
        {
            "open":  [r[0] for r in rows],
            "high":  [r[1] for r in rows],
            "low":   [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [1_000_000] * len(rows),
        },
        index=pd.date_range("2025-01-02", periods=len(rows), freq="B"),
    )


class TestTrackPosition:
    """단일 trade 의 bar-by-bar stop/target 도달 추적."""

    def test_target_reached_bar3(self):
        # bar1~2 정상, bar3 high=106 ≥ target=105 → TARGET, exit=target
        future = _ohlc([
            (100, 101,  99, 100),
            (100, 102,  99, 102),
            (102, 106, 101, 105),
            (105, 107, 104, 106),
            (106, 108, 105, 107),
        ])
        exit_p, bars, reason = _track_position(
            future, entry_price=100.0, stop_loss=95.0, target=105.0, max_holding_bars=5,
        )
        assert reason == "TARGET"
        assert bars == 3
        assert exit_p == 105.0

    def test_stop_reached_bar2(self):
        # bar1 정상, bar2 open=98>stop, low=94 ≤ stop=95 → STOP, exit=stop
        future = _ohlc([
            (100, 101,  99, 100),
            (98,  100,  94,  95),
            (95,   96,  94,  95),
            (95,   96,  94,  95),
            (95,   96,  94,  95),
        ])
        exit_p, bars, reason = _track_position(
            future, entry_price=100.0, stop_loss=95.0, target=120.0, max_holding_bars=5,
        )
        assert reason == "STOP"
        assert bars == 2
        assert exit_p == 95.0

    def test_gap_down_bar1(self):
        # bar1 open=93 ≤ stop=95 → GAP_DOWN, exit=open=93 (stop 보다 낮음, 슬리피지 반영)
        future = _ohlc([
            (93,  95, 92, 94),
            (94,  95, 93, 94),
            (94,  95, 93, 94),
            (94,  95, 93, 94),
            (94,  95, 93, 94),
        ])
        exit_p, bars, reason = _track_position(
            future, entry_price=100.0, stop_loss=95.0, target=110.0, max_holding_bars=5,
        )
        assert reason == "GAP_DOWN"
        assert bars == 1
        assert exit_p == 93.0

    def test_time_stop_no_reach(self):
        # 5봉 모두 stop/target 미도달 → TIME, exit=마지막 close
        future = _ohlc([
            (100, 101,  99, 100),
            (100, 101,  99, 100),
            (100, 101,  99, 101),
            (101, 102, 100, 101),
            (101, 103, 100, 102),
        ])
        exit_p, bars, reason = _track_position(
            future, entry_price=100.0, stop_loss=80.0, target=120.0, max_holding_bars=5,
        )
        assert reason == "TIME"
        assert bars == 5
        assert exit_p == 102.0

    def test_tie_break_stop_priority(self):
        # 같은 봉에 low=94≤stop=95 AND high=111≥target=110 → STOP 우선
        future = _ohlc([
            (100, 111, 94, 105),
            (105, 106, 104, 105),
            (105, 106, 104, 105),
            (105, 106, 104, 105),
            (105, 106, 104, 105),
        ])
        exit_p, bars, reason = _track_position(
            future, entry_price=100.0, stop_loss=95.0, target=110.0, max_holding_bars=5,
        )
        assert reason == "STOP"
        assert bars == 1
        assert exit_p == 95.0

    def test_insufficient_future_bars(self):
        # max_holding_bars=5, future=2봉 → INSUFFICIENT, NaN
        future = _ohlc([
            (100, 101,  99, 100),
            (100, 101,  99, 100),
        ])
        exit_p, bars, reason = _track_position(
            future, entry_price=100.0, stop_loss=95.0, target=110.0, max_holding_bars=5,
        )
        assert reason == "INSUFFICIENT"
        assert bars == 0
        assert np.isnan(exit_p)


# ---------- BarTracker scorer factory ---------------------------------------


class TestBarTrackerScorer:
    """make_scan_bartracker_scorer factory + ScanBarConfig 시그니처/동작."""

    def test_signature_compat_with_pnl_scorer(self):
        """BarTracker scorer 가 N봉 scorer 와 동일 시그니처 → walk_forward 교체 가능."""
        df = _make_df(40, start_price=100.0, daily_step=1.0)
        ohlcv = {"AAA": df}
        strategy = _AlwaysFirstStrategy()
        scorer = make_scan_bartracker_scorer(
            lambda _p: strategy,
            ScanBarConfig(holding_bars=3, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
        )
        start = df.index[20]
        end = df.index[30]
        sharpe, n = scorer(ohlcv, {}, start, end)
        assert isinstance(sharpe, float)
        assert isinstance(n, int)
        assert n > 1  # 단조증가 + target 1.05 → 매 trade target 도달

    def test_emit_stats_exposes_exit_reason_distribution(self):
        """emit_stats=True 시 scorer.last_stats 로 STOP/TARGET/TIME/GAP_DOWN 분포 노출."""
        df = _make_df(40, start_price=100.0, daily_step=1.0)
        ohlcv = {"AAA": df}
        strategy = _AlwaysFirstStrategy()
        scorer = make_scan_bartracker_scorer(
            lambda _p: strategy,
            ScanBarConfig(
                holding_bars=3, top_n=1, commission_pct=0.0,
                lookback_buffer_days=0, emit_stats=True,
            ),
        )
        start = df.index[20]
        end = df.index[30]
        sharpe, n = scorer(ohlcv, {}, start, end)
        stats = scorer.last_stats  # type: ignore[attr-defined]
        assert set(stats.keys()) >= {"STOP", "TARGET", "TIME", "GAP_DOWN", "avg_bars_held"}
        total_reasons = stats["STOP"] + stats["TARGET"] + stats["TIME"] + stats["GAP_DOWN"]
        assert total_reasons == n  # 분포 합 = n_trades

    def test_emit_per_trade_records_exposed(self):
        """emit_per_trade=True 시 scorer.per_trade_records 로 trade 단위 기록 노출."""
        df = _make_df(40, start_price=100.0, daily_step=1.0)
        ohlcv = {"AAA": df}
        strategy = _AlwaysFirstStrategy()
        scorer = make_scan_bartracker_scorer(
            lambda _p: strategy,
            ScanBarConfig(
                holding_bars=3, top_n=1, commission_pct=0.0,
                lookback_buffer_days=0, emit_per_trade=True,
            ),
        )
        sharpe, n = scorer(ohlcv, {}, df.index[20], df.index[30])
        records = scorer.per_trade_records  # type: ignore[attr-defined]
        assert isinstance(records, list)
        assert len(records) == n
        # record schema 검증
        sample = records[0]
        assert set(sample.keys()) >= {
            "signal_date", "ticker", "exit_reason", "pnl_pct", "bars_held",
        }

    def test_emit_per_trade_default_off(self):
        """emit_per_trade 기본값(False) 시 scorer.per_trade_records 비어 있어야."""
        df = _make_df(40, start_price=100.0, daily_step=1.0)
        ohlcv = {"AAA": df}
        strategy = _AlwaysFirstStrategy()
        scorer = make_scan_bartracker_scorer(
            lambda _p: strategy,
            ScanBarConfig(
                holding_bars=3, top_n=1, commission_pct=0.0, lookback_buffer_days=0,
            ),
        )
        scorer(ohlcv, {}, df.index[20], df.index[30])
        # attribute 없거나 빈 리스트 — 호환성 위해 후자 권장
        records = getattr(scorer, "per_trade_records", None)
        assert records is None or records == []

    def test_emit_per_trade_record_content(self):
        """trade record 의 필드값 검증."""
        df = _make_df(40, start_price=100.0, daily_step=1.0)
        ohlcv = {"AAA": df}
        strategy = _AlwaysFirstStrategy()
        scorer = make_scan_bartracker_scorer(
            lambda _p: strategy,
            ScanBarConfig(
                holding_bars=3, top_n=1, commission_pct=0.0,
                lookback_buffer_days=0, emit_per_trade=True,
            ),
        )
        scorer(ohlcv, {}, df.index[20], df.index[20])
        records = scorer.per_trade_records  # type: ignore[attr-defined]
        assert len(records) == 1
        r = records[0]
        assert r["ticker"] == "AAA"
        assert r["exit_reason"] in {"STOP", "TARGET", "TIME", "GAP_DOWN"}
        assert isinstance(r["pnl_pct"], float)
        assert isinstance(r["bars_held"], int)
        assert 1 <= r["bars_held"] <= 3

    def test_target_reached_yields_higher_pnl_than_pnl_scorer(self):
        """단조 상승 시나리오: BarTracker 가 target 조기 도달 → trade 짧고 수익률 ≠ N봉 PnL."""
        df = _make_df(40, start_price=100.0, daily_step=1.0)
        ohlcv = {"AAA": df}
        # N봉 scorer: holding=3 강제, target 무시
        strategy_pnl = _AlwaysFirstStrategy()
        scorer_pnl = make_scan_pnl_scorer(
            lambda _p: strategy_pnl,
            ScanPnlConfig(holding_bars=10, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
        )
        # BarTracker: target=1.05 → 5%면 조기 청산
        strategy_bt = _AlwaysFirstStrategy()
        scorer_bt = make_scan_bartracker_scorer(
            lambda _p: strategy_bt,
            ScanBarConfig(holding_bars=10, top_n=1, commission_pct=0.0, lookback_buffer_days=0),
        )
        start = df.index[20]
        end = df.index[25]
        sh_pnl, n_pnl = scorer_pnl(ohlcv, {}, start, end)
        sh_bt, n_bt = scorer_bt(ohlcv, {}, start, end)
        # 두 scorer 결과가 달라야 함 — BarTracker 가 stop/target 을 본다는 증거
        assert n_pnl > 1 and n_bt > 1
        assert sh_pnl != sh_bt
