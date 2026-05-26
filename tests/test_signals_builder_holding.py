"""tests/test_signals_builder_holding.py — DecisionMeta holding wiring 검증.

signals_builder 의 _build_signal 가 holding_recommender lookup 결과를
DecisionMeta.recommended_holding_bars/holding_confidence/holding_status 에
정확히 채워 넣는지 검증.

mock holding_recommendations.json 으로 결합 규칙 시나리오 + edge cases.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture
def mock_rec_file(tmp_path: Path, monkeypatch) -> Path:
    """data/holding_recommendations.json mock 으로 교체."""
    rec_data = {
        "schema_version": "1.0",
        "min_trades_per_cell": 30,
        "primary": {
            "S2_CrossSectional": {
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
        timeframe="1D",
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
        timeframe="1D",
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


def _snapshot(ticker: str = "001") -> object:
    from output.models import Flow, Fundamentals, MarketSnapshot, TickerSnapshot

    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-20T16:00:00+09:00",
        source={},
        market_indices={},
        tickers={
            ticker: TickerSnapshot(
                ticker=ticker,
                name=f"종목{ticker}",
                current_price=7100,
                change_pct=0.5,
                volume=100_000,
                market_cap_krw=100_000_000_000,
                fundamentals=Fundamentals(),
                flow=Flow(),
            ),
        },
    )


def _candidate(strategy: str, ticker: str = "001", timeframe: str = "1D") -> object:
    from core.strategy_base import Candidate

    c = Candidate(
        ticker=ticker,
        name=f"종목{ticker}",
        strategy=strategy,
        signal_date=pd.Timestamp.now(tz="Asia/Seoul"),
        score=80.0,
        entry_price=7000.0,
        stop_loss=6800.0,
        target_1=7400.0,
        target_2=7800.0,
        current_price=7100.0,
        market_cap_bil=100.0,
        volume_20d_avg=100_000.0,
        metadata={
            "rr_ratio": 2.0,
            "rr_band": "sweet",
            "atr_14": 100,
            "product_type": "STOCK",
            "per_ticker_regime": "UPTREND_STRONG",
            "atr_bucket": "MID",
            "naver_url": f"http://x/{ticker}",
        },
    )
    c.timeframe = timeframe
    return c


def _weight_config() -> object:
    from core.decision.config import Priority, WeightConfig

    return WeightConfig(
        priorities=[Priority("score", 100.0, "higher_better", "전략점수")],
    )


def test_signals_builder_maps_1d_runtime_strategy_to_holding_rec(mock_rec_file):
    """signals_builder — 운영 strategy id 로 1D 백테스트 holding 추천을 채운다."""
    from output.signals_builder import build_signals_payload

    cand = _candidate("strategy_two_cross_sectional_momentum", timeframe="1D")
    payload = build_signals_payload(
        _snapshot(),
        {"strategy_two_cross_sectional_momentum": [cand]},
        weight_config=_weight_config(),
        market_regime={"1d": {"regime": "BULL", "score": 80}},
    )
    sig = next(s for s in payload.signals if s.strategy.id != "all")

    assert sig.ranking.decision is not None
    assert sig.ranking.decision.holding_status == "OK"
    assert sig.ranking.decision.recommended_holding_bars == 7
    assert sig.ranking.decision.holding_confidence == 1.0


def test_signals_builder_omits_holding_rec_for_intraday(mock_rec_file):
    """signals_builder — 1h/30m 에는 1D holding 추천을 노출하지 않는다."""
    from output.signals_builder import build_signals_payload

    cand = _candidate("strategy_two_1h", timeframe="1h")
    payload = build_signals_payload(
        _snapshot(),
        {"strategy_two_1h": [cand]},
        weight_config=_weight_config(),
        market_regime={"1d": {"regime": "BULL", "score": 80}},
    )
    sig = next(s for s in payload.signals if s.strategy.id != "all")

    assert sig.ranking.decision is not None
    assert sig.ranking.decision.holding_status is None
    assert sig.ranking.decision.recommended_holding_bars is None
    assert sig.ranking.decision.holding_confidence is None
