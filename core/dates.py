"""
core/dates.py — 거래일 계산 헬퍼.

휴장일은 미고려 (주말만 처리). 한국 공휴일은 별도 캘린더 필요 시
holiday_calendar 인자로 확장 (현재 미구현).
"""
from __future__ import annotations

from datetime import datetime, timedelta


def _now() -> datetime:
    """테스트에서 patch 할 수 있도록 datetime.now() 를 격리."""
    return datetime.now()


def latest_business_day(allow_today: bool = True) -> str:
    """가장 최근 영업일 (YYYYMMDD).

    allow_today=True (기본): 평일이면 오늘 반환 (장중 미완료 봉 포함).
    allow_today=False: 16:00 이전이면 전일로 walk-back (구버전 동작, 회귀용).
    어느 경우든 주말이면 직전 평일까지 walk-back. 한국 공휴일은 미고려.
    """
    now = _now()
    today = now.date()

    if not allow_today and now.hour < 16:
        today -= timedelta(days=1)

    while today.weekday() >= 5:
        today -= timedelta(days=1)

    return today.strftime("%Y%m%d")
