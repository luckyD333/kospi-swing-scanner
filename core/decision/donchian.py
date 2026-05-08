"""
core/decision/donchian.py — Donchian 채널 분석 (Multi-TF).

DonchianFrame dataclass: 시간대별(1d/1h/30m) 채널 위치·폭·기울기·신호 정보.
compute_donchian: OHLCV 시계열 → DonchianFrame 계산.

특징:
- position: (close - lower) / (upper - lower), 0~1 정규화
- width_percentile_60: 최근 60봉 채널 폭 분포 내 현재 percentile (변동성 압축 감지)
- slope: middle의 5봉 기울기 (정규화) — 추세 방향 지표
- days_since_*_break: 마지막 신고가/신저가 이후 경과 봉 수
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DonchianFrame:
    """시간대별 Donchian 채널 분석 결과."""

    timeframe: str  # "1d" / "1h" / "30m"
    period: int  # 기본 20

    # 채널 경계
    upper: float  # N봉 최고가 (현재 봉 제외)
    lower: float  # N봉 최저가
    middle: float  # (upper + lower) / 2

    # 채널 폭 & 변동성
    width_pct: float  # (upper - lower) / middle * 100
    width_percentile_60: float  # 최근 60봉 width 분포에서의 percentile (0~1 또는 NaN)

    # 추세 위치 & 방향
    position: float  # (close - lower) / (upper - lower), 0~1
    days_since_upper_break: int  # 마지막 close > rolling upper 이후 봉 수 (없으면 period)
    days_since_lower_break: int  # 마지막 close < rolling lower 이후 봉 수
    slope: float  # middle의 5봉 기울기 (per bar, 정규화)


def compute_donchian(
    ohlcv: pd.DataFrame,
    *,
    timeframe: str,
    period: int = 20,
    width_window: int = 60,
    slope_window: int = 5,
) -> DonchianFrame | None:
    """OHLCV → DonchianFrame 계산.

    Args:
        ohlcv: columns=[open/high/low/close/volume], index=시간순
        timeframe: "1d" / "1h" / "30m"
        period: Donchian lookback (기본 20)
        width_window: width_percentile_60 계산 윈도우 (기본 60)
        slope_window: slope 계산 윈도우 (기본 5)

    반환:
        - ohlcv 길이 < period + 1 → None (계산 불가)
        - ohlcv 길이 ≥ period + 1 → DonchianFrame (width_percentile_60은 데이터 부족 시 NaN)

    구현 주의:
        - upper/lower는 최근 N봉(현재 봉 제외) → ohlcv[-period-1:-1]
        - position: (close[-1] - lower) / max(upper - lower, 1e-9) (0 division 회피)
        - width_percentile_60: 최근 width_window 봉의 rolling width 분포 내 percentile
        - days_since_*_break: rolling upper/lower와 close 비교해 경과 봉 수 계산
    """
    if len(ohlcv) < period + 1:
        return None
    if not {"close", "high", "low"}.issubset(ohlcv.columns):
        return None  # 컬럼 누락 시 graceful fallback (테스트 fixture 호환)

    close = ohlcv["close"].astype(float)
    high = ohlcv["high"].astype(float)
    low = ohlcv["low"].astype(float)

    # --- Channel boundaries (최근 period봉, 현재 봉 제외) ---
    # 최근 period+1 봉 중 처음 period 봉의 high/low
    recent_high = high.iloc[-period - 1 : -1]
    recent_low = low.iloc[-period - 1 : -1]

    upper = float(recent_high.max())
    lower = float(recent_low.min())
    middle = (upper + lower) / 2.0

    # --- Width Percentage ---
    width_pct = (upper - lower) / middle * 100 if middle != 0 else 0.0

    # --- Width Percentile (최근 width_window 봉) ---
    width_percentile_60 = _compute_width_percentile(high, low, width_window)

    # --- Position (0~1) ---
    current_close = float(close.iloc[-1])
    channel_width = max(upper - lower, 1e-9)
    position = (current_close - lower) / channel_width

    # --- Days Since Break ---
    # rolling upper/lower와 close 비교해서 신고가 돌파 여부 판정
    rolling_high = high.rolling(window=period, min_periods=period)
    rolling_low = low.rolling(window=period, min_periods=period)

    days_since_upper_break = _compute_days_since_break_rolling(
        close, rolling_high, direction="upper", period=period
    )
    days_since_lower_break = _compute_days_since_break_rolling(
        close, rolling_low, direction="lower", period=period
    )

    # --- Slope (middle의 5봉 기울기) ---
    slope = _compute_slope(high, low, slope_window)

    return DonchianFrame(
        timeframe=timeframe,
        period=period,
        upper=upper,
        lower=lower,
        middle=middle,
        width_pct=width_pct,
        width_percentile_60=width_percentile_60,
        position=position,
        days_since_upper_break=days_since_upper_break,
        days_since_lower_break=days_since_lower_break,
        slope=slope,
    )


def _compute_width_percentile(
    high: pd.Series, low: pd.Series, width_window: int
) -> float:
    """최근 width_window 봉의 rolling width 분포 내 현재 width percentile.

    args:
        width_window: 최근 N봉 (기본 60)

    반환:
        - 데이터 부족 (< width_window) → NaN
        - 충분 → 0~1 percentile rank (scipy.stats.rankdata 사용)
    """
    if len(high) < width_window:
        return float("nan")

    # 각 봉의 채널 폭 계산 (rolling 아님, 각 봉별)
    rolling_high = high.rolling(window=20, min_periods=1).max()
    rolling_low = low.rolling(window=20, min_periods=1).min()
    widths = rolling_high - rolling_low

    # 최근 width_window 봉의 width 분포
    recent_widths = widths.iloc[-width_window:]
    current_width = widths.iloc[-1]

    # percentile rank: current 보다 작은 값의 비율
    count_less = (recent_widths < current_width).sum()
    percentile = count_less / max(1, len(recent_widths) - 1)

    return float(percentile)


def _compute_days_since_break_rolling(
    close: pd.Series, rolling_level: pd.core.window.Rolling, direction: str, period: int
) -> int:
    """마지막 close > rolling_level.max() (upper) 또는 close < rolling_level.min() (lower).

    args:
        close: 종가 시계열
        rolling_level: rolling high 또는 rolling low
        direction: "upper" (rolling high) or "lower" (rolling low)
        period: lookback period (default break 없을 때 반환값)

    반환:
        마지막 break 이후 봉 수. 없으면 period.
    """
    if direction == "upper":
        level_series = rolling_level.max()
        breaks = close > level_series
    else:  # lower
        level_series = rolling_level.min()
        breaks = close < level_series

    # 역순으로 처음 True 찾기
    for i in range(len(breaks) - 1, -1, -1):
        if breaks.iloc[i]:
            return len(breaks) - 1 - i

    return period


def _compute_slope(high: pd.Series, low: pd.Series, slope_window: int) -> float:
    """Middle의 5봉 기울기 (정규화).

    middle = (rolling_high + rolling_low) / 2 의 최근 slope_window 봉
    변화량 / 평균 middle (정규화해서 스케일 무관하게 함).

    반환:
        기울기 (양수=상승, 음수=하락, 0=평탄)
    """
    rolling_high = high.rolling(window=20, min_periods=1).max()
    rolling_low = low.rolling(window=20, min_periods=1).min()
    middle = (rolling_high + rolling_low) / 2.0

    if len(middle) < slope_window + 1:
        return 0.0

    recent_middle = middle.iloc[-slope_window - 1 :]
    if recent_middle.isna().all():
        return 0.0

    # 변화량 = 마지막 - 처음
    change = recent_middle.iloc[-1] - recent_middle.iloc[0]

    # 평균 middle (정규화 분모)
    avg_middle = recent_middle.mean()
    if avg_middle == 0 or pd.isna(avg_middle):
        return 0.0

    slope = change / avg_middle
    return float(slope)
