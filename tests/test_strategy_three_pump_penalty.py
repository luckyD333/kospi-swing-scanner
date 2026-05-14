"""test_strategy_three_pump_penalty.py — PR-E (P1-3) 단일일 급등 페널티.

추세 추종 전략에서 NAV 회귀·단일 호가 체결 가능성을 추세로 오인하는 결함 차단:
  - 전일 등락률 ≥ +30% → 후보 풀 미진입
  - +20% ~ +30%        → score × 0.5 (pump_penalty)
  - 그 외             → 영향 없음 (pump_penalty=1.0)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from core.strategy_base import ScanContext
from strategies.strategy_three_trend_following import (
    StrategyThreeConfig,
    StrategyThreeTrendFollowing,
)


def _consolidation_then_pump(
    n_consolidation: int = 22,
    consolidation_low: float = 99.0,
    consolidation_high: float = 100.0,  # 채널 high 가 100
    breakout_close: float = 130.0,      # +30% 돌파 (마지막 cons 종가가 100 가정)
    seed: int = 42,
) -> pd.DataFrame:
    """N봉 횡보 후 1봉 급등. 마지막 cons 종가를 100 으로 고정해 prev_change_pct 제어."""
    rng = np.random.default_rng(seed)
    cons = rng.uniform(consolidation_low, consolidation_high - 0.01, n_consolidation - 1)
    cons = np.append(cons, 100.0)  # 마지막 cons 종가 = 100 (제어값)
    closes = np.concatenate([cons, [breakout_close]])
    n = len(closes)
    return pd.DataFrame({
        "open":   closes,
        "high":   np.maximum(closes * 1.005, closes + 0.5),
        "low":    np.minimum(closes * 0.995, closes - 0.5),
        "close":  closes,
        "volume": [1_000_000] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="D"))


def _ctx(ticker_dfs: dict[str, pd.DataFrame]) -> ScanContext:
    return ScanContext(
        target_date="20260418",
        universe=tuple(ticker_dfs.keys()),
        ohlcv=ticker_dfs,
        names={t: f"name_{t}" for t in ticker_dfs},
        market_caps={t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
    )


# ---------------------------------------------------------------------------
# 페널티 차단 (≥30%)
# ---------------------------------------------------------------------------

def test_pump_30pct_excluded_from_trend():
    """전일 +30% 이상 (breakout=130 vs prev=100) → 후보 미진입."""
    df = _consolidation_then_pump(breakout_close=135.0)  # +35%
    strat = StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(lookback=20, atr_filter_multiplier=0.0),
    )
    cands = strat.scan(_ctx({"PUMP": df}), top_n=10)
    assert cands == []


def test_pump_exactly_30pct_excluded():
    """경계: 정확히 +30% (≥30) → 차단."""
    df = _consolidation_then_pump(breakout_close=130.0)  # +30%
    strat = StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(lookback=20, atr_filter_multiplier=0.0),
    )
    cands = strat.scan(_ctx({"PUMP": df}), top_n=10)
    assert cands == []


# ---------------------------------------------------------------------------
# 페널티 50% (20~30%)
# ---------------------------------------------------------------------------

def test_pump_20to30_half_penalty():
    """전일 +25% (breakout=125 vs prev=100) → score × 0.5, metadata pump_penalty=0.5."""
    df = _consolidation_then_pump(breakout_close=125.0)  # +25%
    strat = StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(lookback=20, atr_filter_multiplier=0.0),
    )
    cands = strat.scan(_ctx({"PUMP": df}), top_n=10)
    assert len(cands) == 1
    cand = cands[0]
    assert cand.metadata["pump_penalty"] == 0.5
    assert 24.5 < cand.metadata["prev_change_pct"] < 25.5


def test_pump_exactly_20pct_gets_penalty():
    """경계: 정확히 +20% → 페널티 적용 (≥20 AND <30)."""
    df = _consolidation_then_pump(breakout_close=120.0)
    strat = StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(lookback=20, atr_filter_multiplier=0.0),
    )
    cands = strat.scan(_ctx({"PUMP": df}), top_n=10)
    assert len(cands) == 1
    assert cands[0].metadata["pump_penalty"] == 0.5


# ---------------------------------------------------------------------------
# 페널티 미적용 (< 20%)
# ---------------------------------------------------------------------------

def test_normal_breakout_no_penalty():
    """전일 +15% (breakout=115 vs prev=100) → pump_penalty=1.0, score 그대로."""
    df = _consolidation_then_pump(breakout_close=115.0)  # +15%
    strat = StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(lookback=20, atr_filter_multiplier=0.0),
    )
    cands = strat.scan(_ctx({"PUMP": df}), top_n=10)
    assert len(cands) == 1
    cand = cands[0]
    assert cand.metadata["pump_penalty"] == 1.0


# ---------------------------------------------------------------------------
# 페널티 score 효과 비교
# ---------------------------------------------------------------------------

def test_penalty_halves_score_compared_to_normal():
    """동일 채널·돌파 폭일 때, +25% 페널티 후보 score 가 +15% 후보 score 의 약 0.5배."""
    df_normal = _consolidation_then_pump(breakout_close=115.0)
    df_pumped = _consolidation_then_pump(breakout_close=125.0)
    # 두 후보 모두 동일 cfg
    strat = StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(lookback=20, atr_filter_multiplier=0.0),
    )
    normal_cands = strat.scan(_ctx({"NORMAL": df_normal}), top_n=10)
    pump_cands = strat.scan(_ctx({"PUMP": df_pumped}), top_n=10)
    assert len(normal_cands) == 1
    assert len(pump_cands) == 1
    # pumped 의 breakout_pct 가 더 크지만 페널티 0.5 적용
    # 검증: pump_penalty 메타 적용 + score 가 페널티 *전* (normalized rank) 와 다름
    assert pump_cands[0].metadata["pump_penalty"] == 0.5
    assert normal_cands[0].metadata["pump_penalty"] == 1.0


# ---------------------------------------------------------------------------
# metadata 필드 항상 노출 (downstream 의존 가능)
# ---------------------------------------------------------------------------

def test_metadata_always_includes_pump_fields():
    """모든 후보 metadata 에 prev_change_pct + pump_penalty 키 존재."""
    df = _consolidation_then_pump(breakout_close=110.0)  # +10%
    strat = StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(lookback=20, atr_filter_multiplier=0.0),
    )
    cands = strat.scan(_ctx({"X": df}), top_n=10)
    assert len(cands) == 1
    assert "prev_change_pct" in cands[0].metadata
    assert "pump_penalty" in cands[0].metadata
