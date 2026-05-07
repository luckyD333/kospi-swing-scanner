"""
test_targets.py — PR-G: T1/T2 차별화 + T2 gap collapse 검증.

검증 항목:
  1. 평균 회귀(strategy_one): T1 = 20MA, T2 = 20MA + 1σ
  2. 추세 추종(strategy_three): T1 = entry+1R, T2 = entry+Donchian width
  3. 전략 2·4 ATR×3.0 default 유지 (D1)
  4. T2-T1 < 1.5% → signals_builder 에서 target_2=None
  5. target_*_rationale metadata 키 존재
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest_engine.scenarios import ScenarioBuilder
from core.strategy_base import ScanContext
from output.models import Fundamentals, Flow, MarketSnapshot, TickerSnapshot
from output.signals_builder import build_signals_payload
from strategies.strategy_one_d_v2 import StrategyOneDv2
from strategies.strategy_three_trend_following import (
    StrategyThreeConfig,
    StrategyThreeTrendFollowing,
)


# ============================================================================
# 공통 헬퍼
# ============================================================================

def _make_ctx(ticker_dfs: dict[str, pd.DataFrame]) -> ScanContext:
    return ScanContext(
        target_date="20260418",
        universe=tuple(ticker_dfs.keys()),
        ohlcv=ticker_dfs,
        names={t: t for t in ticker_dfs},
        market_caps={t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
    )


def _make_breakout_df(
    n_consolidation: int = 25,
    consolidation_low: float = 9900.0,
    consolidation_high: float = 10100.0,
    breakout_close: float = 10250.0,
) -> pd.DataFrame:
    n = n_consolidation + 1
    closes = np.array([
        *(np.linspace(consolidation_low, consolidation_high, n_consolidation)),
        breakout_close,
    ])
    highs = np.where(np.arange(n) < n_consolidation, consolidation_high, breakout_close).astype(float)
    lows  = np.where(np.arange(n) < n_consolidation, consolidation_low,  breakout_close * 0.998).astype(float)
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": [1_000_000] * n},
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


def _make_breakout_df_wide_channel(
    n_consolidation: int = 25,
    breakout_close: float = 10300.0,
) -> pd.DataFrame:
    """채널은 넓고(≈500p) ATR은 작은(≈100p) 픽스처.

    Donchian width(≈500) > 1R(≈150) 이 돼서 T2 = entry + donchian_width 검증 가능.
    """
    closes = np.linspace(9600.0, 10100.0, n_consolidation)
    highs  = closes + 50.0   # bar 내 변동폭 100 → ATR ≈ 100
    lows   = closes - 50.0
    n = n_consolidation + 1
    closes_all = np.append(closes, breakout_close)
    highs_all  = np.append(highs,  breakout_close)
    lows_all   = np.append(lows,   breakout_close * 0.998)
    return pd.DataFrame(
        {"open": closes_all, "high": highs_all, "low": lows_all,
         "close": closes_all, "volume": [1_000_000] * n},
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


# ============================================================================
# 평균 회귀 (strategy_one) T1/T2
# ============================================================================

def test_mean_reversion_t1_is_20ma():
    """T1 ≈ 20MA — 평균 회귀 첫 번째 목표는 20일 이동평균."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]
    ctx = _make_ctx({"MR": df})
    cands = StrategyOneDv2().scan(ctx, top_n=5)
    assert cands

    c = cands[0]
    sma_20 = float(df["close"].iloc[-20:].mean())
    expected_t1 = sma_20

    # tick 반올림 오차(최대 100원) 허용
    assert abs(c.target_1 - expected_t1) <= 100, (
        f"target_1={c.target_1}, expected≈{expected_t1:.1f}"
    )


def test_mean_reversion_t2_is_20ma_plus_1sigma():
    """T2 ≈ 20MA + 1σ — 평균 회귀 오버슈트 목표."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]
    ctx = _make_ctx({"MR": df})
    cands = StrategyOneDv2().scan(ctx, top_n=5)
    assert cands

    c = cands[0]
    sma_20 = float(df["close"].iloc[-20:].mean())
    std_20 = float(df["close"].iloc[-20:].std(ddof=1))
    expected_t2 = sma_20 + std_20

    assert abs(c.target_2 - expected_t2) <= 100, (
        f"target_2={c.target_2}, expected≈{expected_t2:.1f}"
    )


def test_mean_reversion_t2_gte_t1():
    """T2 ≥ T1 항상 보장."""
    for seed in [42, 7, 99]:
        scenario = ScenarioBuilder.perfect_double_bottom(seed=seed)
        df = scenario.df.iloc[:33]
        ctx = _make_ctx({f"MR{seed}": df})
        cands = StrategyOneDv2().scan(ctx, top_n=5)
        for c in cands:
            assert c.target_2 >= c.target_1, f"seed={seed}: T2={c.target_2} < T1={c.target_1}"


# ============================================================================
# 추세 추종 (strategy_three) T1/T2
# ============================================================================

def test_trend_following_t1_is_1r():
    """T1 = entry + 1R (1R = entry - stop_loss)."""
    df = _make_breakout_df()
    ctx = _make_ctx({"TF": df})
    cands = StrategyThreeTrendFollowing(
        StrategyThreeConfig(atr_filter_multiplier=0.0, lookback=20)
    ).scan(ctx, top_n=5)
    assert cands

    c = cands[0]
    risk = c.entry_price - c.stop_loss
    expected_t1 = c.entry_price + risk

    assert abs(c.target_1 - expected_t1) <= 15, (
        f"target_1={c.target_1}, expected≈{expected_t1:.1f} "
        f"(entry={c.entry_price}, stop={c.stop_loss})"
    )


def test_trend_following_t2_uses_donchian_width():
    """T2 = entry + (channel_high - channel_low) = entry + Donchian width.

    wide_channel 픽스처: ATR≈100 < 채널폭≈500 → Donchian T2 > T1(1R) 보장.
    """
    df = _make_breakout_df_wide_channel()
    ctx = _make_ctx({"TF": df})
    cands = StrategyThreeTrendFollowing(
        StrategyThreeConfig(atr_filter_multiplier=0.0, lookback=20)
    ).scan(ctx, top_n=5)
    assert cands, "wide_channel breakout 후보 발생 필요"

    c = cands[0]
    channel_high = c.metadata["channel_high"]
    channel_low  = c.metadata["channel_low"]
    donchian_width = channel_high - channel_low
    expected_t2 = c.entry_price + donchian_width

    # T2 = max(entry+donchian_width, T1) 이므로 donchian_width > 1R 이면 donchian T2 채택
    assert donchian_width > (c.entry_price - c.stop_loss), (
        f"픽스처 조건 미충족: donchian_width={donchian_width:.1f} ≤ 1R={c.entry_price - c.stop_loss:.1f}"
    )
    assert abs(c.target_2 - expected_t2) <= 15, (
        f"target_2={c.target_2}, expected≈{expected_t2:.1f} "
        f"(width={donchian_width:.1f})"
    )


# ============================================================================
# 전략 2·4 ATR×3.0 default 유지 확인 (D1)
# ============================================================================

def test_strategy_two_four_unchanged_default_atr_3x():
    """전략 2·4 는 c4c1bc9 의 ATR×3.0 default 미수정 (D1 결정)."""
    from strategies.strategy_two_cross_sectional_momentum import StrategyTwoConfig
    from strategies.strategy_four_pullback_ma import StrategyFourConfig

    assert StrategyTwoConfig().atr_target_mult == 3.0, "전략 2 ATR×3.0 default 변경됨"
    assert StrategyFourConfig().atr_target_mult == 3.0, "전략 4 ATR×3.0 default 변경됨"


# ============================================================================
# T2 gap collapse (signals_builder)
# ============================================================================

def _make_snapshot(ticker: str = "TEST01") -> MarketSnapshot:
    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-07T22:00:00+09:00",
        source={},
        market_indices={},
        tickers={ticker: TickerSnapshot(
            ticker=ticker, name="테스트종목",
            current_price=10000, change_pct=0.0, volume=100_000,
            market_cap_krw=500_000_000_000,
            fundamentals=Fundamentals(),
            flow=Flow(),
        )},
    )


def _make_mock_candidate(
    ticker: str = "TEST01",
    entry: int = 10000,
    stop: int = 9750,
    t1: int = 10150,
    t2: int | None = 10250,
) -> MagicMock:
    c = MagicMock()
    c.ticker = ticker
    c.name = "테스트종목"
    c.score = 500.0
    c.timeframe = "1D"
    c.entry_price = entry
    c.stop_loss = stop
    c.target_1 = t1
    c.target_2 = t2
    c.signal_date = None
    c.limit_entry = None
    c.limit_stop = None
    c.metadata = {"rr_ratio": 2.0, "rr_band": "sweet", "atr_14": 200}
    return c


def test_t2_t1_gap_collapse_below_1_5pct():
    """T2-T1 < 1.5% × entry → signals_builder 에서 target_2=None."""
    # entry=10000, T1=10100, T2=10200 → gap=100 = 1.0% < 1.5% → collapse
    snap = _make_snapshot()
    c = _make_mock_candidate(entry=10000, stop=9750, t1=10100, t2=10200)
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [c]})
    assert payload.signals
    assert payload.signals[0].trade_plan.target_2 is None, (
        "T2-T1=100 (1.0% of 10000) < 1.5% → target_2 should be None"
    )


def test_t2_t1_gap_preserved_above_1_5pct():
    """T2-T1 ≥ 1.5% × entry → target_2 유지."""
    # entry=10000, T1=10100, T2=10300 → gap=200 = 2.0% ≥ 1.5% → 유지
    snap = _make_snapshot()
    c = _make_mock_candidate(entry=10000, stop=9750, t1=10100, t2=10300)
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [c]})
    assert payload.signals
    assert payload.signals[0].trade_plan.target_2 == 10300


# ============================================================================
# target_*_rationale metadata
# ============================================================================

def test_mean_reversion_target_rationale_in_metadata():
    """평균 회귀 Candidate 에 target_1_rationale / target_2_rationale 존재."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]
    ctx = _make_ctx({"MR": df})
    cands = StrategyOneDv2().scan(ctx, top_n=5)
    assert cands
    c = cands[0]
    assert "target_1_rationale" in c.metadata, "target_1_rationale 키 부재"
    assert "target_2_rationale" in c.metadata, "target_2_rationale 키 부재"
    assert c.metadata["target_1_rationale"] == "20MA 회귀 가격"
    assert c.metadata["target_2_rationale"] == "20MA + 1σ"


def test_trend_following_target_rationale_in_metadata():
    """추세 추종 Candidate 에 target_1_rationale / target_2_rationale 존재."""
    df = _make_breakout_df()
    ctx = _make_ctx({"TF": df})
    cands = StrategyThreeTrendFollowing(
        StrategyThreeConfig(atr_filter_multiplier=0.0, lookback=20)
    ).scan(ctx, top_n=5)
    assert cands
    c = cands[0]
    assert "target_1_rationale" in c.metadata
    assert "target_2_rationale" in c.metadata
    assert c.metadata["target_1_rationale"] == "1R 목표가 (진입-손절 × 1)"
    assert c.metadata["target_2_rationale"] == "Donchian 채널 폭 목표가"
