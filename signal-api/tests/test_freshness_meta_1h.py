"""1h 신호의 plan_expired 는 signal_status 의 STALE 판정과 일치해야 한다."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.join import compute_freshness_meta
from core.decision.signal_status import compute_signal_status

KST = ZoneInfo("Asia/Seoul")


def test_같은_거래일_3시간_전_1h_신호는_만료다():
    """거래일이 안 바뀌어도 2시간을 넘기면 만료다."""
    now = datetime(2026, 5, 15, 14, 0, tzinfo=KST)      # 금요일 장중
    signal_date = "2026-05-15T11:00:00+09:00"           # 같은 날 3시간 전

    meta = compute_freshness_meta(
        signal_date_str=signal_date, current_price=10000.0,
        entry_price=10000.0, timeframe="1h", now=now,
    )

    assert meta["plan_expired"] is True
    assert meta["bars_since_trigger"] == 3


def test_같은_거래일_30분_전_1h_신호는_유효하다():
    now = datetime(2026, 5, 15, 14, 0, tzinfo=KST)
    signal_date = "2026-05-15T13:30:00+09:00"

    meta = compute_freshness_meta(
        signal_date_str=signal_date, current_price=10000.0,
        entry_price=10000.0, timeframe="1h", now=now,
    )

    assert meta["plan_expired"] is False


def test_1h_판정이_signal_status_와_어긋나지_않는다():
    """같은 입력에 대해 plan_expired 와 STALE 이 같은 방향이어야 한다."""
    now = datetime(2026, 5, 16, 11, 0, tzinfo=KST)      # 토요일
    signal_date = "2026-05-15T14:00:00+09:00"           # 금요일 1h 신호

    meta = compute_freshness_meta(
        signal_date_str=signal_date, current_price=10000.0,
        entry_price=10000.0, timeframe="1h", now=now,
    )
    status = compute_signal_status(
        current_price=10000.0, stop=9500.0, target_1=10500.0,
        signal_date_str=signal_date, now=now, timeframe="1h",
    )

    assert meta["plan_expired"] is True
    assert status == "STALE"


def test_신호_시각이_미래여도_봉_수가_음수가_되지_않는다():
    """Review Focus 2 — 시계 어긋남으로 미래 시각이 들어와도 UI 가 깨지지 않게 한다."""
    now = datetime(2026, 5, 15, 11, 0, tzinfo=KST)
    signal_date = "2026-05-15T14:00:00+09:00"      # 3시간 뒤

    meta = compute_freshness_meta(
        signal_date_str=signal_date, current_price=10000.0,
        entry_price=10000.0, timeframe="1h", now=now,
    )

    assert meta["bars_since_trigger"] == 0
    assert meta["plan_expired"] is False


def test_임계_직후_2시간_30분도_만료다():
    """내림을 쓰면 2.5시간이 2봉이 되어 `2 > 2` 가 거짓이 된다. 이 구간을 못 박는다."""
    now = datetime(2026, 5, 15, 13, 30, tzinfo=KST)
    signal_date = "2026-05-15T11:00:00+09:00"      # 2시간 30분 전

    meta = compute_freshness_meta(
        signal_date_str=signal_date, current_price=10000.0,
        entry_price=10000.0, timeframe="1h", now=now,
    )
    status = compute_signal_status(
        current_price=10000.0, stop=9500.0, target_1=10500.0,
        signal_date_str=signal_date, now=now, timeframe="1h",
    )

    assert meta["plan_expired"] is True
    assert status == "STALE"
