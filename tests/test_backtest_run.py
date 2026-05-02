"""
tests/test_backtest_run.py — backtest_run.py 단위 테스트 (네트워크 없음)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from backtest_run import (
    BacktestRunConfig,
    calc_sharpe,
    load_manifest,
    load_ohlcv_1d,
    prepare_data_for_tf,
    run_backtest,
    save_csv,
    save_markdown,
)
from backtest_engine.core import BacktestResult, ExitReason, Trade
from core.cache.ohlcv_disk import OhlcvDiskCache


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ohlcv_1d() -> pd.DataFrame:
    dates = pd.bdate_range("2025-08-01", periods=65)
    rng = np.random.default_rng(42)
    close = 50_000 + rng.normal(0, 500, 65).cumsum()
    close = np.abs(close) + 10_000
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": rng.integers(100_000, 1_000_000, 65).astype(float),
    }, index=dates)


@pytest.fixture
def fake_cache(tmp_path, sample_ohlcv_1d):
    cache_root = tmp_path / ".cache"
    tf_dir = cache_root / "1D"
    tf_dir.mkdir(parents=True)
    for ticker in ["005930", "000660"]:
        sample_ohlcv_1d.to_parquet(tf_dir / f"{ticker}.parquet")
    manifest = {
        "collected_at": "2026-05-01T00:00:00",
        "market": "KOSPI",
        "target_date": "20260501",
        "tickers": ["005930", "000660"],
        "base_tfs": ["1D"],
    }
    (cache_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return cache_root


# ── load_manifest ─────────────────────────────────────────────────────────────

def test_load_manifest_success(fake_cache):
    m = load_manifest(fake_cache)
    assert m["market"] == "KOSPI"
    assert "005930" in m["tickers"]


def test_load_manifest_missing(tmp_path):
    with pytest.raises(SystemExit):
        load_manifest(tmp_path / "nonexistent")


# ── load_ohlcv_1d ─────────────────────────────────────────────────────────────

def test_load_ohlcv_filters_short(tmp_path, sample_ohlcv_1d):
    cache_root = tmp_path / ".cache"
    tf_dir = cache_root / "1D"
    tf_dir.mkdir(parents=True)

    # 정상 종목 (65봉)
    sample_ohlcv_1d.to_parquet(tf_dir / "005930.parquet")
    # 짧은 종목 (39봉 — MIN_BARS_1D=40 미만)
    short_df = sample_ohlcv_1d.iloc[:39]
    short_df.to_parquet(tf_dir / "000660.parquet")

    disk = OhlcvDiskCache(cache_root)
    data = load_ohlcv_1d(disk, ["005930", "000660"])
    assert "005930" in data
    assert "000660" not in data


def test_load_ohlcv_all_empty_exits(tmp_path):
    cache_root = tmp_path / ".cache"
    (cache_root / "1D").mkdir(parents=True)
    disk = OhlcvDiskCache(cache_root)
    with pytest.raises(SystemExit):
        load_ohlcv_1d(disk, ["999999"])


# ── prepare_data_for_tf ───────────────────────────────────────────────────────

def test_prepare_data_1d_passthrough(sample_ohlcv_1d):
    data = {"005930": sample_ohlcv_1d}
    result = prepare_data_for_tf(data, "1D")
    assert result is data


def test_prepare_data_1w_resample(sample_ohlcv_1d):
    data = {"005930": sample_ohlcv_1d}
    result = prepare_data_for_tf(data, "1W")
    assert "005930" in result
    df_w = result["005930"]
    # 주봉 high >= 일봉 max (해당 주)
    assert (df_w["high"] >= df_w["low"]).all()
    # 행 수는 일봉보다 적어야 함
    assert len(df_w) < len(sample_ohlcv_1d)


def test_prepare_data_1w_aggregation(sample_ohlcv_1d):
    data = {"005930": sample_ohlcv_1d}
    df_w = prepare_data_for_tf(data, "1W")["005930"]
    # 첫 주의 high는 해당 주 1D high들의 max
    first_week_end = df_w.index[0]
    mask = sample_ohlcv_1d.index <= first_week_end
    expected_high = sample_ohlcv_1d.loc[mask, "high"].max()
    assert abs(df_w["high"].iloc[0] - expected_high) < 1e-6


def test_prepare_data_unsupported_tf(sample_ohlcv_1d):
    with pytest.raises(ValueError, match="지원하지 않는"):
        prepare_data_for_tf({"A": sample_ohlcv_1d}, "1h")


# ── calc_sharpe ───────────────────────────────────────────────────────────────

def test_calc_sharpe_positive():
    # 꾸준히 오르는 equity curve → 양수 sharpe
    equity = pd.Series([10_000 + i * 100 for i in range(50)])
    s = calc_sharpe(equity)
    assert s > 0


def test_calc_sharpe_too_short():
    equity = pd.Series([10_000])
    assert math.isnan(calc_sharpe(equity))


def test_calc_sharpe_flat():
    equity = pd.Series([10_000] * 30)
    assert math.isnan(calc_sharpe(equity))


# ── save_csv ──────────────────────────────────────────────────────────────────

def _make_fake_result(initial_capital: float = 10_000_000.0) -> BacktestResult:
    trade = Trade(
        ticker="005930",
        entry_time=pd.Timestamp("2026-01-02"),
        exit_time=pd.Timestamp("2026-01-05"),
        entry_price=70_000.0,
        exit_price=72_100.0,
        shares=10,
        exit_reason=ExitReason.TARGET_1,
        bars_held=3,
    )
    equity = pd.Series(
        [initial_capital, initial_capital * 1.01, initial_capital * 1.03],
        index=pd.date_range("2026-01-02", periods=3),
    )
    return BacktestResult(
        trades=[trade],
        initial_capital=initial_capital,
        final_capital=initial_capital * 1.03,
        equity_curve=equity,
    )


def test_save_csv_columns(tmp_path):
    result = _make_fake_result()
    save_csv(result, tmp_path, "20260501", "1D")
    csv_path = tmp_path / "backtest_20260501_1D.csv"
    assert csv_path.exists()
    df = pd.read_csv(csv_path)
    expected_cols = {
        "ticker", "entry_time", "exit_time", "entry_price",
        "exit_price", "shares", "pnl_pct", "exit_reason", "bars_held",
    }
    assert expected_cols.issubset(set(df.columns))
    assert len(df) == 1


def test_save_markdown_exists(tmp_path):
    result = _make_fake_result()
    from backtest_run import build_metrics
    metrics_list = [build_metrics(result, "1D")]
    save_markdown(metrics_list, {"1D": result}, tmp_path, "20260501", top_n=5)
    md_path = tmp_path / "backtest_20260501.md"
    assert md_path.exists()
    content = md_path.read_text()
    assert "백테스트 리포트" in content
    assert "005930" in content


# ── end-to-end ────────────────────────────────────────────────────────────────

def test_backtest_run_e2e(fake_cache, tmp_path):
    cfg = BacktestRunConfig(
        cache_root=fake_cache,
        timeframes=["1D"],
        output_dir=tmp_path / "results",
        no_file=False,
    )
    run_backtest(cfg)
    # CSV 파일 생성 확인
    csv_files = list((tmp_path / "results").glob("backtest_*_1D.csv"))
    assert len(csv_files) == 1
    # Markdown 파일 생성 확인
    md_files = list((tmp_path / "results").glob("backtest_*.md"))
    assert len(md_files) == 1
