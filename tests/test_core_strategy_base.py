"""
test_core_strategy_base.py — Strategy Protocol / ScanContext / Candidate 검증.
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.strategy_base import Candidate, ScanContext, Strategy

# ============================================================================
# Candidate invariants
# ============================================================================

def _make_candidate(**overrides):
    base = dict(
        ticker="005930",
        name="삼성전자",
        strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-04-18"),
        score=700.0,
        entry_price=100.0,
        stop_loss=97.5,
        target_1=103.0,
        target_2=105.0,
    )
    base.update(overrides)
    return Candidate(**base)


def test_candidate_valid():
    c = _make_candidate()
    assert c.ticker == "005930"
    assert c.score == 700.0
    assert c.risk_pct == pytest.approx(2.5)
    assert c.reward_pct_t1 == pytest.approx(3.0)
    assert c.reward_pct_t2 == pytest.approx(5.0)


def test_candidate_score_out_of_range():
    with pytest.raises(ValueError):
        _make_candidate(score=1001.0)
    with pytest.raises(ValueError):
        _make_candidate(score=-0.01)


def test_candidate_price_order_invalid():
    # stop_loss > entry
    with pytest.raises(ValueError):
        _make_candidate(stop_loss=101.0)
    # entry > target_1
    with pytest.raises(ValueError):
        _make_candidate(target_1=99.0)
    # target_1 > target_2
    with pytest.raises(ValueError):
        _make_candidate(target_2=102.0)


def test_candidate_target1_eq_target2_allowed():
    """1차 = 2차 동일 허용 (단순 전략 구현 편의)"""
    c = _make_candidate(target_1=105.0, target_2=105.0)
    assert c.target_1 == c.target_2


# ============================================================================
# ScanContext basics
# ============================================================================

def test_scan_context_construction():
    df = pd.DataFrame({"close": [100, 101]}, index=pd.date_range("2026-04-01", periods=2))
    ctx = ScanContext(
        target_date="20260418",
        universe=("005930", "035720"),
        ohlcv={"005930": df, "035720": df},
        names={"005930": "삼성전자", "035720": "카카오"},
        market_caps={"005930": 3.5e14, "035720": 1.9e12},
        market="KOSPI",
    )
    assert ctx.target_date == "20260418"
    assert "035720" in ctx.universe
    assert ctx.names["005930"] == "삼성전자"


# ============================================================================
# Strategy Protocol — runtime_checkable
# ============================================================================

class _DummyStrategy:
    name = "dummy"

    def scan(self, ctx, top_n):
        return []


class _NotAStrategy:
    """name 속성 없음"""
    def scan(self, ctx, top_n):
        return []


def test_protocol_accepts_compliant():
    assert isinstance(_DummyStrategy(), Strategy)


def test_protocol_rejects_missing_name():
    """runtime_checkable Protocol 은 attribute 존재만 확인.
    name 이 없으면 isinstance 가 False 가 되어야 한다."""
    assert not isinstance(_NotAStrategy(), Strategy)
