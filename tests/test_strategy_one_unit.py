"""
test_strategy_one_unit.py — StrategyOneDv2 단위 테스트.

회귀 테스트는 snapshot 비교가 담당. 여기선 단위 동작 (volume 필터, detector
선택, 빈 universe, ticker 순서 보존)만 검증.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from backtest_engine.scenarios import ScenarioBuilder
from core.strategy_base import ScanContext
from strategies.strategy_one_d_v2 import StrategyOneDv2, StrategyOneDv2Config


def _make_ctx(ticker_dfs: dict[str, pd.DataFrame], names=None, caps=None) -> ScanContext:
    return ScanContext(
        target_date="20260418",
        universe=tuple(ticker_dfs.keys()),
        ohlcv=ticker_dfs,
        names=names or {t: t for t in ticker_dfs},
        market_caps=caps or {t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
    )


def test_perfect_double_bottom_emits_signal():
    """ScenarioBuilder.perfect_double_bottom 시나리오는 진입 시그널 발생해야 함."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]  # 진입봉 (snapshot 캡처와 동일 슬라이싱)
    ctx = _make_ctx({"TEST": df})

    strat = StrategyOneDv2()
    candidates = strat.scan(ctx, top_n=5)

    assert len(candidates) == 1
    c = candidates[0]
    assert c.ticker == "TEST"
    assert 550.0 <= c.score <= 1000.0
    assert c.stop_loss < c.entry_price < c.target_1


def test_uptrend_scenario_emits_no_signal():
    """no_signal_uptrend 시나리오는 진입 조건 미충족."""
    scenario = ScenarioBuilder.no_signal_uptrend(seed=99)
    ctx = _make_ctx({"TEST": scenario.df})

    strat = StrategyOneDv2()
    candidates = strat.scan(ctx, top_n=5)
    assert candidates == []


def test_volume_filter_excludes_low_volume_tickers():
    """min_daily_volume 미만 ticker 는 스킵."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33].copy()
    df["volume"] = 100   # 매우 낮음
    ctx = _make_ctx({"LOW": df})

    strat = StrategyOneDv2(StrategyOneDv2Config(min_daily_volume=100_000))
    candidates = strat.scan(ctx, top_n=5)
    assert candidates == []


def test_top_n_cut():
    """top_n 보다 많은 시그널이 나오면 잘라내야 함."""
    scenarios = [ScenarioBuilder.perfect_double_bottom(seed=s) for s in [1, 2, 3, 4]]
    dfs = {f"T{i}": s.df.iloc[:33] for i, s in enumerate(scenarios)}
    ctx = _make_ctx(dfs)

    strat = StrategyOneDv2()
    candidates = strat.scan(ctx, top_n=2)
    assert len(candidates) == 2


def test_strategy_name_constant():
    """REGISTRY 키 안정성을 위해 name 은 strategy_one_d_v2."""
    assert StrategyOneDv2.name == "strategy_one_d_v2"


def test_invalid_detector_name_raises():
    with pytest.raises(ValueError):
        StrategyOneDv2(StrategyOneDv2Config(detector_name="bogus"))


def test_empty_universe_returns_empty():
    ctx = _make_ctx({})
    strat = StrategyOneDv2()
    assert strat.scan(ctx, top_n=10) == []


def test_candidate_metadata_has_bridge_keys():
    """Candidate.metadata에 source_strategy, rr_ratio, rr_band, atr_14 키 포함."""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.iloc[:33]
    ctx = _make_ctx({"TEST": df})

    strat = StrategyOneDv2()
    candidates = strat.scan(ctx, top_n=5)

    assert len(candidates) == 1
    c = candidates[0]

    # 신규 4개 키 검증
    assert "source_strategy" in c.metadata
    assert c.metadata["source_strategy"] == "strategy_one_d_v2"

    assert "rr_ratio" in c.metadata
    assert isinstance(c.metadata["rr_ratio"], (int, float))
    assert c.metadata["rr_ratio"] >= 0.0

    assert "rr_band" in c.metadata
    assert c.metadata["rr_band"] in ("sweet", "over", "below")

    assert "atr_14" in c.metadata
    # atr_14은 float 또는 None 가능 (데이터 부족 시)
    assert c.metadata["atr_14"] is None or isinstance(c.metadata["atr_14"], (int, float))
