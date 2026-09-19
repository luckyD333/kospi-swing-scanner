"""tests/test_strategy_seven_unit.py — StrategySevenCfi 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.price_utils import floor_to_tick
from strategies.strategy_seven_cfi import StrategySevenCfi, StrategySevenConfig
from tests.fixtures_channel_grid import make_ctx, make_df


def reversal_close() -> np.ndarray:
    """220봉 시나리오.

    0~149   1000 근처 좁은 횡보 → 매물대 POC 가 여기 형성된다.
    150~218 1150 → 1080 완만한 하락 → 방향이 -1 로 정착한다.
    219     1105 반등 → 직전 5봉 하이킨아시 채널 상단을 넘어 방향이 +1 로 바뀐다.
    """
    flat = 1000.0 + np.tile([0.0, 3.0, -3.0, 2.0, -2.0], 30)
    fall = np.linspace(1150.0, 1080.0, 69)
    return np.concatenate([flat, fall, [1105.0]])


def reversal_ctx(ticker: str = "TEST"):
    close = reversal_close()
    vol = np.full(len(close), 200_000.0)
    vol[-1] = 900_000.0
    return make_ctx({ticker: make_df(close, vol)})


def test_하락_후_상승_전환_봉에서_후보를_낸다():
    cands = StrategySevenCfi().scan(reversal_ctx(), top_n=5)

    assert len(cands) == 1
    c = cands[0]
    assert c.ticker == "TEST"
    assert c.strategy == "strategy_seven_cfi"
    assert c.metadata["direction_flipped"] is True
    assert c.metadata["tsl"] > 0
    assert c.metadata["poc"] is not None


def test_가격_불변식을_만족한다():
    c = StrategySevenCfi().scan(reversal_ctx(), top_n=5)[0]

    assert c.stop_loss < c.entry_price < c.target_1 <= c.target_2
    assert 0.0 <= c.score <= 1000.0


def test_tsl_을_손절가_하한으로_넘긴다():
    c = StrategySevenCfi().scan(reversal_ctx(), top_n=5)[0]

    assert c.metadata["trade_plan_support_floor"] == c.metadata["tsl"]
    assert c.metadata["trade_plan_method"] == "atr_dynamic"


def test_ATR_손절이_tsl_보다_타이트하면_ATR_손절이_채택된다():
    c = StrategySevenCfi().scan(reversal_ctx(), top_n=5)[0]
    m = c.metadata
    atr_stop = c.entry_price - m["k_used"] * m["atr_14"]

    assert m["tsl"] < atr_stop, "이 시나리오는 ATR 손절이 더 높은 경우다"
    assert c.stop_loss == floor_to_tick(atr_stop)


def test_tsl_이_ATR_손절보다_타이트하면_tsl_이_채택된다():
    # 톱니 하락으로 ATR 을 키우면 ATR 손절이 tsl 아래로 내려간다.
    flat = 1000.0 + np.tile([0.0, 3.0, -3.0, 2.0, -2.0], 30)
    saw = np.tile([20.0, -20.0, 10.0, -10.0, 0.0], 14)[:69]
    close = np.concatenate([flat, np.linspace(1150.0, 1080.0, 69) + saw, [1105.0]])
    vol = np.full(len(close), 200_000.0)
    vol[-1] = 900_000.0

    c = StrategySevenCfi().scan(make_ctx({"TEST": make_df(close, vol)}), top_n=5)[0]
    m = c.metadata
    atr_stop = c.entry_price - m["k_used"] * m["atr_14"]

    assert m["tsl"] > atr_stop, "이 시나리오는 tsl 이 더 높은 경우다"
    assert c.stop_loss == floor_to_tick(m["tsl"])


def test_상승_추세가_이어지는_봉에서는_후보를_내지_않는다():
    close = np.linspace(1000.0, 1400.0, 220)
    ctx = make_ctx({"TEST": make_df(close, np.full(220, 200_000.0))})

    assert StrategySevenCfi().scan(ctx, top_n=5) == []


def test_매물대와_피보_조건을_모두_놓치면_후보를_내지_않는다():
    # 매물대를 진입가 위로 올려 poc_ok 를 깨고, 피보 밴드를 0 으로 좁혀 fib_ok 를 깬다.
    close = reversal_close()
    close[:150] = 1300.0 + np.tile([0.0, 3.0, -3.0, 2.0, -2.0], 30)
    vol = np.full(len(close), 200_000.0)
    vol[:150] = 2_000_000.0
    ctx = make_ctx({"TEST": make_df(close, vol)})

    cfg = StrategySevenConfig(fib_band_atr_mult=0.0)
    assert StrategySevenCfi(config=cfg).scan(ctx, top_n=5) == []


def test_봉_수가_모자라면_건너뛴다():
    close = reversal_close()[-50:]
    ctx = make_ctx({"TEST": make_df(close, np.full(50, 200_000.0))})

    assert StrategySevenCfi().scan(ctx, top_n=5) == []


def test_종목_하나가_터져도_나머지_스캔은_계속된다():
    close = reversal_close()
    vol = np.full(len(close), 200_000.0)
    vol[-1] = 900_000.0
    good = make_df(close, vol)
    broken = good.copy()
    broken["close"] = np.nan

    ctx = make_ctx({"AAAAAA": broken, "TEST": good})
    out = StrategySevenCfi().scan(ctx, top_n=5)

    assert [c.ticker for c in out] == ["TEST"]


def test_레지스트리에_자동_등록된다():
    from strategies import REGISTRY, available

    assert StrategySevenCfi.name in REGISTRY
    assert StrategySevenCfi.name in available()
    assert REGISTRY[StrategySevenCfi.name]().name == "strategy_seven_cfi"


def test_지원하지_않는_시간대는_생성자에서_거부한다():
    with pytest.raises(ValueError, match="unsupported timeframe"):
        StrategySevenCfi(timeframe="1W")


def test_잘못된_설정값은_생성자에서_거부한다():
    with pytest.raises(ValueError, match="depth"):
        StrategySevenCfi(config=StrategySevenConfig(depth=1))
    with pytest.raises(ValueError, match="vp_lookback"):
        StrategySevenCfi(config=StrategySevenConfig(vp_lookback=0))
