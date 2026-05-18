"""Phase 2 Step 4: trade_plan_calc helper 단위 테스트.

- compute_trade_plan: k_adj 동적, r 비율 고정, support_floor floor, edge case
- resolve_base_strategy_id: REGISTRY 의 모든 variant 키 → 5 base 매핑
- STRATEGY_PARAMS: 5 base 전략만 (단일 위치 보장)
"""
import pytest

from core.trade_plan_calc import (
    STRATEGY_PARAMS,
    TradePlanParams,
    compute_trade_plan,
    resolve_base_strategy_id,
)


# ── STRATEGY_PARAMS 무결성 ────────────────────────────────────────────────────


def test_strategy_params_has_exactly_five_base_keys():
    expected = {
        "strategy_one", "strategy_two", "strategy_three",
        "strategy_four", "strategy_five",
    }
    assert set(STRATEGY_PARAMS.keys()) == expected


def test_strategy_params_values_are_dataclass_instances():
    for params in STRATEGY_PARAMS.values():
        assert isinstance(params, TradePlanParams)
        assert params.base_k_stop > 0
        assert params.r_target_1 > 0
        assert params.r_target_2 > 0


# ── resolve_base_strategy_id ────────────────────────────────────────────────


def test_resolve_base_handles_d_v2_variants():
    assert resolve_base_strategy_id("strategy_one_d_v2") == "strategy_one"
    assert resolve_base_strategy_id("strategy_one_w_v2") == "strategy_one"
    assert resolve_base_strategy_id("strategy_one_1h_v2") == "strategy_one"
    assert resolve_base_strategy_id("strategy_one_30m_v2") == "strategy_one"


def test_resolve_base_handles_r1_r2_fallbacks():
    assert resolve_base_strategy_id("strategy_one_d_v2_r1") == "strategy_one"
    assert resolve_base_strategy_id("strategy_one_30m_v2_r2") == "strategy_one"
    assert resolve_base_strategy_id("strategy_one_w_v2_r1") == "strategy_one"


def test_resolve_base_handles_full_descriptive_names():
    assert resolve_base_strategy_id("strategy_two_cross_sectional_momentum") == "strategy_two"
    assert resolve_base_strategy_id("strategy_three_trend_following") == "strategy_three"
    assert resolve_base_strategy_id("strategy_four_pullback_ma") == "strategy_four"
    assert resolve_base_strategy_id("strategy_five_bull_flag") == "strategy_five"


def test_resolve_base_handles_intraday_suffixes():
    assert resolve_base_strategy_id("strategy_two_30m") == "strategy_two"
    assert resolve_base_strategy_id("strategy_three_1h") == "strategy_three"
    assert resolve_base_strategy_id("strategy_four_pullback_ma_30m") == "strategy_four"
    assert resolve_base_strategy_id("strategy_five_bull_flag_1h") == "strategy_five"


def test_resolve_base_unknown_raises():
    with pytest.raises(KeyError):
        resolve_base_strategy_id("strategy_six_unknown")
    with pytest.raises(KeyError):
        resolve_base_strategy_id("")
    with pytest.raises(KeyError):
        resolve_base_strategy_id("other_prefix")


def test_resolve_base_covers_all_registry_keys():
    """REGISTRY 의 모든 키가 5 base 로 resolve 되는지 — STRATEGY_PARAMS 동기 보장."""
    from strategies import REGISTRY
    for key in REGISTRY.keys():
        base = resolve_base_strategy_id(key)
        assert base in STRATEGY_PARAMS, f"{key} → {base} not in STRATEGY_PARAMS"


# ── compute_trade_plan 핵심 동작 ────────────────────────────────────────────


def test_score_05_uses_base_k_unchanged():
    """score=0.5 면 k_adj = base × 1.0 = base."""
    r = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_five_bull_flag",
        score_percentile=0.5,
    )
    # base_k=1.5, k_adj = 1.5 × (1.3 - 0.6×0.5) = 1.5 × 1.0 = 1.5
    assert abs(r.k_used - 1.5) < 1e-9
    assert abs(r.stop - (10000 - 1.5 * 200)) < 1e-9  # 9700
    assert abs(r.risk - 300) < 1e-9
    # r2=3.0 → target_2 = entry + 3.0 × 300 = 10900
    assert abs(r.target_2 - 10900) < 1e-9


def test_score_high_tightens_stop():
    """score=1.0 → k_adj = base × 0.7 → stop 가까이."""
    r = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_five_bull_flag",
        score_percentile=1.0,
    )
    # 1.5 × (1.3 - 0.6) = 1.5 × 0.7 = 1.05
    assert abs(r.k_used - 1.05) < 1e-9
    assert r.stop > 10000 - 1.5 * 200  # 더 높은 stop (좁은 risk)


def test_score_low_widens_stop():
    """score=0.0 → k_adj = base × 1.3 → stop 멀리."""
    r = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_five_bull_flag",
        score_percentile=0.0,
    )
    # 1.5 × 1.3 = 1.95
    assert abs(r.k_used - 1.95) < 1e-9
    assert r.stop < 10000 - 1.5 * 200  # 더 낮은 stop (넓은 risk)


def test_score_clamps_above_one():
    r1 = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_two_30m",
        score_percentile=1.5,
    )
    r2 = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_two_30m",
        score_percentile=1.0,
    )
    assert abs(r1.k_used - r2.k_used) < 1e-9


def test_support_floor_caps_stop_from_below():
    """support_floor > 산정 stop 이면 floor 적용."""
    r = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_four_pullback_ma",
        score_percentile=0.0,  # k=2.34 → stop=9532
        support_floor=9700.0,  # 더 보수적
    )
    # floor 9700 > 9532 → stop = 9700
    assert abs(r.stop - 9700.0) < 1e-9


def test_support_floor_below_computed_stop_ignored():
    """support_floor < 산정 stop 이면 무시 (더 보수적인 쪽 유지)."""
    r = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_four_pullback_ma",
        score_percentile=1.0,  # k=1.26 → stop=9748
        support_floor=9000.0,  # 더 멀어서 무시
    )
    assert abs(r.stop - (10000 - 1.26 * 200)) < 1e-2


def test_support_floor_above_entry_raises():
    """floor 가 entry 이상이면 strategy 코드의 logic bug — silent 보정 대신 raise."""
    with pytest.raises(ValueError, match="support_floor"):
        compute_trade_plan(
            entry=10000.0, atr_14=200.0,
            strategy_id="strategy_three_trend_following",
            score_percentile=0.5,
            support_floor=10500.0,  # entry 위
        )


def test_r_target_proportional_to_risk():
    r = compute_trade_plan(
        entry=10000.0, atr_14=200.0,
        strategy_id="strategy_three_trend_following",
        score_percentile=0.5,
    )
    # base_k=1.8 score 0.5 → 1.8, stop=9640, risk=360, r1=1.0 r2=2.5
    assert abs(r.target_1 - (10000 + 360)) < 1e-9
    assert abs(r.target_2 - (10000 + 2.5 * 360)) < 1e-9


def test_invalid_entry_raises():
    with pytest.raises(ValueError):
        compute_trade_plan(
            entry=0.0, atr_14=200.0,
            strategy_id="strategy_one_d_v2", score_percentile=0.5,
        )


def test_invalid_atr_raises():
    with pytest.raises(ValueError):
        compute_trade_plan(
            entry=10000.0, atr_14=0.0,
            strategy_id="strategy_one_d_v2", score_percentile=0.5,
        )
