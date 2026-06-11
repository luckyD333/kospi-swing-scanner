"""감사 회귀 테스트 — `_expanding_percentile_score` 의 no-lookahead 보장.

docs/audit/trading_system_audit.md §6 참조. market_health_score 의 기반인
expanding percentile 은 "각 시점 값을 그 시점까지의 분포로만 평가"가 설계
계약이다. 미래 데이터를 append 해도 과거 시점 출력이 변하지 않아야 한다.
(HMM predict_proba history 와 달리 이 성분은 leakage-free 임을 고정.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.decision.market_regime import _expanding_percentile_score


def test_expanding_percentile_past_values_invariant_to_future_append():
    rng = np.random.RandomState(42)
    past = pd.Series(rng.normal(0, 1, 60))
    future = pd.Series(rng.normal(5, 1, 40))  # 분포가 크게 다른 미래 구간
    full = pd.concat([past, future], ignore_index=True)

    score_past_only = _expanding_percentile_score(past, min_periods=10)
    score_full = _expanding_percentile_score(full, min_periods=10)

    pd.testing.assert_series_equal(
        score_past_only,
        score_full.iloc[:60],
        check_names=False,
    )


def test_expanding_percentile_respects_min_periods_default():
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = _expanding_percentile_score(series, min_periods=3, default=50.0)

    # min_periods 미만 구간은 default — 미래 분포로 소급 채점하지 않음
    assert out.iloc[0] == 50.0
    assert out.iloc[1] == 50.0
    # 단조 증가 수열에서 각 시점 값은 자기 시점까지의 최댓값 → percentile 100
    assert out.iloc[2] == 100.0
    assert out.iloc[4] == 100.0
