"""tests/test_aggregate_holding_recommendations.py — Step 2 TDD.

modifier_table_by_regime: market_regime 별 modifier marginal 산출 검증.

기존 modifier_table 은 (label) aggregate marginal 이라 strategy-mix 효과가 섞임.
재설계: regime 별 segmenting → {regime: {label: delta}} nested.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.aggregate_holding_recommendations import (
    modifier_table,
    modifier_table_by_regime,
    primary_table,
    resolve_date_range,
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


def _trades(strategy: str, regime: str, holding: int, pnls: list[float]) -> list[dict]:
    return [
        {
            "strategy": strategy,
            "market_regime": regime,
            "holding_bars_config": holding,
            "pnl_pct": p,
        }
        for p in pnls
    ]


def test_후보가_전부_음수인_셀은_제외한다():
    """S6/BULL 실제 사례 — 4개 후보 평균이 모두 음수면 셀 자체를 버린다."""
    trades = (
        _trades("S6_ChannelGrid", "BULL", 1, [-0.01] * 30)
        + _trades("S6_ChannelGrid", "BULL", 7, [-0.002] * 30)
    )

    result = primary_table(trades, min_n=30)

    assert "S6_ChannelGrid" not in result


def test_양수_후보가_하나라도_있으면_그것을_고른다():
    trades = (
        _trades("S3_TrendFollowing", "NEUTRAL", 1, [-0.01] * 30)
        + _trades("S3_TrendFollowing", "NEUTRAL", 5, [0.012] * 30)
    )

    result = primary_table(trades, min_n=30)

    assert result["S3_TrendFollowing"]["NEUTRAL"]["best"] == 5
    assert result["S3_TrendFollowing"]["NEUTRAL"]["mean_pnl"] > 0


def test_평균_손익이_정확히_0_인_셀도_제외한다():
    """Review Focus 4 — 수수료를 뺀 뒤 본전이면 추천할 이유가 없다."""
    trades = _trades("S7_CfiReversal", "NEUTRAL", 3, [0.0] * 30)

    result = primary_table(trades, min_n=30)

    assert result == {}


def test_거래_건수_미달은_기존대로_제외한다():
    trades = _trades("S1_MeanReversion", "NEUTRAL", 3, [0.05] * 29)

    result = primary_table(trades, min_n=30)

    assert result == {}


def test_캐시_구간에서_날짜를_유도한다():
    data = {
        "005930": pd.DataFrame(
            {"close": [1.0, 2.0, 3.0]},
            index=pd.to_datetime(["2025-06-02", "2026-01-05", "2026-09-18"]),
        ),
        "000660": pd.DataFrame(
            {"close": [1.0, 2.0]},
            index=pd.to_datetime(["2025-05-30", "2026-09-19"]),
        ),
    }

    start, end = resolve_date_range(data, None, None, cache_root=Path(".cache_wf"))

    assert start == "2025-05-30"
    assert end == "2026-09-19"


def test_명시한_날짜가_캐시보다_우선한다():
    data = {
        "005930": pd.DataFrame(
            {"close": [1.0]}, index=pd.to_datetime(["2025-06-02"]),
        ),
    }

    start, end = resolve_date_range(
        data, "2025-01-01", "2025-12-31", cache_root=Path(".cache_wf"),
    )

    assert start == "2025-01-01"
    assert end == "2025-12-31"


def test_한쪽_날짜만_주면_나머지는_캐시에서_채운다():
    """Review Focus 3 — "이 날짜부터 지금까지" 가 가장 흔한 사용법이다."""
    data = {
        "005930": pd.DataFrame(
            {"close": [1.0, 2.0]},
            index=pd.to_datetime(["2025-06-02", "2026-09-18"]),
        ),
    }

    start, end = resolve_date_range(
        data, "2026-01-01", None, cache_root=Path(".cache_wf"),
    )

    assert start == "2026-01-01"
    assert end == "2026-09-18"


def test_캐시가_비면_오류를_낸다():
    with pytest.raises(SystemExit) as excinfo:
        resolve_date_range({}, None, None, cache_root=Path(".cache_wf"))

    assert excinfo.value.code == 1
