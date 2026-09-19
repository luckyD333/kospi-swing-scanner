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


def _tomorrow_str() -> str:
    return (datetime.now(KST) + timedelta(days=1)).strftime("%Y-%m-%d")


def test_incomplete_when_target_is_future_label():
    """주봉 W-FRI 라벨처럼 target_date 가 미래면 진행 중인 봉이다.

    월~목 스캔에서 주봉 라벨은 이번 주 금요일이 된다. 기존 구현은
    '오늘이 아님 → 확정' 규칙에 걸려 진행 중인 봉을 확정으로 오판했다.
    """
    tomorrow = _tomorrow_str()
    fetched = datetime.now(KST).replace(hour=15, minute=35, second=0).isoformat()
    assert is_today_bar_complete(tomorrow, fetched) is False


def test_future_label_incomplete_regardless_of_fetch_time():
    """미래 라벨은 수집 시각과 무관하게 항상 미완성이다."""
    tomorrow = _tomorrow_str()
    morning = datetime.now(KST).replace(hour=9, minute=5, second=0).isoformat()
    assert is_today_bar_complete(tomorrow, morning) is False
