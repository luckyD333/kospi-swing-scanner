"""tests/test_regime_weights.py — regime 가중치와 구형 F&G 설정 호환 테스트.

대상:
  - WeightConfig.effective_strategy_weight(strategy, regime, fng_label)
  - weights.yml schema 확장 (strategy_weights_by_regime + fng_modifier) 라운드트립
  - compute_regime_aware_ensemble_score() — 차단 전략 무시 / fallback
  - _normalize_fng_label 유틸
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest

from core.decision.config import (
    Priority,
    WeightConfig,
    _normalize_fng_label,
)
from core.decision.ensemble import compute_regime_aware_ensemble_score
from core.strategy_base import Candidate


# -----------------------------------------------------------------------------
# 헬퍼
# -----------------------------------------------------------------------------


def _mk_priorities() -> list[Priority]:
    """검증 통과용 최소 priorities (sum=100)."""
    return [
        Priority(key="momentum_3m", weight=50.0, direction="higher_better", label="momentum"),
        Priority(key="liquidity", weight=50.0, direction="higher_better", label="liquidity"),
    ]


def _mk_candidate(ticker: str, score: float = 50.0) -> Candidate:
    """검증 통과용 최소 Candidate (가격 순서: sl < entry < t1 <= t2)."""
    return Candidate(
        ticker=ticker,
        name=ticker,
        strategy="test",
        signal_date=pd.Timestamp("2024-01-01"),
        score=score,
        entry_price=100.0,
        stop_loss=97.0,
        target_1=103.0,
        target_2=105.0,
        metadata={},
    )


# -----------------------------------------------------------------------------
# _normalize_fng_label
# -----------------------------------------------------------------------------


def test_normalize_fng_label_spaces_and_case():
    assert _normalize_fng_label("Extreme Fear") == "extreme_fear"
    assert _normalize_fng_label("Greed") == "greed"
    assert _normalize_fng_label("  Neutral  ") == "neutral"
    assert _normalize_fng_label(None) == ""
    assert _normalize_fng_label("") == ""


# -----------------------------------------------------------------------------
# WeightConfig.effective_strategy_weight
# -----------------------------------------------------------------------------


def test_effective_weight_fallback_when_no_regime_table():
    """strategy_weights_by_regime 비어있으면 static strategy_weights 사용."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"strategy_one_d_v2": 1.3, "strategy_two": 0.8},
    )
    assert cfg.effective_strategy_weight("strategy_one_d_v2", regime=None, fng_label=None) == 1.3
    assert cfg.effective_strategy_weight("strategy_two", regime=None, fng_label=None) == 0.8
    # 미등록 전략 → 1.0
    assert cfg.effective_strategy_weight("strategy_unknown", None, None) == 1.0


def test_effective_weight_regime_table_overrides_static():
    """regime table 에 등록된 전략은 매트릭스 값 우선."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.3},  # static fallback
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_one": 0.5, "s_three": 1.5},
            "DOWNTREND_STRONG": {"s_one": 0.0, "s_three": 0.0},
        },
    )
    assert cfg.effective_strategy_weight("s_one", regime="UPTREND_STRONG", fng_label=None) == 0.5
    assert cfg.effective_strategy_weight("s_three", regime="UPTREND_STRONG", fng_label=None) == 1.5
    assert cfg.effective_strategy_weight("s_one", regime="DOWNTREND_STRONG", fng_label=None) == 0.0


def test_effective_weight_falls_back_when_strategy_not_in_regime_table():
    """regime table 에 strategy 가 없으면 static 값 사용."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.3},
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_three": 1.5},  # s_one 미등록
        },
    )
    # s_one 은 매트릭스에 없으므로 static fallback
    assert cfg.effective_strategy_weight("s_one", regime="UPTREND_STRONG", fng_label=None) == 1.3


def test_effective_weight_unknown_regime_falls_back_to_static():
    """등록 안 된 regime → static 동작 (회귀 안전)."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.3},
        strategy_weights_by_regime={"UPTREND_STRONG": {"s_one": 0.5}},
    )
    assert cfg.effective_strategy_weight("s_one", regime="UNKNOWN_REGIME", fng_label=None) == 1.3


def test_effective_weight_ignores_deprecated_fng_modifier():
    """F&G 라벨은 호환용으로 받아도 전략 가중치에 영향을 주지 않는다."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0},
        fng_modifier={"extreme_fear": 0.3, "neutral": 1.0, "extreme_greed": 0.6},
    )
    assert cfg.effective_strategy_weight("s_one", None, "Extreme Fear") == pytest.approx(1.0)
    assert cfg.effective_strategy_weight("s_one", None, "Neutral") == pytest.approx(1.0)
    assert cfg.effective_strategy_weight("s_one", None, "Extreme Greed") == pytest.approx(1.0)


def test_effective_weight_uses_regime_and_ignores_fng():
    """regime 가중치는 적용하고 구형 F&G modifier는 무시한다."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0},
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_one": 1.5},
        },
        fng_modifier={"extreme_greed": 0.6},
    )
    # regime base = 1.5, F&G modifier는 정보용 전환으로 미적용
    result = cfg.effective_strategy_weight("s_one", regime="UPTREND_STRONG", fng_label="Extreme Greed")
    assert result == pytest.approx(1.5)


def test_effective_weight_unknown_fng_label_no_modifier():
    """fng_modifier 에 없는 라벨 → 1.0 (modifier 미적용)."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.3},
        fng_modifier={"extreme_fear": 0.3},
    )
    assert cfg.effective_strategy_weight("s_one", None, "Greed") == pytest.approx(1.3)


# -----------------------------------------------------------------------------
# weights.yml schema 라운드트립
# -----------------------------------------------------------------------------


def test_load_with_regime_and_fng(tmp_path: Path):
    yaml_text = textwrap.dedent("""
        priorities:
          - key: momentum_3m
            label: momentum
            weight: 50.0
            direction: higher_better
          - key: liquidity
            label: liquidity
            weight: 50.0
            direction: higher_better
        must_have: []
        strategy_weights:
          strategy_one_d_v2: 1.3
        strategy_weights_by_regime:
          UPTREND_STRONG:
            strategy_one_d_v2: 0.5
            strategy_two: 1.5
          DOWNTREND_STRONG:
            strategy_one_d_v2: 0.0
        fng_modifier:
          extreme_fear: 0.3
          neutral: 1.0
          extreme_greed: 0.6
    """)
    p = tmp_path / "weights.yml"
    p.write_text(yaml_text)
    cfg = WeightConfig.load(p)
    assert cfg.strategy_weights_by_regime["UPTREND_STRONG"]["strategy_two"] == 1.5
    assert cfg.strategy_weights_by_regime["DOWNTREND_STRONG"]["strategy_one_d_v2"] == 0.0
    assert cfg.fng_modifier["extreme_fear"] == 0.3


def test_load_yml_with_capitalized_fng_label_normalizes(tmp_path: Path):
    """yaml 에 'Extreme Fear' 키로 작성해도 load 시 normalize 된다."""
    yaml_text = textwrap.dedent("""
        priorities:
          - key: momentum_3m
            label: momentum
            weight: 100.0
            direction: higher_better
        must_have: []
        fng_modifier:
          'Extreme Fear': 0.3
          Greed: 1.0
    """)
    p = tmp_path / "weights.yml"
    p.write_text(yaml_text)
    cfg = WeightConfig.load(p)
    assert "extreme_fear" in cfg.fng_modifier
    assert "greed" in cfg.fng_modifier


def test_save_roundtrip_preserves_regime_and_fng(tmp_path: Path):
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.3},
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_one": 0.5},
            "RANGE": {"s_one": 1.2},
        },
        fng_modifier={"extreme_fear": 0.3, "neutral": 1.0},
    )
    out = tmp_path / "weights.yml"
    cfg.save(out)
    loaded = WeightConfig.load(out)
    assert loaded.strategy_weights_by_regime == cfg.strategy_weights_by_regime
    assert loaded.fng_modifier == cfg.fng_modifier


def test_save_skips_empty_optional_sections(tmp_path: Path):
    """regime/fng 비어있으면 yaml 에 출력 안 함 (기존 weights.yml 호환)."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.3},
    )
    out = tmp_path / "weights.yml"
    cfg.save(out)
    text = out.read_text()
    assert "strategy_weights_by_regime" not in text
    assert "fng_modifier" not in text


# -----------------------------------------------------------------------------
# compute_regime_aware_ensemble_score
# -----------------------------------------------------------------------------


def test_ensemble_aggregates_with_regime_weights():
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0, "s_two": 1.0},
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_one": 0.5, "s_two": 1.5},
        },
    )
    cands = {
        "s_one": [_mk_candidate("AAA"), _mk_candidate("BBB")],
        "s_two": [_mk_candidate("AAA")],
    }
    scores = compute_regime_aware_ensemble_score(
        cands, cfg, regime="UPTREND_STRONG", fng_label=None
    )
    # AAA: 0.5 (s_one) + 1.5 (s_two) = 2.0
    # BBB: 0.5 (s_one) = 0.5
    assert scores["AAA"] == pytest.approx(2.0)
    assert scores["BBB"] == pytest.approx(0.5)


def test_ensemble_excludes_blocked_strategies():
    """effective_weight ≤ 0 인 전략은 score 가산에서 제외."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0, "s_two": 1.0},
        strategy_weights_by_regime={
            "DOWNTREND_STRONG": {"s_one": 0.0, "s_two": 0.0},
        },
    )
    cands = {
        "s_one": [_mk_candidate("AAA")],
        "s_two": [_mk_candidate("AAA")],
    }
    scores = compute_regime_aware_ensemble_score(
        cands, cfg, regime="DOWNTREND_STRONG", fng_label=None
    )
    assert scores == {}


def test_ensemble_fallback_when_no_regime_provided():
    """regime=None → static strategy_weights 동작 회귀."""
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.5, "s_two": 0.8},
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_one": 0.5},  # 미사용
        },
    )
    cands = {
        "s_one": [_mk_candidate("AAA")],
        "s_two": [_mk_candidate("AAA")],
    }
    scores = compute_regime_aware_ensemble_score(cands, cfg, regime=None, fng_label=None)
    # AAA: 1.5 (s_one) + 0.8 (s_two) = 2.3
    assert scores["AAA"] == pytest.approx(2.3)


def test_ensemble_ignores_fng_in_practice():
    cfg = WeightConfig(
        priorities=_mk_priorities(),
        strategy_weights={"s_one": 1.0},
        strategy_weights_by_regime={
            "UPTREND_STRONG": {"s_one": 1.5},
        },
        fng_modifier={"extreme_greed": 0.6},
    )
    cands = {"s_one": [_mk_candidate("AAA")]}
    scores = compute_regime_aware_ensemble_score(
        cands, cfg, regime="UPTREND_STRONG", fng_label="Extreme Greed"
    )
    assert scores["AAA"] == pytest.approx(1.5)
