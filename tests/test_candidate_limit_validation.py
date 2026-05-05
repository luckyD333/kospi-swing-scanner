"""tests/test_candidate_limit_validation.py — Candidate.limit_* 검증 테스트."""
from __future__ import annotations

import pandas as pd
import pytest

from core.strategy_base import Candidate


def _make_candidate(**overrides) -> Candidate:
    base = dict(
        ticker="000660",
        name="SK하이닉스",
        strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-05"),
        score=500.0,
        entry_price=1000,
        stop_loss=975,
        target_1=1030,
        target_2=1050,
    )
    base.update(overrides)
    return Candidate(**base)


def test_candidate_without_limit_fields():
    c = _make_candidate()
    assert c.limit_entry is None
    assert c.limit_stop is None


def test_candidate_with_valid_limit_fields():
    c = _make_candidate(limit_entry=985, limit_stop=970)
    assert c.limit_entry == 985
    assert c.limit_stop == 970


def test_candidate_limit_entry_without_limit_stop_fails():
    with pytest.raises(ValueError, match="limit_stop required"):
        _make_candidate(limit_entry=985, limit_stop=None)


def test_candidate_limit_stop_above_limit_entry_fails():
    # limit_stop ≥ limit_entry 는 가격 순서 위반
    with pytest.raises(ValueError, match="limit price order invalid"):
        _make_candidate(limit_entry=985, limit_stop=985)


def test_candidate_limit_entry_above_target_1_fails():
    with pytest.raises(ValueError, match="limit price order invalid"):
        _make_candidate(limit_entry=1030, limit_stop=1020)


def test_candidate_limit_entry_above_entry_price_fails():
    # limit_entry 가 entry_price 이상이면 의미 없음 — 가격 순서는 OK이나 별도 검증
    with pytest.raises(ValueError, match="limit_entry must be below entry_price"):
        _make_candidate(limit_entry=1000, limit_stop=985)


def test_candidate_limit_stop_zero_fails():
    with pytest.raises(ValueError, match="limit price order invalid"):
        _make_candidate(limit_entry=985, limit_stop=0)
