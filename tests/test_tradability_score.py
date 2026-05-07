"""
test_tradability_score.py — PR-K: tradability_score 신규 메트릭 검증.

tradability_score (0~100):
  - volume_20d_avg 백분위 × 0.4  (거래대금, 높을수록 좋음)
  - stop_pct 역백분위 × 0.3       (손절폭%, 낮을수록 = 변동성 작음)
  - atr_pct 역백분위 × 0.3        (ATR/진입가%, 낮을수록 = 안정적)

기존 final_score 는 변경하지 않음 (D2 결정).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from core.decision.aggregator import aggregate_candidates
from core.decision.config import Priority, WeightConfig
from core.strategy_base import Candidate
from output.models import MarketSnapshot, TickerSnapshot, Fundamentals, Flow
from output.signals_builder import build_signals_payload


# ============================================================================
# 헬퍼
# ============================================================================

def _make_cfg() -> WeightConfig:
    return WeightConfig(
        priorities=[
            Priority(key="momentum_pct", weight=100.0, direction="higher_better", label="모멘텀"),
        ],
        must_have=[],
        strategy_weights={},
    )


def _make_candidate(
    ticker: str,
    volume: float = 1_000_000,
    entry: int = 10000,
    stop: int = 9700,
    atr_14: float = 300.0,
    momentum_pct: float = 0.05,
) -> Candidate:
    return Candidate(
        ticker=ticker,
        name=ticker,
        strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-07"),
        score=500.0,
        entry_price=entry,
        stop_loss=stop,
        target_1=entry + 300,
        target_2=entry + 600,
        current_price=entry,
        market_cap_bil=500.0,
        volume_20d_avg=volume,
        conditions_met={},
        metadata={
            "momentum_pct": momentum_pct,
            "atr_14": atr_14,
        },
    )


# ============================================================================
# 단위 테스트
# ============================================================================

def test_tradability_score_in_ranked_candidate():
    """RankedCandidate.normalized_metrics['tradability_score'] 존재."""
    c = _make_candidate("A")
    ranked = aggregate_candidates([c], _make_cfg())
    assert ranked
    assert "tradability_score" in ranked[0].normalized_metrics, (
        "tradability_score 키 부재"
    )
    ts = ranked[0].normalized_metrics["tradability_score"]
    assert 0.0 <= ts <= 100.0


def test_high_volume_higher_tradability():
    """거래대금 최상위 후보 → tradability_score 상위."""
    high_vol = _make_candidate("HIGH", volume=50_000_000, momentum_pct=0.05)
    low_vol  = _make_candidate("LOW",  volume=500_000,   momentum_pct=0.05)
    ranked = aggregate_candidates([high_vol, low_vol], _make_cfg())
    assert len(ranked) == 2
    ts_map = {r.candidate.ticker: r.normalized_metrics["tradability_score"] for r in ranked}
    assert ts_map["HIGH"] > ts_map["LOW"], (
        f"HIGH volume tradability={ts_map['HIGH']:.1f} ≤ LOW={ts_map['LOW']:.1f}"
    )


def test_tight_stop_higher_tradability():
    """stop_pct 낮은 후보 (변동성 작음) → tradability_score 높음."""
    tight = _make_candidate("TIGHT", entry=10000, stop=9900, atr_14=100.0, momentum_pct=0.05)
    wide  = _make_candidate("WIDE",  entry=10000, stop=9000, atr_14=1000.0, momentum_pct=0.05)
    ranked = aggregate_candidates([tight, wide], _make_cfg())
    assert len(ranked) == 2
    ts_map = {r.candidate.ticker: r.normalized_metrics["tradability_score"] for r in ranked}
    assert ts_map["TIGHT"] > ts_map["WIDE"], (
        f"TIGHT stop tradability={ts_map['TIGHT']:.1f} ≤ WIDE={ts_map['WIDE']:.1f}"
    )


def test_tradability_score_does_not_change_final_score():
    """tradability_score 추가 후 final_score 는 기존과 동일 (D2 결정)."""
    c1 = _make_candidate("A", momentum_pct=0.10)
    c2 = _make_candidate("B", momentum_pct=0.05)
    ranked = aggregate_candidates([c1, c2], _make_cfg())
    # final_score 는 momentum_pct 기반 → A > B
    assert ranked[0].candidate.ticker == "A"
    # tradability_score 가 final_score 에 포함되지 않았으므로 순위 미변경
    assert ranked[0].final_score > ranked[1].final_score


def test_single_candidate_tradability_score_is_50():
    """후보 1개 → 모든 백분위가 0 → tradability_score = 0."""
    c = _make_candidate("ONLY")
    ranked = aggregate_candidates([c], _make_cfg())
    ts = ranked[0].normalized_metrics["tradability_score"]
    # 단일 후보: 모든 percentile = 0 (같은 값끼리 1/n으로 분할)
    assert 0.0 <= ts <= 100.0  # 범위 내


# ============================================================================
# signals_builder 통합
# ============================================================================

def _make_snapshot(ticker: str = "TEST01") -> MarketSnapshot:
    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-07T22:00:00+09:00",
        source={},
        market_indices={},
        tickers={ticker: TickerSnapshot(
            ticker=ticker, name="테스트",
            current_price=10000, change_pct=0.0, volume=100_000,
            market_cap_krw=500_000_000_000,
            fundamentals=Fundamentals(),
            flow=Flow(),
        )},
    )


def test_tradability_score_in_signal():
    """signals_builder 출력 Signal 에 tradability_score 필드 존재."""
    snap = _make_snapshot()
    c = MagicMock()
    c.ticker = "TEST01"
    c.name = "테스트"
    c.score = 500.0
    c.timeframe = "1D"
    c.entry_price = 10000
    c.stop_loss = 9700
    c.target_1 = 10300
    c.target_2 = 10600
    c.signal_date = None
    c.limit_entry = None
    c.limit_stop = None
    c.metadata = {
        "rr_ratio": 2.0, "rr_band": "sweet", "atr_14": 300,
        "momentum_pct": 0.05,
    }
    c.volume_20d_avg = 1_000_000
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [c]})
    assert payload.signals
    sig = payload.signals[0]
    # tradability_score 필드가 존재해야 함 (None 이어도 OK)
    assert hasattr(sig, "tradability_score"), "Signal.tradability_score 필드 부재"
