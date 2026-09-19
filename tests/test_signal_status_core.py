"""core/decision/signal_status.compute_signal_status 단위 테스트."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.decision.signal_status import compute_signal_status

KST = ZoneInfo("Asia/Seoul")


def _today_iso(hour: int = 14, minute: int = 0) -> str:
    return datetime.now(KST).replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def _days_ago_iso(days: int) -> str:
    return (datetime.now(KST) - timedelta(days=days)).replace(hour=14, minute=0, second=0, microsecond=0).isoformat()


def test_valid_when_cp_between_stop_and_target():
    status = compute_signal_status(
        current_price=10000, stop=9500, target_1=10500,
        signal_date_str=_today_iso(), timeframe="1D",
    )
    assert status == "VALID"


def test_target_reached_when_cp_above_target():
    status = compute_signal_status(
        current_price=10500, stop=9500, target_1=10400,
        signal_date_str=_today_iso(), timeframe="1D",
    )
    assert status == "TARGET_REACHED"


def test_stopped_out_when_cp_below_stop():
    status = compute_signal_status(
        current_price=9400, stop=9500, target_1=10500,
        signal_date_str=_today_iso(), timeframe="1D",
    )
    assert status == "STOPPED_OUT"


def test_stale_when_signal_date_more_than_3_trading_days_ago():
    status = compute_signal_status(
        current_price=10000, stop=9500, target_1=10500,
        signal_date_str=_days_ago_iso(10),  # 10 일 전 → > 3 거래일
        timeframe="1D",
    )
    assert status == "STALE"


def test_stale_when_1h_signal_older_than_2h():
    fetched = (datetime.now(KST) - timedelta(hours=3)).isoformat()
    status = compute_signal_status(
        current_price=10000, stop=9500, target_1=10500,
        signal_date_str=fetched, timeframe="1h",
    )
    assert status == "STALE"


def test_weekly_signal_valid_within_one_week():
    """주봉 신호는 5거래일까지 유효하다. 1D 임계(1거래일)를 쓰면 안 된다."""
    now = datetime(2026, 5, 20, 14, 0, tzinfo=KST)   # 수요일, 신호일로부터 3거래일
    status = compute_signal_status(
        current_price=8000.0, stop=7000.0, target_1=9000.0,
        signal_date_str="2026-05-15T15:30:00+09:00",  # 직전 금요일
        now=now, timeframe="1W",
    )
    assert status == "VALID"


def test_weekly_signal_stale_after_one_week():
    """5거래일을 넘으면 주봉 신호도 STALE 이다."""
    now = datetime(2026, 5, 26, 14, 0, tzinfo=KST)   # 6거래일 경과
    status = compute_signal_status(
        current_price=8000.0, stop=7000.0, target_1=9000.0,
        signal_date_str="2026-05-15T15:30:00+09:00",
        now=now, timeframe="1W",
    )
    assert status == "STALE"
