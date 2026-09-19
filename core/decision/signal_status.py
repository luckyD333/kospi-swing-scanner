"""신호 상태 (VALID / TARGET_REACHED / STOPPED_OUT / STALE) 동적 계산.

signal-api 응답 시점 + cli.py 산출 시점 양쪽에서 동일 helper 로 사용.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.dates import is_same_trading_day, trading_days_since

_KST = ZoneInfo("Asia/Seoul")

# 1D 신호 STALE 임계 (거래일). signal_date 후 이 거래일 수 초과 시 STALE.
# Step 2 audit(scripts/stale_drift_audit.py, 2026-05-18) 결과 채택:
#   horizon=1 |drift|≥5% 비율 43.7% (cutoff 30% 초과) — 487 종목 / 14,986 신호.
#   즉 다음 거래일이면 이미 40%+ 종목이 5%+ 표류 → expired 판정.
# 운영 1주 후 walk-forward 데이터로 재검증 예정 (~2026-05-25).
STALE_THRESHOLD_1D: int = 1

# 1W 신호 STALE 임계 (거래일). 주봉 셋업의 유효 기간은 1주 = 5거래일.
STALE_THRESHOLD_1W: int = 5


def compute_signal_status(
    current_price: float | None,
    stop: int | float | None,
    target_1: int | float | None,
    signal_date_str: str | None,
    now: datetime | None = None,
    timeframe: str | None = None,
) -> str:
    """API 응답 시점에 신호 상태 계산.

    우선순위:
      1. 장외 시간 (signal_date 거래일 ≠ 오늘 거래일) → STALE 또는 VALID
         (임계: 1D 는 1거래일, 1W 는 5거래일, 1h 등 장중 TF 는 거래일 교차 즉시)
      2. 같은 거래일 + cp ≤ stop → STOPPED_OUT
      3. 같은 거래일 + cp ≥ target_1 → TARGET_REACHED
      4. 장중 TF 신호 만료 (1h: 2봉) → STALE
      5. 그 외 → VALID

    timeframe: "1h" 일 때 장중 신호 만료 감지 적용.
    """
    now = now or datetime.now(tz=_KST)
    today = now.date()

    sd_dt: datetime | None = None
    if signal_date_str:
        try:
            sd_dt = datetime.fromisoformat(signal_date_str)
            # naive datetime 이면 KST 로 가정 (signals.json 은 KST 기반 생성)
            if sd_dt.tzinfo is None:
                sd_dt = sd_dt.replace(tzinfo=_KST)
            sd = sd_dt.astimezone(_KST).date()
        except ValueError:
            return "STALE"
        if not is_same_trading_day(sd, today):
            # current_price 가 전일 종가일 가능성 → cp 비교 의미 없음
            # join.compute_freshness_meta 의 plan_expired 와 같은 판정이어야 한다.
            # 어긋나면 같은 응답 안에서 signal_status 와 plan_expired 가 모순된다.
            if timeframe == "1W":
                threshold = STALE_THRESHOLD_1W
            elif timeframe in (None, "1D"):
                threshold = STALE_THRESHOLD_1D
            else:
                # 1h 등 장중 TF: 거래일이 바뀌면 2봉(2h) 창을 이미 넘었으므로 즉시 STALE.
                # join 은 bars=거래일×6 > 2 로 같은 결과를 낸다.
                threshold = 0
            if trading_days_since(sd, today) > threshold:
                return "STALE"
            return "VALID"

    # STOPPED_OUT / TARGET_REACHED 는 신호 발생 시각과 무관하게 우선 적용
    if current_price is not None and stop is not None and current_price <= stop:
        return "STOPPED_OUT"
    if current_price is not None and target_1 is not None and current_price >= target_1:
        return "TARGET_REACHED"

    # 장중 TF 신호 만료: 가격 미발동(VALID 후보) 상태에서만 검사
    # 1h: 2봉(2h) 경과 → 재진입 기회 소멸로 간주
    if sd_dt is not None and timeframe == "1h":
        stale_hours = 2.0
        age_hours = (now - sd_dt.astimezone(_KST)).total_seconds() / 3600
        if age_hours > stale_hours:
            return "STALE"

    return "VALID"
