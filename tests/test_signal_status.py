"""tests/test_signal_status.py — compute_signal_status 단위 테스트."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# signal-api 모듈을 import 가능하게
_SIGNAL_API = Path(__file__).resolve().parent.parent / "signal-api"
sys.path.insert(0, str(_SIGNAL_API))

from app.services.join import compute_signal_status  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


def _now(d: str = "2026-05-11T10:00:00+09:00") -> datetime:
    """2026-05-11 = 월요일 (정상 거래일)."""
    return datetime.fromisoformat(d)


def test_status_valid_normal():
    status = compute_signal_status(
        current_price=1000,
        stop=975,
        target_1=1030,
        signal_date_str="2026-05-11T16:00:00+09:00",
        now=_now(),
    )
    assert status == "VALID"


def test_status_stopped_out():
    status = compute_signal_status(
        current_price=970,  # ≤ stop
        stop=975,
        target_1=1030,
        signal_date_str="2026-05-11T16:00:00+09:00",
        now=_now(),
    )
    assert status == "STOPPED_OUT"


def test_status_target_reached():
    status = compute_signal_status(
        current_price=1035,  # ≥ target_1
        stop=975,
        target_1=1030,
        signal_date_str="2026-05-11T16:00:00+09:00",
        now=_now(),
    )
    assert status == "TARGET_REACHED"


def test_status_stale_old_signal():
    # signal_date 가 5거래일 전: 2026-05-04(월) → 2026-05-11(월) 사이
    # 5/5 어린이날 제외하면 4거래일이지만, 주말 포함 5거래일 (월화수목금)
    # 정확히 4거래일 경과는 STALE 임계값(>3) 초과
    status = compute_signal_status(
        current_price=1000,
        stop=975,
        target_1=1030,
        signal_date_str="2026-05-04T16:00:00+09:00",
        now=_now(),
    )
    assert status == "STALE"


def test_status_other_trading_day_returns_valid():
    # signal_date 가 1거래일 전 (오늘 ≠ signal_date 이지만 STALE 아님)
    # current_price 가 stop 이하라도 비교 스킵 → VALID 유지
    status = compute_signal_status(
        current_price=970,  # 같은 날이면 STOPPED_OUT 일 가격
        stop=975,
        target_1=1030,
        signal_date_str="2026-05-08T16:00:00+09:00",  # 금요일
        now=_now(),
    )
    assert status == "VALID"


def test_status_invalid_signal_date_format():
    status = compute_signal_status(
        current_price=1000,
        stop=975,
        target_1=1030,
        signal_date_str="not-a-date",
        now=_now(),
    )
    assert status == "STALE"


def test_status_no_signal_date_uses_today_compare():
    # signal_date_str 없으면 직접 가격 비교
    status = compute_signal_status(
        current_price=970,
        stop=975,
        target_1=1030,
        signal_date_str=None,
        now=_now(),
    )
    assert status == "STOPPED_OUT"


def test_status_priority_stopped_out_over_target_reached():
    # cp 가 stop 이하이면서 target_1 이상이면 (이론적으로 불가하지만)
    # STOPPED_OUT 우선
    status = compute_signal_status(
        current_price=970,
        stop=1000,  # cp <= stop
        target_1=900,  # cp >= target_1 도 만족
        signal_date_str="2026-05-11T16:00:00+09:00",
        now=_now(),
    )
    assert status == "STOPPED_OUT"
