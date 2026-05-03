import json
from pathlib import Path
import pytest


SAMPLE_SIGNALS = {
    "schema_version": "1.0",
    "generated_at": "2026-05-03T18:16:11.375020+09:00",
    "generated_at_display": "2026-05-03 18:16 KST",
    "market_indices": {
        "kospi": {
            "label": "코스피",
            "value_display": "6,598.87",
            "change_display": "-1.38%",
            "direction": "down",
        }
    },
    "filters": {
        "strategies": ["ALL", "STRATEGY TWO"],
        "timeframes": ["ALL", "1D"],
        "sort_options": ["score"],
    },
    "signals": [
        {
            "ticker": "006340",
            "name": "대원전선",
            "name_en": None,
            "strategy": {
                "id": "strategy_two_cross_sectional_momentum",
                "label": "STRATEGY TWO",
                "category": "MOMENTUM",
                "timeframe": "1D",
                "description": None,
            },
            "trade_plan": {
                "entry": 15050,
                "stop": 14673,
                "target_1": 15501,
                "target_2": 15802,
                "rr_ratio": 2.0,
                "rr_band": "SWEET",
                "atr_14": 1173,
                "derived": {
                    "risk_per_share": 377,
                    "risk_pct": 2.5,
                    "reward_1_pct": 3.0,
                    "reward_2_pct": 5.0,
                },
            },
            "ranking": {"score": 1000.0, "rank": 1, "percentile": 97.5},
            "live_quote": {
                "current_price": 15050,
                "change_pct": 0.0,
                "volume": 0,
                "market_cap_krw": None,
            },
            "fundamentals": {
                "per": None,
                "pbr": None,
                "eps": None,
                "dividend_yield_pct": None,
                "high_52w": None,
                "low_52w": None,
            },
            "flow": {"foreign_ratio_pct": None, "institutional_net_krw": None},
            "external_links": {
                "naver_finance": "https://finance.naver.com/item/main.naver?code=006340"
            },
        }
    ],
    "stats": {"total_signals": 1, "by_strategy": {"STRATEGY TWO": 1}, "by_rr_band": {"SWEET": 1}},
}

SAMPLE_MARKET = {
    "schema_version": "1.0",
    "generated_at": "2026-05-03T18:29:41.187459+09:00",
    "source": {"collected_at": "2026-05-03T18:29:41.187459+09:00"},
    "market_indices": {
        "kospi": {"value": 6598.87, "change_pct": -1.38},
        "kosdaq": {"value": 1192.35, "change_pct": -2.29},
    },
    "tickers": {},
}


@pytest.fixture
def signals_file(tmp_path: Path) -> Path:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps(SAMPLE_SIGNALS, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def market_file(tmp_path: Path) -> Path:
    p = tmp_path / "market_snapshot.json"
    p.write_text(json.dumps(SAMPLE_MARKET, ensure_ascii=False), encoding="utf-8")
    return p
