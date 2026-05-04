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
    "tickers": {
        "006340": {
            "ticker": "006340",
            "name": "대원전선",
            "current_price": 17160,
            "change_pct": 15.42,
            "volume": 36582243,
            "market_cap_krw": 1344800000000,
            "fundamentals": {
                "per": 151.77,
                "high_52w": 18560,
                "low_52w": 3435,
            },
            "flow": {"foreign_ratio_pct": 5.51},
            "external_links": {
                "naver_finance": "https://finance.naver.com/item/main.naver?code=006340"
            },
            "rsi_by_tf": {"1D": 60.0, "1h": 50.0, "30m": 45.0},
        }
    },
}


@pytest.fixture
def signals_file(tmp_path: Path) -> Path:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps(SAMPLE_SIGNALS, ensure_ascii=False), encoding="utf-8")
    return p


def _make_entry(strategy_id: str, label: str, timeframe: str, score: float, rsi_14: float) -> dict:
    return {
        "ticker": "006340",
        "name": "대원전선",
        "name_en": None,
        "strategy": {
            "id": strategy_id, "label": label, "category": "MOMENTUM",
            "timeframe": timeframe, "description": None,
        },
        "trade_plan": {
            "entry": 17160, "stop": 16700, "target_1": 17500, "target_2": 17800,
            "rr_ratio": 2.0, "rr_band": "SWEET", "atr_14": 200, "rsi_14": rsi_14,
            "derived": None,
        },
        "ranking": {"score": score, "rank": 1, "percentile": 95.0},
        "live_quote": {
            "current_price": 17160, "change_pct": 0.0, "volume": 0,
            "market_cap_krw": None,
        },
        "fundamentals": {"per": None, "pbr": None, "eps": None,
                         "dividend_yield_pct": None, "high_52w": None, "low_52w": None},
        "flow": {"foreign_ratio_pct": None, "institutional_net_krw": None},
        "external_links": {"naver_finance": None},
    }


SAMPLE_SIGNALS_MULTI_TF = {
    **SAMPLE_SIGNALS,
    "signals": [
        _make_entry("strategy_one_d_v2",   "STRATEGY ONE", "1D", 80.0, 65.5),
        _make_entry("strategy_one_1h_v2",  "STRATEGY ONE", "1h", 90.0, 72.3),
        _make_entry("strategy_one_30m_v2", "STRATEGY ONE", "30m", 85.0, 58.1),
    ],
}


@pytest.fixture
def signals_multi_tf_file(tmp_path: Path) -> Path:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps(SAMPLE_SIGNALS_MULTI_TF, ensure_ascii=False), encoding="utf-8")
    return p


SAMPLE_SIGNALS_WITH_ALL = {
    **SAMPLE_SIGNALS,
    "signals": [
        _make_entry("strategy_one_d_v2", "STRATEGY ONE", "1D", 80.0, 65.5),
        _make_entry("strategy_two_cross_sectional_momentum",
                    "STRATEGY TWO", "1D", 70.0, 55.0),
        # 'all' 통합 entry (서버 dedup 결과)
        _make_entry("all", "ALL", "MULTI", 95.0, 60.0),
    ],
}


@pytest.fixture
def signals_with_all_file(tmp_path: Path) -> Path:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps(SAMPLE_SIGNALS_WITH_ALL, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def market_file(tmp_path: Path) -> Path:
    p = tmp_path / "market_snapshot.json"
    p.write_text(json.dumps(SAMPLE_MARKET, ensure_ascii=False), encoding="utf-8")
    return p
