"""1D today row 의 종가 확정 여부 판정 utility 테스트."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.cache.incomplete_bar import is_today_bar_complete

KST = ZoneInfo("Asia/Seoul")


def _today_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _yesterday_str() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")


def test_complete_when_fetched_after_market_close():
    today = _today_str()
    fetched = datetime.now(KST).replace(hour=15, minute=35, second=0).isoformat()
    assert is_today_bar_complete(today, fetched) is True


def test_incomplete_when_fetched_before_market_close():
    today = _today_str()
    fetched = datetime.now(KST).replace(hour=11, minute=44, second=0).isoformat()
    assert is_today_bar_complete(today, fetched) is False


def test_complete_when_target_is_past_date():
    """target_date 가 과거면 fetched 시각 무관 항상 confirmed."""
    yesterday = _yesterday_str()
    fetched = datetime.now(KST).replace(hour=11, minute=44, second=0).isoformat()
    assert is_today_bar_complete(yesterday, fetched) is True


def test_incomplete_when_fetched_at_missing():
    today = _today_str()
    assert is_today_bar_complete(today, None) is False


def test_complete_at_market_close_boundary():
    """15:30 정각 = 종가 확정 시작점 (>= 비교)."""
    today = _today_str()
    fetched = datetime.now(KST).replace(hour=15, minute=30, second=0).isoformat()
    assert is_today_bar_complete(today, fetched) is True


def test_handles_naive_iso_as_kst():
    """tz 없는 ISO 도 KST 로 해석."""
    today = _today_str()
    fetched = datetime.now(KST).replace(hour=15, minute=35, second=0, tzinfo=None).isoformat()
    assert is_today_bar_complete(today, fetched) is True


def test_handles_invalid_iso_as_incomplete():
    today = _today_str()
    assert is_today_bar_complete(today, "not-an-iso") is False
