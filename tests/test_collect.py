"""
Task 1: scripts/collect.py — 수집 Job 테스트.

검증:
  - run_collect() 실행 후 manifest.json 생성
  - manifest에 market, collected_at, base_tfs 포함
  - parquet 파일이 {cache_root}/1D/ 에 생성
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd


def _make_mock_client(tickers=("005930", "000660"), with_fundamentals=True):
    client = MagicMock()
    client.get_tickers.return_value = list(tickers)
    client.get_ticker_name.side_effect = lambda t: f"종목{t}"
    caps = {t: 5_000 * 1e8 for t in tickers}
    cap_df = pd.DataFrame(
        {t: {"시가총액": caps[t], "종목명": f"종목{t}"} for t in tickers}
    ).T
    client.get_market_cap.return_value = cap_df
    idx = pd.date_range("2026-01-01", periods=120, freq="B")
    ohlcv = pd.DataFrame(
        {
            "open": [100.0] * 120,
            "high": [101.0] * 120,
            "low": [99.0] * 120,
            "close": [100.0] * 120,
            "volume": [1_000_000] * 120,
        },
        index=idx,
    )
    client.get_ohlcv.return_value = ohlcv
    if with_fundamentals:
        funda = {}
        for i, t in enumerate(tickers):
            funda[t] = {
                "per": 33.59 + i,
                "roe": 10.85 + i,
                "foreign_pct": 49.27 + i,
                "naver_url": f"https://finance.naver.com/item/main.naver?code={t}",
            }
        client.get_fundamentals.return_value = pd.DataFrame(funda).T
    else:
        client.get_fundamentals.return_value = pd.DataFrame(
            columns=["per", "roe", "foreign_pct", "naver_url"]
        )
    return client


def test_collect_creates_manifest(tmp_path):
    from scripts.collect import CollectConfig, run_collect

    cfg = CollectConfig(
        market="KOSPI",
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        base_tfs=["1D"],
        lookback_days=60,
        min_market_cap_bil=0.0,
        max_market_cap_bil=999999.0,
    )
    with patch("scripts.collect.DataClient", return_value=_make_mock_client()):
        run_collect(cfg, target_date="20260430")

    manifest = tmp_path / ".cache" / "manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text())
    assert data["market"] == "KOSPI"
    assert "collected_at" in data
    assert "1D" in data["base_tfs"]


def test_collect_creates_parquet_files(tmp_path):
    from scripts.collect import CollectConfig, run_collect

    cfg = CollectConfig(
        market="KOSPI",
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        base_tfs=["1D"],
        lookback_days=60,
        min_market_cap_bil=0.0,
        max_market_cap_bil=999999.0,
    )
    with patch("scripts.collect.DataClient", return_value=_make_mock_client()):
        run_collect(cfg, target_date="20260430")

    parquet_dir = tmp_path / ".cache" / "1D"
    assert parquet_dir.exists()
    parquet_files = list(parquet_dir.glob("*.parquet"))
    assert len(parquet_files) == 2  # 005930, 000660


def test_collect_tf_to_base_mapping():
    """--timeframes 1D 1W 30m → base_tfs = ["1D", "1m"]."""
    from scripts.collect import _TF_TO_BASE

    assert _TF_TO_BASE["1D"] == "1D"
    assert _TF_TO_BASE["1W"] == "1D"
    assert _TF_TO_BASE["30m"] == "1m"
    assert _TF_TO_BASE["1h"] == "1m"


def test_manifest_includes_tickers_meta(tmp_path):
    """수집 manifest에 tickers_meta dict가 포함되고 row_count/last_date가 정확한지."""
    from scripts.collect import CollectConfig, run_collect

    cfg = CollectConfig(
        market="KOSPI",
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        base_tfs=["1D"],
        lookback_days=60,
        min_market_cap_bil=0.0,
        max_market_cap_bil=999999.0,
    )
    with patch("scripts.collect.DataClient", return_value=_make_mock_client()):
        run_collect(cfg, target_date="20260430")

    manifest = tmp_path / ".cache" / "manifest.json"
    data = json.loads(manifest.read_text())

    assert "tickers_meta" in data
    assert isinstance(data["tickers_meta"], dict)
    assert "summary" in data
    assert "total_tickers" in data["summary"]
    assert "duration_sec" in data["summary"]

    # 각 ticker의 메타 검증
    for ticker, meta in data["tickers_meta"].items():
        assert "row_count_1D" in meta
        assert "last_date_1D" in meta
        assert "base_tfs" in meta
        assert "1D" in meta["base_tfs"]
        assert meta["row_count_1D"] > 0
        assert len(meta["last_date_1D"]) == 10  # YYYY-MM-DD


def test_build_tickers_metadata_skips_empty(tmp_path):
    """빈 DataFrame이 반환되는 ticker는 tickers_meta에서 제외되는지."""
    from scripts.collect import _build_tickers_metadata
    from core.cache.ohlcv_disk import OhlcvDiskCache

    cache = OhlcvDiskCache(tmp_path / ".cache")

    # 한 ticker는 1D 데이터 있음, 한 ticker는 없음
    ticker1 = "005930"
    ticker2 = "000660"

    # ticker1에만 데이터 쓰기
    idx = pd.date_range("2026-01-01", periods=10, freq="B")
    df1 = pd.DataFrame(
        {
            "open": [100.0] * 10,
            "high": [101.0] * 10,
            "low": [99.0] * 10,
            "close": [100.0] * 10,
            "volume": [1_000_000] * 10,
        },
        index=idx,
    )
    cache.write(ticker1, "1D", df1)

    meta = _build_tickers_metadata(cache, [ticker1, ticker2], ["1D"])

    assert ticker1 in meta
    assert ticker2 not in meta
    assert meta[ticker1]["row_count_1D"] == 10


def test_build_tickers_metadata_handles_missing_parquet(tmp_path):
    """parquet 파일이 없는 (ticker, tf) 조합은 skip하는지."""
    from scripts.collect import _build_tickers_metadata
    from core.cache.ohlcv_disk import OhlcvDiskCache

    cache = OhlcvDiskCache(tmp_path / ".cache")
    meta = _build_tickers_metadata(cache, ["005930"], ["1D"])

    # 데이터 없으므로 빈 dict
    assert meta == {}


def test_manifest_includes_fundamentals_in_tickers_meta(tmp_path):
    """수집 manifest의 tickers_meta에 per/roe/foreign_pct/naver_url 포함 (UI 인덱스용)."""
    from scripts.collect import CollectConfig, run_collect

    cfg = CollectConfig(
        market="KOSPI",
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        base_tfs=["1D"],
        lookback_days=60,
        min_market_cap_bil=0.0,
        max_market_cap_bil=999999.0,
    )
    with patch("scripts.collect.DataClient", return_value=_make_mock_client()):
        run_collect(cfg, target_date="20260430")

    data = json.loads((tmp_path / ".cache" / "manifest.json").read_text())
    meta = data["tickers_meta"]

    # 005930 (삼성전자 mock)
    assert "005930" in meta
    assert meta["005930"]["per"] == 33.59
    assert meta["005930"]["roe"] == 10.85
    assert meta["005930"]["foreign_pct"] == 49.27
    assert meta["005930"]["naver_url"] == \
        "https://finance.naver.com/item/main.naver?code=005930"


def test_manifest_naver_url_present_even_without_fundamentals(tmp_path):
    """get_fundamentals가 빈 DataFrame이어도 naver_url은 ticker 기반으로 항상 채움."""
    from scripts.collect import CollectConfig, run_collect

    cfg = CollectConfig(
        market="KOSPI",
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        base_tfs=["1D"],
        lookback_days=60,
        min_market_cap_bil=0.0,
        max_market_cap_bil=999999.0,
    )
    with patch("scripts.collect.DataClient",
               return_value=_make_mock_client(with_fundamentals=False)):
        run_collect(cfg, target_date="20260430")

    data = json.loads((tmp_path / ".cache" / "manifest.json").read_text())
    meta = data["tickers_meta"]
    for ticker, m in meta.items():
        assert m["naver_url"] == \
            f"https://finance.naver.com/item/main.naver?code={ticker}"
        # 결측은 None (JSON null)
        assert m["per"] is None
        assert m["roe"] is None
        assert m["foreign_pct"] is None


def test_collect_force_refetch_replaces_existing_parquet(tmp_path):
    """--force-refetch: 기존 parquet 무시하고 새 fetch 결과로 덮어씀."""
    from scripts.collect import CollectConfig, run_collect
    from core.cache.ohlcv_disk import OhlcvDiskCache

    cache_root = tmp_path / ".cache"
    # 1) 기존 parquet 시뮬레이션 — 옛 schema (foreign_rate 없음)
    disk = OhlcvDiskCache(cache_root)
    old_df = pd.DataFrame(
        {"open": [50.0]*10, "high": [51.0]*10, "low": [49.0]*10,
         "close": [50.0]*10, "volume": [500]*10},
        index=pd.date_range("2025-01-01", periods=10, freq="B"),
    )
    disk.write("005930", "1D", old_df)
    assert disk.has_cache("005930", "1D")

    # 2) force_refetch=True 로 수집 → 기존 옛 데이터 사라지고 mock 의 새 데이터로 교체
    cfg = CollectConfig(
        market="KOSPI",
        cache_root=cache_root,
        max_universe_size=10,
        base_tfs=["1D"],
        lookback_days=60,
        min_market_cap_bil=0.0,
        max_market_cap_bil=999999.0,
        force_refetch=True,
    )
    with patch("scripts.collect.DataClient", return_value=_make_mock_client()):
        run_collect(cfg, target_date="20260430")

    # 새 fetch 결과 (mock: 120 rows, 2026 인덱스) 로 교체
    new_df = disk.read("005930", "1D")
    assert len(new_df) == 120  # mock 데이터
    # 옛 2025-01-01 인덱스는 사라짐
    assert pd.Timestamp("2025-01-01") not in new_df.index


def test_collect_default_no_force_refetch_preserves_existing(tmp_path):
    """default(force_refetch=False): 기존 parquet 유지 (incremental gap fetch)."""
    from scripts.collect import CollectConfig, run_collect
    from core.cache.ohlcv_disk import OhlcvDiskCache

    cache_root = tmp_path / ".cache"
    disk = OhlcvDiskCache(cache_root)
    old_idx = pd.date_range("2025-12-01", periods=10, freq="B")
    old_df = pd.DataFrame(
        {"open": [50.0]*10, "high": [51.0]*10, "low": [49.0]*10,
         "close": [50.0]*10, "volume": [500]*10},
        index=old_idx,
    )
    disk.write("005930", "1D", old_df)

    cfg = CollectConfig(
        market="KOSPI", cache_root=cache_root, max_universe_size=10,
        base_tfs=["1D"], lookback_days=60,
        min_market_cap_bil=0.0, max_market_cap_bil=999999.0,
        force_refetch=False,  # default
    )
    with patch("scripts.collect.DataClient", return_value=_make_mock_client()):
        run_collect(cfg, target_date="20260430")

    merged = disk.read("005930", "1D")
    # 옛 2025-12 인덱스 보존 + 새 데이터 union
    assert pd.Timestamp("2025-12-01") in merged.index


def test_manifest_summary_fields(tmp_path):
    """summary dict에 total_tickers, duration_sec가 포함되는지."""
    from scripts.collect import CollectConfig, run_collect

    cfg = CollectConfig(
        market="KOSPI",
        cache_root=tmp_path / ".cache",
        max_universe_size=10,
        base_tfs=["1D"],
        lookback_days=60,
        min_market_cap_bil=0.0,
        max_market_cap_bil=999999.0,
    )
    with patch("scripts.collect.DataClient", return_value=_make_mock_client()):
        run_collect(cfg, target_date="20260430")

    manifest = tmp_path / ".cache" / "manifest.json"
    data = json.loads(manifest.read_text())

    assert "summary" in data
    assert "total_tickers" in data["summary"]
    assert "duration_sec" in data["summary"]
    assert data["summary"]["total_tickers"] >= 0
    assert data["summary"]["duration_sec"] >= 0
