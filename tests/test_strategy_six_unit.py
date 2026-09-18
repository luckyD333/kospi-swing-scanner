"""tests/test_strategy_six_unit.py — StrategySixChannelGrid 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.strategy_six_channel_grid import StrategySixChannelGrid, StrategySixConfig
from tests.fixtures_channel_grid import make_ctx, make_df, scenario_close, scenario_df


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


def _scan(df):
    return StrategySixChannelGrid().scan(make_ctx({"TEST": df}), top_n=5)


def test_거래량_조건_없는_돌파는_게이트를_열지_않는다():
    df = scenario_df()
    df.loc[df.index[62], "volume"] = 200_000
    assert _scan(df) == []


def test_돌파_후_채널_복귀가_있으면_후보가_없다():
    df = scenario_df()
    df.loc[df.index[66], "close"] = 920.0
    assert _scan(df) == []


def test_선에_닿지_않으면_후보가_없다():
    close = scenario_close()
    close[79] = 940.0
    vol = [200_000] * 80
    vol[62] = 500_000
    assert _scan(make_df(close, vol)) == []          # 오늘 low 덮어쓰기 없음


def test_손익비가_1_미만이면_후보가_없다():
    close = scenario_close()
    close[79] = 940.0                                 # entry 940, 목표 944, 손절 926 → RR 0.29
    vol = [200_000] * 80
    vol[62] = 500_000
    df = make_df(close, vol)
    df.loc[df.index[-1], "low"] = 929.0
    assert _scan(df) == []


def test_오늘_신고가면_채널이_소멸해_후보가_없다():
    df = scenario_df()
    df.loc[df.index[-1], "high"] = 1010.0
    assert _scan(df) == []


def test_돌파일이_창_밖이면_후보가_없다():
    ctx = make_ctx({"TEST": scenario_df()})
    strat = StrategySixChannelGrid(StrategySixConfig(breakout_window_bars=10))  # 79-62=17 > 10
    assert strat.scan(ctx, top_n=5) == []


def test_재돌파는_돌파일을_갱신한다():
    """밴드 안 이탈(복귀 아님) 뒤 거래량 동반 재돌파 → d=71, bars_since_trigger 가 0 부터 다시 센다.

    주의: close[70]=920 으로 룩백 최저점 P 가 61 → 70 으로 옮겨가 지지선이 사라진다.
    따라서 이 변형에서는 target_confluence 가 False 다. 단언 대상이 아니므로 놀라지 말 것.
    실측: 터치선 L(0.5), 목표 944, 손절 925, RR 1.375 → 후보 1건.
    """
    close = scenario_close()
    close[70] = 920.0                                 # L0(70)=920.9 아래, L0-0.3ATR=918.4 위 → 복귀 아님
    close[71] = 940.0                                 # L0(71)+0.5ATR=923.9 위로 재돌파
    vol = [200_000] * 80
    vol[62] = 500_000
    vol[71] = 500_000
    df = make_df(close, vol)
    df.loc[df.index[-1], "low"] = 929.0
    cands = _scan(df)
    assert len(cands) == 1
    assert cands[0].metadata["breakout_day_idx"] == 71
    assert cands[0].metadata["bars_since_trigger"] == 8


def test_데이터_부족이면_빈_리스트():
    assert _scan(scenario_df().iloc[-70:]) == []      # min_bars 80 미달


def test_빈_유니버스():
    assert StrategySixChannelGrid().scan(make_ctx({}), top_n=5) == []


def test_top_n_으로_자른다():
    dfs = {f"T{i}": scenario_df() for i in range(4)}
    assert len(StrategySixChannelGrid().scan(make_ctx(dfs), top_n=2)) == 2
