"""
test_core_indicators.py — core/indicators.py 헬퍼 검증.

backtest_engine.core 의 RSI/BB/MACD/ATR 는 별도 테스트로 검증되었으므로 여기선
신규 추가된 helper 만 테스트한다.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from core.indicators import (
    calc_atr,
    calc_bollinger,
    calc_macd,
    calc_rsi,  # 재export 확인용
    momentum_pct,
    moving_average,
    volume_zscore,
)


def test_re_exports_match_backtest_engine():
    """core.indicators 가 backtest_engine.core 함수를 그대로 노출"""
    from backtest_engine.core import (
        calc_atr as bt_atr,
    )
    from backtest_engine.core import (
        calc_bollinger as bt_bb,
    )
    from backtest_engine.core import (
        calc_macd as bt_macd,
    )
    from backtest_engine.core import (
        calc_rsi as bt_rsi,
    )
    assert calc_rsi is bt_rsi
    assert calc_bollinger is bt_bb
    assert calc_macd is bt_macd
    assert calc_atr is bt_atr


def test_moving_average_window_5():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
    ma = moving_average(s, period=5)
    # 처음 4개는 NaN (min_periods=5)
    assert ma.iloc[:4].isna().all()
    # 5번째 = (1+2+3+4+5)/5 = 3.0
    assert ma.iloc[4] == pytest.approx(3.0)
    # 마지막 = (6+7+8+9+10)/5 = 8.0
    assert ma.iloc[-1] == pytest.approx(8.0)


def test_momentum_pct_basic():
    s = pd.Series([100, 105, 110, 121], dtype=float)
    m = momentum_pct(s, lookback=2)
    # 0,1번 NaN, 2번 = 110/100 - 1 = 0.10
    assert math.isnan(m.iloc[0]) and math.isnan(m.iloc[1])
    assert m.iloc[2] == pytest.approx(0.10)
    # 3번 = 121/105 - 1
    assert m.iloc[3] == pytest.approx(121/105 - 1)


def test_momentum_pct_invalid_lookback():
    s = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        momentum_pct(s, lookback=0)
    with pytest.raises(ValueError):
        momentum_pct(s, lookback=-1)


def test_volume_zscore_basic():
    # 마지막 값이 평균보다 높을 때 양의 z-score
    vol = pd.Series([100] * 19 + [200], dtype=float)
    z = volume_zscore(vol, window=20)
    assert math.isnan(z.iloc[-2])  # window 미달
    assert z.iloc[-1] > 0


def test_volume_zscore_zero_std_returns_nan():
    """std==0 (모든 값이 동일)이면 0 division 회피해 NaN 반환."""
    vol = pd.Series([100] * 25, dtype=float)
    z = volume_zscore(vol, window=20)
    assert z.iloc[-1] is np.nan or math.isnan(z.iloc[-1])


def test_volume_zscore_invalid_window():
    vol = pd.Series([1.0, 2.0, 3.0])
    with pytest.raises(ValueError):
        volume_zscore(vol, window=1)
    with pytest.raises(ValueError):
        volume_zscore(vol, window=0)
