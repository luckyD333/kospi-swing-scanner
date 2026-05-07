"""
test_regime_overlay_pipeline.py — PR-J: regime_overlay 파이프라인 통합 검증.

기존 apply_regime_overlay 단위 테스트(test_market_regime.py)와 분리.
여기서는 aggregate_candidates 에 실제 regime-adjusted config 가 적용됐을 때
최종 ranking 결과가 달라지는지 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from core.decision.aggregator import aggregate_candidates
from core.decision.config import Priority, WeightConfig
from core.decision.market_regime import apply_regime_overlay
from core.strategy_base import Candidate


# ============================================================================
# 헬퍼
# ============================================================================

def _make_candidate(
    ticker: str,
    momentum_pct: float = 0.05,
    per: float = 15.0,
) -> Candidate:
    return Candidate(
        ticker=ticker,
        name=ticker,
        strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-07"),
        score=500.0,
        entry_price=10000,
        stop_loss=9700,
        target_1=10300,
        target_2=10600,
        current_price=10000,
        market_cap_bil=500.0,
        volume_20d_avg=1_000_000,
        conditions_met={},
        metadata={
            "momentum_pct": momentum_pct,
            "per": per,
        },
    )


def _make_base_config() -> WeightConfig:
    """momentum_pct 와 per 두 항목만 가진 단순 WeightConfig."""
    return WeightConfig(
        priorities=[
            Priority(key="momentum_pct", weight=50.0, direction="higher_better", label="모멘텀"),
            Priority(key="per", weight=50.0, direction="lower_better", label="PER"),
        ],
        must_have=[],
        strategy_weights={},
    )


# ============================================================================
# 테스트: regime-adjusted config 가 ranking 에 영향을 주는지
# ============================================================================

def test_bull_regime_boosts_momentum_candidate():
    """BULL(score=80): momentum_pct weight 증가 → momentum 후보가 더 높은 순위.

    momentum_heavy: momentum_pct=0.10, per=25 (고PER)
    quality_heavy : momentum_pct=0.02, per=8  (저PER)

    base config (50/50): quality_heavy 가 PER 에서 우위 → 더 높이 랭크될 수 있음.
    BULL config: momentum weight 1.3배 → momentum_heavy 우위 기대.
    """
    momentum_heavy = _make_candidate("MOM", momentum_pct=0.10, per=25.0)
    quality_heavy  = _make_candidate("QUA", momentum_pct=0.02, per=8.0)
    candidates = [momentum_heavy, quality_heavy]

    base_cfg = _make_base_config()
    bull_cfg = apply_regime_overlay(base_cfg, regime_score=80)

    # momentum_pct weight 가 증가했는지 확인
    base_mom_w = next(p.weight for p in base_cfg.priorities if p.key == "momentum_pct")
    bull_mom_w = next(p.weight for p in bull_cfg.priorities if p.key == "momentum_pct")
    assert bull_mom_w > base_mom_w, "BULL 국면: momentum_pct weight 증가 필요"

    ranked_bull = aggregate_candidates(candidates, bull_cfg)
    assert ranked_bull
    # BULL config 에서 momentum_heavy 가 상위권
    assert ranked_bull[0].candidate.ticker == "MOM", (
        f"BULL 국면: momentum 후보가 1위여야 함. 실제: {ranked_bull[0].candidate.ticker}"
    )


def test_bear_regime_boosts_quality_candidate():
    """BEAR(score=20): per/roe weight 증가 → quality 후보가 더 높은 순위."""
    momentum_heavy = _make_candidate("MOM", momentum_pct=0.10, per=30.0)
    quality_heavy  = _make_candidate("QUA", momentum_pct=0.02, per=7.0)
    candidates = [momentum_heavy, quality_heavy]

    bear_cfg = apply_regime_overlay(_make_base_config(), regime_score=20)
    ranked_bear = aggregate_candidates(candidates, bear_cfg)
    assert ranked_bear
    assert ranked_bear[0].candidate.ticker == "QUA", (
        f"BEAR 국면: quality 후보가 1위여야 함. 실제: {ranked_bear[0].candidate.ticker}"
    )


def test_neutral_regime_same_as_base():
    """NEUTRAL(score=50): weight 미조정 → base 와 동일 ranking."""
    c1 = _make_candidate("A", momentum_pct=0.08, per=20.0)
    c2 = _make_candidate("B", momentum_pct=0.03, per=10.0)
    candidates = [c1, c2]

    base_cfg = _make_base_config()
    neutral_cfg = apply_regime_overlay(base_cfg, regime_score=50)

    ranked_base    = aggregate_candidates(candidates, base_cfg)
    ranked_neutral = aggregate_candidates(candidates, neutral_cfg)

    base_order    = [r.candidate.ticker for r in ranked_base]
    neutral_order = [r.candidate.ticker for r in ranked_neutral]
    assert base_order == neutral_order, (
        f"NEUTRAL 국면: ranking 동일해야 함. base={base_order}, neutral={neutral_order}"
    )


def test_regime_overlay_applied_before_aggregate():
    """cli 파이프라인: weight_config 로드 후 regime overlay 가 적용된 뒤 aggregate 호출.

    cli.py 에 apply_regime_overlay 호출이 없으면 이 테스트가 의미하는 패턴이 누락됨.
    현재 이 테스트는 apply_regime_overlay 를 직접 호출해 pipeline 패턴을 재현.
    """
    base_cfg = _make_base_config()
    regime = {"1D": {"score": 80, "label": "BULL"}}

    # cli.py 에 추가될 패턴 재현
    score_1d = int(regime.get("1D", {}).get("score", 50))
    adjusted_cfg = apply_regime_overlay(base_cfg, score_1d)

    # adjusted_cfg 가 base 와 다른지 확인
    base_weights    = {p.key: p.weight for p in base_cfg.priorities}
    adjusted_weights = {p.key: p.weight for p in adjusted_cfg.priorities}
    assert adjusted_weights != base_weights, "BULL 국면: overlay 후 weight 가 변경돼야 함"
    assert adjusted_weights["momentum_pct"] > base_weights["momentum_pct"]
