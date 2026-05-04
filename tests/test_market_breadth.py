"""
test_market_breadth.py — compute_market_breadth 단위 테스트.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from core.decision.market_breadth import compute_market_breadth


def _make_ohlcv(n_days: int = 40, seed: int = 42) -> pd.DataFrame:
    """합성 OHLCV DataFrame."""
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")
    rng = np.random.default_rng(seed)
    close = 10000 * np.cumprod(1 + rng.normal(0, 0.01, n_days))
    high = close * (1 + rng.uniform(0, 0.01, n_days))
    low = close * (1 - rng.uniform(0, 0.01, n_days))
    volume = rng.integers(100_000, 1_000_000, n_days).astype(float)
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def _make_manifest(tmp_path: Path, n_tickers: int = 20) -> None:
    meta = {f"{i:06d}": {"market_cap_bil": 1000 - i} for i in range(n_tickers)}
    (tmp_path / "manifest.json").write_text(json.dumps({"tickers_meta": meta}))


@patch("core.decision.market_breadth.OhlcvDiskCache")
def test_returns_expected_keys(mock_cls, tmp_path):
    """정상 케이스: 4개 키 모두 반환."""
    mock_disk = MagicMock()
    mock_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(40)
    _make_manifest(tmp_path, 20)

    result = compute_market_breadth(tmp_path, tf="1D", max_tickers=10)
    assert set(result.keys()) >= {"up_ratio", "above_ma20_ratio", "avg_atr_pct", "top_volume_return_avg"}


@patch("core.decision.market_breadth.OhlcvDiskCache")
def test_up_ratio_range(mock_cls, tmp_path):
    """up_ratio 는 0~1 범위."""
    mock_disk = MagicMock()
    mock_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(40)
    _make_manifest(tmp_path, 20)

    result = compute_market_breadth(tmp_path, tf="1D", max_tickers=10)
    assert 0.0 <= result["up_ratio"] <= 1.0


@patch("core.decision.market_breadth.OhlcvDiskCache")
def test_all_up_returns_high_ratio(mock_cls, tmp_path):
    """모든 종목이 전일 대비 상승이면 up_ratio == 1.0."""
    mock_disk = MagicMock()
    mock_cls.return_value = mock_disk

    # 단조 증가 시계열
    dates = pd.date_range("2025-01-01", periods=40, freq="B")
    close = pd.Series(range(10000, 10040), dtype=float, index=dates)
    df = pd.DataFrame(
        {"open": close, "high": close * 1.01, "low": close * 0.99,
         "close": close, "volume": 500_000.0},
        index=dates,
    )
    mock_disk.read.return_value = df
    _make_manifest(tmp_path, 20)

    result = compute_market_breadth(tmp_path, tf="1D", max_tickers=10)
    assert result["up_ratio"] == 1.0


@patch("core.decision.market_breadth.OhlcvDiskCache")
def test_above_ma20_ratio_range(mock_cls, tmp_path):
    """above_ma20_ratio 는 0~1 범위."""
    mock_disk = MagicMock()
    mock_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(40)
    _make_manifest(tmp_path, 20)

    result = compute_market_breadth(tmp_path, tf="1D", max_tickers=10)
    r = result.get("above_ma20_ratio")
    assert r is None or 0.0 <= r <= 1.0


@patch("core.decision.market_breadth.OhlcvDiskCache")
def test_no_manifest_returns_empty(mock_cls, tmp_path):
    """manifest 없으면 빈 dict."""
    result = compute_market_breadth(tmp_path, tf="1D")
    assert result == {}


@patch("core.decision.market_breadth.OhlcvDiskCache")
def test_insufficient_tickers_returns_empty(mock_cls, tmp_path):
    """종목 0개 → 빈 dict."""
    mock_disk = MagicMock()
    mock_cls.return_value = mock_disk
    mock_disk.read.side_effect = Exception("no data")
    _make_manifest(tmp_path, 5)

    result = compute_market_breadth(tmp_path, tf="1D", max_tickers=5)
    assert result == {}
