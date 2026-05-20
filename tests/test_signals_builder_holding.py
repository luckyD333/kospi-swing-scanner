"""tests/test_signals_builder_holding.py — DecisionMeta holding wiring 검증.

signals_builder 의 _build_signal 가 holding_recommender lookup 결과를
DecisionMeta.recommended_holding_bars/holding_confidence/holding_status 에
정확히 채워 넣는지 검증.

mock holding_recommendations.json 으로 결합 규칙 시나리오 + edge cases.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def mock_rec_file(tmp_path: Path, monkeypatch) -> Path:
    """data/holding_recommendations.json mock 으로 교체."""
    rec_data = {
        "schema_version": "1.0",
        "min_trades_per_cell": 30,
        "primary": {
            "strategy_two_cross_sectional_momentum": {
                "BULL":    {"best": 7, "n_trades": 500, "mean_pnl": 0.022},
                "NEUTRAL": {"best": 5, "n_trades": 300, "mean_pnl": 0.012},
            },
        },
        "modifier_fng": {},
        "modifier_per_ticker": {"DOWNTREND_STRONG": "skip"},
        "modifier_atr": {},
    }
    # signals_builder 모듈의 cache 초기화 + path 강제 교체
    import output.signals_builder as sb
    sb._HOLDING_RECS_CACHE = rec_data  # type: ignore[attr-defined]
    yield None
    sb._HOLDING_RECS_CACHE = None  # type: ignore[attr-defined]


def test_holding_lookup_normal_case(mock_rec_file):
    """정상 케이스 — primary 매칭, OK 상태로 채워짐."""
    from output.holding_recommender import recommend_holding
    import output.signals_builder as sb

    rec = recommend_holding(
        sb._holding_recs(),
        strategy="strategy_two_cross_sectional_momentum",
        market_regime="BULL",
        fng_label=None,
        per_ticker_regime="UPTREND_STRONG",
        atr_bucket="MID",
    )
    assert rec.status == "OK"
    assert rec.recommended_bars == 7
    assert 0.0 < rec.confidence <= 1.0


def test_holding_lookup_skip_downtrend(mock_rec_file):
    """per_ticker_regime=DOWNTREND_STRONG → SKIP."""
    from output.holding_recommender import recommend_holding
    import output.signals_builder as sb

    rec = recommend_holding(
        sb._holding_recs(),
        strategy="strategy_two_cross_sectional_momentum",
        market_regime="BULL",
        fng_label=None,
        per_ticker_regime="DOWNTREND_STRONG",
        atr_bucket="MID",
    )
    assert rec.status == "SKIP"
    assert rec.recommended_bars is None


def test_holding_lookup_unknown_strategy_low_confidence(mock_rec_file):
    """primary 에 없는 strategy → LOW_CONFIDENCE."""
    from output.holding_recommender import recommend_holding
    import output.signals_builder as sb

    rec = recommend_holding(
        sb._holding_recs(),
        strategy="strategy_unknown",
        market_regime="BULL",
        fng_label=None,
        per_ticker_regime="UPTREND_STRONG",
        atr_bucket="MID",
    )
    assert rec.status == "LOW_CONFIDENCE"


def test_holding_lookup_no_recs_file_low_confidence(tmp_path, monkeypatch):
    """data/holding_recommendations.json 부재 시 lookup → LOW_CONFIDENCE."""
    import output.signals_builder as sb
    sb._HOLDING_RECS_CACHE = {}  # type: ignore[attr-defined]
    from output.holding_recommender import recommend_holding

    rec = recommend_holding(
        sb._holding_recs(),
        strategy="strategy_two_cross_sectional_momentum",
        market_regime="BULL",
        fng_label=None,
        per_ticker_regime="UPTREND_STRONG",
        atr_bucket="MID",
    )
    assert rec.status == "LOW_CONFIDENCE"
    sb._HOLDING_RECS_CACHE = None  # type: ignore[attr-defined]
