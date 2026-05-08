"""
core/decision/squeeze.py — Squeeze 워치리스트 감지 + 우선순위 큐.

Squeeze 정의: 1d + 1h 동시 width_percentile_60 < 0.25 + 1d position 0.4~0.7
  → 에너지 응축 중 + 중상단 위치 (큰 변동 임박 신호)

build_squeeze_queue: 최근 신호 중 squeeze 종목을 찾아 1d width_percentile 낮은 순
정렬 후 max_queue_size 만큼만 반환 (카탈로그 "돌파 대기 큐" 노출용).
"""
from __future__ import annotations

from core.decision.donchian import DonchianFrame


def is_squeeze(d_1d: DonchianFrame | None, d_1h: DonchianFrame | None) -> bool:
    """1d + 1h 동시 width_percentile_60 < 0.25 + 1d position 0.4~0.7 → 에너지 응축.

    Args:
        d_1d: 1일봉 DonchianFrame
        d_1h: 1시간봉 DonchianFrame

    Returns:
        True if squeeze 조건 만족, False otherwise.
        None input 또는 NaN width_percentile_60 → False.
    """
    if d_1d is None or d_1h is None:
        return False

    # NaN 확인 (width_percentile_60 != width_percentile_60 는 NaN 체크)
    if d_1d.width_percentile_60 != d_1d.width_percentile_60:  # NaN check
        return False
    if d_1h.width_percentile_60 != d_1h.width_percentile_60:  # NaN check
        return False

    return (
        d_1d.width_percentile_60 < 0.25
        and d_1h.width_percentile_60 < 0.25
        and 0.4 <= d_1d.position <= 0.7
    )


def build_squeeze_queue(
    donchian_1d_by_ticker: dict[str, DonchianFrame | None],
    donchian_1h_by_ticker: dict[str, DonchianFrame | None],
    max_queue_size: int = 20,
) -> list[str]:
    """Squeeze 종목 ticker list (최대 max_queue_size).

    우선순위: 1d width_percentile_60 낮은 순 (에너지 응축도 높음).

    Args:
        donchian_1d_by_ticker: ticker → DonchianFrame | None
        donchian_1h_by_ticker: ticker → DonchianFrame | None
        max_queue_size: 큐 최대 크기 (기본 20)

    Returns:
        Squeeze 조건 만족 ticker 리스트 (1d width_percentile 낮은 순).
    """
    squeeze_list: list[tuple[str, float]] = []

    # 공통 ticker 찾기
    all_tickers = set(donchian_1d_by_ticker.keys()) | set(donchian_1h_by_ticker.keys())

    for ticker in all_tickers:
        d_1d = donchian_1d_by_ticker.get(ticker)
        d_1h = donchian_1h_by_ticker.get(ticker)

        if is_squeeze(d_1d, d_1h):
            # width_percentile_60 낮은 순 정렬 (우선순위 높음)
            width = d_1d.width_percentile_60  # d_1d is not None if is_squeeze is True
            squeeze_list.append((ticker, width))

    # 1d width_percentile_60 낮은 순 정렬
    squeeze_list.sort(key=lambda x: x[1])

    # max_queue_size 제한
    queue = [ticker for ticker, _ in squeeze_list[:max_queue_size]]

    return queue
