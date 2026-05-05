"""tests/test_trade_plan_limit.py — TradePlan limit_* 자동 계산 validator 테스트."""
from __future__ import annotations

from output.models import TradePlan


def test_trade_plan_without_limit_fields():
    tp = TradePlan(
        entry=1000, stop=975, target_1=1030, target_2=1050,
        rr_ratio=1.2, rr_band="UNDER",
    )
    assert tp.limit_entry is None
    assert tp.limit_stop is None
    assert tp.rr_ratio_limit is None
    assert tp.rr_band_limit is None


def test_trade_plan_with_limit_fields_auto_computes_rr():
    # limit_entry=985, limit_stop=970, target_1=1030
    # risk = 985-970 = 15, reward = 1030-985 = 45 → rr = 3.0 → OVER band
    tp = TradePlan(
        entry=1000, stop=975, target_1=1030, target_2=1050,
        rr_ratio=1.2, rr_band="UNDER",
        limit_entry=985, limit_stop=970,
    )
    assert tp.rr_ratio_limit == 3.0
    assert tp.rr_band_limit == "OVER"


def test_trade_plan_limit_rr_under_band():
    # rr = 18/10 = 1.8 < 2.0 → UNDER
    tp = TradePlan(
        entry=1000, stop=975, target_1=1003, target_2=1010,
        rr_ratio=0.5, rr_band="UNDER",
        limit_entry=985, limit_stop=975,
    )
    assert tp.rr_ratio_limit == 1.8
    assert tp.rr_band_limit == "UNDER"


def test_trade_plan_limit_rr_sweet_band():
    # rr = 23/10 = 2.3 → SWEET
    tp = TradePlan(
        entry=1000, stop=975, target_1=1008, target_2=1015,
        rr_ratio=0.7, rr_band="UNDER",
        limit_entry=985, limit_stop=975,
    )
    assert tp.rr_ratio_limit == 2.3
    assert tp.rr_band_limit == "SWEET"


def test_trade_plan_limit_only_one_field_no_compute():
    # limit_entry 만 있고 limit_stop 없으면 R/R 계산 스킵
    tp = TradePlan(
        entry=1000, stop=975, target_1=1030, target_2=1050,
        rr_ratio=1.2, rr_band="UNDER",
        limit_entry=985,  # limit_stop 누락
    )
    assert tp.rr_ratio_limit is None
    assert tp.rr_band_limit is None
