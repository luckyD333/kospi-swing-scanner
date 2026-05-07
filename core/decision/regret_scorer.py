"""
core/decision/regret_scorer.py — 비대칭 후회 점수 산출.

"매수하지 않으면 가장 후회 남을 종목" 식별을 위한 4축 가중합 점수.
각 축은 cross-sectional percentile (0~1) 로 정규화 후 가중합 → 0~100:

  - bull_reward (+):  Candidate.reward_pct_t2  — 놓친 상승 (안 사면 후회)
  - ensemble (+):     ticker → 가중 등장 합   — 합의된 신호
  - max_drawdown (-): Candidate.risk_pct       — 사서 후회 (손절 폭)
  - dist_to_stop (+): (current - stop)/current — 멀수록 즉시 손실 위험 ↓

설계:
  - aggregator._percentile_rank 패턴 재사용 (결정론적 unique rank)
  - lower_better 축은 (1 - rank) 적용
  - 후보 1개 이하면 regret_score = 0
  - 동률 시 final_score 큰 순 → ticker 알파벳 (결정론)
"""
from __future__ import annotations

from dataclasses import dataclass

from core.strategy_base import Candidate

from .aggregator import RankedCandidate


def _avg_percentile_rank(values: list[float | None]) -> list[float]:
    """동률 그룹은 평균 rank, 결측(None) 은 0.5 중립.

    aggregator._percentile_rank 와 다르게 stable-sort 분할을 쓰지 않음.
    동률 후보가 여러 축에 동시에 존재할 때 인덱스 의존 분할이 다른 축의
    가중치 효과를 왜곡하지 않도록 평균 rank 채택.

    [D5 결정 — 결측 0.5 의도적 유지]
      aggregator 는 결측을 0.0 (가산 회피) 으로 두지만, 본 함수는 0.5 (중립) 유지.
      이유: regret_scorer 의 4축(bull_reward, ensemble, max_drawdown, dist_to_stop)은
      비대칭 구조이므로 결측을 0 으로 두면 "가장 안 좋다" 로 의미 왜곡됨. 예를 들어
      max_drawdown 결측을 0 으로 두면 "손실폭 가장 큼" 으로 해석되어 후회값이 오히려 ↑.
      도구 의도가 다르므로 DRY 보다 *의미 보존* 우선.
    """
    n = len(values)
    if n == 0:
        return []
    valid = [(v, i) for i, v in enumerate(values) if v is not None]
    if not valid:
        return [0.5] * n
    valid.sort(key=lambda p: p[0])
    m = len(valid)
    ranks = [0.5] * n
    i = 0
    while i < m:
        j = i
        while j < m and valid[j][0] == valid[i][0]:
            j += 1
        # i..j-1 은 동률 그룹 (1-based rank: i+1 ~ j)
        avg = (i + 1 + j) / 2.0 / m
        for k in range(i, j):
            ranks[valid[k][1]] = avg
        i = j
    return ranks


@dataclass(frozen=True)
class RegretWeights:
    """비대칭 후회 점수 가중치. 합 = 1.0 권장 (정규화 안 함)."""
    bull_reward: float = 0.45
    ensemble: float = 0.25
    max_drawdown: float = 0.20
    dist_to_stop: float = 0.10


DEFAULT_WEIGHTS = RegretWeights()


def _bull_reward(cand: Candidate) -> float | None:
    return cand.reward_pct_t2


def _max_drawdown(cand: Candidate) -> float | None:
    """손절 폭 (%) — 사서 후회 척도."""
    return cand.risk_pct


def _dist_to_stop(cand: Candidate) -> float | None:
    """현재가에서 손절선까지 거리 (%) — 클수록 안전."""
    if cand.current_price <= 0:
        return None
    return (cand.current_price - cand.stop_loss) / cand.current_price * 100


def compute_regret_scores(
    ranked: list[RankedCandidate],
    ensemble_scores: dict[str, float] | None = None,
    weights: RegretWeights | None = None,
) -> list[RankedCandidate]:
    """비대칭 후회 점수 + rank 부여 후 정렬된 리스트 반환.

    각 RankedCandidate.normalized_metrics 에 다음 키 주입:
      regret_score  (float, 0~100)
      regret_rank   (int,   1-based)
      regret_total  (int,   전체 수)

    - ensemble_scores: ticker → 가중 등장 합. 누락 ticker 는 1.0.
    - weights: None 이면 DEFAULT_WEIGHTS.
    """
    w = weights or DEFAULT_WEIGHTS
    es = ensemble_scores or {}

    n = len(ranked)
    if n == 0:
        return []
    if n == 1:
        rc = ranked[0]
        rc.normalized_metrics["regret_score"] = 0.0
        rc.normalized_metrics["regret_rank"] = 1
        rc.normalized_metrics["regret_total"] = 1
        return [rc]

    bulls: list[float | None] = [_bull_reward(rc.candidate) for rc in ranked]
    dds: list[float | None] = [_max_drawdown(rc.candidate) for rc in ranked]
    dists: list[float | None] = [_dist_to_stop(rc.candidate) for rc in ranked]
    ens: list[float | None] = [
        es.get(rc.candidate.ticker, 1.0) for rc in ranked
    ]

    bull_rank = _avg_percentile_rank(bulls)
    ens_rank = _avg_percentile_rank(ens)
    dd_rank = _avg_percentile_rank(dds)
    dist_rank = _avg_percentile_rank(dists)

    # max_drawdown 만 lower_better → 1 - r, 결측은 0.5 유지
    dd_norm = [
        (1.0 - r) if dds[i] is not None else 0.5
        for i, r in enumerate(dd_rank)
    ]

    annotated: list[tuple[float, RankedCandidate]] = []
    for i, rc in enumerate(ranked):
        score01 = (
            w.bull_reward * bull_rank[i]
            + w.ensemble * ens_rank[i]
            + w.max_drawdown * dd_norm[i]
            + w.dist_to_stop * dist_rank[i]
        )
        score = round(score01 * 100, 4)
        rc.normalized_metrics["regret_score"] = score
        rc.normalized_metrics["regret_total"] = n
        annotated.append((score, rc))

    # regret_score 내림차순 → final_score 내림차순 → ticker 알파벳
    annotated.sort(
        key=lambda t: (-t[0], -t[1].final_score, t[1].candidate.ticker)
    )
    for rank_idx, (_score, rc) in enumerate(annotated, start=1):
        rc.normalized_metrics["regret_rank"] = rank_idx

    return [rc for _s, rc in annotated]
