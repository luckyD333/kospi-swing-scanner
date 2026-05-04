"""
tests/test_strategy_five_unit.py — StrategyFiveBullFlag 단위 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_base import ScanContext
from strategies.strategy_five_bull_flag import StrategyFiveBullFlag


def _make_df(close_arr, vol_arr, high_mult=1.001, low_mult=0.999):
    n = len(close_arr)
    c = pd.Series(close_arr, dtype=float)
    v = pd.Series(vol_arr, dtype=float)
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open":   c.values * 0.999,
            "high":   c.values * high_mult,
            "low":    c.values * low_mult,
            "close":  c.values,
            "volume": v.values,
        },
        index=dates,
    )


def _make_ctx(ticker_dfs: dict[str, pd.DataFrame]) -> ScanContext:
    return ScanContext(
        target_date="20260503",
        universe=tuple(ticker_dfs.keys()),
        ohlcv=ticker_dfs,
        names={t: t for t in ticker_dfs},
        market_caps={t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
    )


def _pass_df():
    """flagpole +8.9% + 거래량 수축 + 가격 압축 + 돌파 패턴 (33 bars)."""
    close, vol = [], []
    # bars 0-9: 패딩
    close += [1000.0] * 10
    vol += [200_000] * 10
    # bars 10-24: pole 1000→1084 (step 6, 15 bars)
    for i in range(15):
        close.append(1000.0 + i * 6)
        vol.append(300_000)
    # bars 25-31: flag 1089 (7 bars, low volume, tight range)
    close += [1089.0] * 7
    vol += [100_000] * 7
    # bar 32: today, breakout
    close.append(1100.0)
    vol.append(400_000)
    return _make_df(close, vol)


def test_pass_emits_candidate():
    df = _pass_df()
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFiveBullFlag().scan(ctx, top_n=5)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == "TEST"
    assert c.metadata["pole_pct"] >= 8.0


def test_fail_pole_too_small():
    """flagpole +3.5% (< min_pole_pct 8%) → 신호 없음.

    pole_end = close[idx-flag_bars] = 첫 번째 flag 봉이므로
    flag 가격도 pole 상승 범위(~1035)에 맞춰야 한다.
    """
    close, vol = [], []
    close += [1000.0] * 10
    vol += [200_000] * 10
    for i in range(15):
        close.append(1000.0 + i * 2.5)
        vol.append(300_000)  # pole +3.5%
    close += [1035.0] * 7
    vol += [100_000] * 7  # flag near pole end
    close.append(1040.0)
    vol.append(400_000)
    df = _make_df(close, vol)
    ctx = _make_ctx({"TEST": df})
    assert StrategyFiveBullFlag().scan(ctx, top_n=5) == []


def test_fail_no_volume_shrink():
    """flag 거래량 수축 없음 → 신호 없음."""
    close, vol = [], []
    close += [1000.0] * 10
    vol += [200_000] * 10
    for i in range(15):
        close.append(1000.0 + i * 6)
        vol.append(300_000)
    close += [1089.0] * 7
    vol += [300_000] * 7  # same volume as pole
    close.append(1100.0)
    vol.append(400_000)
    df = _make_df(close, vol)
    ctx = _make_ctx({"TEST": df})
    assert StrategyFiveBullFlag().scan(ctx, top_n=5) == []


def test_fail_not_price_compressed():
    """flag 가격 범위 너무 넓음 → 신호 없음."""
    close, vol = [], []
    close += [1000.0] * 10
    vol += [200_000] * 10
    for i in range(15):
        close.append(1000.0 + i * 6)
        vol.append(300_000)
    close += [1089.0] * 7
    vol += [100_000] * 7
    close.append(1100.0)
    vol.append(400_000)
    # 넓은 high/low 범위 (3%) → ATR 대비 flag_range 초과
    df = _make_df(close, vol, high_mult=1.03, low_mult=0.97)
    ctx = _make_ctx({"TEST": df})
    assert StrategyFiveBullFlag().scan(ctx, top_n=5) == []


def test_fail_no_breakout():
    """당일 close <= flag_high → 신호 없음."""
    close, vol = [], []
    close += [1000.0] * 10
    vol += [200_000] * 10
    for i in range(15):
        close.append(1000.0 + i * 6)
        vol.append(300_000)
    close += [1089.0] * 7
    vol += [100_000] * 7
    close.append(1089.0)
    vol.append(400_000)  # 돌파 없음
    df = _make_df(close, vol)
    ctx = _make_ctx({"TEST": df})
    assert StrategyFiveBullFlag().scan(ctx, top_n=5) == []


def test_fail_low_breakout_volume():
    """돌파 거래량 < avg_volume → 신호 없음."""
    close, vol = [], []
    close += [1000.0] * 10
    vol += [200_000] * 10
    for i in range(15):
        close.append(1000.0 + i * 6)
        vol.append(300_000)
    close += [1089.0] * 7
    vol += [100_000] * 7
    close.append(1100.0)
    vol.append(50_000)  # 거래량 너무 낮음
    df = _make_df(close, vol)
    ctx = _make_ctx({"TEST": df})
    assert StrategyFiveBullFlag().scan(ctx, top_n=5) == []


def test_fail_avg_volume_below_min():
    """평균 거래량 < min_daily_volume → 스킵."""
    close, vol = [], []
    close += [1000.0] * 10
    vol += [50_000] * 10
    for i in range(15):
        close.append(1000.0 + i * 6)
        vol.append(50_000)
    close += [1089.0] * 7
    vol += [50_000] * 7
    close.append(1100.0)
    vol.append(50_000)
    df = _make_df(close, vol)
    ctx = _make_ctx({"TEST": df})
    assert StrategyFiveBullFlag().scan(ctx, top_n=5) == []


def test_invariant_stop_entry_target():
    """stop_loss < entry_price < target_1 <= target_2 불변식."""
    df = _pass_df()
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFiveBullFlag().scan(ctx, top_n=5)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.stop_loss < c.entry_price
    assert c.entry_price < c.target_1
    assert c.target_1 <= c.target_2


def test_data_too_short_returns_empty():
    """min_bars 미달 → 빈 리스트."""
    close = [1000.0 + i * 10 for i in range(20)]
    vol = [200_000] * 20
    df = _make_df(close, vol)
    ctx = _make_ctx({"TEST": df})
    assert StrategyFiveBullFlag().scan(ctx, top_n=5) == []


def test_timeframe_name_mapping():
    assert StrategyFiveBullFlag(timeframe="1D").name == "strategy_five_bull_flag"
    assert StrategyFiveBullFlag(timeframe="1h").name == "strategy_five_bull_flag_1h"
    assert StrategyFiveBullFlag(timeframe="30m").name == "strategy_five_bull_flag_30m"


def test_invalid_timeframe_raises():
    with pytest.raises(ValueError):
        StrategyFiveBullFlag(timeframe="5m")
