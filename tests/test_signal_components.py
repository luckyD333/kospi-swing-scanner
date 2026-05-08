"""전략 고유 신호 컴포넌트 빌더 단위 테스트.

각 전략의 metadata dict 가 입력일 때, 사용자가 보는 ✓/⚠ 컴포넌트 리스트가
어떻게 만들어지는지 검증한다. UI 표시용이므로 순서·라벨·값 형식까지 고정한다.
"""
from __future__ import annotations

from output.signal_components import build_signal_components


# ---------------------------------------------------------------------------
# 전략 1 — Mean Reversion (RSI + BB + 쌍바닥 + 장악형 양봉)
# ---------------------------------------------------------------------------

def test_strategy_one_full_triggers_all_ok():
    metadata = {
        "rsi_14": 28.5,
        "triggers_fired": [
            "bb_lower_breach", "bullish_engulfing", "double_bottom", "rsi_oversold",
        ],
        "confirmation_level": "STRONG",
    }
    components = build_signal_components(metadata, "strategy_one_d_v2")

    keys = [c["key"] for c in components]
    assert keys == ["rsi_oversold", "bb_lower_touch", "double_bottom", "bullish_engulfing"]
    assert all(c["status"] == "ok" for c in components)

    rsi = next(c for c in components if c["key"] == "rsi_oversold")
    assert rsi["label"] == "RSI 과매도"
    assert rsi["value"] == "28.5"


def test_strategy_one_rsi_warn_zone():
    metadata = {
        "rsi_14": 33.0,
        "triggers_fired": ["double_bottom"],
        "confirmation_level": "MEDIUM",
    }
    components = build_signal_components(metadata, "strategy_one_d_v2")
    rsi = next(c for c in components if c["key"] == "rsi_oversold")
    assert rsi["status"] == "warn"
    assert rsi["value"] == "33.0"


def test_strategy_one_missing_trigger_omitted():
    metadata = {"rsi_14": 28.5, "triggers_fired": ["double_bottom"]}
    components = build_signal_components(metadata, "strategy_one_d_v2")
    keys = {c["key"] for c in components}
    # bb_lower_touch / bullish_engulfing 은 triggers_fired 에 없음 → 미포함
    assert "bb_lower_touch" not in keys
    assert "bullish_engulfing" not in keys
    assert "double_bottom" in keys
    assert "rsi_oversold" in keys


def test_strategy_one_rsi_above_threshold_omitted():
    metadata = {"rsi_14": 50.0, "triggers_fired": ["double_bottom"]}
    components = build_signal_components(metadata, "strategy_one_d_v2")
    keys = {c["key"] for c in components}
    # 중립 RSI 는 컴포넌트에서 빠짐 (35 초과)
    assert "rsi_oversold" not in keys


def test_strategy_one_w_v2_uses_same_rules():
    metadata = {"rsi_14": 25.0, "triggers_fired": ["rsi_oversold", "double_bottom"]}
    components = build_signal_components(metadata, "strategy_one_w_v2")
    assert any(c["key"] == "rsi_oversold" for c in components)
    assert any(c["key"] == "double_bottom" for c in components)


def test_strategy_one_fallback_variant_r1_uses_same_rules():
    metadata = {"rsi_14": 25.0, "triggers_fired": ["double_bottom"]}
    components = build_signal_components(metadata, "strategy_one_d_v2_r1")
    keys = {c["key"] for c in components}
    assert "rsi_oversold" in keys
    assert "double_bottom" in keys


# ---------------------------------------------------------------------------
# 전략 2 — Cross-sectional Momentum
# ---------------------------------------------------------------------------

def test_strategy_two_strong_momentum():
    metadata = {"momentum_pct": 0.082, "percentile_rank": 0.91}
    components = build_signal_components(metadata, "strategy_two_cross_sectional_momentum")
    keys = [c["key"] for c in components]
    assert "momentum_15d" in keys
    assert "top_quartile" in keys

    mom = next(c for c in components if c["key"] == "momentum_15d")
    assert mom["status"] == "ok"
    assert mom["value"] == "+8.2%"

    rank = next(c for c in components if c["key"] == "top_quartile")
    assert rank["status"] == "ok"
    assert rank["value"] == "91%"


def test_strategy_two_weak_momentum_warn():
    metadata = {"momentum_pct": 0.018, "percentile_rank": 0.78}
    components = build_signal_components(metadata, "strategy_two_cross_sectional_momentum")
    mom = next(c for c in components if c["key"] == "momentum_15d")
    assert mom["status"] == "warn"


def test_strategy_two_negative_momentum_omitted():
    metadata = {"momentum_pct": -0.02, "percentile_rank": 0.5}
    components = build_signal_components(metadata, "strategy_two_cross_sectional_momentum")
    keys = {c["key"] for c in components}
    assert "momentum_15d" not in keys
    # percentile_rank < 0.75 도 omit
    assert "top_quartile" not in keys


# ---------------------------------------------------------------------------
# 전략 3 — Trend Following (Donchian)
# ---------------------------------------------------------------------------

def test_strategy_three_breakout_with_volume():
    metadata = {
        "breakout_pct": 0.024,
        "vol_ratio": 1.8,
        "channel_high": 50000,
        "channel_low": 45000,
    }
    components = build_signal_components(metadata, "strategy_three_trend_following")
    keys = [c["key"] for c in components]
    assert keys == ["donchian_breakout", "volume_surge"]

    breakout = components[0]
    assert breakout["status"] == "ok"
    assert breakout["label"] == "Donchian 20일 돌파"
    assert breakout["value"] == "+2.40%"

    vol = components[1]
    assert vol["status"] == "ok"
    assert vol["value"] == "1.8x"


def test_strategy_three_low_volume_warn():
    metadata = {"breakout_pct": 0.012, "vol_ratio": 1.1}
    components = build_signal_components(metadata, "strategy_three_trend_following")
    vol = next(c for c in components if c["key"] == "volume_surge")
    assert vol["status"] == "warn"


def test_strategy_three_30m_uses_same_rules():
    metadata = {"breakout_pct": 0.03, "vol_ratio": 2.0}
    components = build_signal_components(metadata, "strategy_three_30m")
    assert len(components) == 2


# ---------------------------------------------------------------------------
# 전략 4 — Pullback to MA
# ---------------------------------------------------------------------------

def test_strategy_four_components():
    metadata = {
        "above_ma20_pct": 1.5,
        "ma5": 51000,
        "ma20": 50000,
        "vol_ratio": 1.2,
    }
    components = build_signal_components(metadata, "strategy_four_pullback_ma")
    keys = [c["key"] for c in components]
    assert keys == ["ma20_uptrend", "ma5_pullback_recovery", "volume_confirm"]

    uptrend = components[0]
    assert uptrend["status"] == "ok"
    assert uptrend["label"] == "MA20 상승 추세"
    assert uptrend["value"] == "+1.5%"

    recovery = components[1]
    # 진입 조건상 항상 충족 (스캐너가 통과시킨 후보) → status=ok, value=None
    assert recovery["status"] == "ok"
    assert recovery["value"] is None

    vol = components[2]
    assert vol["status"] == "ok"
    assert vol["value"] == "1.2x"


def test_strategy_four_below_ma20_omitted():
    metadata = {"above_ma20_pct": -0.3, "ma5": 50000, "ma20": 50500, "vol_ratio": 1.0}
    components = build_signal_components(metadata, "strategy_four_pullback_ma")
    keys = {c["key"] for c in components}
    assert "ma20_uptrend" not in keys


# ---------------------------------------------------------------------------
# 전략 5 — Bull Flag
# ---------------------------------------------------------------------------

def test_strategy_five_components():
    metadata = {
        "pole_pct": 12.0,
        "flag_vol_ratio": 0.55,
        "breakout_pct": 1.8,
        "vol_ratio": 1.6,
    }
    components = build_signal_components(metadata, "strategy_five_bull_flag")
    keys = [c["key"] for c in components]
    assert keys == ["flagpole", "flag_consolidation", "breakout", "volume_expansion"]

    pole = components[0]
    assert pole["status"] == "ok"
    assert pole["label"] == "Flagpole 상승"
    assert pole["value"] == "+12.0%"

    consol = components[1]
    assert consol["status"] == "ok"
    assert consol["value"] == "55%"

    breakout = components[2]
    assert breakout["status"] == "ok"
    assert breakout["value"] == "+1.80%"

    vol = components[3]
    assert vol["status"] == "ok"
    assert vol["value"] == "1.6x"


def test_strategy_five_weak_pole_warn():
    metadata = {
        "pole_pct": 8.5,  # 8% 직선 살짝 위 → warn
        "flag_vol_ratio": 0.6,
        "breakout_pct": 1.0,
        "vol_ratio": 1.1,
    }
    components = build_signal_components(metadata, "strategy_five_bull_flag")
    pole = next(c for c in components if c["key"] == "flagpole")
    assert pole["status"] == "warn"


# ---------------------------------------------------------------------------
# 일반 동작 — 미지정 전략, metadata 누락, 'all' aggregator
# ---------------------------------------------------------------------------

def test_unknown_strategy_returns_empty():
    components = build_signal_components({"rsi_14": 28.5}, "strategy_unknown")
    assert components == []


def test_all_aggregator_returns_empty():
    """'all' 통합 entry 는 매칭별 표시이므로 컴포넌트 별도 산출하지 않는다."""
    components = build_signal_components({"rsi_14": 28.5}, "all")
    assert components == []


def test_empty_metadata_returns_empty_list():
    components = build_signal_components({}, "strategy_one_d_v2")
    assert components == []


def test_metadata_none_safe():
    components = build_signal_components(None, "strategy_one_d_v2")  # type: ignore[arg-type]
    assert components == []


def test_components_dict_shape():
    """반환 dict 는 key/label/status/value 4개 필드만 포함해 직렬화 안정성을 보장."""
    metadata = {"rsi_14": 28.5, "triggers_fired": ["rsi_oversold"]}
    components = build_signal_components(metadata, "strategy_one_d_v2")
    assert components, "RSI 과매도 컴포넌트가 산출되어야 한다"
    sample = components[0]
    assert set(sample.keys()) == {"key", "label", "status", "value"}
    assert sample["status"] in ("ok", "warn", "miss")
