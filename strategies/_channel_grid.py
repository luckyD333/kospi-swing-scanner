"""
strategies/_channel_grid.py — 추세선·평행 격자 순수 기하 (Strategy Six 전용 부품).

ScanContext/Candidate 를 모르는 numpy 함수만 둔다. 모든 인덱스는 전역 봉 인덱스.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import argrelextrema


def find_confirmed_pivots(values: np.ndarray, window: int, *, highs: bool) -> list[int]:
    """좌우 window 봉보다 높은(highs=True) 또는 낮은 값의 인덱스.

    - 오른쪽 window 봉이 존재해야 확정 (미래 정보 유입 방지).
    - argrelextrema 는 mode="clip" 이라 첫·끝 봉을 돌려주므로 경계를 잘라낸다.
    - 같은 값이 연속되는 평탄 구간은 마지막 인덱스 하나로 접는다.
    """
    n = len(values)
    if n < 2 * window + 1:
        return []
    cmp = np.greater_equal if highs else np.less_equal
    idx = argrelextrema(np.asarray(values, dtype=float), cmp, order=window)[0]
    idx = idx[(idx >= window) & (idx <= n - 1 - window)]
    if len(idx) == 0:
        return []
    runs = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
    return [int(r[-1]) for r in runs]
