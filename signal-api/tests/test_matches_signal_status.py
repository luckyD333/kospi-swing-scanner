"""matches[] 응답에 strategy 별 signal_status 가 동적 계산되어 들어간다.

161890 (한국콜마) 운영 케이스 회귀:
- strategy_two_1h: entry=93600, target_1=96400, current=93600 → VALID
- strategy_four_pullback_ma: entry=88200, target_1=90800, current=93600 → TARGET_REACHED
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.join import aggregate_entries_for_ticker

KST = ZoneInfo("Asia/Seoul")


def _recent_iso(minutes_ago: int = 15) -> str:
    """현재 시각의 N 분 전 KST ISO. 1h timeframe 의 stale 가드 (2h) 회피용."""
    return (datetime.now(KST) - timedelta(minutes=minutes_ago)).isoformat()


def _entry(strategy_id: str, timeframe: str, score: float, entry: int,
           stop: int, target_1: int, signal_date_iso: str) -> dict:
    return {
        "ticker": "161890",
        "name": "한국콜마",
        "strategy": {
            "id": strategy_id,
            "label": "STRATEGY",
            "category": "MOMENTUM",
            "timeframe": timeframe,
        },
        "trade_plan": {"entry": entry, "stop": stop, "target_1": target_1, "target_2": entry * 1.05, "rr_ratio": 2.0, "rr_band": "SWEET"},
        "ranking": {"score": score, "rank": 1, "percentile": 80.0, "signal_strength": 70.0},
        "live_quote": {"current_price": entry, "change_pct": 0.0, "volume": 100_000},
        "fundamentals": {},
        "flow": {},
        "external_links": {},
        "signal_date": signal_date_iso,
    }


def test_matches_signal_status_keys_present():
    """matches[] 모두 signal_status 키 존재."""
    today_iso = _recent_iso(15)
    entries = [
        _entry("strategy_two_1h", "1h", 800.0, 93600, 90000, 96400, today_iso),
        _entry("strategy_four_pullback_ma", "1D", 700.0, 88200, 86000, 90800, today_iso),
    ]
    snapshot_ticker = {"current_price": 93600, "change_pct": 7.71, "volume": 671390}

    result = aggregate_entries_for_ticker(entries, "161890", snapshot_ticker)

    assert "matches" in result
    assert len(result["matches"]) == 2
    for m in result["matches"]:
        assert "signal_status" in m
        assert m["signal_status"] is not None


def test_matches_signal_status_target_reached():
    """strategy_four (entry=88200, target_1=90800) + current=93600 → TARGET_REACHED."""
    today_iso = _recent_iso(15)
    entries = [
        _entry("strategy_two_1h", "1h", 800.0, 93600, 90000, 96400, today_iso),
        _entry("strategy_four_pullback_ma", "1D", 700.0, 88200, 86000, 90800, today_iso),
    ]
    snapshot_ticker = {"current_price": 93600, "change_pct": 7.71, "volume": 671390}

    result = aggregate_entries_for_ticker(entries, "161890", snapshot_ticker)

    statuses = {m["strategy"]["id"]: m["signal_status"] for m in result["matches"]}
    assert statuses["strategy_two_1h"] == "VALID", \
        f"strategy_two_1h (current=entry, target 미달성) 은 VALID 여야 함. got {statuses}"
    assert statuses["strategy_four_pullback_ma"] == "TARGET_REACHED", \
        f"strategy_four (current >> target_1) 은 TARGET_REACHED 여야 함. got {statuses}"


def test_matches_signal_status_stopped_out():
    """current=85000 < stop=86000 → STOPPED_OUT."""
    today_iso = _recent_iso(15)
    entries = [
        _entry("strategy_four_pullback_ma", "1D", 700.0, 88200, 86000, 90800, today_iso),
    ]
    snapshot_ticker = {"current_price": 85000, "change_pct": -3.0, "volume": 100_000}

    result = aggregate_entries_for_ticker(entries, "161890", snapshot_ticker)

    assert result["matches"][0]["signal_status"] == "STOPPED_OUT"
