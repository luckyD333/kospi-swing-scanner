"""tests/test_aggregate_holding_recommendations.py — Step 2 TDD.

modifier_table_by_regime: market_regime 별 modifier marginal 산출 검증.

기존 modifier_table 은 (label) aggregate marginal 이라 strategy-mix 효과가 섞임.
재설계: regime 별 segmenting → {regime: {label: delta}} nested.
"""
from __future__ import annotations


from scripts.aggregate_holding_recommendations import (
    modifier_table,
    modifier_table_by_regime,
)


def _make_trades(
    regime: str, label_key: str, label_value: str,
    holding: int, pnl: float, n: int,
) -> list[dict]:
    """동일 (regime, label_value, holding) trade n 개 반복."""
    return [
        {
            "strategy": "S1",
            "market_regime": regime,
            label_key: label_value,
            "holding_bars_config": holding,
            "pnl_pct": pnl,
        }
        for _ in range(n)
    ]


def test_modifier_table_by_regime_returns_nested_structure():
    """반환 구조가 {regime: {label_value: delta}} nested 인지 검증."""
    trades = (
        _make_trades("BULL", "atr_bucket", "LOW", holding=5, pnl=0.01, n=40)
        + _make_trades("BULL", "atr_bucket", "HIGH", holding=3, pnl=0.02, n=40)
        + _make_trades("NEUTRAL", "atr_bucket", "LOW", holding=7, pnl=0.005, n=40)
    )
    out = modifier_table_by_regime(
        trades, "atr_bucket", baseline_holding=5, min_n=30,
    )
    assert isinstance(out, dict)
    assert set(out.keys()).issubset({"BULL", "NEUTRAL", "BEAR"})
    assert "BULL" in out and "NEUTRAL" in out
    # BULL/LOW: best_holding=5 (유일), delta = 5-5 = 0
    assert out["BULL"]["LOW"] == 0
    # BULL/HIGH: best_holding=3, delta = 3-5 = -2
    assert out["BULL"]["HIGH"] == -2
    # NEUTRAL/LOW: best=7, delta=2
    assert out["NEUTRAL"]["LOW"] == 2


def test_modifier_table_by_regime_omits_low_sample_cells():
    """regime 내 label 의 trade 가 min_n 미달이면 셀이 제외된다."""
    trades = (
        _make_trades("BULL", "atr_bucket", "LOW", holding=5, pnl=0.01, n=40)
        + _make_trades("BEAR", "atr_bucket", "LOW", holding=3, pnl=0.005, n=10)  # 부족
    )
    out = modifier_table_by_regime(
        trades, "atr_bucket", baseline_holding=5, min_n=30,
    )
    assert "BULL" in out
    assert out["BULL"]["LOW"] == 0
    # BEAR 는 sample 부족 → 빈 dict 또는 키 부재
    assert out.get("BEAR", {}) == {}


def test_modifier_table_by_regime_picks_best_holding_per_cell():
    """동일 (regime, label) 에 여러 holding 후보가 있으면 mean_pnl 최대 holding 선택."""
    trades = (
        _make_trades("BULL", "atr_bucket", "MID", holding=1, pnl=0.001, n=35)
        + _make_trades("BULL", "atr_bucket", "MID", holding=5, pnl=0.020, n=35)
        + _make_trades("BULL", "atr_bucket", "MID", holding=7, pnl=0.010, n=35)
    )
    out = modifier_table_by_regime(
        trades, "atr_bucket", baseline_holding=5, min_n=30,
    )
    # best holding = 5 (mean_pnl 0.020 최대) → delta = 0
    assert out["BULL"]["MID"] == 0


def test_modifier_table_legacy_still_returns_flat():
    """기존 modifier_table 은 v1.0 호환을 위해 flat 구조 유지."""
    trades = _make_trades("BULL", "atr_bucket", "LOW", holding=5, pnl=0.01, n=40)
    out = modifier_table(trades, "atr_bucket", baseline_holding=5, min_n=30)
    # flat: {label: delta}
    assert "LOW" in out
    assert out["LOW"] == 0
