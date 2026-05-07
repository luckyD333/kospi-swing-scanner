"""
test_multi_timeframe.py — PR-I: 멀티 TF RSI 역할 분리 + 동시 과열 페널티 검증.

검증 항목:
  1. compute_multi_tf_penalty 단위 테스트
  2. strategy_one 통합: 멀티 TF 데이터 있어도 RSI 중복 가산 없음
  3. strategy_one 통합: metadata에 rsi_1h, rsi_30m 노출
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest_engine.scenarios import ScenarioBuilder
from core.decision.multi_timeframe import compute_multi_tf_penalty
from core.strategy_base import ScanContext
from strategies.strategy_one_d_v2 import StrategyOneDv2


# ============================================================================
# compute_multi_tf_penalty 단위 테스트
# ============================================================================

def test_all_tf_overbought_penalty():
    """1D/1h/30m 모두 RSI 80+ → 0.85 페널티."""
    result = compute_multi_tf_penalty({"1D": 85.0, "1h": 82.0, "30m": 88.0})
    assert abs(result - 0.85) < 1e-6


def test_all_tf_oversold_penalty():
    """1D/1h/30m 모두 RSI 20- → 0.85 페널티."""
    result = compute_multi_tf_penalty({"1D": 15.0, "1h": 18.0, "30m": 12.0})
    assert abs(result - 0.85) < 1e-6


def test_no_penalty_when_mixed():
    """일부만 극단적이면 페널티 없음."""
    result = compute_multi_tf_penalty({"1D": 30.0, "1h": 85.0, "30m": 50.0})
    assert abs(result - 1.0) < 1e-6


def test_no_penalty_with_single_tf():
    """단일 TF 만 있으면 패널티 없음 (비교 불가)."""
    result = compute_multi_tf_penalty({"1D": 88.0})
    assert abs(result - 1.0) < 1e-6


def test_no_penalty_when_all_none():
    """모두 None 이면 페널티 없음."""
    result = compute_multi_tf_penalty({"1D": None, "1h": None})
    assert abs(result - 1.0) < 1e-6


def test_partial_none_uses_available_values():
    """None 제외하고 나머지가 모두 극단적이면 페널티 적용."""
    result = compute_multi_tf_penalty({"1D": 85.0, "1h": None, "30m": 90.0})
    assert abs(result - 0.85) < 1e-6


def test_boundary_exactly_80_is_overbought():
    """RSI 정확히 80 → 과열 아님 (80 초과만 해당)."""
    result = compute_multi_tf_penalty({"1D": 80.0, "1h": 80.0})
    assert abs(result - 1.0) < 1e-6


def test_boundary_exactly_20_is_not_oversold():
    """RSI 정확히 20 → 과매도 아님 (20 미만만 해당)."""
    result = compute_multi_tf_penalty({"1D": 20.0, "1h": 20.0})
    assert abs(result - 1.0) < 1e-6


# ============================================================================
# strategy_one 통합 — RSI 중복 가산 없음
# ============================================================================

def _make_ctx_with_multi_tf(
    ticker: str,
    df_1d: pd.DataFrame,
    df_1h: pd.DataFrame | None = None,
    df_30m: pd.DataFrame | None = None,
) -> ScanContext:
    ohlcv_by_tf: dict[str, dict[str, pd.DataFrame]] = {"1D": {ticker: df_1d}}
    if df_1h is not None:
        ohlcv_by_tf["1h"] = {ticker: df_1h}
    if df_30m is not None:
        ohlcv_by_tf["30m"] = {ticker: df_30m}
    return ScanContext(
        target_date="20260418",
        universe=(ticker,),
        ohlcv={ticker: df_1d},
        ohlcv_by_tf=ohlcv_by_tf,
        names={ticker: ticker},
        market_caps={ticker: 5_000 * 1e8},
        market="KOSPI",
    )


def _make_normal_rsi_tf_df(base_df: pd.DataFrame, rsi_target: float = 45.0) -> pd.DataFrame:
    """RSI ≈ rsi_target 인 합성 TF 데이터 (30봉)."""
    n = 30
    # rsi_target 에 가까운 RSI 를 만들기 위해 약간 오르내리는 가격 시퀀스
    closes = np.linspace(100.0, 105.0, n)
    return pd.DataFrame(
        {"open": closes, "high": closes * 1.005, "low": closes * 0.995,
         "close": closes, "volume": [100_000] * n},
        index=pd.date_range("2026-01-01", periods=n, freq="h"),
    )


def test_rsi_not_summed_across_tf():
    """멀티 TF 데이터가 있어도 RSI 점수가 중복 가산되지 않는다.

    동일 ticker 에 대해 1D 단독 스캔 score 와 1D+1h+30m 스캔 score 를 비교.
    multi-TF 가 normal RSI (극단값 아님) 이면 페널티 미적용 → score 동일해야 함.
    """
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df_1d = scenario.df.iloc[:33]
    df_1h = _make_normal_rsi_tf_df(df_1d)
    df_30m = _make_normal_rsi_tf_df(df_1d)

    # 1D 만
    ctx_1d = _make_ctx_with_multi_tf("MR", df_1d)
    cands_1d = StrategyOneDv2().scan(ctx_1d, top_n=5)

    # 1D + 1h + 30m
    ctx_multi = _make_ctx_with_multi_tf("MR", df_1d, df_1h=df_1h, df_30m=df_30m)
    cands_multi = StrategyOneDv2().scan(ctx_multi, top_n=5)

    assert cands_1d and cands_multi
    # normal RSI 이면 multi-TF 페널티 없음 → score 동일
    assert abs(cands_1d[0].score - cands_multi[0].score) < 1e-6, (
        f"멀티 TF 가산: 1D score={cands_1d[0].score}, multi score={cands_multi[0].score}"
    )


def test_strategy_one_has_rsi_tf_metadata():
    """strategy_one metadata 에 rsi_1h, rsi_30m 키 존재."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df_1d = scenario.df.iloc[:33]
    df_1h = _make_normal_rsi_tf_df(df_1d)
    df_30m = _make_normal_rsi_tf_df(df_1d)

    ctx = _make_ctx_with_multi_tf("MR", df_1d, df_1h=df_1h, df_30m=df_30m)
    cands = StrategyOneDv2().scan(ctx, top_n=5)
    assert cands
    c = cands[0]
    assert "rsi_1h" in c.metadata, "rsi_1h 키 부재 (PR-I)"
    assert "rsi_30m" in c.metadata, "rsi_30m 키 부재 (PR-I)"
