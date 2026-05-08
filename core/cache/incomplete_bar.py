"""
core/cache/incomplete_bar.py — 1D today row 의 종가 확정 여부 판정.

휴리스틱: fetched_at_kst >= 15:30 KST 이면 confirmed close.
target_date 가 과거 영업일이면 fetched 시각 무관 항상 confirmed.
네이버 응답에 close_status 메타가 없어 시각 기반 가드만 가능.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
MARKET_CLOSE = time(15, 30)


def is_today_bar_complete(
    target_date: str,
    fetched_at_iso: str | None,
) -> bool:
    """1D 의 target_date row 가 종가 확정인지 판정.

    Args:
        target_date: "YYYY-MM-DD" — 1D row 의 날짜 (KST).
        fetched_at_iso: "YYYY-MM-DDTHH:MM:SS+09:00" 또는 naive ISO.
                        manifest.collected_at 또는 호출자 now() 를 넘긴다.
                        None / 파싱 실패 → incomplete.

    Returns:
        True: target_date row 가 confirmed close (호출 측 그대로 사용 가능).
        False: incomplete bar (호출 측은 어제 종가로 fallback 권장).
    """
    if fetched_at_iso is None:
        return False
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    if target_date != today_kst:
        return True
    try:
        fetched = datetime.fromisoformat(fetched_at_iso)
    except ValueError:
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=KST)
    fetched_kst = fetched.astimezone(KST)
    return fetched_kst.time() >= MARKET_CLOSE
