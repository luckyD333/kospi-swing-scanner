"""Phase 1 Step 1: 응답 시점 동적 신선도 메타 (bars_since_trigger / price_drift_pct
/ plan_expired / scan_freshness_warning) 검증."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.join import (
    aggregate_entries_for_ticker,
    apply_snapshot_overlay,
    compute_freshness_meta,
    compute_scan_freshness_warning,
)

_KST = ZoneInfo("Asia/Seoul")


def test_freshness_meta_same_day_returns_zero_bars():
    now = datetime(2026, 5, 18, 14, 0, tzinfo=_KST)
    meta = compute_freshness_meta(
        signal_date_str="2026-05-18T09:30:00+09:00",
        current_price=8000.0,
        entry_price=7900.0,
        timeframe="1D",
        now=now,
    )
    assert meta["bars_since_trigger"] == 0
    assert meta["plan_expired"] is False
    assert meta["price_drift_pct"] == 1.2658  # (8000-7900)/7900*100


def test_freshness_meta_three_days_ago_marks_expired_true():
    """signal_date 후 3 거래일 경과 → STALE_THRESHOLD_1D(=1, audit 채택) 초과 → expired."""
    now = datetime(2026, 5, 18, 14, 0, tzinfo=_KST)
    meta = compute_freshness_meta(
        signal_date_str="2026-05-13T09:30:00+09:00",
        current_price=8750.0,
        entry_price=7900.0,
        timeframe="1D",
        now=now,
    )
    # 5/13~5/18 사이 거래일: 5/14, 5/15, 5/16(금) = 3 거래일
    assert meta["bars_since_trigger"] == 3
    assert meta["price_drift_pct"] == 10.7595  # (8750-7900)/7900*100 round 4
    # threshold=1, 3 > 1 → True
    assert meta["plan_expired"] is True


def test_freshness_meta_one_day_boundary_not_expired():
    """1 거래일 경과 = threshold 정확 일치 → 초과 아님 (boundary not expired)."""
    now = datetime(2026, 5, 18, 14, 0, tzinfo=_KST)
    meta = compute_freshness_meta(
        signal_date_str="2026-05-15T09:30:00+09:00",  # 1 거래일 전 (5/16 = 1)
        current_price=8000.0,
        entry_price=7900.0,
        timeframe="1D",
        now=now,
    )
    # 5/15~5/18: 5/16(금) = 1 거래일
    assert meta["bars_since_trigger"] == 1
    assert meta["plan_expired"] is False  # 1 > 1 False


def test_freshness_meta_hourly_timeframe_multiplies_bars():
    now = datetime(2026, 5, 18, 14, 0, tzinfo=_KST)
    meta = compute_freshness_meta(
        signal_date_str="2026-05-15T10:00:00+09:00",
        current_price=8000.0,
        entry_price=7900.0,
        timeframe="1h",
        now=now,
    )
    # 5/15~5/18: 5/16(금) = 1 거래일 → 1×6 = 6 bars
    assert meta["bars_since_trigger"] == 6
    # 1h threshold=2 → 6 > 2 → expired
    assert meta["plan_expired"] is True


def test_freshness_meta_handles_missing_current_price():
    now = datetime(2026, 5, 18, tzinfo=_KST)
    meta = compute_freshness_meta(
        signal_date_str="2026-05-18T09:30:00+09:00",
        current_price=None,
        entry_price=7900.0,
        timeframe="1D",
        now=now,
    )
    assert meta["price_drift_pct"] is None
    assert meta["bars_since_trigger"] == 0


def test_scan_freshness_warning_recent_returns_false():
    now = datetime(2026, 5, 18, 14, 0, tzinfo=_KST)
    assert compute_scan_freshness_warning("2026-05-18T13:00:00+09:00", now=now) is False
    # 1거래일 전 (5/16 금) → STALE 임계(3) 이하라 warning 없음
    assert compute_scan_freshness_warning("2026-05-16T13:00:00+09:00", now=now) is False


def test_scan_freshness_warning_old_scan_returns_true():
    now = datetime(2026, 5, 18, 14, 0, tzinfo=_KST)
    # 5/11~5/18 거래일 차 = 5/12,13,14,15,16 = 5 거래일 > 3 → True
    assert compute_scan_freshness_warning("2026-05-11T13:00:00+09:00", now=now) is True


def test_apply_snapshot_overlay_injects_signal_freshness():
    signal = {
        "ticker": "001740",
        "trade_plan": {"entry": 7900, "stop": 7700, "target_1": 8140},
        "live_quote": {"current_price": 7950},
        "signal_date": "2026-05-18T09:30:00+09:00",
        "strategy": {"timeframe": "1D"},
    }
    out = apply_snapshot_overlay(signal, None)
    assert "signal_freshness" in out
    fr = out["signal_freshness"]
    assert fr["bars_since_trigger"] is not None
    assert "price_drift_pct" in fr
    assert "plan_expired" in fr


def test_aggregate_entries_includes_scan_freshness_warning():
    entries = [
        {
            "ticker": "001740",
            "name": "SK네트웍스",
            "asset_class": "EQUITY",
            "strategy": {"id": "strategy_four_pullback_ma", "timeframe": "1D"},
            "trade_plan": {"entry": 7900, "stop": 7700, "target_1": 8140},
            "live_quote": {"current_price": 8750},
            "signal_date": "2026-05-15T13:30:00+09:00",
            "ranking": {"score": 67, "signal_strength": 74.6, "decision": {"final_score": 66.8}},
        },
    ]
    body = aggregate_entries_for_ticker(
        entries, "001740", None,
        generated_at="2026-05-11T13:28:35+09:00",  # 5 거래일 전
    )
    assert body["scan_freshness_warning"] is True
    assert "signal_freshness" in body
    # match 각각도 freshness 포함
    assert all("signal_freshness" in m for m in body["matches"])
