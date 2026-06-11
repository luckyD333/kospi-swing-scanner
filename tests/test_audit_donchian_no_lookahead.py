"""감사 회귀 테스트 — Strategy 3 Donchian 채널의 당일 봉 제외 (lookahead 방지).

docs/audit/trading_system_audit.md §5 참조. 채널이 당일 high 를 포함하면
(close ≤ channel_high 가 항상 성립해) 돌파 시그널이 정의상 불가능해지는
합성 케이스로, 채널 산출이 직전 lookback 봉만 사용함을 고정한다.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.strategy_base import ScanContext
from strategies.strategy_three_trend_following import StrategyThreeTrendFollowing


def _make_breakout_df() -> pd.DataFrame:
    """직전 25봉 평탄(고가 100.5) + 당일 돌파봉(고가 112, 종가 110).

    당일 high(112) > 당일 close(110) 이므로:
      - 채널이 당일 제외(올바름) → channel_high=100.5 < close=110 → 시그널 발생
      - 채널이 당일 포함(버그)   → channel_high=112   ≥ close=110 → 시그널 없음
    """
    n_flat = 25
    dates = pd.date_range("2026-05-01", periods=n_flat + 1, freq="D")
    rows = {
        "open": [100.0] * n_flat + [105.0],
        "high": [100.5] * n_flat + [112.0],
        "low": [99.5] * n_flat + [104.0],
        "close": [100.0] * n_flat + [110.0],
        "volume": [1_000_000] * n_flat + [2_000_000],
    }
    return pd.DataFrame(rows, index=dates)


def _make_ctx(df: pd.DataFrame) -> ScanContext:
    return ScanContext(
        target_date="20260611",
        universe=("TEST",),
        ohlcv={"TEST": df},
        names={"TEST": "테스트종목"},
        market_caps={"TEST": 1_000_000_000_000.0},
        market="KOSPI",
    )


def test_donchian_channel_excludes_today_bar():
    df = _make_breakout_df()
    strategy = StrategyThreeTrendFollowing()
    candidates = strategy.scan(_make_ctx(df), top_n=5)

    assert len(candidates) == 1, (
        "돌파 시그널이 생성돼야 함 — 채널이 당일 high 를 포함하면 "
        "(channel_high=112 ≥ close=110) 시그널이 사라진다"
    )
    cand = candidates[0]
    channel_high = cand.metadata["channel_high"]
    today_high = float(df["high"].iloc[-1])

    assert channel_high == pytest.approx(100.5), (
        f"channel_high 는 직전 20봉 최고가(100.5)여야 함, got {channel_high}"
    )
    assert channel_high < today_high, "채널에 당일 high 가 섞이면 안 됨"


def test_donchian_channel_low_excludes_today_bar():
    df = _make_breakout_df()
    strategy = StrategyThreeTrendFollowing()
    candidates = strategy.scan(_make_ctx(df), top_n=5)

    assert len(candidates) == 1
    channel_low = candidates[0].metadata["channel_low"]
    assert channel_low == pytest.approx(99.5), (
        f"channel_low 는 직전 20봉 최저가(99.5)여야 함 (당일 low=104 제외), got {channel_low}"
    )
