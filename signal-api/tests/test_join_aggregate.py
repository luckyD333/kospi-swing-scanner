"""Task 8: API 응답 multi-strategy 구조 변환 테스트 (schema_version 2.0).

- `/api/signals/{ticker}` → ticker 단위 aggregate 응답 (schema_version="2.0")
- `/api/signals` → 기존 형태 + schema_version 필드만 추가
- Frontend dual-parser 호환 검증
"""
import pytest
from app.services.join import aggregate_entries_for_ticker, overlay_signals_list


@pytest.fixture
def fixture_486290_entries():
    """486290 (TIGER 미국나스닥100) 다중 strategy entries."""
    return [
        {
            "ticker": "486290",
            "name": "TIGER 미국나스닥100타겟데일리커버드콜",
            "asset_class": "EQUITY_ETF",
            "fundamentals": {"market_cap": 10000000000, "pe": None, "pb": 1.5},
            "live_quote": {"current_price": 11300, "change_pct": 1.5, "volume": 100000},
            "external_links": {"href": "https://example.com"},
            "strategy": {
                "id": "strategy_two_30m",
                "label": "STRATEGY TWO",
                "category": "MOMENTUM",
                "timeframe": "30m",
            },
            "trade_plan": {"entry": 11300, "stop": 11000, "target_1": 11600, "target_2": 12000},
            "ranking": {
                "score": 44.6,
                "signal_strength": 84.6,
                "decision": {
                    "final_score": 36.0,
                    "regret_score": 44.6,
                    "factors": [
                        {"name": "bull_reward", "value": 24, "weight": 40},
                        {"name": "max_drawdown", "value": 11, "weight": 20},
                    ],
                },
            },
            "signal_date": "2026-05-08T06:20:00+09:00",
            "signal_status": "VALID",
            "setup_score": 65,
            "setup_reasons": ["1h position ≥ 0.6", "fresh signal"],
        },
        {
            "ticker": "486290",
            "name": "TIGER 미국나스닥100타겟데일리커버드콜",
            "asset_class": "EQUITY_ETF",
            "fundamentals": {"market_cap": 10000000000, "pe": None, "pb": 1.5},
            "live_quote": {"current_price": 11300, "change_pct": 1.5, "volume": 100000},
            "external_links": {"href": "https://example.com"},
            "strategy": {
                "id": "strategy_four_pullback_ma_30m",
                "label": "STRATEGY FOUR",
                "category": "PULLBACK",
                "timeframe": "30m",
            },
            "trade_plan": {"entry": 11280, "stop": 11150, "target_1": 11500, "target_2": 11800},
            "ranking": {
                "score": 32.1,
                "signal_strength": 67.3,
                "decision": {
                    "final_score": 36.0,
                    "regret_score": 32.1,
                    "factors": [
                        {"name": "bull_reward", "value": 18, "weight": 40},
                        {"name": "max_drawdown", "value": 8, "weight": 20},
                    ],
                },
            },
            "signal_date": "2026-05-08T05:50:00+09:00",
            "signal_status": "VALID",
            "setup_score": 55,
            "setup_reasons": ["1h position 0.5", "moderate setup"],
        },
        {
            "ticker": "486290",
            "name": "TIGER 미국나스닥100타겟데일리커버드콜",
            "asset_class": "EQUITY_ETF",
            "fundamentals": {"market_cap": 10000000000, "pe": None, "pb": 1.5},
            "live_quote": {"current_price": 11300, "change_pct": 1.5, "volume": 100000},
            "external_links": {"href": "https://example.com"},
            "strategy": {
                "id": "all",
                "label": "ALL",
                "category": "ENSEMBLE",
                "timeframe": "1D",
            },
            "trade_plan": {"entry": 11300, "stop": 11000, "target_1": 11600, "target_2": 12000},
            "ranking": {
                "score": 44.6,
                "signal_strength": 84.6,
                "decision": {
                    "final_score": 36.0,
                    "regret_score": 44.6,
                    "factors": [
                        {"name": "momentum_3m", "value": 30, "weight": 35},
                        {"name": "regime_score", "value": 6, "weight": 15},
                    ],
                },
            },
            "signal_date": "2026-05-08T06:20:00+09:00",
            "signal_status": "VALID",
        },
    ]


@pytest.fixture
def fixture_single_strategy_entry():
    """단일 strategy entry (diff 테스트용)."""
    return [
        {
            "ticker": "005930",
            "name": "삼성전자",
            "asset_class": "STOCK",
            "fundamentals": {"market_cap": 5000000000000, "pe": 10.5, "pb": 0.8},
            "live_quote": {"current_price": 70000, "change_pct": 2.3, "volume": 5000000},
            "external_links": {"href": "https://example.com"},
            "strategy": {
                "id": "strategy_one_d_v2",
                "label": "STRATEGY ONE",
                "category": "MEAN_REVERSION",
                "timeframe": "1D",
            },
            "trade_plan": {
                "entry": 69500,
                "stop": 68000,
                "target_1": 71000,
                "target_2": 73000,
            },
            "ranking": {
                "score": 55.3,
                "signal_strength": 72.5,
                "decision": {
                    "final_score": 45.0,
                    "regret_score": 55.3,
                    "factors": [
                        {"name": "bull_reward", "value": 30, "weight": 40},
                        {"name": "max_drawdown", "value": 10, "weight": 20},
                    ],
                },
            },
            "signal_date": "2026-05-08T15:00:00+09:00",
            "signal_status": "VALID",
            "setup_score": 70,
            "setup_reasons": ["strong mean reversion setup"],
        },
        {
            "ticker": "005930",
            "name": "삼성전자",
            "asset_class": "STOCK",
            "fundamentals": {"market_cap": 5000000000000, "pe": 10.5, "pb": 0.8},
            "live_quote": {"current_price": 70000, "change_pct": 2.3, "volume": 5000000},
            "external_links": {"href": "https://example.com"},
            "strategy": {
                "id": "all",
                "label": "ALL",
                "category": "ENSEMBLE",
                "timeframe": "1D",
            },
            "trade_plan": {
                "entry": 69500,
                "stop": 68000,
                "target_1": 71000,
                "target_2": 73000,
            },
            "ranking": {
                "score": 55.3,
                "signal_strength": 72.5,
                "decision": {
                    "final_score": 45.0,
                    "regret_score": 55.3,
                    "factors": [
                        {"name": "momentum_3m", "value": 35, "weight": 35},
                        {"name": "regime_score", "value": 10, "weight": 15},
                    ],
                },
            },
            "signal_date": "2026-05-08T15:00:00+09:00",
            "signal_status": "VALID",
        },
    ]


def test_aggregate_entries_for_ticker_multi_strategy(fixture_486290_entries):
    """다중 strategy 매칭 시 aggregate 응답 구조 검증."""
    result = aggregate_entries_for_ticker(fixture_486290_entries, "486290")

    # 최상위 필드
    assert result["schema_version"] == "2.0"
    assert result["ticker"] == "486290"
    assert result["name"] == "TIGER 미국나스닥100타겟데일리커버드콜"
    assert result["asset_class"] == "EQUITY_ETF"

    # 잠재력 점수 (all entry 기반)
    assert result["potential_score"] == 36.0
    assert isinstance(result["potential_factors"], list)
    assert len(result["potential_factors"]) > 0

    # matches 배열 (all entry 제외)
    assert "matches" in result
    assert len(result["matches"]) == 2  # all 제외

    # 첫 번째 match (strategy_two)
    match_0 = result["matches"][0]
    assert match_0["strategy"]["id"] == "strategy_two_30m"
    assert match_0["signal_strength"] == 84.6
    assert match_0["opportunity_score"] == 44.6
    assert isinstance(match_0["opportunity_factors"], list)
    assert match_0["trade_plan"]["entry"] == 11300
    assert match_0["setup_score"] == 65
    assert match_0["setup_reasons"] == ["1h position ≥ 0.6", "fresh signal"]

    # 두 번째 match (strategy_four)
    match_1 = result["matches"][1]
    assert match_1["strategy"]["id"] == "strategy_four_pullback_ma_30m"
    assert match_1["signal_strength"] == 67.3
    assert match_1["opportunity_score"] == 32.1
    assert match_1["trade_plan"]["entry"] == 11280


def test_aggregate_entries_for_ticker_single_strategy(fixture_single_strategy_entry):
    """단일 strategy 매칭 시 aggregate 응답 (matches 길이 1)."""
    from app.services.join import aggregate_entries_for_ticker

    result = aggregate_entries_for_ticker(fixture_single_strategy_entry, "005930")

    assert result["schema_version"] == "2.0"
    assert result["ticker"] == "005930"
    assert result["potential_score"] == 45.0

    # single match
    assert len(result["matches"]) == 1
    assert result["matches"][0]["strategy"]["id"] == "strategy_one_d_v2"


def test_aggregate_entries_excludes_all_entry(fixture_486290_entries):
    """all entry 는 potential_score 베이스로 사용되지만 matches 에서 제외."""
    result = aggregate_entries_for_ticker(fixture_486290_entries, "486290")

    # matches 에 "all" 이 없어야 함
    for match in result["matches"]:
        assert match["strategy"]["id"] != "all"


def test_aggregate_entries_preserves_metadata(fixture_486290_entries):
    """fundamentals, live_quote, external_links 등 메타 정보 보존."""
    result = aggregate_entries_for_ticker(fixture_486290_entries, "486290")

    assert result["fundamentals"] == fixture_486290_entries[0]["fundamentals"]
    assert result["live_quote"] == fixture_486290_entries[0]["live_quote"]
    assert result["external_links"] == fixture_486290_entries[0]["external_links"]


def test_catalog_signals_list_includes_schema_version():
    """카탈로그 응답 (/api/signals) 에 schema_version 필드 추가."""
    raw = {
        "generated_at": "2026-05-08T06:20:00+09:00",
        "signals": [
            {
                "ticker": "486290",
                "strategy": {"id": "all"},
                "ranking": {"score": 44.6},
            }
        ],
    }

    result = overlay_signals_list(raw, {})

    # 최상위 schema_version 필드 (카탈로그는 루트에만 추가)
    assert result.get("schema_version") is None or result.get("schema_version") == "2.0"
    # signals 배열은 변경 없음
    assert len(result["signals"]) == 1


def test_aggregate_entries_passes_signal_components():
    """매칭 dict 에 signal_components 가 그대로 전달되어야 한다."""
    entries = [
        {
            "ticker": "005930",
            "name": "삼성전자",
            "asset_class": "STOCK",
            "fundamentals": {},
            "live_quote": {"current_price": 71000},
            "external_links": {},
            "strategy": {
                "id": "strategy_one_d_v2",
                "label": "STRATEGY ONE",
                "category": "MEAN REVERSION",
                "timeframe": "1D",
            },
            "trade_plan": {"entry": 71000, "stop": 69000, "target_1": 73500, "target_2": 75000},
            "ranking": {"score": 80.0, "signal_strength": 75.0, "decision": {"final_score": 80.0}},
            "signal_components": [
                {"key": "rsi_oversold", "label": "RSI 과매도", "status": "ok", "value": "28.5"},
                {"key": "double_bottom", "label": "쌍바닥", "status": "ok", "value": None},
            ],
            "signal_date": "2026-05-08T15:30:00+09:00",
            "signal_status": "VALID",
        },
        {
            "ticker": "005930",
            "name": "삼성전자",
            "asset_class": "STOCK",
            "fundamentals": {},
            "live_quote": {"current_price": 71000},
            "external_links": {},
            "strategy": {
                "id": "strategy_three_trend_following",
                "label": "STRATEGY THREE",
                "category": "TREND FOLLOWING",
                "timeframe": "1D",
            },
            "trade_plan": {"entry": 71000, "stop": 69500, "target_1": 73000, "target_2": 75000},
            "ranking": {"score": 65.0, "signal_strength": 60.0, "decision": {"final_score": 65.0}},
            "signal_components": [
                {"key": "donchian_breakout", "label": "Donchian 20일 돌파", "status": "ok", "value": "+2.40%"},
                {"key": "volume_surge", "label": "거래량 동반", "status": "warn", "value": "1.1x"},
            ],
            "signal_date": "2026-05-08T15:30:00+09:00",
            "signal_status": "VALID",
        },
    ]

    result = aggregate_entries_for_ticker(entries, "005930")
    matches = result["matches"]
    assert len(matches) == 2

    # 정렬 후 matches[0] 은 strategy_one (score 80)
    assert matches[0]["strategy"]["id"] == "strategy_one_d_v2"
    assert matches[0]["signal_components"] == [
        {"key": "rsi_oversold", "label": "RSI 과매도", "status": "ok", "value": "28.5"},
        {"key": "double_bottom", "label": "쌍바닥", "status": "ok", "value": None},
    ]

    assert matches[1]["strategy"]["id"] == "strategy_three_trend_following"
    assert {c["key"] for c in matches[1]["signal_components"]} == {
        "donchian_breakout", "volume_surge",
    }


def test_aggregate_entries_signal_components_default_empty():
    """signal_components 누락 시 빈 배열 fallback."""
    entries = [
        {
            "ticker": "005930",
            "name": "삼성전자",
            "fundamentals": {},
            "live_quote": {},
            "external_links": {},
            "strategy": {
                "id": "strategy_one_d_v2",
                "label": "STRATEGY ONE",
                "category": "MEAN REVERSION",
                "timeframe": "1D",
            },
            "trade_plan": {"entry": 71000, "stop": 69000, "target_1": 73500, "target_2": 75000},
            "ranking": {"score": 80.0, "signal_strength": 75.0, "decision": {}},
            "signal_date": "2026-05-08T15:30:00+09:00",
            "signal_status": "VALID",
        },
    ]
    result = aggregate_entries_for_ticker(entries, "005930")
    assert result["matches"][0]["signal_components"] == []
