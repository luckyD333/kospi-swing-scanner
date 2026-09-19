"""tests/fixtures_channel_grid.py — Strategy Six 합성 시나리오 (80봉).

전역 인덱스 기준: A=22(high 1001.0), A~B 최저=31, B=40(high 970.97, 43에서 확정),
P=61(룩백 최저), d=62(레벨 0 돌파일, 거래량 조건 유일 충족), Q=73(P 이후 최고 저점 피벗),
오늘=79(레벨 0.5 를 위에서 터치, 종가 933 > L(0.5)=929.37).
실측: slope=-1.668/봉, W=46.92, ATR(79)=6.44, L(1)(79)=952.8 ≈ S(79)=954.0 (목표선 합류).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.strategy_base import ScanContext


def make_df(close_arr, vol_arr, high_mult=1.001, low_mult=0.999) -> pd.DataFrame:
    n = len(close_arr)
    c = pd.Series(close_arr, dtype=float)
    v = pd.Series(vol_arr, dtype=float)
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "open": c.values * 0.999,
            "high": c.values * high_mult,
            "low": c.values * low_mult,
            "close": c.values,
            "volume": v.values,
        },
        index=dates,
    )


def make_ctx(
    ticker_dfs: dict[str, pd.DataFrame],
    ohlcv_by_tf: dict[str, dict[str, pd.DataFrame]] | None = None,
) -> ScanContext:
    # ticker_dfs 가 비어있고 ohlcv_by_tf 만 주어지면(예: 1W 전용 시나리오) 그 tf 의
    # ticker 로 universe/names/market_caps 를 채운다.
    universe_dfs = ticker_dfs or (next(iter(ohlcv_by_tf.values())) if ohlcv_by_tf else {})
    kwargs = {"ohlcv_by_tf": ohlcv_by_tf} if ohlcv_by_tf is not None else {}
    return ScanContext(
        target_date="20260503",
        universe=tuple(universe_dfs.keys()),
        ohlcv=ticker_dfs,
        names={t: t for t in universe_dfs},
        market_caps={t: 5_000 * 1e8 for t in universe_dfs},
        market="KOSPI",
        **kwargs,
    )


def scenario_close() -> list[float]:
    return (
        list(np.linspace(900, 985, 20).round(0))                      # 0-19 패딩
        + [990, 995, 1000]                                            # 20-22, 22 = A
        + [993, 985, 978, 970, 962, 955, 948, 943, 940]               # 23-31, 31 = W 저점
        + [945, 950, 954, 958, 961, 964, 966, 968, 970]               # 32-40, 40 = B
        + [962, 958, 955, 950, 948, 945, 943, 940, 938, 936,
           934, 932, 931, 930, 929, 928, 928, 927, 927, 926, 925]     # 41-61, 61 = P
        + [950]                                                       # 62 = d
        + [955, 948, 942, 938, 945, 952, 960, 965, 958, 950,
           945, 950, 955, 948, 944, 940]                              # 63-78, 73 = Q
        + [933]                                                       # 79 = 오늘
    )


def scenario_df() -> pd.DataFrame:
    close = scenario_close()
    vol = [200_000] * 80
    vol[62] = 500_000
    df = make_df(close, vol)
    df.loc[df.index[-1], "low"] = 929.0
    return df
