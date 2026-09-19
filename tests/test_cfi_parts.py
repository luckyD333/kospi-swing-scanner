"""tests/test_cfi_parts.py — strategies/_cfi.py 순수 부품 단위 테스트."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies._cfi import cfi_direction, heikin_ashi, last_wave_fib, volume_poc


def test_하이킨아시_첫봉은_시가종가평균이고_이후는_전봉누적이다():
    o = np.array([100.0, 110.0, 120.0])
    h = np.array([115.0, 125.0, 130.0])
    low = np.array([95.0, 105.0, 115.0])
    c = np.array([110.0, 120.0, 125.0])

    ha_open, ha_high, ha_low, ha_close = heikin_ashi(o, h, low, c)

    # ha_close = (o+h+l+c)/4
    assert ha_close == pytest.approx([105.0, 115.0, 122.5])
    # ha_open[0] = (100+110)/2 = 105, ha_open[1] = (105+105)/2 = 105, ha_open[2] = (105+115)/2 = 110
    assert ha_open == pytest.approx([105.0, 105.0, 110.0])
    # ha_high = max(high, ha_open, ha_close), ha_low = min(low, ha_open, ha_close)
    assert ha_high == pytest.approx([115.0, 125.0, 130.0])
    assert ha_low == pytest.approx([95.0, 105.0, 110.0])


def _ohlc_from_close(close: np.ndarray):
    return close - 1.0, close + 1.0, close - 2.0, close


def test_완만한_하락_뒤_반등봉에서_방향이_한_번만_상승으로_바뀐다():
    # 20봉 완만한 하락 + 마지막 1봉 반등 → 마지막 봉에서만 전환이 일어나야 한다.
    close = np.concatenate([np.linspace(110.0, 100.0, 20), [106.0]])
    o, h, low, c = _ohlc_from_close(close)

    _, ha_high, ha_low, ha_close = heikin_ashi(o, h, low, c)
    direction, tsl = cfi_direction(ha_high, ha_low, ha_close, depth=5)

    flips = [i for i in range(1, len(direction))
             if direction[i] == 1 and direction[i - 1] == -1]
    assert flips == [20], f"상승 전환은 마지막 봉 1회여야 한다: {flips}"
    assert direction[0] == -1, "초기 방향은 하락이다"
    # 상승 방향의 tsl 은 하단선이므로 하이킨아시 종가보다 낮다.
    assert tsl[20] < ha_close[20]


def test_급락_구간에서는_같은_폭_반등으로_전환되지_않는다():
    # 하이킨아시 시가는 하락을 지연해 따라오므로 급락일수록 채널 상단이 높게 남는다.
    # 반등 폭이 하락 기울기에 못 미치면 전환이 일어나지 않아야 한다.
    close = np.concatenate([np.linspace(200.0, 100.0, 20), [130.0]])
    o, h, low, c = _ohlc_from_close(close)

    _, ha_high, ha_low, ha_close = heikin_ashi(o, h, low, c)
    direction, _ = cfi_direction(ha_high, ha_low, ha_close, depth=5)

    assert direction[20] == -1, "30% 반등이어도 급락 구간 채널을 넘지 못한다"


def test_상승이_이어지는_구간에서는_전환이_재발화하지_않는다():
    close = np.linspace(100.0, 300.0, 40)
    o, h, low, c = _ohlc_from_close(close)

    _, ha_high, ha_low, ha_close = heikin_ashi(o, h, low, c)
    direction, _ = cfi_direction(ha_high, ha_low, ha_close, depth=5)

    flips = [i for i in range(1, len(direction))
             if direction[i] == 1 and direction[i - 1] == -1]
    assert len(flips) == 1, f"상승 일변도에서는 전환이 1회뿐이어야 한다: {flips}"
    assert direction[-1] == 1


def test_매물대는_거래량이_몰린_가격대를_돌려준다():
    # 앞 10봉이 1000 부근에서 거래량 10배 → POC 는 1000 부근.
    h = np.concatenate([np.full(10, 1005.0), np.full(20, 1200.0)])
    low = np.concatenate([np.full(10, 995.0), np.full(20, 1190.0)])
    v = np.concatenate([np.full(10, 10_000.0), np.full(20, 1_000.0)])

    poc = volume_poc(h, low, v, lookback=30, bins=100)

    assert poc is not None
    assert 995.0 <= poc <= 1005.0


def test_매물대는_가격폭이_0이면_None():
    h = np.full(30, 100.0)
    low = np.full(30, 100.0)
    v = np.full(30, 1_000.0)

    assert volume_poc(h, low, v, lookback=30, bins=100) is None


def test_직전파동_피보나치는_저점기준_비율가격이다():
    # V 자 뒤 상승. 저점 피벗은 인덱스 5(값 5), 고점 피벗은 인덱스 15(값 17).
    low = np.array([10, 9, 8, 7, 6, 5, 6, 7, 8, 9,
                    10, 11, 12, 13, 14, 15, 14, 13, 12, 11], dtype=float)
    h = low + 2.0

    fib = last_wave_fib(h, low, pivot_window=3, ratio=0.618)

    # 5 + 0.618 * (17 - 5) = 12.416
    assert fib == pytest.approx(12.416)


def test_직전파동_피벗이_없으면_None():
    # 단조 증가 → 좌우 확정 피벗 없음
    h = np.linspace(100.0, 200.0, 30)
    low = h - 5.0

    assert last_wave_fib(h, low, pivot_window=3, ratio=0.618) is None
