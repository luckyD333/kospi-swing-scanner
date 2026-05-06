"""
tests/test_strategy_four_unit.py — StrategyFourPullbackMa 단위 테스트.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_base import ScanContext
from strategies.strategy_four_pullback_ma import StrategyFourPullbackMa
from strategies.price_utils import floor_to_tick


def _make_df(close_arr, vol_arr=None, base_vol=200_000):
    n = len(close_arr)
    c = pd.Series(close_arr, dtype=float)
    v = pd.Series(vol_arr if vol_arr is not None else [base_vol] * n, dtype=float)
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"open": c.values * 0.998, "high": c.values * 1.002, "low": c.values * 0.998, "close": c.values, "volume": v.values},
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
    """MA20 위 + MA5 이탈 후 회복 + 거래량 충분."""
    # bars 0-20: 상승 1000→1200
    close = list(range(1000, 1210, 10))  # 21 bars
    # bars 21-23: 눌림목
    close += [1100, 1080, 1070]
    # bar 24 (today): MA5 회복
    close += [1150]
    return _make_df(close)  # 25 bars


def test_pass_emits_candidate():
    df = _pass_df()
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert len(candidates) == 1
    assert candidates[0].ticker == "TEST"


def test_fail_below_ma20_no_signal():
    """하락 추세 (close < MA20) → 신호 없음."""
    close = list(range(1200, 990, -10))  # 21 bars declining
    close += [1100, 1080, 1070, 1050]
    df = _make_df(close)  # 25 bars, downtrend
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert candidates == []


def test_fail_no_pullback_no_signal():
    """MA5 이탈 없음 (눌림목 없음) → 신호 없음."""
    close = list(range(1000, 1250, 10))  # 25 bars, always rising above MA5
    df = _make_df(close)
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert candidates == []


def test_fail_no_recovery_no_signal():
    """당일 MA5 미회복 → 신호 없음."""
    close = list(range(1000, 1210, 10))  # 21 bars
    close += [1100, 1080, 1070, 1070]   # bar 24 stays below MA5
    df = _make_df(close)
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert candidates == []


def test_fail_low_volume_no_signal():
    """당일 거래량 부족 → 신호 없음."""
    close = list(range(1000, 1210, 10)) + [1100, 1080, 1070, 1150]
    vol = [200_000] * 24 + [50_000]  # today's volume too low
    df = _make_df(close, vol_arr=vol)
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert candidates == []


def test_fail_avg_volume_below_min():
    """평균 거래량 < min_daily_volume → 스킵."""
    close = list(range(1000, 1210, 10)) + [1100, 1080, 1070, 1150]
    df = _make_df(close, base_vol=50_000)  # all volume 50_000 < 100_000
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert candidates == []


def test_invariant_stop_entry_target():
    """stop_loss < entry_price < target_1 <= target_2 불변식."""
    df = _pass_df()
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.stop_loss < c.entry_price < c.target_1 <= c.target_2


def test_data_too_short_returns_empty():
    """min_bars 미달 → 빈 리스트."""
    close = list(range(1000, 1100, 10))  # 10 bars only
    df = _make_df(close)
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert candidates == []


def test_timeframe_name_mapping():
    """timeframe별 name 속성 정확성."""
    assert StrategyFourPullbackMa(timeframe="1D").name == "strategy_four_pullback_ma"
    assert StrategyFourPullbackMa(timeframe="1h").name == "strategy_four_pullback_ma_1h"
    assert StrategyFourPullbackMa(timeframe="30m").name == "strategy_four_pullback_ma_30m"


def test_invalid_timeframe_raises():
    with pytest.raises(ValueError):
        StrategyFourPullbackMa(timeframe="5m")


def test_top_n_limit():
    """top_n 제한 준수."""
    close = list(range(1000, 1210, 10)) + [1100, 1080, 1070, 1150]
    df = _pass_df()
    ctx = _make_ctx({"A": df, "B": _make_df(close), "C": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=2)
    assert len(candidates) <= 2


def _pass_df_highprice():
    """가격대 ~10,000, MA20 이 진입가의 1% 아래 — MA20 anchor 효과 확인용.

    MA20 ≈ 9,920, entry ≈ 9,950.
    sl_ma20 = floor(9920*0.995) = 9,850 (tick=50)
    sl_pct  = floor(9950*0.975) = 9,700 (tick=50)
    → max(9850, 9700) = 9850: MA20 기반 손절 채택.
    """
    close = [9800 + i * 10 for i in range(21)]  # 9800..10000 (21봉)
    close += [9900, 9880, 9870]                  # 눌림목 (MA5 이탈 포함)
    close += [9960]                              # 당일 MA5 회복
    return _make_df(close)


def test_stop_anchored_to_ma20():
    """MA20 이 -2.5% 보다 가까울 때 stop 이 MA20 기반으로 채택."""
    df = _pass_df_highprice()
    ctx = _make_ctx({"TEST": df})
    candidates = StrategyFourPullbackMa().scan(ctx, top_n=5)
    assert len(candidates) == 1, "highprice fixture 가 신호를 생성해야 함"
    c = candidates[0]
    pct_based_stop = floor_to_tick(c.entry_price * 0.975)
    assert c.stop_loss > pct_based_stop, "MA20 anchor 손절이 pct 기반보다 높아야 함"
    assert c.stop_loss < c.entry_price
