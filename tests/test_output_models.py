# tests/test_output_models.py
from output.models import (
    MarketSnapshot, TickerSnapshot, Fundamentals, Flow,
    SignalsPayload, TradePlan,
)


def test_trade_plan_derived_computed():
    plan = TradePlan(
        entry=7070, stop=6820, target_1=7580, target_2=8100,
        rr_ratio=2.04, rr_band="SWEET", atr_14=183
    )
    assert plan.derived.risk_per_share == 250
    assert abs(plan.derived.risk_pct - 3.54) < 0.01
    assert abs(plan.derived.reward_1_pct - 7.21) < 0.01


def test_signals_payload_model_dump_has_display_alias():
    """by_alias=True 시 _display 키가 JSON에 나타나야 함."""
    payload = SignalsPayload(
        schema_version="1.0",
        generated_at="2026-05-03T22:15:00+09:00",
        generated_at_display="2026-05-03 22:15 KST",
        market_indices={},
        filters={"strategies": ["ALL"], "timeframes": ["ALL"], "sort_options": ["score"]},
        signals=[],
        stats={"total_signals": 0, "by_strategy": {}, "by_rr_band": {}}
    )
    data = payload.model_dump_json(by_alias=True)
    assert '"schema_version"' in data
    assert '"signals"' in data


def test_signals_payload_freshness_fields_default_empty():
    """target_date/target_date_display/asof 미지정 시 빈 문자열 default."""
    payload = SignalsPayload(
        schema_version="1.0",
        generated_at="2026-05-04T12:30:00+09:00",
        generated_at_display="2026-05-04 12:30 KST",
        market_indices={},
        filters={"strategies": ["ALL"], "timeframes": ["ALL"], "sort_options": ["score"]},
        signals=[],
        stats={"total_signals": 0, "by_strategy": {}, "by_rr_band": {}},
    )
    assert payload.target_date == ""
    assert payload.target_date_display == ""
    assert payload.asof == ""


def test_signals_payload_freshness_fields_persist():
    """target_date/target_date_display/asof 가 model_dump 에 포함."""
    payload = SignalsPayload(
        schema_version="1.0",
        generated_at="2026-05-04T12:30:00+09:00",
        generated_at_display="2026-05-04 12:30 KST",
        target_date="2026-05-04",
        target_date_display="2026-05-04 (장중)",
        asof="2026-05-04T12:30:00+09:00",
        market_indices={},
        filters={"strategies": ["ALL"], "timeframes": ["ALL"], "sort_options": ["score"]},
        signals=[],
        stats={"total_signals": 0, "by_strategy": {}, "by_rr_band": {}},
    )
    data = payload.model_dump()
    assert data["target_date"] == "2026-05-04"
    assert data["target_date_display"] == "2026-05-04 (장중)"
    assert data["asof"] == "2026-05-04T12:30:00+09:00"


def test_market_snapshot_ticker_lookup():
    snap = MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-03T22:00:00+09:00",
        source={},
        market_indices={},
        tickers={"001390": TickerSnapshot(
            ticker="001390", name="KG케미칼",
            current_price=7120, change_pct=0.71, volume=2847000,
            market_cap_krw=475300000000,
            fundamentals=Fundamentals(per=11.2, pbr=1.45, eps=593,
                                      dividend_yield_pct=2.3,
                                      high_52w=9120, low_52w=5050),
            flow=Flow(foreign_ratio_pct=18.5, institutional_net_krw=None),
            price_history_atr14=183,
            external_links={"naver_finance": "https://finance.naver.com/item/main.naver?code=001390"}
        )}
    )
    assert snap.tickers["001390"].name == "KG케미칼"
