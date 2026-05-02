"""
core/decision/ensemble.py — 다중 전략 교집합 + Minimax Regret.

기능:
  - compute_ensemble_count: ticker가 몇 개 전략에서 등장했는지 집계
  - apply_minimax_regret: 후보별 시나리오 후회 매트릭스 → 최대 후회 최소 순
  - auto_volatility_scenarios: 후보 risk/reward 기반 bull/bear 시나리오 자동 생성

설계:
  - regret_fn: Callable[[Candidate], dict[scenario_name, regret_score]]
    단위 분리로 사용자가 임의 시나리오 주입 가능
  - 동률 (max regret 같음) 시 RankedCandidate.final_score 큰 순 (보조 키)
"""
from __future__ import annotations

from typing import Callable

from core.strategy_base import Candidate

from .aggregator import RankedCandidate

RegretFn = Callable[[Candidate], dict[str, float]]


def compute_ensemble_count(
    candidates_by_strategy: dict[str, list[Candidate]],
) -> dict[str, int]:
    """ticker → 등장한 전략 개수 (cross-strategy 신뢰도 신호)."""
    counts: dict[str, int] = {}
    for cands in candidates_by_strategy.values():
        seen_in_strategy: set[str] = set()
        for c in cands:
            if c.ticker not in seen_in_strategy:
                counts[c.ticker] = counts.get(c.ticker, 0) + 1
                seen_in_strategy.add(c.ticker)
    return counts


def compute_weighted_ensemble_score(
    candidates_by_strategy: dict[str, list[Candidate]],
    strategy_weights: dict[str, float],
) -> dict[str, float]:
    """ticker → weighted_ensemble_score (float).

    각 전략의 등장에 strategy_weights[strategy_name] 만큼의 가중치를 부여.
    strategy_weights 에 없는 전략은 1.0 으로 처리.
    strategy_weights 가 비어있으면 compute_ensemble_count 와 동일 (모두 1.0).
    """
    scores: dict[str, float] = {}
    for strategy_name, cands in candidates_by_strategy.items():
        w = strategy_weights.get(strategy_name, 1.0)
        seen_in_strategy: set[str] = set()
        for c in cands:
            if c.ticker not in seen_in_strategy:
                scores[c.ticker] = scores.get(c.ticker, 0.0) + w
                seen_in_strategy.add(c.ticker)
    return scores


def apply_minimax_regret(
    ranked: list[RankedCandidate],
    regret_fn: RegretFn,
) -> list[RankedCandidate]:
    """
    각 후보의 max regret 계산 후 최대 후회 작은 순 정렬.

    동률 시 final_score 큰 순 (보조 키).
    max_regret 값은 RankedCandidate.normalized_metrics["max_regret"]에 기록.
    """
    annotated: list[tuple[float, RankedCandidate]] = []
    for rc in ranked:
        regrets = regret_fn(rc.candidate) or {}
        max_regret = max(regrets.values()) if regrets else 0.0
        rc.normalized_metrics["max_regret"] = round(max_regret, 4)
        annotated.append((max_regret, rc))

    # 1차: max_regret 오름차순 (작을수록 우선)
    # 2차: final_score 내림차순
    # 3차: ticker 알파벳 (결정론)
    annotated.sort(
        key=lambda t: (t[0], -t[1].final_score, t[1].candidate.ticker)
    )
    return [rc for _mr, rc in annotated]


def auto_volatility_scenarios(ranked: list[RankedCandidate]) -> RegretFn:
    """
    후보들의 risk_pct/reward_pct_t2 분포 기반 bull/bear 시나리오 후회 함수 반환.

    - bull (모두 t2 도달): 후회 = max(reward_pct_t2) - my reward_pct_t2
        ↳ 더 큰 상승을 놓친 상대적 손실
    - bear (모두 stop_loss): 후회 = my risk_pct - min(risk_pct)
        ↳ 더 작은 손실 옵션을 놓친 상대적 손실

    수치는 % 포인트 단위. 후보가 0~1개면 모든 후회 0.
    """
    if len(ranked) <= 1:
        return lambda _c: {"bull": 0.0, "bear": 0.0}

    rewards = [r.candidate.reward_pct_t2 for r in ranked]
    risks = [r.candidate.risk_pct for r in ranked]
    max_reward = max(rewards)
    min_risk = min(risks)

    def regret_fn(cand: Candidate) -> dict[str, float]:
        return {
            "bull": round(max(0.0, max_reward - cand.reward_pct_t2), 4),
            "bear": round(max(0.0, cand.risk_pct - min_risk), 4),
        }

    return regret_fn
