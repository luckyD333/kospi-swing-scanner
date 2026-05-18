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
      2. 같은 거래일 + cp ≤ stop → STOPPED_OUT
      3. 같은 거래일 + cp ≥ target_1 → TARGET_REACHED
      4. 장중 TF 신호 만료 (1h: 2봉, 30m: 2봉) → STALE
      5. 그 외 → VALID

    stop 인자: 호출자가 limit_stop 우선, 없으면 stop 으로 결정해서 전달.
    timeframe: "1h" / "30m" 일 때 장중 신호 만료 감지 적용.
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
            if trading_days_since(sd, today) > STALE_THRESHOLD_1D:
                return "STALE"
            return "VALID"

    # STOPPED_OUT / TARGET_REACHED 는 신호 발생 시각과 무관하게 우선 적용
    if current_price is not None and stop is not None and current_price <= stop:
        return "STOPPED_OUT"
    if current_price is not None and target_1 is not None and current_price >= target_1:
        return "TARGET_REACHED"

    # 장중 TF 신호 만료: 가격 미발동(VALID 후보) 상태에서만 검사
    # 1h: 2봉(2h) 경과, 30m: 2봉(1h) 경과 → 재진입 기회 소멸로 간주
    if sd_dt is not None and timeframe in ("1h", "30m"):
        stale_hours = 2.0 if timeframe == "1h" else 1.0
        age_hours = (now - sd_dt.astimezone(_KST)).total_seconds() / 3600
        if age_hours > stale_hours:
            return "STALE"

    return "VALID"
