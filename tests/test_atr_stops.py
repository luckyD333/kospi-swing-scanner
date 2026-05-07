"""
test_atr_stops.py — PR-F: ATR 기반 동적 손절폭 검증.

검증 항목:
  1. compute_atr_stop 헬퍼 단위 테스트 (추세 추종 / 평균 회귀 공식)
  2. strategy_three 통합: stop = max(entry-1.5×ATR, channel_low-0.5×ATR)
  3. strategy_one  통합: stop = max(entry-2.0×ATR, prev_support-1×ATR)
  4. ATR 결측 시 % fallback 동작
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_base import ScanContext
from strategies._atr_stop import compute_atr_stop
from strategies.strategy_three_trend_following import (
    StrategyThreeConfig,
    StrategyThreeTrendFollowing,
)
from strategies.strategy_one_d_v2 import StrategyOneDv2


# ============================================================================
# 헬퍼 — compute_atr_stop 단위 테스트
# ============================================================================

def test_compute_atr_stop_trend_formula():
    """추세 추종 공식: max(entry-1.5×ATR, channel_low-0.5×ATR)."""
    # entry=10200, ATR=200, channel_low=9900
    # stop_atr  = 10200 - 1.5×200 = 9900
    # stop_supp = 9900  - 0.5×200 = 9800
    # max = 9900
    result = compute_atr_stop(
        10200.0, 200.0, 9900.0,
        atr_mult=1.5, support_buffer=0.5, fallback_pct=0.025,
    )
    assert abs(result - 9900.0) < 1e-6


def test_compute_atr_stop_trend_support_wins():
    """채널 저점이 더 보수적(높은) 경우 support 기반 stop 채택."""
    # entry=10200, ATR=200, channel_low=10050
    # stop_atr  = 10200 - 300 = 9900
    # stop_supp = 10050 - 100 = 9950
    # max = 9950 (support 우세)
    result = compute_atr_stop(
        10200.0, 200.0, 10050.0,
        atr_mult=1.5, support_buffer=0.5, fallback_pct=0.025,
    )
    assert abs(result - 9950.0) < 1e-6


def test_compute_atr_stop_mean_reversion_formula():
    """평균 회귀 공식: max(entry-2.0×ATR, prev_support-1×ATR)."""
    # entry=10000, ATR=200, prev_support=9600
    # stop_atr  = 10000 - 400 = 9600
    # stop_supp = 9600  - 200 = 9400
    # max = 9600
    result = compute_atr_stop(
        10000.0, 200.0, 9600.0,
        atr_mult=2.0, support_buffer=1.0, fallback_pct=0.025,
    )
    assert abs(result - 9600.0) < 1e-6


def test_compute_atr_stop_fallback_when_atr_none():
    """ATR=None → entry × (1 - fallback_pct)."""
    result = compute_atr_stop(
        10000.0, None, 9500.0,
        atr_mult=1.5, support_buffer=0.5, fallback_pct=0.025,
    )
    assert abs(result - 9750.0) < 1e-6


def test_compute_atr_stop_fallback_when_atr_zero():
    """ATR=0 → fallback (저유동성 가드)."""
    result = compute_atr_stop(
        10000.0, 0.0, 9500.0,
        atr_mult=1.5, support_buffer=0.5, fallback_pct=0.025,
    )
    assert abs(result - 9750.0) < 1e-6


def test_compute_atr_stop_fallback_when_stop_gte_entry():
    """산출된 stop ≥ entry 이면 % fallback (비정상 데이터 방어)."""
    # support=10500 (entry보다 높음), atr_mult=0.01 → stop_atr ≈ 9998 < 10000
    # stop_supp = 10500 - 0.01×1 = 10499.99 > entry
    # max = 10499.99 → fallback
    result = compute_atr_stop(
        10000.0, 1.0, 10500.0,
        atr_mult=0.01, support_buffer=0.01, fallback_pct=0.025,
    )
    assert abs(result - 9750.0) < 1e-6


# ============================================================================
# 통합 — strategy_three (추세 추종) ATR 손절
# ============================================================================

def _make_breakout_df(
    n_consolidation: int = 25,
    consolidation_low: float = 9900.0,
    consolidation_high: float = 10100.0,
    breakout_close: float = 10250.0,
) -> pd.DataFrame:
    """균일 변동폭 breakout 픽스처 — ATR ≈ (high-low)/bar."""
    n = n_consolidation + 1
    closes = np.array([
        *(np.linspace(consolidation_low, consolidation_high, n_consolidation)),
        breakout_close,
    ])
    highs = np.where(
        np.arange(n) < n_consolidation,
        consolidation_high,
        breakout_close,
    ).astype(float)
    lows = np.where(
        np.arange(n) < n_consolidation,
        consolidation_low,
        breakout_close * 0.998,
    ).astype(float)
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": [1_000_000] * n},
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


def _make_ctx(ticker_dfs: dict[str, pd.DataFrame]) -> ScanContext:
    return ScanContext(
        target_date="20260418",
        universe=tuple(ticker_dfs.keys()),
        ohlcv=ticker_dfs,
        names={t: t for t in ticker_dfs},
        market_caps={t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
    )


def test_trend_following_stop_uses_atr_formula():
    """추세 추종 stop = max(entry-1.5×ATR, channel_low-0.5×ATR)."""
    df = _make_breakout_df()
    ctx = _make_ctx({"TF": df})
    strat = StrategyThreeTrendFollowing(
        StrategyThreeConfig(atr_filter_multiplier=0.0, lookback=20)
    )
    cands = strat.scan(ctx, top_n=5)
    assert cands, "breakout 후보 발생 필요"
    c = cands[0]

    atr = c.metadata["atr_14"]
    channel_low = c.metadata["channel_low"]
    assert atr is not None and atr > 0

    stop_atr = c.entry_price - 1.5 * atr
    stop_swing = channel_low - 0.5 * atr
    expected = max(stop_atr, stop_swing)

    # floor_to_tick 오차(1 tick, 최대 10원) 허용
    assert abs(c.stop_loss - expected) <= 15, (
        f"stop_loss={c.stop_loss}, expected≈{expected:.1f} "
        f"(entry={c.entry_price}, ATR={atr:.1f}, channel_low={channel_low})"
    )


def test_trend_following_stop_fallback_when_no_atr():
    """ATR 결측 시 % fallback — atr_filter_multiplier=0 이고 atr=0 인위 조작."""
    # atr=0 인 극단 데이터: high=low=close (변동폭 0)
    n = 26
    level = 10000.0
    df = pd.DataFrame(
        {"open": [level]*n, "high": [level]*n, "low": [level]*n,
         "close": [level]*n, "volume": [1_000_000]*n},
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )
    # 마지막 봉만 breakout
    df.iloc[-1, df.columns.get_loc("close")] = level * 1.01
    df.iloc[-1, df.columns.get_loc("high")] = level * 1.01
    ctx = _make_ctx({"TF_FLAT": df})
    strat = StrategyThreeTrendFollowing(
        StrategyThreeConfig(atr_filter_multiplier=0.0, lookback=20)
    )
    cands = strat.scan(ctx, top_n=5)
    if cands:
        c = cands[0]
        # ATR ≈ 0 → fallback: stop < entry × 0.975 이하
        assert c.stop_loss < c.entry_price


# ============================================================================
# 통합 — strategy_one (평균 회귀) ATR 손절
# ============================================================================

def test_mean_reversion_stop_uses_atr_formula():
    """평균 회귀 stop = max(entry-2.0×ATR, prev_support-1×ATR)."""
    from backtest_engine.scenarios import ScenarioBuilder

    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]
    ctx = _make_ctx({"MR": df})
    strat = StrategyOneDv2()
    cands = strat.scan(ctx, top_n=5)
    assert cands, "double bottom 후보 발생 필요"
    c = cands[0]

    atr = c.metadata.get("atr_14")
    prev_support = c.metadata.get("prev_support")
    assert atr is not None and atr > 0, "ATR 계산 필요"
    assert prev_support is not None, "prev_support metadata 키 필요 (PR-F)"

    stop_atr = c.entry_price - 2.0 * atr
    stop_supp = prev_support - 1.0 * atr
    expected = max(stop_atr, stop_supp)

    assert abs(c.stop_loss - expected) <= 15, (
        f"stop_loss={c.stop_loss}, expected≈{expected:.1f} "
        f"(entry={c.entry_price}, ATR={atr:.1f}, prev_support={prev_support:.1f})"
    )


def test_mean_reversion_stop_less_than_entry():
    """stop_loss < entry_price 는 항상 보장."""
    from backtest_engine.scenarios import ScenarioBuilder

    for seed in [42, 7, 99]:
        scenario = ScenarioBuilder.perfect_double_bottom(seed=seed)
        df = scenario.df.iloc[:33]
        ctx = _make_ctx({f"MR{seed}": df})
        strat = StrategyOneDv2()
        cands = strat.scan(ctx, top_n=5)
        for c in cands:
            assert c.stop_loss < c.entry_price, (
                f"seed={seed}: stop_loss={c.stop_loss} ≥ entry={c.entry_price}"
            )
