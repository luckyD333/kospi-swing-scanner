"""test_order_type.py — order_type_classifier 단위 테스트 (PR-C).

검증 케이스:
  Case A (ETN BREAKOUT): entry=250000, current=181290 → BREAKOUT, '역지정가'
  Case B (한국철강 PULLBACK): entry=10150, current=10260 → PULLBACK, '지정가'
"""
from __future__ import annotations

import pytest

from core.decision.order_type_classifier import (
    OrderTypeIntent,
    classify,
    korean_label,
)


# ---------------------------------------------------------------------------
# 분류 — BREAKOUT
# ---------------------------------------------------------------------------

def test_breakout_when_entry_well_above_current():
    """entry > current * 1.005 → BREAKOUT."""
    assert classify(110.0, 100.0) == OrderTypeIntent.BREAKOUT


def test_breakout_etn_case_a():
    """검증 케이스 A — ETN: entry=250000 vs current=181290 → BREAKOUT."""
    assert classify(250000, 181290) == OrderTypeIntent.BREAKOUT


def test_breakout_threshold_just_above():
    """entry/current 가 1.005 보다 약간 위 → BREAKOUT."""
    # 1.0051 > 1.005
    assert classify(100.51, 100.0) == OrderTypeIntent.BREAKOUT


def test_breakout_at_threshold_is_immediate():
    """entry/current = 1.005 정확히 → IMMEDIATE (>1.005 만 BREAKOUT)."""
    assert classify(100.5, 100.0) == OrderTypeIntent.IMMEDIATE


# ---------------------------------------------------------------------------
# 분류 — PULLBACK
# ---------------------------------------------------------------------------

def test_pullback_when_entry_well_below_current():
    """entry < current * 0.995 → PULLBACK."""
    assert classify(90.0, 100.0) == OrderTypeIntent.PULLBACK


def test_pullback_korean_steel_case_b():
    """검증 케이스 B — 한국철강: entry=10150 vs current=10260 → PULLBACK."""
    # 10150 / 10260 = 0.9893 < 0.995
    assert classify(10150, 10260) == OrderTypeIntent.PULLBACK


def test_pullback_threshold_just_below():
    """entry/current 가 0.995 보다 약간 아래 → PULLBACK."""
    # 0.9949 < 0.995
    assert classify(99.49, 100.0) == OrderTypeIntent.PULLBACK


def test_pullback_at_threshold_is_immediate():
    """entry/current = 0.995 정확히 → IMMEDIATE (<0.995 만 PULLBACK)."""
    assert classify(99.5, 100.0) == OrderTypeIntent.IMMEDIATE


# ---------------------------------------------------------------------------
# 분류 — IMMEDIATE
# ---------------------------------------------------------------------------

def test_immediate_when_close():
    """entry ≈ current (0.995 ~ 1.005) → IMMEDIATE."""
    assert classify(100.0, 100.0) == OrderTypeIntent.IMMEDIATE
    assert classify(100.3, 100.0) == OrderTypeIntent.IMMEDIATE
    assert classify(99.7, 100.0) == OrderTypeIntent.IMMEDIATE


def test_immediate_with_zero_current_fallback():
    """current=0 (이상 데이터) → IMMEDIATE 폴백."""
    assert classify(100.0, 0) == OrderTypeIntent.IMMEDIATE
    assert classify(100.0, -1) == OrderTypeIntent.IMMEDIATE


# ---------------------------------------------------------------------------
# 한국어 라벨
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("intent,expected", [
    (OrderTypeIntent.BREAKOUT, "역지정가"),
    (OrderTypeIntent.PULLBACK, "지정가"),
    (OrderTypeIntent.IMMEDIATE, "시장가"),
])
def test_korean_label_mapping(intent: OrderTypeIntent, expected: str):
    """OrderTypeIntent → 한국어 라벨 매핑."""
    assert korean_label(intent) == expected


# ---------------------------------------------------------------------------
# 임계값 커스터마이즈
# ---------------------------------------------------------------------------

def test_classify_with_custom_thresholds():
    """breakout_thr / pullback_thr 커스터마이즈."""
    # 더 보수적인 임계값 (1% 갭만 BREAKOUT 인정)
    assert classify(100.5, 100.0, breakout_thr=1.01) == OrderTypeIntent.IMMEDIATE
    assert classify(101.5, 100.0, breakout_thr=1.01) == OrderTypeIntent.BREAKOUT
