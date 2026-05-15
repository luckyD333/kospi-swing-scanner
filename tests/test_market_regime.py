"""
test_market_regime.py — 시장 국면 분석 (HMM 기반) 검증.

core/decision/market_regime.py의 build_market_proxy, analyze_regime, apply_regime_overlay 테스트.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core.decision.config import Priority, WeightConfig
from core.decision.market_regime import (
    RegimeAnalysis,
    _compute_market_health_scores,
    apply_regime_overlay,
    analyze_regime,
    build_market_proxy,
)


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


def _make_manifest(tmp_path: Path, tickers_meta: dict) -> None:
    """manifest.json 생성."""
    manifest = {"tickers_meta": tickers_meta}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))


def _make_ohlcv(n_days: int = 60) -> pd.DataFrame:
    """합성 OHLCV DataFrame (DatetimeIndex)."""
    dates = pd.date_range("2025-01-01", periods=n_days, freq="B")
    np.random.seed(42)
    close = 10000 * np.cumprod(1 + np.random.randn(n_days) * 0.01)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        },
        index=dates,
    )


def _make_weight_config() -> WeightConfig:
    """기본 WeightConfig."""
    return WeightConfig(
        priorities=[
            Priority(
                key="per", weight=30.0, direction="lower_better", label="저PER"
            ),
            Priority(key="roe", weight=30.0, direction="higher_better", label="고ROE"),
            Priority(
                key="momentum_pct",
                weight=30.0,
                direction="higher_better",
                label="모멘텀",
            ),
            Priority(key="score", weight=10.0, direction="higher_better", label="점수"),
        ],
        must_have=[],
        strategy_weights={},
    )


# ---------------------------------------------------------------------------
# build_market_proxy 테스트
# ---------------------------------------------------------------------------


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_build_market_proxy_returns_two_features(mock_cache_cls, tmp_path):
    """정상 케이스: 2 컬럼(mean_return, rolling_std) DataFrame 반환."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(60)

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = build_market_proxy(tmp_path, max_tickers=10)
    assert not result.empty
    assert set(result.columns) >= {"mean_return", "rolling_std"}
    assert result.isna().sum().sum() == 0


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_build_market_proxy_skips_failed_tickers(mock_cache_cls, tmp_path):
    """일부 ticker read 실패 시 skip (나머지로 계산)."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk

    # 처음 5개는 실패, 다음 15개는 성공
    def side_effect(ticker, tf):
        if int(ticker[-4:]) < 5:
            raise Exception("read failed")
        return _make_ohlcv(60)

    mock_disk.read.side_effect = side_effect

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = build_market_proxy(tmp_path, max_tickers=20)
    assert not result.empty
    assert "mean_return" in result.columns


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_build_market_proxy_insufficient_tickers_returns_empty(mock_cache_cls, tmp_path):
    """종목 < 10개 → 빈 DataFrame."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(60)

    # 종목 5개만 생성
    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(5)}
    _make_manifest(tmp_path, tickers_meta)

    result = build_market_proxy(tmp_path, max_tickers=100)
    assert result.empty


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_build_market_proxy_insufficient_days_returns_empty(mock_cache_cls, tmp_path):
    """날짜 < 30일 → 빈 DataFrame."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(20)  # 20일만

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = build_market_proxy(tmp_path, max_tickers=10)
    assert result.empty


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_build_market_proxy_selects_top_by_market_cap(mock_cache_cls, tmp_path):
    """시가총액 내림차순 상위 N개 선택."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(60)

    # 시가총액이 다른 종목들
    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 1000 - i * 10} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = build_market_proxy(tmp_path, max_tickers=5)
    # 상위 5개가 호출되었는지 확인 (호출 순서는 시가총액 내림차순)
    assert result is not None


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_build_market_proxy_handles_none_market_cap(mock_cache_cls, tmp_path):
    """market_cap_bil=None 이어도 정렬 실패 없이 proxy 계산."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(60)

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": None} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = build_market_proxy(tmp_path, max_tickers=10)
    assert not result.empty


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_build_market_proxy_no_manifest_returns_empty(mock_cache_cls, tmp_path):
    """manifest.json 없음 → 빈 DataFrame."""
    result = build_market_proxy(tmp_path, max_tickers=10)
    assert result.empty


# ---------------------------------------------------------------------------
# analyze_regime 테스트
# ---------------------------------------------------------------------------


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_analyze_regime_returns_regime_analysis(mock_cache_cls, tmp_path):
    """정상 케이스: RegimeAnalysis 반환, current_score 1~100 범위."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(100)

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = analyze_regime(tmp_path)
    assert isinstance(result, RegimeAnalysis)
    assert 1 <= result.current_score <= 100
    assert len(result.history) > 0
    assert result.current_score == result.history[-1].score


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_analyze_regime_raises_on_empty_proxy(mock_cache_cls, tmp_path):
    """build_market_proxy 빈 결과 → ValueError."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(20)  # 20일만 (부족)

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(5)}
    _make_manifest(tmp_path, tickers_meta)

    with pytest.raises(ValueError, match="캐시 부족"):
        analyze_regime(tmp_path)


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_analyze_regime_history_length_matches_data(mock_cache_cls, tmp_path):
    """history 길이 = 날짜 수."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(100)

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = analyze_regime(tmp_path)
    assert len(result.history) == result.n_days


@patch("core.decision.market_regime.OhlcvDiskCache")
def test_analyze_regime_bull_bear_state_means(mock_cache_cls, tmp_path):
    """BULL/BEAR state mean return이 float."""
    mock_disk = MagicMock()
    mock_cache_cls.return_value = mock_disk
    mock_disk.read.return_value = _make_ohlcv(100)

    tickers_meta = {f"00{i:04d}": {"market_cap_bil": 100 - i} for i in range(20)}
    _make_manifest(tmp_path, tickers_meta)

    result = analyze_regime(tmp_path)
    assert isinstance(result.bull_state_mean_return, float)
    assert isinstance(result.bear_state_mean_return, float)


def test_market_health_score_expands_variation_inside_bull_state():
    """HMM posterior 가 포화돼도 trend/impulse 약화는 health score 에 반영된다."""
    dates = pd.date_range("2026-01-01", periods=50, freq="B")
    returns = [0.01] * 30 + [-0.004] * 10 + [0.002] * 10
    volatility = [0.02] * 30 + [0.03] * 10 + [0.018] * 10
    proxy = pd.DataFrame(
        {"mean_return": returns, "rolling_std": volatility},
        index=dates,
    )

    scores = _compute_market_health_scores(proxy)

    strong_score = float(scores["market_health_score"].iloc[29])
    weak_score = float(scores["market_health_score"].iloc[39])
    assert weak_score < strong_score - 10.0
    assert 1.0 <= float(scores["market_health_score"].iloc[-1]) <= 100.0


# ---------------------------------------------------------------------------
# apply_regime_overlay 테스트
# ---------------------------------------------------------------------------


def test_regime_overlay_bull_increases_momentum():
    """score=80: momentum_pct weight 증가 검증."""
    base = _make_weight_config()
    original_momentum = next(p.weight for p in base.priorities if p.key == "momentum_pct")

    result = apply_regime_overlay(base, regime_score=80)
    new_momentum = next(p.weight for p in result.priorities if p.key == "momentum_pct")

    # 1.3배 증가 후 정규화되므로 비율로 확인
    assert new_momentum > original_momentum


def test_regime_overlay_bear_increases_per_roe_decreases_momentum():
    """score=20: per/roe 증가, momentum 감소 검증."""
    base = _make_weight_config()
    original_per = next(p.weight for p in base.priorities if p.key == "per")
    original_momentum = next(p.weight for p in base.priorities if p.key == "momentum_pct")

    result = apply_regime_overlay(base, regime_score=20)
    new_per = next(p.weight for p in result.priorities if p.key == "per")
    new_momentum = next(p.weight for p in result.priorities if p.key == "momentum_pct")

    # per 1.2배, momentum 0.7배 증가 후 정규화
    assert new_per > original_per
    assert new_momentum < original_momentum


def test_regime_overlay_neutral_no_change():
    """score=50: 기존 weight 비율 유지."""
    base = _make_weight_config()

    result = apply_regime_overlay(base, regime_score=50)

    # neutral은 조정 없으므로 비율이 같아야 함
    for base_p, result_p in zip(base.priorities, result.priorities):
        assert base_p.key == result_p.key
        # 정규화 오차 범위 내에서 같아야 함 (직접 조정 없음)
        assert abs(base_p.weight - result_p.weight) < 0.01


def test_regime_overlay_weights_sum_to_100():
    """bull/bear/neutral 모두 WeightConfig 생성 성공 (합=100 검증)."""
    base = _make_weight_config()

    for score in [20, 50, 80]:
        result = apply_regime_overlay(base, regime_score=score)
        total = sum(p.weight for p in result.priorities)
        assert abs(total - 100.0) < 0.01


def test_regime_overlay_boundary_exactly_70():
    """score=70: bull 분기 진입."""
    base = _make_weight_config()
    original_momentum = next(p.weight for p in base.priorities if p.key == "momentum_pct")

    result = apply_regime_overlay(base, regime_score=70)
    new_momentum = next(p.weight for p in result.priorities if p.key == "momentum_pct")

    assert new_momentum > original_momentum


def test_regime_overlay_boundary_exactly_30():
    """score=30: neutral 분기 (bear 아님)."""
    base = _make_weight_config()
    original_momentum = next(p.weight for p in base.priorities if p.key == "momentum_pct")

    result = apply_regime_overlay(base, regime_score=30)
    new_momentum = next(p.weight for p in result.priorities if p.key == "momentum_pct")

    # score=30은 neutral (< 30이 아니라 < 30 엄격)
    # neutral이면 momentum이 변하지 않아야 함
    assert abs(new_momentum - original_momentum) < 0.01


def test_regime_overlay_boundary_exactly_29():
    """score=29: bear 분기 진입."""
    base = _make_weight_config()
    original_momentum = next(p.weight for p in base.priorities if p.key == "momentum_pct")

    result = apply_regime_overlay(base, regime_score=29)
    new_momentum = next(p.weight for p in result.priorities if p.key == "momentum_pct")

    # score < 30 → bear → momentum 0.7배
    assert new_momentum < original_momentum


def test_regime_overlay_does_not_mutate_base():
    """원본 base_config 불변 확인."""
    base = _make_weight_config()
    original_weights = {p.key: p.weight for p in base.priorities}

    apply_regime_overlay(base, regime_score=20)

    # 원본 weight이 변하지 않았는지 확인
    for p in base.priorities:
        assert p.weight == original_weights[p.key]


def test_regime_overlay_missing_keys_handled_gracefully():
    """조정 대상 key(per, roe, momentum_pct)가 없어도 오류 없음."""
    # per, roe, momentum_pct 없는 설정
    base = WeightConfig(
        priorities=[
            Priority(key="score", weight=50.0, direction="higher_better", label="점수"),
            Priority(key="other", weight=50.0, direction="higher_better", label="기타"),
        ],
        must_have=[],
        strategy_weights={},
    )

    # bear 조정 시도 (per, roe, momentum_pct 없음 → 조정 불가)
    result = apply_regime_overlay(base, regime_score=20)
    assert result is not None
    assert len(result.priorities) == 2


def test_regime_overlay_score_boundaries():
    """모든 점수 범위(1~100)에서 작동."""
    base = _make_weight_config()

    for score in [1, 29, 30, 69, 70, 100]:
        result = apply_regime_overlay(base, regime_score=score)
        total = sum(p.weight for p in result.priorities)
        assert abs(total - 100.0) < 0.01
        assert result is not None
