"""
test_factor_performance.py — 팩터 성과 분석 모듈 테스트.

외부 네트워크 금지, tmp_path 픽스처 사용.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from core.decision.config import Priority, WeightConfig
from core.decision.factor_performance import (
    correlations_to_weights,
    measure_factor_correlations,
    update_factor_records,
)


# ============================================================================
# Helper functions
# ============================================================================


def _make_weight_config() -> WeightConfig:
    """테스트용 기본 WeightConfig."""
    return WeightConfig(
        priorities=[
            Priority(
                key="per",
                weight=30.0,
                direction="lower_better",
                label="저PER",
            ),
            Priority(
                key="roe",
                weight=30.0,
                direction="higher_better",
                label="고ROE",
            ),
            Priority(
                key="momentum_pct",
                weight=30.0,
                direction="higher_better",
                label="모멘텀",
            ),
            Priority(
                key="score",
                weight=10.0,
                direction="higher_better",
                label="점수",
            ),
        ],
        must_have=[],
        strategy_weights={},
    )


def _make_ohlcv_for_ticker(n_days: int = 90, end_date: date | None = None) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame.

    Args:
        n_days: 거래일 개수
        end_date: 마지막 거래일 (기본값: 오늘)
    """
    if end_date is None:
        end_date = date.today()
    dates = pd.date_range(end=end_date, periods=n_days, freq="B")
    np.random.seed(42)
    close = 10000 * np.cumprod(1 + np.random.randn(n_days) * 0.01)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n_days, 1_000_000),
        },
        index=dates,
    )


def _make_scan_manifest(
    scan_root: Path, scan_date_str: str, candidates: list[dict]
) -> None:
    """scan_results 디렉토리 + manifest + JSON 파일 생성."""
    strategy = "strategy_one_d_v2"
    tf = "1D"
    out_dir = scan_root / scan_date_str / tf
    out_dir.mkdir(parents=True, exist_ok=True)
    json_file = out_dir / f"{strategy}_{scan_date_str}.json"
    json_file.write_text(json.dumps({"candidates": candidates}))

    manifest_key = f"{strategy}__{tf}"
    manifest = {
        manifest_key: {
            "latest_file": f"{scan_date_str}/{tf}/{strategy}_{scan_date_str}.json"
        }
    }
    (scan_root / "manifest.json").write_text(json.dumps(manifest))


# ============================================================================
# update_factor_records tests
# ============================================================================


@patch("core.decision.factor_performance.OhlcvDiskCache")
def test_update_factor_records_creates_parquet(mock_cache_cls, tmp_path):
    """최초 실행: parquet 없음 → 생성됨, 컬럼 확인."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv_for_ticker(90)

    scan_root = tmp_path / "scan_results"
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    # 30일 전 날짜 (cutoff 통과)
    old_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
    candidates = [
        {
            "ticker": "005930",
            "score": 500.0,
            "metrics": {
                "per": 15.0,
                "roe": 12.0,
                "momentum_pct": 3.0,
                "rr_ratio": 2.5,
            },
        }
    ]
    _make_scan_manifest(scan_root, old_date, candidates)

    result = update_factor_records(scan_root, cache_root)
    assert (cache_root / "factor_records.parquet").exists()
    assert not result.empty
    assert "return_3d" in result.columns
    assert all(
        col in result.columns
        for col in ["date", "ticker", "per", "roe", "momentum_pct", "rr_ratio", "score"]
    )


@patch("core.decision.factor_performance.OhlcvDiskCache")
def test_update_factor_records_skips_recent_dates(mock_cache_cls, tmp_path):
    """scan_date > cutoff → 해당 날짜 row 없음."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv_for_ticker(90)

    scan_root = tmp_path / "scan_results"
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    # 최근 날짜 (cutoff 실패)
    recent_date = (date.today() - timedelta(days=2)).strftime("%Y%m%d")
    candidates = [
        {
            "ticker": "005930",
            "score": 500.0,
            "metrics": {
                "per": 15.0,
                "roe": 12.0,
                "momentum_pct": 3.0,
                "rr_ratio": 2.5,
            },
        }
    ]
    _make_scan_manifest(scan_root, recent_date, candidates)

    result = update_factor_records(scan_root, cache_root, hold_days=3)
    assert result.empty or len(result) == 0


@patch("core.decision.factor_performance.OhlcvDiskCache")
def test_update_factor_records_skips_already_processed(
    mock_cache_cls, tmp_path
):
    """기존 parquet에 날짜 있음 → 중복 없음."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv_for_ticker(90)

    scan_root = tmp_path / "scan_results"
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    # 첫 번째 실행
    old_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
    candidates = [
        {
            "ticker": "005930",
            "score": 500.0,
            "metrics": {
                "per": 15.0,
                "roe": 12.0,
                "momentum_pct": 3.0,
                "rr_ratio": 2.5,
            },
        }
    ]
    _make_scan_manifest(scan_root, old_date, candidates)

    result1 = update_factor_records(scan_root, cache_root)
    initial_len = len(result1)

    # 두 번째 실행 (동일 데이터)
    result2 = update_factor_records(scan_root, cache_root)
    # drop_duplicates 때문에 개수 같아야 함
    assert len(result2) == initial_len


@patch("core.decision.factor_performance.OhlcvDiskCache")
def test_update_factor_records_incremental_append(mock_cache_cls, tmp_path):
    """2회 실행: 두 번째 실행에서 새 날짜만 추가."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv_for_ticker(90)

    scan_root = tmp_path / "scan_results"
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    # 첫 번째 실행 (30일 전)
    old_date1 = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
    candidates1 = [
        {
            "ticker": "005930",
            "score": 500.0,
            "metrics": {
                "per": 15.0,
                "roe": 12.0,
                "momentum_pct": 3.0,
                "rr_ratio": 2.5,
            },
        }
    ]
    _make_scan_manifest(scan_root, old_date1, candidates1)

    result1 = update_factor_records(scan_root, cache_root)
    len1 = len(result1)

    # 두 번째 실행 (다른 날짜, 25일 전)
    old_date2 = (date.today() - timedelta(days=25)).strftime("%Y%m%d")
    candidates2 = [
        {
            "ticker": "000660",
            "score": 450.0,
            "metrics": {
                "per": 18.0,
                "roe": 10.0,
                "momentum_pct": 2.0,
                "rr_ratio": 2.0,
            },
        }
    ]
    _make_scan_manifest(scan_root, old_date2, candidates2)

    result2 = update_factor_records(scan_root, cache_root)
    len2 = len(result2)

    assert len2 > len1


@patch("core.decision.factor_performance.OhlcvDiskCache")
def test_update_factor_records_handles_corrupted_parquet(
    mock_cache_cls, tmp_path
):
    """손상된 parquet → 전체 재구성 (예외 없음)."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv_for_ticker(90)

    scan_root = tmp_path / "scan_results"
    cache_root = tmp_path / "cache"
    cache_root.mkdir()

    # 손상된 parquet 파일 생성
    parquet_path = cache_root / "factor_records.parquet"
    parquet_path.write_text("corrupted data")

    # 첫 번째 실행 (손상된 파일 무시)
    old_date = (date.today() - timedelta(days=30)).strftime("%Y%m%d")
    candidates = [
        {
            "ticker": "005930",
            "score": 500.0,
            "metrics": {
                "per": 15.0,
                "roe": 12.0,
                "momentum_pct": 3.0,
                "rr_ratio": 2.5,
            },
        }
    ]
    _make_scan_manifest(scan_root, old_date, candidates)

    result = update_factor_records(scan_root, cache_root)
    assert not result.empty
    assert (cache_root / "factor_records.parquet").exists()


# ============================================================================
# measure_factor_correlations tests
# ============================================================================


def test_measure_factor_correlations_returns_spearman():
    """30행 mock records → 각 팩터 상관계수 반환."""
    np.random.seed(42)
    n = 30
    data = {
        "return_3d": np.random.randn(n) * 0.05,
        "per": np.random.randn(n) * 10 + 20,
        "roe": np.random.randn(n) * 5 + 10,
        "momentum_pct": np.random.randn(n) * 2 + 3,
        "rr_ratio": np.random.randn(n) * 1 + 2,
        "score": np.random.randn(n) * 100 + 500,
    }
    records = pd.DataFrame(data)

    correlations = measure_factor_correlations(records, min_samples=15)

    assert isinstance(correlations, dict)
    assert len(correlations) > 0
    assert all(isinstance(v, float) for v in correlations.values())
    assert all(-1 <= v <= 1 for v in correlations.values())


def test_measure_factor_correlations_below_min_samples():
    """records < min_samples → 빈 dict."""
    np.random.seed(42)
    n = 10
    data = {
        "return_3d": np.random.randn(n) * 0.05,
        "per": np.random.randn(n) * 10 + 20,
    }
    records = pd.DataFrame(data)

    correlations = measure_factor_correlations(records, min_samples=15)
    assert correlations == {}


def test_measure_factor_correlations_empty():
    """빈 DataFrame → 빈 dict."""
    records = pd.DataFrame()
    correlations = measure_factor_correlations(records)
    assert correlations == {}


def test_measure_factor_correlations_all_nan():
    """모든 값이 NaN → 빈 dict."""
    records = pd.DataFrame(
        {
            "return_3d": [np.nan] * 30,
            "per": [np.nan] * 30,
            "roe": [np.nan] * 30,
        }
    )
    correlations = measure_factor_correlations(records, min_samples=15)
    assert correlations == {}


# ============================================================================
# correlations_to_weights tests
# ============================================================================


def test_correlations_to_weights_empty_correlations_returns_base():
    """빈 dict → base_config 그대로."""
    base_cfg = _make_weight_config()
    correlations = {}

    result = correlations_to_weights(correlations, base_cfg)

    assert result.priorities == base_cfg.priorities
    assert result.must_have == base_cfg.must_have
    assert result.strategy_weights == base_cfg.strategy_weights


def test_correlations_to_weights_applies_floor():
    """floor 적용 후 모든 weight >= floor_pct."""
    base_cfg = _make_weight_config()
    correlations = {
        "per": 0.1,
        "roe": 0.9,
        "momentum_pct": 0.5,
        "score": 0.2,
    }

    result = correlations_to_weights(correlations, base_cfg, floor_pct=5.0)

    assert all(p.weight >= 5.0 for p in result.priorities)


def test_correlations_to_weights_sum_100():
    """결과 weight 합 = 100 (±0.01)."""
    base_cfg = _make_weight_config()
    correlations = {
        "per": 0.5,
        "roe": 0.8,
        "momentum_pct": 0.3,
        "score": 0.6,
    }

    result = correlations_to_weights(correlations, base_cfg, floor_pct=5.0)

    total = sum(p.weight for p in result.priorities)
    assert abs(total - 100.0) < 0.01


def test_correlations_to_weights_all_zero_correlations_uniform():
    """모두 0 → 균등 가중치."""
    base_cfg = _make_weight_config()
    correlations = {
        "per": 0.0,
        "roe": 0.0,
        "momentum_pct": 0.0,
        "score": 0.0,
    }

    result = correlations_to_weights(correlations, base_cfg, floor_pct=0.0)

    # softmax가 균등해지므로, 모든 우선순위가 비슷한 가중치를 가져야 함
    weights = [p.weight for p in result.priorities]
    expected_uniform = 100.0 / len(weights)
    assert all(abs(w - expected_uniform) < 5.0 for w in weights)


def test_correlations_to_weights_negative_correlations_clipped():
    """음수 상관계수는 0으로 clip."""
    base_cfg = _make_weight_config()
    correlations = {
        "per": -0.5,  # lower_better이므로, 음수는 좋은 신호 → 부호 반전 후 0 clip
        "roe": 0.8,
        "momentum_pct": -0.2,
        "score": 0.5,
    }

    result = correlations_to_weights(correlations, base_cfg, floor_pct=1.0)

    assert all(p.weight > 0 for p in result.priorities)
    total = sum(p.weight for p in result.priorities)
    assert abs(total - 100.0) < 0.01


def test_correlations_to_weights_lower_better_direction():
    """direction='lower_better'는 음수 상관계수가 좋은 신호."""
    base_cfg = WeightConfig(
        priorities=[
            Priority(
                key="per",
                weight=50.0,
                direction="lower_better",
                label="저PER",
            ),
            Priority(
                key="roe",
                weight=50.0,
                direction="higher_better",
                label="고ROE",
            ),
        ],
        must_have=[],
        strategy_weights={},
    )

    # per는 음수 상관 (낮을수록 높은 수익률), roe는 양수 상관
    correlations = {
        "per": -0.8,
        "roe": 0.5,
    }

    result = correlations_to_weights(correlations, base_cfg, floor_pct=1.0)

    # per가 direction 조정 후 0.8이 되므로, roe(0.5)보다 높은 가중치를 가져야 함
    per_weight = [p.weight for p in result.priorities if p.key == "per"][0]
    roe_weight = [p.weight for p in result.priorities if p.key == "roe"][0]
    assert per_weight > roe_weight


def test_correlations_to_weights_preserves_metadata():
    """must_have, strategy_weights 유지."""
    base_cfg = WeightConfig(
        priorities=[
            Priority(
                key="per",
                weight=50.0,
                direction="lower_better",
                label="저PER",
            ),
            Priority(
                key="roe",
                weight=50.0,
                direction="higher_better",
                label="고ROE",
            ),
        ],
        must_have=["per<30", "roe>=10"],
        strategy_weights={"strat_a": 0.5, "strat_b": 0.5},
    )

    correlations = {"per": 0.5, "roe": 0.8}

    result = correlations_to_weights(correlations, base_cfg, floor_pct=5.0)

    assert result.must_have == base_cfg.must_have
    assert result.strategy_weights == base_cfg.strategy_weights


def test_correlations_to_weights_partial_correlations():
    """일부 팩터만 correlations에 있을 때 나머지는 0으로 처리."""
    base_cfg = _make_weight_config()
    correlations = {
        "per": 0.5,
        "roe": 0.8,
        # momentum_pct, score는 없음 → 0으로 처리
    }

    result = correlations_to_weights(correlations, base_cfg, floor_pct=1.0)

    assert len(result.priorities) == len(base_cfg.priorities)
    assert all(p.weight > 0 for p in result.priorities)
    total = sum(p.weight for p in result.priorities)
    assert abs(total - 100.0) < 0.01
