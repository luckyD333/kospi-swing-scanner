# tests/test_signals_builder.py
from unittest.mock import MagicMock
from output.signals_builder import build_signals_payload, _fmt_krw, _fmt_pct
from output.models import SignalsPayload, MarketSnapshot, TickerSnapshot, Fundamentals, Flow


def _make_snapshot():
    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-03T22:00:00+09:00",
        source={},
        market_indices={},
        tickers={"001390": TickerSnapshot(
            ticker="001390", name="KG케미칼",
            current_price=7120, change_pct=0.71, volume=2847000,
            market_cap_krw=475300000000,
            fundamentals=Fundamentals(per=11.2, high_52w=9120, low_52w=5050),
            flow=Flow(foreign_ratio_pct=18.5),
        )}
    )


def _make_candidate(rr_band_raw="sweet"):
    c = MagicMock()
    c.ticker = "001390"
    c.name = "KG케미칼"
    c.score = 87.0
    c.timeframe = "1D"
    c.entry_price = 7070
    c.stop_loss = 6820
    c.target_1 = 7580
    c.target_2 = 8100
    c.metadata = {
        "rr_ratio": 2.04,
        "rr_band": rr_band_raw,   # strategy 저장 값 (소문자)
        "atr_14": 183,
        "per": 11.2,
        "foreign_pct": 18.5,
        "naver_url": "https://finance.naver.com/item/main.naver?code=001390",
    }
    return c


def test_build_signals_payload_basic():
    snap = _make_snapshot()
    candidates = {"strategy_one_d_v2": [_make_candidate("sweet")]}
    payload = build_signals_payload(snap, candidates_by_strategy=candidates)
    assert isinstance(payload, SignalsPayload)
    assert len(payload.signals) == 1
    assert payload.signals[0].ticker == "001390"
    assert payload.stats["total_signals"] == 1


def test_rr_band_mapping():
    """strategy 소문자 → 모델 대문자 매핑 확인."""
    snap = _make_snapshot()
    for raw, expected in [("below", "UNDER"), ("sweet", "SWEET"), ("over", "OVER")]:
        payload = build_signals_payload(snap, {"strategy_one_d_v2": [_make_candidate(raw)]})
        assert payload.signals[0].trade_plan.rr_band == expected, f"raw={raw}"


def test_fmt_krw():
    assert _fmt_krw(475300000000) == "₩4,753억"
    assert _fmt_krw(1200000000000) == "₩1조 2,000억"


def test_fmt_pct():
    assert _fmt_pct(0.71, positive_prefix="+") == "+0.71%"
    assert _fmt_pct(-1.23, positive_prefix="+") == "-1.23%"
