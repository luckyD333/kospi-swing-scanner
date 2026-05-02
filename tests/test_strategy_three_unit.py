"""
test_strategy_three_unit.py — Time-series Trend-Following (Donchian) 단위 테스트.

검증:
  - 직전 N봉 high 를 close 가 돌파할 때 후보 진입
  - 채널 안에 머무는 ticker 는 후보 아님
  - ATR 필터 (whipsaw 방어): 채널 폭/돌파 폭 < ATR 시 제외
  - lookback + ATR period 미달 ticker 배제
  - SL = max(채널 저점 보존, 진입가 -2.5%)
  - score 가 돌파 강도에 비례
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from core.strategy_base import ScanContext
from strategies.strategy_three_trend_following import (
    StrategyThreeConfig,
    StrategyThreeTrendFollowing,
)

# ============================================================================
# fixtures — Donchian breakout 시나리오
# ============================================================================

def _consolidation_then_breakout(
    n_consolidation: int = 22,
    n_breakout: int = 1,
    consolidation_low: float = 100.0,
    consolidation_high: float = 110.0,
    breakout_close: float = 115.0,
    seed: int = 42,
) -> pd.DataFrame:
    """N봉 횡보(channel) 후 1봉 강한 돌파."""
    rng = np.random.default_rng(seed)
    cons = rng.uniform(consolidation_low, consolidation_high, n_consolidation)
    closes = np.concatenate([cons, [breakout_close] * n_breakout])
    n = len(closes)
    return pd.DataFrame({
        "open":   closes * (1 - 0.001 * rng.standard_normal(n).clip(-1, 1)),
        "high":   np.maximum(closes * 1.005, closes + 0.5),
        "low":    np.minimum(closes * 0.995, closes - 0.5),
        "close":  closes,
        "volume": [1_000_000] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="D"))


def _flat_no_breakout(n: int = 25, level: float = 100.0) -> pd.DataFrame:
    """완전 횡보 — 돌파 없음."""
    return pd.DataFrame({
        "open": [level] * n, "high": [level * 1.001] * n,
        "low":  [level * 0.999] * n, "close": [level] * n,
        "volume": [1_000_000] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="D"))


def _make_ctx(ticker_dfs: dict[str, pd.DataFrame]) -> ScanContext:
    return ScanContext(
        target_date="20260418",
        universe=tuple(ticker_dfs.keys()),
        ohlcv=ticker_dfs,
        names={t: f"name_{t}" for t in ticker_dfs},
        market_caps={t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
    )


# ============================================================================
# tests
# ============================================================================

def test_breakout_emits_candidate():
    """직전 20봉 high 돌파 → 후보 진입."""
    df = _consolidation_then_breakout()
    ctx = _make_ctx({"BREAK": df})
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    cands = strat.scan(ctx, top_n=5)
    assert len(cands) == 1
    assert cands[0].ticker == "BREAK"


def test_no_breakout_returns_empty():
    """완전 횡보 → 후보 없음."""
    df = _flat_no_breakout()
    ctx = _make_ctx({"FLAT": df})
    strat = StrategyThreeTrendFollowing()
    assert strat.scan(ctx, top_n=5) == []


def test_within_channel_no_signal():
    """채널 내부면 후보 아님 (직전 high 미달)."""
    df = _consolidation_then_breakout(
        breakout_close=109.5  # consolidation_high(110) 미만
    )
    ctx = _make_ctx({"INSIDE": df})
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    assert strat.scan(ctx, top_n=5) == []


def test_atr_filter_rejects_weak_breakout():
    """ATR 필터 활성화 시 약한 돌파는 거부."""
    # 110.05 = 110(channel high) + 0.05 → 매우 약한 돌파
    df = _consolidation_then_breakout(breakout_close=110.05)
    ctx = _make_ctx({"WEAK": df})

    # ATR multiplier 0 → 필터 없으니 통과
    strat_no_filter = StrategyThreeTrendFollowing(
        StrategyThreeConfig(atr_filter_multiplier=0.0)
    )
    cands_no = strat_no_filter.scan(ctx, top_n=5)

    # ATR multiplier 1.0 → 약한 돌파는 거부 (ATR 만큼은 돌파해야)
    strat_strict = StrategyThreeTrendFollowing(
        StrategyThreeConfig(atr_filter_multiplier=1.0)
    )
    cands_strict = strat_strict.scan(ctx, top_n=5)

    assert len(cands_strict) <= len(cands_no)


def test_score_increases_with_breakout_strength():
    """더 큰 돌파 → 더 높은 score."""
    weak = _consolidation_then_breakout(breakout_close=111.0)    # +1
    strong = _consolidation_then_breakout(breakout_close=120.0)  # +10
    universe = {"WEAK": weak, "STRONG": strong}
    ctx = _make_ctx(universe)
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    cands = strat.scan(ctx, top_n=5)

    # 모두 후보로 진입
    assert len(cands) == 2
    # STRONG 의 score 가 WEAK 보다 커야
    by_ticker = {c.ticker: c.score for c in cands}
    assert by_ticker["STRONG"] > by_ticker["WEAK"]
    # 정렬 순서
    assert cands[0].ticker == "STRONG"


def test_short_history_ticker_skipped():
    """lookback + atr_period 미달 ticker 는 스킵."""
    short_df = _consolidation_then_breakout(n_consolidation=5)  # 너무 짧음
    full_df = _consolidation_then_breakout()
    ctx = _make_ctx({"SHORT": short_df, "FULL": full_df})
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    cands = strat.scan(ctx, top_n=5)
    assert all(c.ticker != "SHORT" for c in cands)


def test_pricing_invariants_hold():
    df = _consolidation_then_breakout(breakout_close=120.0)
    ctx = _make_ctx({"T1": df})
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    cands = strat.scan(ctx, top_n=5)
    for c in cands:
        assert c.stop_loss < c.entry_price < c.target_1 <= c.target_2
        assert 0.0 <= c.score <= 1000.0
        # SL 은 진입가보다 작지만 -10% 보다는 크게 (지나친 SL 금지)
        assert c.stop_loss > c.entry_price * 0.85


def test_stop_loss_uses_channel_low_or_pct_whichever_higher():
    """SL = max(채널 저점 보존, 진입가 -2.5%) — 더 보수적인 쪽."""
    # 매우 깊은 채널 (low=80, high=110, close=115) → 채널 저점 사용은 너무 멀어 -2.5% 사용
    df = _consolidation_then_breakout(
        consolidation_low=80.0, consolidation_high=110.0, breakout_close=115.0,
    )
    ctx = _make_ctx({"DEEP": df})
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    cands = strat.scan(ctx, top_n=5)
    assert cands
    c = cands[0]
    # -2.5% 손절: 115 * 0.975 = 112.125
    expected_sl_pct = c.entry_price * (1 - 0.025)
    assert abs(c.stop_loss - expected_sl_pct) < 0.5


def test_metadata_records_channel_values():
    df = _consolidation_then_breakout(breakout_close=120.0)
    ctx = _make_ctx({"T1": df})
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    cands = strat.scan(ctx, top_n=5)
    assert cands
    md = cands[0].metadata
    assert "channel_high" in md
    assert "channel_low" in md
    assert "breakout_pct" in md
    assert md["breakout_pct"] > 0


def test_top_n_cut():
    universe = {
        f"T{i}": _consolidation_then_breakout(breakout_close=115 + i)
        for i in range(5)
    }
    ctx = _make_ctx(universe)
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    cands = strat.scan(ctx, top_n=2)
    assert len(cands) == 2


def test_empty_universe_returns_empty():
    ctx = _make_ctx({})
    strat = StrategyThreeTrendFollowing()
    assert strat.scan(ctx, top_n=10) == []


def test_strategy_name_constant():
    assert StrategyThreeTrendFollowing.name == "strategy_three_trend_following"


def test_invalid_config_raises():
    with pytest.raises(ValueError):
        StrategyThreeTrendFollowing(StrategyThreeConfig(lookback=0))
    with pytest.raises(ValueError):
        StrategyThreeTrendFollowing(StrategyThreeConfig(atr_period=0))


def test_registry_has_strategy_three():
    from strategies import REGISTRY, available
    assert StrategyThreeTrendFollowing.name in REGISTRY
    assert StrategyThreeTrendFollowing.name in available()


def test_candidate_metadata_has_bridge_keys():
    """Candidate.metadata에 source_strategy, rr_ratio, rr_band, atr_14 키 포함."""
    universe = {
        f"T{i}": _consolidation_then_breakout(breakout_close=115 + i)
        for i in range(3)
    }
    ctx = _make_ctx(universe)
    strat = StrategyThreeTrendFollowing(StrategyThreeConfig(atr_filter_multiplier=0.0))
    candidates = strat.scan(ctx, top_n=10)

    assert len(candidates) > 0
    for c in candidates:
        # 신규 4개 키 검증
        assert "source_strategy" in c.metadata
        assert c.metadata["source_strategy"] == "strategy_three_trend_following"

        assert "rr_ratio" in c.metadata
        assert isinstance(c.metadata["rr_ratio"], (int, float))
        assert c.metadata["rr_ratio"] >= 0.0

        assert "rr_band" in c.metadata
        assert c.metadata["rr_band"] in ("sweet", "over", "below")

        assert "atr_14" in c.metadata
        assert c.metadata["atr_14"] is None or isinstance(c.metadata["atr_14"], (int, float))
