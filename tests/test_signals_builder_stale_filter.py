"""signals_builder.build_signals_payload 가 stale 신호를 산출 단에서 제외한다."""
from unittest.mock import MagicMock

from output.signals_builder import build_signals_payload
from output.models import MarketSnapshot, TickerSnapshot, Fundamentals, Flow


def _snap_with_cp(current_price: int) -> MarketSnapshot:
    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-08T17:00:00+09:00",
        source={},
        market_indices={},
        tickers={"001390": TickerSnapshot(
            ticker="001390", name="KG케미칼",
            current_price=current_price, change_pct=0.0, volume=1_000_000,
            market_cap_krw=475_300_000_000,
            fundamentals=Fundamentals(per=11.2),
            flow=Flow(foreign_ratio_pct=18.5),
        )}
    )


def _candidate(entry: int = 7070, stop: int = 6820, target_1: int = 7580, target_2: int = 8100):
    c = MagicMock()
    c.ticker = "001390"
    c.name = "KG케미칼"
    c.score = 87.0
    c.timeframe = "1D"
    c.entry_price = entry
    c.stop_loss = stop
    c.target_1 = target_1
    c.target_2 = target_2
    c.signal_date = None
    c.limit_entry = None  # MagicMock auto-attr 회피 (None 명시)
    c.limit_stop = None
    c.metadata = {
        "rr_ratio": 2.04,
        "rr_band": "sweet",
        "atr_14": 183,
        "naver_url": "",
    }
    return c


def test_signals_builder_drops_target_reached():
    """current_price >= target_1 → signals.json 에서 제외."""
    snap = _snap_with_cp(current_price=7600)  # > target_1=7580
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [_candidate()]})
    assert payload.signals == [], \
        f"TARGET_REACHED candidate 가 signals 에 포함됨: {[s.ticker for s in payload.signals]}"


def test_signals_builder_drops_stopped_out():
    """current_price <= stop → signals.json 에서 제외."""
    snap = _snap_with_cp(current_price=6800)  # < stop=6820
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [_candidate()]})
    assert payload.signals == [], \
        f"STOPPED_OUT candidate 가 signals 에 포함됨: {[s.ticker for s in payload.signals]}"


def test_signals_builder_keeps_valid():
    """stop < current_price < target_1 → 포함."""
    snap = _snap_with_cp(current_price=7200)  # 6820 < 7200 < 7580
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [_candidate()]})
    assert len(payload.signals) == 1
    assert payload.signals[0].ticker == "001390"
