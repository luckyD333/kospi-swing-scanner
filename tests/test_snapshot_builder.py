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


def test_build_market_snapshot_uses_minute_close_when_available():
    """1m 분봉 close 가 있으면 current_price 는 그 값 (= 더 신선)."""
    ohlcv = {
        "001390": {
            **MOCK_OHLCV["001390"],
            "minute_close": 7185.0,
            "minute_close_at": "2026-05-04T12:30:00+09:00",
        }
    }
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=ohlcv,
        market_indices={},
    )
    # 일봉 close 7120 대신 분봉 close 7185 사용
    assert snapshot.tickers["001390"].current_price == 7185


def test_build_market_snapshot_falls_back_to_daily_close():
    """1m 분봉 close 없으면 일봉 마지막 close fallback."""
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=MOCK_OHLCV,
        market_indices={},
    )
    assert snapshot.tickers["001390"].current_price == 7120


def test_minute_close_change_pct_uses_prev_day_close_not_stale_today_row():
    """760013 회귀: 1D parquet 의 오늘 row 가 장중 stale (close=250000) 이고
    분봉 close 가 그 후 갱신된 EOD 값 (181290) 일 때, change_pct 는 stale 일봉
    pct_change(54.32%) 가 아니라 분봉 vs 전일 종가(162000) 기준(11.91%) 으로 산출.

    오늘 row 가 1D parquet 에 박혀 있다는 신호: ohlcv["last_date"] == today_kst.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    ohlcv = {
        "001390": {
            "close": [140740.0, 162000.0, 250000.0],   # 오늘 row=250000 (stale)
            "high":  [148725.0, 162000.0, 250000.0],
            "low":   [140740.0, 146805.0, 168845.0],
            "volume": [4825, 2398, 8],                  # 오늘 1D vol=8 (stale)
            "change_pct": [0.0, 15.11, 54.32],          # 오늘 stale pct
            "minute_close": 181290.0,                   # 분봉 EOD close (정확)
            "minute_volume_today": 9686.0,              # 분봉 누적 거래량 (정확)
            "last_date": today_kst,                     # 1D 마지막 row 가 오늘
        }
    }
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=ohlcv,
        market_indices={},
    )
    snap = snapshot.tickers["001390"]
    assert snap.current_price == 181290
    # (181290 - 162000) / 162000 * 100 = 11.91%
    assert snap.change_pct == 11.91
    # 분봉 누적 volume 우선 사용
    assert snap.volume == 9686


def test_minute_close_change_pct_when_today_row_absent():
    """1D parquet 의 마지막 row 가 어제까지만 있고 오늘 row 가 없는 케이스.
    이때 prev_close 는 closes[-1] (어제 종가) 가 정답.
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    yesterday = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)).strftime("%Y-%m-%d")
    ohlcv = {
        "001390": {
            "close":  [140000.0, 162000.0],   # last = 어제 종가
            "high":   [148000.0, 162000.0],
            "low":    [140000.0, 146000.0],
            "volume": [4825, 2398],
            "change_pct": [0.0, 15.71],
            "minute_close": 181290.0,
            "minute_volume_today": 9686.0,
            "last_date": yesterday,           # 오늘 row 없음
        }
    }
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=ohlcv,
        market_indices={},
    )
    snap = snapshot.tickers["001390"]
    assert snap.current_price == 181290
    # (181290 - 162000) / 162000 * 100 = 11.91%
    assert snap.change_pct == 11.91
    assert snap.volume == 9686


def test_no_minute_close_keeps_legacy_daily_change_pct():
    """분봉 데이터 없을 때는 기존 일봉 기반 change_pct/volume 동작 유지."""
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=MOCK_OHLCV,
        market_indices={},
    )
    snap = snapshot.tickers["001390"]
    assert snap.current_price == 7120
    assert snap.change_pct == 0.71      # MOCK 의 마지막 change_pct
    assert snap.volume == 2847000        # MOCK 의 마지막 volume


def test_safety_net_for_missing_signal_tickers(tmp_path):
    """universe 가 시그널 ticker 를 누락해도 disk 1D parquet 에서 보강된다."""
    import pandas as pd

    cache_dir = tmp_path / "1D"
    cache_dir.mkdir()
    df = pd.DataFrame(
        {
            "open":   [29000, 29500],
            "high":   [29800, 30100],
            "low":    [28800, 29200],
            "close":  [29500, 30000],
            "volume": [1_000_000, 1_500_000],
        },
        index=pd.to_datetime(["2026-05-07", "2026-05-08"]),
    )
    df.to_parquet(cache_dir / "0101N0.parquet")

    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,                     # 0101N0 누락
        ohlcv_latest=MOCK_OHLCV,
        market_indices={},
        signal_tickers=["0101N0", "001390"],         # 001390 은 universe 에 이미 있음
        cache_root=str(tmp_path),
    )

    # 안전망: universe 누락 ETF 가 disk 1D 로 보강
    assert "0101N0" in snapshot.tickers
    assert snapshot.tickers["0101N0"].current_price == 30000
    assert snapshot.tickers["0101N0"].volume == 1_500_000
    # 기존 universe ticker 는 그대로
    assert snapshot.tickers["001390"].current_price == 7120


def test_safety_net_skips_when_no_disk_parquet(tmp_path):
    """signal_ticker 의 1D parquet 이 없으면 silently skip (예외 X)."""
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=MOCK_OHLCV,
        market_indices={},
        signal_tickers=["NOTEXIST"],
        cache_root=str(tmp_path),
    )
    assert "NOTEXIST" not in snapshot.tickers
    assert "001390" in snapshot.tickers  # 기존 동작 회귀 없음


def test_safety_net_no_op_when_signal_tickers_omitted():
    """signal_tickers 인자 미지정 시 기존 동작 그대로."""
    snapshot = build_market_snapshot(
        universe=MOCK_UNIVERSE,
        ohlcv_latest=MOCK_OHLCV,
        market_indices={},
    )
    assert list(snapshot.tickers.keys()) == ["001390"]
