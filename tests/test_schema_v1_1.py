"""
test_schema_v1_1.py — PR-L: 출력 스키마 v1.1 검증.

검증 항목:
  1. SignalsPayload.schema_version == "1.1"
  2. Signal.confirmation_level 필드 존재 (Phase 1 PR-H 노출)
  3. Signal.active_regime 필드 존재 (현재 국면 라벨)
  4. confirmation_level 이 candidate.metadata 에서 pass-through
  5. active_regime 이 market_regime 인자에서 pass-through
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from output.models import Fundamentals, Flow, MarketSnapshot, SignalsPayload, TickerSnapshot
from output.signals_builder import build_signals_payload


# ============================================================================
# 헬퍼
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


def _make_candidate(ticker: str = "TEST01", confirmation_level: str | None = "STRONG") -> MagicMock:
    c = MagicMock()
    c.ticker = ticker
    c.name = "테스트"
    c.score = 500.0
    c.timeframe = "1D"
    c.entry_price = 10000
    c.stop_loss = 9700
    c.target_1 = 10400
    c.target_2 = 10700
    c.signal_date = None
    c.limit_entry = None
    c.limit_stop = None
    c.metadata = {
        "rr_ratio": 2.0, "rr_band": "sweet", "atr_14": 300,
        "confirmation_level": confirmation_level,
    }
    return c


# ============================================================================
# 테스트
# ============================================================================

def test_schema_version_is_1_1():
    """SignalsPayload.schema_version == '1.1'."""
    snap = _make_snapshot()
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [_make_candidate()]})
    assert payload.schema_version == "1.1", (
        f"schema_version={payload.schema_version!r} (expected '1.1')"
    )


def test_default_schema_version_in_model():
    """SignalsPayload 기본값이 '1.1' 이다."""
    assert SignalsPayload.model_fields["schema_version"].default == "1.1"


def test_signal_has_confirmation_level_field():
    """Signal 에 confirmation_level 필드 존재."""
    snap = _make_snapshot()
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [_make_candidate()]})
    assert payload.signals
    sig = payload.signals[0]
    assert hasattr(sig, "confirmation_level"), "Signal.confirmation_level 필드 부재"


def test_confirmation_level_pass_through():
    """candidate.metadata['confirmation_level'] → Signal.confirmation_level."""
    snap = _make_snapshot()
    c = _make_candidate(confirmation_level="STRONG")
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [c]})
    assert payload.signals[0].confirmation_level == "STRONG"


def test_confirmation_level_none_when_absent():
    """metadata 에 confirmation_level 없으면 Signal.confirmation_level=None."""
    snap = _make_snapshot()
    c = _make_candidate(confirmation_level=None)
    c.metadata = {"rr_ratio": 2.0, "rr_band": "sweet", "atr_14": 300}
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [c]})
    assert payload.signals[0].confirmation_level is None


def test_signal_has_active_regime_field():
    """Signal 에 active_regime 필드 존재."""
    snap = _make_snapshot()
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [_make_candidate()]})
    assert payload.signals
    assert hasattr(payload.signals[0], "active_regime"), "Signal.active_regime 필드 부재"


def test_active_regime_pass_through():
    """market_regime 에 1D score 있으면 Signal.active_regime 에 BULL/NEUTRAL/BEAR 라벨."""
    snap = _make_snapshot()
    regime = {"1d": {"score": 80, "regime": "BULL"}}
    payload = build_signals_payload(
        snap, {"strategy_one_d_v2": [_make_candidate()]},
        market_regime=regime,
    )
    assert payload.signals[0].active_regime == "BULL"


def test_active_regime_none_when_no_regime():
    """market_regime 없으면 Signal.active_regime=None."""
    snap = _make_snapshot()
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [_make_candidate()]})
    assert payload.signals[0].active_regime is None
