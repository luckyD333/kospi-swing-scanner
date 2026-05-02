"""
core/dates.py — 거래일 계산 헬퍼.

휴장일은 미고려 (주말만 처리). 한국 공휴일은 별도 캘린더 필요 시 도입.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta


def latest_business_day() -> str:
    """장 마감(16:00) 이전이면 전일 기준. 주말이면 직전 금요일.

    Returns: YYYYMMDD 문자열.
    """
    today = date.today()
    now = datetime.now()
    if now.hour < 16:
        today -= timedelta(days=1)
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    return today.strftime("%Y%m%d")
