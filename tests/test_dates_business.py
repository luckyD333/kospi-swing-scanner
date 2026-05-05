"""tests/test_dates_business.py — XKRX 캘린더 거래일 계산 테스트."""
from __future__ import annotations

from datetime import date


from core.dates import is_same_trading_day, trading_days_since


# ──────────── trading_days_since ────────────


def test_trading_days_same_day():
    assert trading_days_since(date(2026, 5, 5), date(2026, 5, 5)) == 0


def test_trading_days_today_before_signal():
    assert trading_days_since(date(2026, 5, 8), date(2026, 5, 5)) == 0


def test_trading_days_skip_weekend():
    # 2026-05-08(금) → 2026-05-11(월): 주말 제외 → 1거래일
    assert trading_days_since(date(2026, 5, 8), date(2026, 5, 11)) == 1


def test_trading_days_skip_korean_holiday():
    # 2026-05-04(월) → 2026-05-06(수): 5/5 어린이날 공휴일 제외 → 1거래일
    assert trading_days_since(date(2026, 5, 4), date(2026, 5, 6)) == 1


def test_trading_days_one_week_normal():
    # 2026-05-11(월) → 2026-05-15(금): 평일 5일 → 4거래일 (signal_date 당일 제외)
    assert trading_days_since(date(2026, 5, 11), date(2026, 5, 15)) == 4


# ──────────── is_same_trading_day ────────────


def test_is_same_trading_day_normal_weekday():
    # 2026-05-11(월) — 평일
    assert is_same_trading_day(date(2026, 5, 11), date(2026, 5, 11)) is True


def test_is_same_trading_day_different_dates():
    assert is_same_trading_day(date(2026, 5, 11), date(2026, 5, 12)) is False


def test_is_same_trading_day_holiday_returns_false():
    # 2026-05-05 어린이날 — 같은 날짜여도 거래일 아니므로 False
    assert is_same_trading_day(date(2026, 5, 5), date(2026, 5, 5)) is False


def test_is_same_trading_day_weekend_returns_false():
    # 2026-05-09(토)
    assert is_same_trading_day(date(2026, 5, 9), date(2026, 5, 9)) is False
