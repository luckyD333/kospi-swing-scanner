"""tests/test_strategy_seven_registration.py — 전략 7 등록 지점 동기 검사.

누락되어도 예외 없이 조용히 실패하는 지점들을 한 곳에 하나씩 고정한다.
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

SID = "strategy_seven_cfi"
FAMILY = "strategy_seven"

_REGIMES_3 = ("BULL", "NEUTRAL", "BEAR")
_REGIMES_7 = ("UPTREND_STRONG", "UPTREND_WEAK", "RANGE_TIGHT", "RANGE",
              "DOWNTREND_WEAK", "DOWNTREND_STRONG", "MIXED")


def test_REGISTRY에_일봉_전략으로_등록된다():
    from strategies import REGISTRY, available

    assert SID in REGISTRY
    assert SID in available()
    assert REGISTRY[SID]().timeframe == "1D"


def test_entry_gate_정책에_7개_국면이_모두_있다():
    from core.decision.entry_gate import ENTRY_GATE_POLICY, _normalize_family

    policy = ENTRY_GATE_POLICY[FAMILY]
    for regime in _REGIMES_7:
        assert regime in policy, regime
    assert policy["DOWNTREND_STRONG"] == "block"
    assert _normalize_family(SID) == FAMILY


def test_trade_plan_정규식과_파라미터가_seven을_받는다():
    from core.trade_plan_calc import STRATEGY_PARAMS, resolve_base_strategy_id

    assert resolve_base_strategy_id(SID) == FAMILY
    assert STRATEGY_PARAMS[FAMILY].base_k_stop > 0


def test_인버스_제외_패밀리에_포함된다():
    from core.runner import _INVERSE_EXCLUDED_FAMILIES

    assert SID.startswith(_INVERSE_EXCLUDED_FAMILIES)


def test_weights_3표에_모두_등록되어_있다():
    data = yaml.safe_load((ROOT / "weights.yml").read_text(encoding="utf-8"))

    assert SID in data["strategy_weights"]
    by_regime = data["strategy_weights_by_regime"]
    for regime in _REGIMES_3 + _REGIMES_7:
        assert SID in by_regime[regime], regime
    assert by_regime["DOWNTREND_STRONG"][SID] == 0.0


def test_signals_builder_라벨과_가중치가_등록되어_있다():
    from output.signals_builder import _STRATEGY_LABELS, _base_strategy

    assert _base_strategy(SID) == FAMILY
    assert _STRATEGY_LABELS[SID] == ("STRATEGY SEVEN", "CFI REVERSAL")

    src = (ROOT / "output" / "signals_builder.py").read_text(encoding="utf-8")
    # KOSPI·KOSDAQ strategy_score_weights 2곳 + _base_strategy 튜플 1곳
    assert src.count(f'"{FAMILY}"') >= 3


def test_근거_칩_4개가_정해진_순서로_나온다():
    from output.signal_components import (
        _RULES_BY_BASE,
        _STRATEGY_ID_BASE,
        build_signal_components,
    )

    assert _STRATEGY_ID_BASE[SID] == FAMILY
    assert [r.key for r in _RULES_BY_BASE[FAMILY]] == [
        "ha_breakout", "dir_flip", "poc_above", "fib_touch"]

    metadata = {
        "atr_14": 20.0,
        "ha_channel_high": 1085.9,
        "breakout_strength": 1.0,
        "direction_flipped": True,
        "tsl": 1078.9,
        "poc": 997.1,
        "poc_above": True,
        "fib_618": 1091.88,
        "fib_touch": False,
    }
    chips = build_signal_components(metadata, SID)
    assert [c["key"] for c in chips] == [
        "ha_breakout", "dir_flip", "poc_above", "fib_touch"]
    for chip in chips:
        assert set(chip) == {"key", "label", "status", "value"}
    assert chips[0]["value"] == "채널 상단 +1.00×ATR"
    assert chips[1]["value"] == "tsl 1,079원 상향"
    assert chips[2]["value"] == "POC 997원 위"
    assert chips[3]["status"] == "warn"


def test_성과집계_키가_등록되어_있다():
    from core.strategy_performance import STRATEGY_DEFINITIONS, canonical_strategy_key

    assert STRATEGY_DEFINITIONS[FAMILY]["source_ids"] == (SID,)
    assert canonical_strategy_key(SID, "1D") == FAMILY


def test_holding_추천_키가_양방향으로_연결된다():
    from output.holding_recommender import (
        _BACKTEST_STRATEGY_KEYS,
        canonical_holding_strategy,
    )

    assert "S7_CfiReversal" in _BACKTEST_STRATEGY_KEYS
    assert canonical_holding_strategy(SID, "1D") == "S7_CfiReversal"


def test_UI_차트_3맵에_등록되어_있다():
    tsx = (ROOT / "signal-web" / "src" / "components"
           / "StrategyPerformanceChart.tsx").read_text(encoding="utf-8")

    assert "'strategy_seven'," in tsx
    assert tsx.count("strategy_seven:") >= 2


def test_walk_forward_비교_스크립트에_팩토리가_등록된다():
    import scripts.wf_strategy_compare as m

    names = [name for name, _ in m.STRATEGIES]
    assert "S7_CfiReversal" in names
