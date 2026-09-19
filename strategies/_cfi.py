"""
strategies/_cfi.py — CFI(CLUVIC Favorite Indicator) 매매기법 순수 부품 (Strategy Seven 전용).

ScanContext/Candidate 를 모르는 numpy 함수만 둔다. 모든 인덱스는 전역 봉 인덱스.
원본은 TradingView Pine Script 지표의 tradeType == "CFI기법" 분기.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ._channel_grid import find_confirmed_pivots


def heikin_ashi(
    open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """실제 OHLC → 하이킨아시 OHLC. 반환 순서는 (open, high, low, close).

    ha_close = (o+h+l+c)/4
    ha_open[0] = (o[0]+c[0])/2, ha_open[i] = (ha_open[i-1]+ha_close[i-1])/2
    ha_high = max(high, ha_open, ha_close), ha_low = min(low, ha_open, ha_close)
    """
    open_ = np.asarray(open_, dtype=float)
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    close = np.asarray(close, dtype=float)

    ha_close = (open_ + high + low + close) / 4.0
    ha_open = np.empty_like(ha_close)
    ha_open[0] = (open_[0] + close[0]) / 2.0
    for i in range(1, len(ha_close)):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0
    ha_high = np.maximum(high, np.maximum(ha_open, ha_close))
    ha_low = np.minimum(low, np.minimum(ha_open, ha_close))
    return ha_open, ha_high, ha_low, ha_close


def cfi_direction(
    ha_high: np.ndarray, ha_low: np.ndarray, ha_close: np.ndarray, *, depth: int
) -> tuple[np.ndarray, np.ndarray]:
    """CFI 추세 방향(-1/+1)과 추적 손절선 tsl.

    원본 Pine 의 avdTR/avnTR/tslTR 에 해당한다. 방향은 직전 봉까지의 depth 봉 채널을
    현재 하이킨아시 종가가 넘을 때만 바뀌고, 그 사이에는 직전 값을 유지한다(초기값 -1).
    tsl 은 상승 방향이면 하단선(sup), 하락 방향이면 상단선(res).

    원본의 buyCond = crossover(closeHA, tslTR) 은 방향이 -1 에서 +1 로 바뀌는 봉과
    등가다. 하락 방향 구간에서는 tsl = res >= ha_high >= ha_close 라 돌파가 불가능하고,
    상승 방향 구간에서는 ha_close < sup 인 순간 방향이 뒤집히기 때문이다.
    """
    res = pd.Series(ha_high).rolling(depth).max().to_numpy()
    sup = pd.Series(ha_low).rolling(depth).min().to_numpy()
    n = len(ha_close)
    direction = np.full(n, -1, dtype=np.int8)
    cur = -1
    for i in range(1, n):
        r, s = res[i - 1], sup[i - 1]
        if not np.isnan(r) and ha_close[i] > r:
            cur = 1
        elif not np.isnan(s) and ha_close[i] < s:
            cur = -1
        direction[i] = cur
    tsl = np.where(direction == 1, sup, res)
    return direction, tsl


def volume_poc(
    high: np.ndarray, low: np.ndarray, volume: np.ndarray, *, lookback: int, bins: int
) -> float | None:
    """최근 lookback 봉 매물대의 POC 가격. 가격폭이 0 이면 None.

    각 봉의 거래량을 그 봉이 걸친 가격 구간에 균등 분배해 누적하고, 누적이 최대인
    구간의 중심 가격을 돌려준다. 원본 Pine 의 매물대(VPVR) 블록과 같은 방식.
    """
    h = np.asarray(high[-lookback:], dtype=float)
    lo = np.asarray(low[-lookback:], dtype=float)
    v = np.asarray(volume[-lookback:], dtype=float)
    top, bottom = float(h.max()), float(lo.min())
    if not (top > bottom):
        return None
    edges = np.linspace(bottom, top, bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2.0
    mask = (lo[:, None] < centers) & (h[:, None] > centers)
    spans = mask.sum(axis=1)
    ok = spans > 0
    if not ok.any():
        return None
    share = np.zeros(mask.shape, dtype=float)
    share[ok] = mask[ok] * (v[ok] / spans[ok])[:, None]
    dist = share.sum(axis=0)
    return float(centers[int(np.argmax(dist))])


def last_wave_fib(
    high: np.ndarray, low: np.ndarray, *, pivot_window: int, ratio: float
) -> float | None:
    """직전 파동(마지막 확정 저점·고점)의 피보나치 되돌림 가격. 없으면 None.

    원본 Pine 의 지그재그(lastLowZZ/lastHighZZ) + 직전파동 피보나치에 해당한다.
    원본 규약대로 0% 를 저점으로 두므로 가격은 저점 + ratio × (고점 - 저점).
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    hi_idx = find_confirmed_pivots(high, pivot_window, highs=True)
    lo_idx = find_confirmed_pivots(low, pivot_window, highs=False)
    if not hi_idx or not lo_idx:
        return None
    top = float(high[hi_idx[-1]])
    bottom = float(low[lo_idx[-1]])
    if top <= bottom:
        return None
    return bottom + ratio * (top - bottom)
