"""
Task 3: OhlcvDiskCache parquet 영속 캐시.

핵심 행동:
  - write 후 read 가 같은 DataFrame 반환 (datetime index 보존)
  - 미존재 키는 빈 DataFrame
  - 손상된 parquet 파일은 .corrupted 로 격리되고 빈 DataFrame 반환
  - append 가 기존 + 신규 합치고 중복 제거 후 정렬
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.cache.ohlcv_disk import OhlcvDiskCache


def _make_df(rows):
    idx = pd.DatetimeIndex(
        [datetime.strptime(d, "%Y-%m-%d") for d, _ in rows], name="date"
    )
    return pd.DataFrame(
        {
            "open": [v for _, v in rows],
            "high": [v for _, v in rows],
            "low": [v for _, v in rows],
            "close": [v for _, v in rows],
            "volume": [100 for _ in rows],
        },
        index=idx,
    )


def test_write_then_read_roundtrip(tmp_path):
    cache = OhlcvDiskCache(root=tmp_path)
    df = _make_df([("2026-04-30", 1.0), ("2026-04-29", 2.0)])
    cache.write("005930", "1D", df)
    out = cache.read("005930", "1D")
    pd.testing.assert_frame_equal(out, df)


def test_read_missing_returns_empty(tmp_path):
    cache = OhlcvDiskCache(root=tmp_path)
    assert cache.read("999999", "1D").empty


def test_corrupted_file_renamed_and_returns_empty(tmp_path):
    (tmp_path / "1D").mkdir()
    (tmp_path / "1D" / "123456.parquet").write_bytes(b"not parquet")
    cache = OhlcvDiskCache(root=tmp_path)
    out = cache.read("123456", "1D")
    assert out.empty
    assert (tmp_path / "1D" / "123456.parquet.corrupted").exists()


def test_append_merges_and_dedups(tmp_path):
    cache = OhlcvDiskCache(root=tmp_path)
    cache.write("005930", "1D", _make_df([("2026-04-28", 1.0), ("2026-04-29", 2.0)]))
    merged = cache.append(
        "005930",
        "1D",
        _make_df([("2026-04-29", 99.0), ("2026-04-30", 3.0)]),  # 04-29 중복
    )
    # 정렬 + 04-29 는 새 값 99.0 우선 (keep="last")
    assert list(merged.index.strftime("%Y-%m-%d")) == [
        "2026-04-28",
        "2026-04-29",
        "2026-04-30",
    ]
    assert merged.loc["2026-04-29", "close"] == 99.0


def test_write_empty_is_noop(tmp_path):
    cache = OhlcvDiskCache(root=tmp_path)
    cache.write("005930", "1D", pd.DataFrame())  # 빈 DF 는 디스크에 안 적힘
    assert cache.read("005930", "1D").empty


def test_append_unions_columns_for_schema_migration(tmp_path):
    """Phase 1 schema migration: 기존 parquet (foreign_rate 없음) + 새 fetch (foreign_rate 있음) → union.

    실제 운영 시나리오: Step 2 이전에 수집된 .cache/1D/*.parquet 은 5컬럼.
    Step 2 이후 새 fetch 시 foreign_rate 컬럼 포함 → append 시 pd.concat 이 union.
    옛 행은 NaN, 새 행은 값.
    """
    cache = OhlcvDiskCache(root=tmp_path)
    # 기존 OHLCV (Step 2 이전 — 5컬럼만)
    old_idx = pd.date_range("2026-01-01", periods=3, freq="B")
    old_df = pd.DataFrame({
        "open": [100.0, 100.0, 100.0],
        "high": [101.0, 101.0, 101.0],
        "low":  [99.0, 99.0, 99.0],
        "close":[100.0, 100.0, 100.0],
        "volume":[1000, 1000, 1000],
    }, index=old_idx)
    cache.write("005930", "1D", old_df)
    # 디스크 재로드: foreign_rate 없음 검증
    reloaded = cache.read("005930", "1D")
    assert "foreign_rate" not in reloaded.columns

    # 새 fetch (Step 2 이후 — foreign_rate 포함)
    new_idx = pd.date_range("2026-01-08", periods=3, freq="B")
    new_df = pd.DataFrame({
        "open": [110.0, 110.0, 110.0],
        "high": [111.0, 111.0, 111.0],
        "low":  [109.0, 109.0, 109.0],
        "close":[110.0, 110.0, 110.0],
        "volume":[2000, 2000, 2000],
        "foreign_rate":[49.5, 49.6, 49.7],
    }, index=new_idx)
    merged = cache.append("005930", "1D", new_df)

    # union schema
    assert "foreign_rate" in merged.columns
    # 옛 행은 NaN
    assert pd.isna(merged.loc[old_idx[0], "foreign_rate"])
    # 새 행은 값
    assert merged.loc[new_idx[0], "foreign_rate"] == 49.5

    # 디스크 재로드 후에도 schema 보존
    reloaded2 = cache.read("005930", "1D")
    assert "foreign_rate" in reloaded2.columns
    assert pd.isna(reloaded2.loc[old_idx[0], "foreign_rate"])
    assert reloaded2.loc[new_idx[0], "foreign_rate"] == 49.5
