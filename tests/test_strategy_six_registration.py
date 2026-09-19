"""tests/test_strategy_six_registration.py — 예외 없이 조용히 누락되는 등록 지점 동기 검사."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

SID = "strategy_six_channel_grid"
SID_W = "strategy_six_channel_grid_w"
ROOT = Path(__file__).parent.parent


def test_weights_yml_세_표에_모두_등록된다():
    w = yaml.safe_load((ROOT / "weights.yml").read_text())
    assert SID in w["strategy_weights"]
    assert SID_W in w["strategy_weights"]
    for regime in ("BULL", "NEUTRAL", "BEAR",
                   "UPTREND_STRONG", "UPTREND_WEAK", "RANGE", "RANGE_TIGHT",
                   "DOWNTREND_WEAK", "DOWNTREND_STRONG", "MIXED"):
        assert SID in w["strategy_weights_by_regime"][regime], regime
        assert SID_W in w["strategy_weights_by_regime"][regime], regime
    assert w["strategy_weights_by_regime"]["DOWNTREND_STRONG"][SID] == 0.0
    assert w["strategy_weights_by_regime"]["DOWNTREND_STRONG"][SID_W] == 0.0


def test_signals_builder_기본_전략_라벨_가중치():
    from output.signals_builder import _STRATEGY_LABELS, _base_strategy, _build_market_configs
    assert _base_strategy(SID) == "strategy_six"
    assert _STRATEGY_LABELS[SID] == ("STRATEGY SIX", "CHANNEL GRID")
    assert _base_strategy(SID_W) == "strategy_six"
    assert _STRATEGY_LABELS[SID_W] == ("STRATEGY SIX", "CHANNEL GRID")
    for market, cfg in _build_market_configs().items():
        assert "strategy_six" in cfg.strategy_score_weights, market


def test_registry_에_주봉_변형이_등록된다():
    from strategies import REGISTRY
    assert REGISTRY[SID_W]().timeframe == "1W"


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


def test_wf_factory_와_compare_목록():
    from scripts.wf_strategy_compare import STRATEGIES
    from scripts.wf_validate_s2_to_s5 import _s6_factory
    strat = _s6_factory({"touch_atr_mult": 0.4})
    assert strat.name == SID and strat.config.touch_atr_mult == 0.4
    assert ("S6_ChannelGrid", _s6_factory) in STRATEGIES


def test_signal_components_여섯_개의_근거_칩():
    from output.signal_components import build_signal_components
    meta = {"bars_since_breakout": 17, "touch_kind": "grid", "grid_level": 0.5,
            "confluence": False, "target_kind": "grid", "target_level": 1.0,
            "target_confluence": True, "channel_width": 46.92, "atr_14": 6.44,
            "baseline_slope": -1.668}
    comps = build_signal_components(meta, SID)
    keys = [c["key"] for c in comps]
    assert keys == ["baseline_breakout", "line_touch", "confluence",
                     "target_line", "channel_width", "baseline_slope"]
    assert all(set(c) == {"key", "label", "status", "value"} for c in comps)
    assert comps[2]["status"] == "warn"          # 합류 없음 → warn
    assert comps[3]["value"] == "레벨 1.0 · 합류"
    assert comps[4]["value"] == "47원 (7.3×ATR)"
    assert comps[5]["value"] == "-1.67원/봉"
