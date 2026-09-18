"""tests/test_strategy_six_unit.py — StrategySixChannelGrid 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.strategy_six_channel_grid import StrategySixChannelGrid, StrategySixConfig
from tests.fixtures_channel_grid import make_ctx, scenario_df


def test_시나리오는_후보_하나를_낸다():
    ctx = make_ctx({"TEST": scenario_df()})
    cands = StrategySixChannelGrid().scan(ctx, top_n=5)
    assert len(cands) == 1
    c = cands[0]
    assert c.ticker == "TEST"
    assert c.strategy == "strategy_six_channel_grid"
    assert c.metadata["touch_kind"] == "grid"
    assert c.metadata["grid_level"] == 0.5
    assert c.metadata["confluence"] is False
    assert c.metadata["target_confluence"] is True      # L(1) ≈ 지지선 S
    assert c.metadata["bars_since_trigger"] == 17       # 79 - 62
    assert c.metadata["trade_plan_method"] == "line_based"


def test_가격_불변식과_손익비():
    ctx = make_ctx({"TEST": scenario_df()})
    c = StrategySixChannelGrid().scan(ctx, top_n=5)[0]
    assert c.stop_loss < c.entry_price < c.target_1 <= c.target_2
    assert c.target_1 == c.target_2
    assert c.entry_price == 933
    assert (c.target_1 - c.entry_price) >= 1.0 * (c.entry_price - c.stop_loss)


def test_메타데이터_브리지_키():
    ctx = make_ctx({"TEST": scenario_df()})
    c = StrategySixChannelGrid().scan(ctx, top_n=5)[0]
    for key in ("source_strategy", "rr_ratio", "rr_band", "atr_14", "market"):
        assert key in c.metadata
    assert c.metadata["source_strategy"] == "strategy_six_channel_grid"
    assert c.metadata["rr_band"] in ("below", "sweet", "over")


def test_레지스트리에_자동_등록된다():
    from strategies import REGISTRY, available
    assert StrategySixChannelGrid.name in REGISTRY
    assert StrategySixChannelGrid.name in available()
    assert REGISTRY[StrategySixChannelGrid.name]().name == "strategy_six_channel_grid"


def test_일봉_외_타임프레임은_거부한다():
    assert StrategySixChannelGrid(timeframe="1D").name == "strategy_six_channel_grid"
    with pytest.raises(ValueError):
        StrategySixChannelGrid(timeframe="1h")


def test_잘못된_설정은_거부한다():
    with pytest.raises(ValueError):
        StrategySixChannelGrid(StrategySixConfig(lookback_bars=0))
    with pytest.raises(ValueError):
        StrategySixChannelGrid(StrategySixConfig(pivot_window=0))
