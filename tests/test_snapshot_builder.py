# tests/test_snapshot_builder.py
from output.snapshot_builder import build_market_snapshot
from output.models import MarketSnapshot

MOCK_UNIVERSE = {
    "tickers": {
        "001390": {
            "name": "KG케미칼",
            "market_cap_bil": 4753,
            "per": 11.2, "pbr": 1.45, "eps": 593,
            "foreign_pct": 18.5,
            "naver_url": "https://finance.naver.com/item/main.naver?code=001390"
        }
    }
}

# 250일치 데이터 — tail(252) 로직 검증
MOCK_OHLCV = {
    "001390": {
        "close":   [7000] * 248 + [7050, 7120],
        "high":    [7200] * 248 + [7150, 7180],
        "low":     [5050] * 248 + [6980, 7050],
        "volume":  [2800000] * 248 + [2900000, 2847000],
        "change_pct": [0.0] * 248 + [0.71, 0.71],
    }
}


def test_build_market_snapshot_structure():
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=MOCK_OHLCV,
        market_indices={"kospi": {"value": 2641.32, "change_pct": 0.84}}
    )
    assert isinstance(snapshot, MarketSnapshot)
    assert "001390" in snapshot.tickers
    assert snapshot.tickers["001390"].current_price == 7120
    assert snapshot.tickers["001390"].fundamentals.per == 11.2


def test_build_market_snapshot_52w():
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=MOCK_OHLCV,
        market_indices={}
    )
    # tail(252) 범위에서 high max / low min
    assert snapshot.tickers["001390"].fundamentals.high_52w == 7200
    assert snapshot.tickers["001390"].fundamentals.low_52w == 5050
