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
