"""
core/decision/per_ticker_regime.py — 일봉 Donchian 기반 7단계 regime 분류.

종목별 1d DonchianFrame → UPTREND_STRONG/WEAK, RANGE_TIGHT, RANGE,
DOWNTREND_WEAK/STRONG, MIXED 분류.

위계 원칙:
  - 1d: "이 종목 매수해도 되는 환경인가?" (Yes/No 게이트)
  - 1h: 셋업 품질 점수 (메타)

경계값 캘리브레이션 (Phase 2 튜닝 포인트):
  - POSITION_STRONG_UP = 0.70 (strong uptrend 하한)
  - POSITION_WEAK_UP = 0.55 (weak uptrend 하한)
  - POSITION_WEAK_DOWN = 0.30 (weak downtrend 상한, range 경계)
  - POSITION_STRONG_DOWN = 0.15 (strong downtrend 상한)
  - WIDTH_TIGHT_THRESHOLD = 0.4 (에너지 응축 임계값)
"""
from __future__ import annotations

import math

import pandas as pd

from core.decision.donchian import DonchianFrame, compute_donchian

# --- Threshold constants (캘리브레이션 가능) ---
POSITION_STRONG_UP = 0.70
POSITION_WEAK_UP = 0.55
POSITION_WEAK_DOWN = 0.30
POSITION_STRONG_DOWN = 0.15
WIDTH_TIGHT_THRESHOLD = 0.4

# 7단계 regime labels
REGIME_LABELS = [
    "UPTREND_STRONG",
    "UPTREND_WEAK",
    "RANGE_TIGHT",
    "RANGE",
    "DOWNTREND_WEAK",
    "DOWNTREND_STRONG",
    "MIXED",
]


def daily_regime(d_1d: DonchianFrame) -> str:
    """일봉 DonchianFrame → 7단계 추세 분류.

    Args:
        d_1d: 1d timeframe DonchianFrame

    Returns:
        UPTREND_STRONG, UPTREND_WEAK, RANGE_TIGHT, RANGE,
        DOWNTREND_WEAK, DOWNTREND_STRONG, MIXED 중 하나
    """
    pos = d_1d.position
    slope = d_1d.slope
    w_pct = d_1d.width_percentile_60

    # UPTREND_STRONG: pos >= 0.70 and slope > 0
    if pos >= POSITION_STRONG_UP and slope > 0:
        return "UPTREND_STRONG"

    # UPTREND_WEAK: pos >= 0.55 and slope >= 0
    if pos >= POSITION_WEAK_UP and slope >= 0:
        return "UPTREND_WEAK"

    # RANGE_TIGHT: 0.30 <= pos <= 0.70 and w_pct < 0.4 (에너지 응축)
    if (
        POSITION_WEAK_DOWN <= pos <= 0.70
        and not math.isnan(w_pct)
        and w_pct < WIDTH_TIGHT_THRESHOLD
    ):
        return "RANGE_TIGHT"

    # RANGE: 0.30 <= pos <= 0.70
    if POSITION_WEAK_DOWN <= pos <= 0.70:
        return "RANGE"

    # DOWNTREND_WEAK: 0.15 <= pos < 0.30 and slope <= 0
    if POSITION_STRONG_DOWN <= pos < POSITION_WEAK_DOWN and slope <= 0:
        return "DOWNTREND_WEAK"

    # DOWNTREND_STRONG: pos < 0.15 and slope < 0
    if pos < POSITION_STRONG_DOWN and slope < 0:
        return "DOWNTREND_STRONG"

    # MIXED: 이외 모든 경우
    return "MIXED"


def build_per_ticker_regime_map(
    ohlcv_1d_by_ticker: dict[str, pd.DataFrame],
    period: int = 20,
) -> dict[str, str]:
    """전체 종목 1d ohlcv → ticker 별 regime dict.

    데이터 부족 또는 compute_donchian 실패 시 'MIXED' 할당.

    Args:
        ohlcv_1d_by_ticker: {ticker: ohlcv DataFrame, ...}
        period: Donchian lookback (기본 20)

    Returns:
        {ticker: regime_label, ...}
    """
    result = {}
    for ticker, ohlcv in ohlcv_1d_by_ticker.items():
        d = compute_donchian(ohlcv, timeframe="1d", period=period)
        result[ticker] = "MIXED" if d is None else daily_regime(d)
    return result


def daily_regime_series(ohlcv: pd.DataFrame, period: int = 20) -> pd.Series:
    """종목 하나의 OHLCV → 봉별 regime 라벨 시계열.

    s.iloc[i] 는 daily_regime(compute_donchian(ohlcv.iloc[:i+1])) 과 같다
    (계산 불가 봉은 "MIXED"). 각 값이 해당 봉 이하만 참조하므로 룩어헤드가 없다.

    ponytail: 봉마다 다시 계산하는 O(n^2). 341종목 245봉 grid 가 실행당 약 54초다.
    grid 는 실행당 1회만 만들므로(Task 13) 지금은 이걸로 충분하다. WF 실행 시간의
    유의미한 몫이 되면 그때 벡터화한다.
    """
    labels = []
    for i in range(len(ohlcv)):
        frame = compute_donchian(ohlcv.iloc[: i + 1], timeframe="1d", period=period)
        labels.append("MIXED" if frame is None else daily_regime(frame))
    return pd.Series(labels, index=ohlcv.index, dtype=object)
