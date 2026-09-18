"""tests/test_strategy_six_unit.py — StrategySixChannelGrid 단위 테스트."""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.strategy_six_channel_grid import StrategySixChannelGrid, StrategySixConfig
from tests.fixtures_channel_grid import make_ctx, make_df, scenario_close, scenario_df

KST = ZoneInfo("Asia/Seoul")


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
    assert c.metadata["bars_since_breakout"] == 17      # 79 - 62
    assert c.metadata["bars_since_trigger"] == 0        # 진입 계기 = 오늘의 터치
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
    """밴드 안 이탈(복귀 아님) 뒤 거래량 동반 재돌파 → d=71, bars_since_breakout 가 0 부터 다시 센다.

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
    assert cands[0].metadata["bars_since_breakout"] == 8


def test_데이터_부족이면_빈_리스트():
    assert _scan(scenario_df().iloc[-70:]) == []      # min_bars 80 미달


def test_빈_유니버스():
    assert StrategySixChannelGrid().scan(make_ctx({}), top_n=5) == []


def _vol():
    v = [200_000] * 80
    v[62] = 500_000
    return v


def test_점수_내림차순으로_정렬한_뒤_top_n_으로_자른다():
    close = scenario_close()
    close[79] = 907.0
    high_df = make_df(close, _vol())
    high_df.loc[high_df.index[-1], "low"] = 906.0   # score 700
    ctx = make_ctx({"LOW": scenario_df(), "HIGH": high_df})   # LOW 는 score 500
    strat = StrategySixChannelGrid()
    assert [c.ticker for c in strat.scan(ctx, top_n=1)] == ["HIGH"]
    assert [c.score for c in strat.scan(ctx, top_n=2)] == [700.0, 500.0]


def test_기본_시나리오_점수는_400_기본에_거래량_100():
    c = _scan(scenario_df())[0]
    assert c.score == 500.0                       # 400 + 합류 0 + 실측선 0 + 거래량 100


def test_레벨0_터치는_실측선_보너스_200을_받는다():
    close = scenario_close()
    close[79] = 907.0                             # L0(79)=905.9 를 위에서 터치
    df = make_df(close, _vol())
    df.loc[df.index[-1], "low"] = 906.0
    c = _scan(df)[0]
    assert c.score == 700.0                       # 400 + 200 + 거래량 100
    assert c.metadata["grid_level"] == 0.0
    assert c.metadata["touch_kind"] == "grid"
    assert (c.entry_price, c.target_1, c.stop_loss) == (907, 921, 901)


def test_지지선이_터치선과_겹치면_합류_보너스_300을_받는다():
    df = scenario_df()
    df.loc[df.index[66], "low"] = 920.0           # 룩백 최저점 P 를 66 으로 이동
    df.loc[df.index[73], "low"] = 925.0           # S(79)=929.29 ≈ L(0.5)(79)=929.37
    c = _scan(df)[0]
    assert c.score == 800.0                       # 400 + 300 + 거래량 100
    assert c.metadata["confluence"] is True
    assert c.metadata["touch_kind"] == "grid"
    assert c.metadata["grid_level"] == 0.5
    assert (c.target_1, c.stop_loss) == (944, 925)


def test_지지선_터치는_실측선과_합류_보너스를_모두_받아_상한에_닿는다():
    df = scenario_df()
    df.loc[df.index[66], "low"] = 920.0
    df.loc[df.index[73], "low"] = 926.0           # S(79)=931.14 > L(0.5)(79) → 지지선이 터치선
    c = _scan(df)[0]
    assert c.score == 1000.0                      # 400 + 300 + 200 + 100, 상한과 정확히 일치
    assert c.metadata["touch_kind"] == "support"
    assert c.metadata["grid_level"] is None
    assert c.metadata["confluence"] is True
    assert (c.entry_price, c.target_1, c.stop_loss) == (933, 944, 927)


def test_보유_상한_시점에_목표선이_진입가_아래면_후보가_없다():
    """L(1)(79)=952.83 은 진입가 946 위지만 5봉 뒤 944.49 로 내려온다."""
    close = scenario_close()
    close[79] = 946.0
    df = make_df(close, _vol())
    df.loc[df.index[-1], "low"] = 929.0
    assert _scan(df) == []


def test_국면이_차단하면_후보가_없다():
    """RANGE 는 추세 계열 차단 국면. 전략이 self.name 을 게이트에 넘기는지 확인한다."""
    ctx = make_ctx({"TEST": scenario_df()})
    ctx.per_ticker_regime["TEST"] = "RANGE"
    assert StrategySixChannelGrid().scan(ctx, top_n=5) == []


def _df_with_incomplete_today_bar():
    """80봉 시나리오 뒤에 오늘자 미완료 봉 1개를 붙이고 인덱스를 오늘로 맞춘다.

    is_today_bar_complete 가 실제 오늘 날짜(KST)와 비교하므로 인덱스 재배치가 필수다.
    붙이는 봉은 고가 1010 이라 그대로 쓰이면 채널이 소멸해 후보가 사라진다 —
    가드가 이 봉을 잘라 냈는지 결과로 구분할 수 있다.
    """
    df = scenario_df()
    extra = df.iloc[[-1]].copy()
    extra["close"] = 1005.0
    extra["high"] = 1010.0
    df2 = pd.concat([df, extra])
    df2.index = pd.date_range(end=pd.Timestamp(datetime.now(KST).date()),
                              periods=len(df2), freq="D")
    return df2


def test_미완료_봉은_잘라내고_어제_종가로_산출한다():
    ctx = make_ctx({"TEST": _df_with_incomplete_today_bar()})
    ctx.meta["manifest_collected_at"] = datetime.now(KST).replace(hour=11, minute=0).isoformat()
    cands = StrategySixChannelGrid().scan(ctx, top_n=5)
    assert len(cands) == 1
    assert cands[0].entry_price == 933              # 기준 시나리오와 동일
    assert cands[0].score == 500.0


def test_종가_확정_후에는_마지막_봉을_그대로_쓴다():
    """15:30 이후 수집이면 고가 1010 봉이 살아 채널이 소멸한다."""
    ctx = make_ctx({"TEST": _df_with_incomplete_today_bar()})
    ctx.meta["manifest_collected_at"] = datetime.now(KST).replace(hour=16, minute=0).isoformat()
    assert StrategySixChannelGrid().scan(ctx, top_n=5) == []


def test_한_종목이_실패해도_나머지_후보는_살아남는다(caplog):
    bad = scenario_df().drop(columns=["volume"])   # _scan_one 이 KeyError
    ctx = make_ctx({"BAD": bad, "TEST": scenario_df()})
    with caplog.at_level(logging.DEBUG, logger="strategies.strategy_six_channel_grid"):
        cands = StrategySixChannelGrid().scan(ctx, top_n=5)
    assert [c.ticker for c in cands] == ["TEST"]
    assert sum("BAD" in r.getMessage() for r in caplog.records) == 1


def test_목표선이_지지선일_수_있다():
    df = scenario_df()
    df.loc[df.index[66], "low"] = 920.0
    df.loc[df.index[73], "low"] = 931.5             # S(79)=941.36 이 L(1) 보다 진입가에 가깝다
    c = _scan(df)[0]
    assert c.metadata["target_kind"] == "support"
    assert c.metadata["target_level"] is None
    assert c.target_1 == 941
