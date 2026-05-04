"""
Task 4: OhlcvCache 디스크 통합 (단일 인터페이스).

검증:
  - disk= 미주입 시 기존 메모리 동작 보존 (회귀 보호)
  - disk= 주입 + cold: 전체 fetch + 디스크 저장
  - disk= 주입 + warm: gap 만 fetch + append
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from core.cache.ohlcv_disk import OhlcvDiskCache
from core.data_fetch import OhlcvCache


def _make_df(start_date: str, n: int) -> pd.DataFrame:
    idx = pd.date_range(start_date, periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": [100] * n,
        },
        index=idx,
    )


def test_legacy_memory_only_no_regression():
    """disk= 미주입 시 기존 동작 그대로 (memory hit count = 1)."""
    client = MagicMock()
    client.get_ohlcv.return_value = _make_df("2026-01-02", 80)
    cache = OhlcvCache(client)

    cache.get_or_fetch("005930", "20260102", "20260430")
    cache.get_or_fetch("005930", "20260102", "20260430")  # 두 번째는 memory hit

    assert client.get_ohlcv.call_count == 1
    assert cache.stats["hit_count"] == 1


def test_disk_cold_does_full_fetch_then_persist(tmp_path):
    disk = OhlcvDiskCache(root=tmp_path)
    client = MagicMock()
    client.get_ohlcv.return_value = _make_df("2026-01-02", 80)
    cache = OhlcvCache(client, disk=disk)

    cache.get_or_fetch("005930", "20260102", "20260430", timeframe="1D")

    assert not disk.read("005930", "1D").empty
    client.get_ohlcv.assert_called_once_with(
        "005930", "20260102", "20260430", timeframe="1D"
    )


def test_disk_warm_does_incremental_fetch(tmp_path):
    disk = OhlcvDiskCache(root=tmp_path)
    # 80 영업일 캐시 (마지막 = 2026-04-23 목)
    disk.write("005930", "1D", _make_df("2026-01-02", 80))
    client = MagicMock()
    # 실제 API 처럼 gap_start (04-24) 부터 5 영업일 반환
    client.get_ohlcv.return_value = _make_df("2026-04-24", 5)
    cache = OhlcvCache(client, disk=disk)

    df = cache.get_or_fetch("005930", "20260102", "20260430", timeframe="1D")

    # 80 + 5 = 85 행 (중복 없음)
    assert len(df) == 85
    # gap_start 가 캐시 끝 + 1 영업일 이상이어야 함
    args, _ = client.get_ohlcv.call_args
    assert args[0] == "005930"
    assert args[1] >= "20260424"


def test_disk_warm_no_gap_skips_fetch(tmp_path):
    """캐시가 이미 end 까지 채워져 있으면 fetch 호출 X."""
    disk = OhlcvDiskCache(root=tmp_path)
    disk.write("005930", "1D", _make_df("2026-01-02", 200))  # 충분히 멀리까지
    client = MagicMock()
    cache = OhlcvCache(client, disk=disk)

    # 캐시 끝 < end 인지 확인
    cache.get_or_fetch("005930", "20260102", "20260330", timeframe="1D")

    # 200 영업일 = ~10/8 까지 → end=20260330 보다 큼 → fetch X
    assert client.get_ohlcv.call_count == 0
