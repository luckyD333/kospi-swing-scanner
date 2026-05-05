"""
core/dates.py — 거래일 계산 헬퍼.

`latest_business_day`: 주말만 처리 (한국 공휴일 미고려, 레거시 호환).
`trading_days_since` / `is_same_trading_day`: XKRX 캘린더 기반 한국 공휴일 반영.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta


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


_XKRX_CALENDAR = None


def _xkrx_calendar():
    """XKRX 캘린더 lazy load + 모듈 캐시 (exchange_calendars 의존성).

    매 요청마다 get_calendar 재호출하면 latency 누적되므로 1회만 로드.
    """
    global _XKRX_CALENDAR
    if _XKRX_CALENDAR is None:
        from exchange_calendars import get_calendar
        _XKRX_CALENDAR = get_calendar("XKRX")
    return _XKRX_CALENDAR


def trading_days_since(signal_date: date, today: date | None = None) -> int:
    """signal_date 이후 경과 거래일 수 (XKRX 캘린더, signal_date 당일 제외).

    today 가 signal_date 와 같거나 이전이면 0.
    """
    import pandas as pd

    today = today or date.today()
    if today <= signal_date:
        return 0
    cal = _xkrx_calendar()
    sessions = cal.sessions_in_range(pd.Timestamp(signal_date), pd.Timestamp(today))
    return max(0, len(sessions) - 1)  # signal_date 당일 제외


def is_same_trading_day(signal_date: date, today: date | None = None) -> bool:
    """signal_date 와 today 가 같은 거래일인지 (한국 공휴일 반영).

    today 가 거래일 아니면(주말/공휴일) False — 장외 시간 분기에 활용.
    """
    import pandas as pd

    today = today or date.today()
    if today != signal_date:
        return False
    cal = _xkrx_calendar()
    return bool(cal.is_session(pd.Timestamp(today)))
