"""
core/decision/aggregator.py — 가중 점수 산출 + ranking.

후보 메트릭을 cross-sectional percentile rank 로 정규화하고 (outlier robust),
WeightConfig 의 가중치로 합산해 final_score 를 계산한다.

설계:
  - direction='lower_better': 작은 값이 좋음 → 1 - rank
  - direction='higher_better': 큰 값이 좋음 → rank
  - 결측(None): rank 0.5 (중립 — ETF 등 펀더멘털 N/A 종목을 최하위 취급하지 않음)
  - must_have 탈락 후보는 결과에서 제외

key 우선순위:
  - "score" → Candidate.score 직접 참조
  - 그 외 → Candidate.metadata.get(key) (per/roe/foreign_pct/momentum_pct 등)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.strategy_base import Candidate

from .config import WeightConfig, eval_must_have


@dataclass
class RankedCandidate:
    """후보 + 가중 점수 + 항목별 기여도."""
    candidate: Candidate
    final_score: float
    contributions: dict[str, float] = field(default_factory=dict)
    normalized_metrics: dict[str, float] = field(default_factory=dict)


def _extract_metric(cand: Candidate, key: str):
    """Candidate.score 또는 metadata에서 메트릭 값 추출. None 가능."""
    if key == "score":
        return cand.score
    return (cand.metadata or {}).get(key)


def _percentile_rank(values: list[float | None]) -> list[float]:
    """결측은 rank 0, 나머지는 cross-sectional percentile (0~1).

    동률은 안정 정렬 순서에 따라 분할 — 결정론적 unique rank.
    """
    n = len(values)
    if n == 0:
        return []
    # 결측 인덱스 분리
    valid_indices = [i for i, v in enumerate(values) if v is not None]
    if not valid_indices:
        return [0.5] * n
    # valid 값 정렬해서 rank 부여
    valid_pairs = [(values[i], i) for i in valid_indices]
    # NOTE: 동률 처리 — average rank 대신 stable sort로 분할.
    # 같은 값이라도 입력 순서대로 1/m, 2/m, ... 로 unique rank 할당.
    # 이유: 동률 종목 다수(시장 정체) 시 일부를 배제하는 필터 효과 → 신호 신뢰도 낮은
    # 동률 케이스에서 ranking 분산을 줄여요. (Strategy 2와 동일한 정책으로 일관성 유지)
    sorted_pairs = sorted(valid_pairs, key=lambda x: (x[0], x[1]))
    ranks = [0.5] * n
    m = len(sorted_pairs)
    for rank_idx, (_v, orig_i) in enumerate(sorted_pairs):
        # 1/m..1.0 (작은 값 = 낮은 rank)
        ranks[orig_i] = (rank_idx + 1) / m
    # 결측은 0
    return ranks


def aggregate_candidates(
    candidates: list[Candidate], cfg: WeightConfig,
) -> list[RankedCandidate]:
    """후보 리스트 + WeightConfig → RankedCandidate (final_score 내림차순)."""
    if not candidates:
        return []

    # 1) must_have 탈락
    survivors: list[Candidate] = []
    for cand in candidates:
        metrics = {"score": cand.score, **(cand.metadata or {})}
        if eval_must_have(cfg.must_have, metrics):
            survivors.append(cand)
    if not survivors:
        return []

    # 2) priority 별 percentile rank 정규화
    normalized: dict[str, list[float]] = {}
    for prio in cfg.priorities:
        raw = [_extract_metric(c, prio.key) for c in survivors]
        rank = _percentile_rank(raw)
        if prio.direction == "lower_better":
            # 작은 값이 좋음 → 1 - rank, 단 결측은 0 유지
            rank = [
                (1.0 - r) if raw[i] is not None else 0.5
                for i, r in enumerate(rank)
            ]
        normalized[prio.key] = rank

    # 3) 가중 합산
    # 스케일: contribution = (정규화 점수 0~1) × (가중치 0~100) → 항목별 0~weight 범위.
    # final_score = sum(contributions) → 0~100 범위 (가중치 합 = 100 보장됨).
    # 모든 항목이 percentile 1.0 이면 final_score = 100, 모두 결측이면 0.
    ranked: list[RankedCandidate] = []
    for i, cand in enumerate(survivors):
        contributions: dict[str, float] = {}
        norm_metrics: dict[str, float] = {}
        total = 0.0
        for prio in cfg.priorities:
            n = normalized[prio.key][i]
            contrib = n * prio.weight  # 0~weight 범위
            contributions[prio.key] = contrib
            norm_metrics[prio.key] = n
            total += contrib
        ranked.append(RankedCandidate(
            candidate=cand,
            final_score=round(total, 4),
            contributions={k: round(v, 4) for k, v in contributions.items()},
            normalized_metrics=norm_metrics,
        ))

    # 4) final_score 내림차순. 동률 시 ticker 알파벳 순 (결정론).
    ranked.sort(key=lambda r: (-r.final_score, r.candidate.ticker))
    return ranked
