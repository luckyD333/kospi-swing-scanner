"""tests/test_holding_recommender.py — 상황별 holding 추천 lookup 검증.

mock JSON 으로 결합 규칙 검증:
  - 정상: primary + modifier sum → clamp [1, 7]
  - DOWNTREND_STRONG → SKIP
  - primary trade < min_n → LOW_CONFIDENCE
  - 결측 modifier → 0 delta
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from output.holding_recommender import (
    HoldingRecommendation,
    load_recommendations,
    recommend_holding,
)


@pytest.fixture
def mock_recs(tmp_path: Path) -> dict:
    data = {
        "schema_version": "1.0",
        "min_trades_per_cell": 30,
        "baseline_holding": 5,
        "primary": {
            "S1_MeanReversion": {
                "BULL":    {"best": 5, "n_trades": 120, "mean_pnl": 0.015},
                "NEUTRAL": {"best": 5, "n_trades": 80, "mean_pnl": 0.008},
                "BEAR":    {"best": 3, "n_trades": 15, "mean_pnl": 0.002},
            },
            "S2_CrossSectional": {
                "BULL":    {"best": 7, "n_trades": 500, "mean_pnl": 0.022},
                "NEUTRAL": {"best": 5, "n_trades": 300, "mean_pnl": 0.012},
            },
        },
        "modifier_fng": {"Extreme_Greed": -1, "Extreme_Fear": +1},
        "modifier_per_ticker": {
            "UPTREND_STRONG": 1,
            "RANGE": 0,
            "DOWNTREND_STRONG": "skip",
        },
        "modifier_atr": {"LOW": 0, "MID": 0, "HIGH": -1},
    }
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(data))
    return data


def test_recommend_normal_case(mock_recs, tmp_path):
    """정상 케이스 — primary + modifiers → clamp."""
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(mock_recs))
    recs = load_recommendations(p)
    # S2 / BULL primary best=7, modifiers: UPTREND_STRONG=+1, HIGH=-1 → 7+1-1=7
    out = recommend_holding(
        recs,
        strategy="S2_CrossSectional",
        market_regime="BULL",
        fng_label=None,
        per_ticker_regime="UPTREND_STRONG",
        atr_bucket="HIGH",
    )
    assert isinstance(out, HoldingRecommendation)
    assert out.status == "OK"
    assert out.recommended_bars == 7
    assert 0.0 < out.confidence <= 1.0


def test_recommend_skip_on_downtrend_strong(mock_recs, tmp_path):
    """per_ticker_regime=DOWNTREND_STRONG → SKIP."""
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(mock_recs))
    recs = load_recommendations(p)
    out = recommend_holding(
        recs,
        strategy="S1_MeanReversion",
        market_regime="BULL",
        fng_label=None,
        per_ticker_regime="DOWNTREND_STRONG",
        atr_bucket="MID",
    )
    assert out.status == "SKIP"
    assert out.recommended_bars is None
    assert out.confidence == 0.0


def test_recommend_low_confidence_sparse(mock_recs, tmp_path):
    """primary trade < min_n → LOW_CONFIDENCE."""
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(mock_recs))
    recs = load_recommendations(p)
    # S1 / BEAR n_trades=15 < 30 → LOW_CONFIDENCE
    out = recommend_holding(
        recs,
        strategy="S1_MeanReversion",
        market_regime="BEAR",
        fng_label=None,
        per_ticker_regime="RANGE",
        atr_bucket="MID",
    )
    assert out.status == "LOW_CONFIDENCE"
    assert out.recommended_bars is None


def test_recommend_clamp_to_bounds(mock_recs, tmp_path):
    """modifier 합산이 [1, 7] 밖이면 clamp."""
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(mock_recs))
    recs = load_recommendations(p)
    # S2/BULL primary=7, fng=Extreme_Fear(+1), per_ticker=UPTREND_STRONG(+1)
    # → 7+1+1=9 → clamp 7
    out = recommend_holding(
        recs,
        strategy="S2_CrossSectional",
        market_regime="BULL",
        fng_label="Extreme_Fear",
        per_ticker_regime="UPTREND_STRONG",
        atr_bucket="MID",
    )
    assert out.recommended_bars == 7


def test_recommend_missing_modifier_treated_as_zero(mock_recs, tmp_path):
    """결측 modifier (unknown label) → 0 delta."""
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(mock_recs))
    recs = load_recommendations(p)
    # S1/NEUTRAL primary=5, unknown labels → 0+0+0=5
    out = recommend_holding(
        recs,
        strategy="S1_MeanReversion",
        market_regime="NEUTRAL",
        fng_label="Greed",  # mock 에 없음 → 0
        per_ticker_regime="MIXED",  # mock 에 없음 → 0
        atr_bucket="MID",
    )
    assert out.recommended_bars == 5


def test_recommend_strategy_not_in_primary(mock_recs, tmp_path):
    """primary 에 없는 strategy → LOW_CONFIDENCE."""
    p = tmp_path / "rec.json"
    p.write_text(json.dumps(mock_recs))
    recs = load_recommendations(p)
    out = recommend_holding(
        recs,
        strategy="S99_NewStrategy",  # primary 부재
        market_regime="BULL",
        fng_label=None,
        per_ticker_regime="RANGE",
        atr_bucket="MID",
    )
    assert out.status == "LOW_CONFIDENCE"
