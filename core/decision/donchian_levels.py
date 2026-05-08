"""
core/decision/donchian_levels.py — 30m Donchian 기반 trade_plan 자동 산출 (Optional).

Task 5d: execution_levels() 함수로 entry/stop/T1/T2/trailing 자동 계산.
전략 family (추세 추종 vs 평균 회귀) 에 따라 로직 분기.

특징:
- can_use_donchian_levels(): 1m 캐시 데이터 부족 시 fallback 판정
- execution_levels(): 30m/1h Donchian 기반 가격 수준 산출
- 기존 ATR+채널 산식과 병존 (strategy config flag 로 분기)
"""
from core.decision.donchian import DonchianFrame

# Strategy family 분류
TREND_FAMILIES = {"strategy_two", "strategy_three", "strategy_four", "strategy_five"}
MEAN_REVERSION_FAMILIES = {"strategy_one"}


def can_use_donchian_levels(d_30m: DonchianFrame | None) -> bool:
    """30m DonchianFrame 이 trade_plan 산출에 사용 가능한지 판정.

    Fallback 트리거 조건:
    - d_30m = None (1m 데이터 missing / 30m 리샘플링 결과 < 60봉)
    - d_30m.width_percentile_60 = NaN (width 계산 불가)

    Args:
        d_30m: 30분봉 Donchian 분석 결과

    반환:
        True: 사용 가능 / False: fallback 필요
    """
    if d_30m is None:
        return False
    # NaN check (width_percentile_60 != width_percentile_60 is True for NaN)
    if d_30m.width_percentile_60 != d_30m.width_percentile_60:  # NaN
        return False
    return True


def execution_levels(
    strategy_family: str,
    d_30m: DonchianFrame,
    d_1h: DonchianFrame,
    atr_30m: float,
    tick: float = 1.0,
) -> dict[str, float | str | None]:
    """30m Donchian 기반 entry/stop/T1/T2/trailing 산출.

    추세 추종 (strategy_two/three/four/five):
      entry = d_30m.upper + tick        # 상단 돌파 역지정가
      stop  = max(d_30m.lower, d_1h.middle - 0.5*atr_30m)
      T1    = d_30m.middle + (d_30m.upper - d_30m.middle)  # 중간선 상단
      T2    = d_30m.upper + (d_30m.upper - d_30m.lower)    # 상단 위로 채널폭만큼
      trailing = "1h_lower"             # 1h 하단 trailing stop

    평균 회귀 (strategy_one):
      entry = d_30m.lower + 0.3 * (d_30m.middle - d_30m.lower)  # 하단 근처
      stop  = d_30m.lower - 1.0 * atr_30m
      T1    = d_30m.middle              # 회귀 1차 목표 (중간선)
      T2    = d_30m.upper               # 회귀 2차 목표 (상단)
      trailing = None

    Args:
        strategy_family: strategy_one | strategy_two | strategy_three | strategy_four | strategy_five
        d_30m: 30분봉 Donchian 분석 결과
        d_1h: 1시간봉 Donchian 분석 결과 (추세 추종 시 stop 계산용)
        atr_30m: 30분봉 ATR(14)
        tick: 호가 단위 (기본 1.0)

    반환:
        dict[str, float | str | None]:
            - entry: 진입가
            - stop: 손절가
            - T1: 1차 목표가
            - T2: 2차 목표가
            - trailing: trailing stop 기준 ("1h_lower" | None)

    예외:
        ValueError: 알 수 없는 strategy_family
    """
    channel_width_30m = d_30m.upper - d_30m.lower

    if strategy_family in TREND_FAMILIES:
        # --- 추세 추종 ---
        entry = d_30m.upper + tick
        stop = max(d_30m.lower, d_1h.middle - 0.5 * atr_30m)
        T1 = d_30m.middle + channel_width_30m / 2.0
        T2 = d_30m.upper + channel_width_30m
        trailing = "1h_lower"
        return {
            "entry": entry,
            "stop": stop,
            "T1": T1,
            "T2": T2,
            "trailing": trailing,
        }

    elif strategy_family in MEAN_REVERSION_FAMILIES:
        # --- 평균 회귀 ---
        entry = d_30m.lower + 0.3 * (d_30m.middle - d_30m.lower)
        stop = d_30m.lower - 1.0 * atr_30m
        T1 = d_30m.middle
        T2 = d_30m.upper
        trailing = None
        return {
            "entry": entry,
            "stop": stop,
            "T1": T1,
            "T2": T2,
            "trailing": trailing,
        }

    else:
        raise ValueError(f"알 수 없는 strategy_family: {strategy_family}")
