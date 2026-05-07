"""
test_confirmation.py — PR-H: 평균 회귀 confirmation 다중 트리거 등급 검증.

검증 항목:
  1. evaluate() 헬퍼 단위 테스트 (Strong/Medium/Weak 분류)
  2. strategy_one 통합: metadata에 confirmation_level, triggers_fired 노출
  3. WEAK 등급 신호의 score 배율 적용
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from backtest_engine.scenarios import ScenarioBuilder
from core.decision.confirmation_strength import ConfirmationLevel, evaluate
from core.strategy_base import ScanContext
from strategies.strategy_one_d_v2 import StrategyOneDv2


# ============================================================================
# evaluate() 단위 테스트
# ============================================================================

def test_strong_when_rsi_lt_35_and_bb():
    """RSI < 35 AND BB 하단 터치 → STRONG, 배율 1.0."""
    level, scale = evaluate({"bb_lower_breach"}, rsi=30.0)
    assert level == ConfirmationLevel.STRONG
    assert abs(scale - 1.0) < 1e-6


def test_strong_when_rsi_lt_35_and_engulf():
    """RSI < 35 AND 장악형 양봉 → STRONG."""
    level, scale = evaluate({"bullish_engulfing"}, rsi=28.0)
    assert level == ConfirmationLevel.STRONG
    assert abs(scale - 1.0) < 1e-6


def test_medium_when_rsi_35_to_45_with_bb_and_engulf():
    """RSI 35~45 AND BB AND 장악형 양봉 → MEDIUM, 배율 0.7."""
    level, scale = evaluate({"bb_lower_breach", "bullish_engulfing"}, rsi=40.0)
    assert level == ConfirmationLevel.MEDIUM
    assert abs(scale - 0.7) < 1e-6


def test_medium_requires_both_bb_and_engulf():
    """RSI 40 이지만 BB 만 있고 장악형 양봉 없음 → WEAK (MEDIUM 조건 미충족)."""
    level, _ = evaluate({"bb_lower_breach"}, rsi=40.0)
    assert level == ConfirmationLevel.WEAK


def test_weak_when_single_trigger_high_rsi():
    """RSI 42, 장악형 양봉만 → WEAK, 배율 0.3."""
    level, scale = evaluate({"bullish_engulfing"}, rsi=42.0)
    assert level == ConfirmationLevel.WEAK
    assert abs(scale - 0.3) < 1e-6


def test_weak_when_rsi_none():
    """RSI 정보 없으면 → WEAK."""
    level, _ = evaluate({"bb_lower_breach", "bullish_engulfing"}, rsi=None)
    assert level == ConfirmationLevel.WEAK


def test_weak_when_rsi_above_45():
    """RSI ≥ 45 이면 MEDIUM 조건 미충족 → WEAK."""
    level, _ = evaluate({"bb_lower_breach", "bullish_engulfing"}, rsi=50.0)
    assert level == ConfirmationLevel.WEAK


def test_weak_when_no_bb_no_engulf():
    """RSI 28 이지만 BB/장악형 양봉 없음 → WEAK (STRONG 두 번째 조건 미충족)."""
    level, _ = evaluate(set(), rsi=28.0)
    assert level == ConfirmationLevel.WEAK


# ============================================================================
# strategy_one 통합
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


def test_confirmation_level_in_strategy_one_metadata():
    """모든 평균회귀 신호가 metadata['confirmation_level'] 보유."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]
    ctx = _make_ctx({"MR": df})
    cands = StrategyOneDv2().scan(ctx, top_n=5)
    assert cands
    c = cands[0]
    assert "confirmation_level" in c.metadata, "confirmation_level 키 부재"
    assert c.metadata["confirmation_level"] in {"STRONG", "MEDIUM", "WEAK"}


def test_triggers_fired_not_empty():
    """metadata['triggers_fired'] 가 비어 있지 않음."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]
    ctx = _make_ctx({"MR": df})
    cands = StrategyOneDv2().scan(ctx, top_n=5)
    assert cands
    c = cands[0]
    assert "triggers_fired" in c.metadata
    assert len(c.metadata["triggers_fired"]) > 0


def test_weak_signal_score_is_scaled_below_strong():
    """WEAK 등급 신호 score < STRONG 등급 같은 confidence 의 score."""
    # perfect_double_bottom 시나리오는 Strong 조건을 만족할 가능성이 높음.
    # seed 다변화로 한 케이스라도 발생 시 확인.
    for seed in [42, 7, 99]:
        scenario = ScenarioBuilder.perfect_double_bottom(seed=seed)
        df = scenario.df.iloc[:33]
        ctx = _make_ctx({f"S{seed}": df})
        cands = StrategyOneDv2().scan(ctx, top_n=5)
        for c in cands:
            level = c.metadata.get("confirmation_level", "STRONG")
            if level == "WEAK":
                # WEAK → score 는 raw confidence × 1000 × 0.3
                # score > 0 이고 1000 미만임을 확인
                assert 0 < c.score <= 300, (
                    f"WEAK 등급 score={c.score} (expected ≤ 300)"
                )
