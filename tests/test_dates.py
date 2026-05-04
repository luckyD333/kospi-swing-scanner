"""tests/test_dates.py — latest_business_day() 단위 테스트."""
from __future__ import annotations

from datetime import datetime

import pytest

from core import dates


@pytest.fixture
def freeze_now(monkeypatch):
    def _set(dt: datetime) -> None:
        monkeypatch.setattr(dates, "_now", lambda: dt)
    return _set


def test_monday_intraday_returns_today(freeze_now):
    """월요일 12:30 → 오늘 반환 (장중 미완료 봉 허용)."""
    freeze_now(datetime(2026, 5, 4, 12, 30))
    assert dates.latest_business_day() == "20260504"


def test_monday_after_close_returns_today(freeze_now):
    """월요일 16:30 → 오늘 반환."""
    freeze_now(datetime(2026, 5, 4, 16, 30))
    assert dates.latest_business_day() == "20260504"


def test_saturday_walks_back_to_friday(freeze_now):
    """토요일 10:00 → 직전 금요일."""
    freeze_now(datetime(2026, 5, 2, 10, 0))
    assert dates.latest_business_day() == "20260501"


def test_sunday_walks_back_to_friday(freeze_now):
    """일요일 14:00 → 직전 금요일."""
    freeze_now(datetime(2026, 5, 3, 14, 0))
    assert dates.latest_business_day() == "20260501"


def test_legacy_cutoff_before_close(freeze_now):
    """allow_today=False + 16:00 이전 → 전일 walk-back (구버전 동작)."""
    freeze_now(datetime(2026, 5, 4, 12, 30))
    # 5/4 (월) → 5/3 (일) → 5/2 (토) → 5/1 (금)
    assert dates.latest_business_day(allow_today=False) == "20260501"


def test_legacy_cutoff_after_close(freeze_now):
    """allow_today=False + 16:00 이후 평일 → 오늘."""
    freeze_now(datetime(2026, 5, 4, 16, 30))
    assert dates.latest_business_day(allow_today=False) == "20260504"
