"""tests/test_strategy_six_registration.py — 예외 없이 조용히 누락되는 등록 지점 동기 검사."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

SID = "strategy_six_channel_grid"
ROOT = Path(__file__).parent.parent


def test_weights_yml_세_표에_모두_등록된다():
    w = yaml.safe_load((ROOT / "weights.yml").read_text())
    assert SID in w["strategy_weights"]
    for regime in ("BULL", "NEUTRAL", "BEAR",
                   "UPTREND_STRONG", "UPTREND_WEAK", "RANGE", "RANGE_TIGHT",
                   "DOWNTREND_WEAK", "DOWNTREND_STRONG", "MIXED"):
        assert SID in w["strategy_weights_by_regime"][regime], regime
    assert w["strategy_weights_by_regime"]["DOWNTREND_STRONG"][SID] == 0.0


def test_signals_builder_기본_전략_라벨_가중치():
    from output.signals_builder import _STRATEGY_LABELS, _base_strategy, _build_market_configs
    assert _base_strategy(SID) == "strategy_six"
    assert _STRATEGY_LABELS[SID] == ("STRATEGY SIX", "CHANNEL GRID")
    for market, cfg in _build_market_configs().items():
        assert "strategy_six" in cfg.strategy_score_weights, market


def test_strategy_performance_canonical_key():
    from core.strategy_performance import STRATEGY_DEFINITIONS, canonical_strategy_key
    assert canonical_strategy_key(SID, "1D") == "strategy_six"
    assert STRATEGY_DEFINITIONS["strategy_six"]["label"] == "Strategy Six"


def test_holding_recommender_백테스트_키():
    from output.holding_recommender import _BACKTEST_STRATEGY_KEYS, canonical_holding_strategy
    assert canonical_holding_strategy(SID, "1D") == "S6_ChannelGrid"
    assert "S6_ChannelGrid" in _BACKTEST_STRATEGY_KEYS


def test_성과_차트_세_맵에_등록된다():
    tsx = (ROOT / "signal-web/src/components/StrategyPerformanceChart.tsx").read_text()
    assert "'strategy_six'," in tsx                      # STRATEGY_ORDER
    assert tsx.count("strategy_six:") >= 2               # STRATEGY_COLORS + FALLBACK_LABELS
