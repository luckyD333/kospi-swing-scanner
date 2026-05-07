"""
core/decision/aggregator.py — 가중 점수 산출 + ranking.

후보 메트릭을 cross-sectional percentile rank 로 정규화하고 (outlier robust),
WeightConfig 의 가중치로 합산해 final_score 를 계산한다.

설계:
  - direction='lower_better': 작은 값이 좋음 → 1 - rank
  - direction='higher_better': 큰 값이 좋음 → rank
  - 결측(None): rank 0.0 (가산 회피 — PR-A 결정).
    분기 사유는 normalized_metrics 의 '<key>_missing_reason' 에 기록.
      * NEGATIVE_EARNINGS: candidate.metadata['<key>_negative'] == True 인 경우 (적자)
      * DATA_MISSING: 그 외 단순 누락
    NOT_APPLICABLE (ETN/ETF 등) 은 PR-B 에서 product_type 도입과 함께 추가.
  - must_have 탈락 후보는 결과에서 제외

regret_scorer 와의 의도적 차이 (D5 결정):
  본 모듈의 결측 = 0 정책은 "가산 회피". regret_scorer._avg_percentile_rank 는
  4축 비대칭 구조에서 결측을 0 으로 두면 "가장 안 좋다" 로 의미 왜곡되므로 0.5 유지.

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
    """후보 + 가중 점수 + 항목별 기여도.

    normalized_metrics 는 mixed type:
      - 'per', 'roe' 등 priority key → float (0~1 정규화 점수)
      - '<key>_missing_reason' → str ('NEGATIVE_EARNINGS' | 'DATA_MISSING')
      - 'regret_score'/'regret_rank'/'regret_total' → float/int (regret_scorer 주입)
    """
    candidate: Candidate
    final_score: float
    contributions: dict[str, float] = field(default_factory=dict)
    normalized_metrics: dict[str, float | int | str] = field(default_factory=dict)


def _extract_metric(cand: Candidate, key: str):
    """Candidate.score 또는 metadata에서 메트릭 값 추출. None 가능."""
    if key == "score":
        return cand.score
    return (cand.metadata or {}).get(key)


def _classify_missing(value, negative_flag: bool) -> str:
    """결측 사유 분류 — PR-A 범위 (NEGATIVE_EARNINGS / DATA_MISSING / PRESENT).

    NOT_APPLICABLE (ETN/ETF 등) 은 PR-B 에서 product_type 도입과 함께 추가.
    """
    if value is not None:
        return "PRESENT"
    return "NEGATIVE_EARNINGS" if negative_flag else "DATA_MISSING"


def _percentile_rank(values: list[float | None]) -> list[float]:
    """결측은 rank 0.0, 나머지는 cross-sectional percentile (0~1).

    동률은 안정 정렬 순서에 따라 분할 — 결정론적 unique rank.

    PR-A 변경: 결측 default 0.5 (중립) → 0.0 (가산 회피).
    분기 사유(NEGATIVE_EARNINGS/DATA_MISSING) 는 aggregate_candidates 가
    candidate.metadata 의 '<key>_negative' 플래그를 읽어 normalized_metrics 에 기록.
    """
    n = len(values)
    if n == 0:
        return []
    # 결측 인덱스 분리
    valid_indices = [i for i, v in enumerate(values) if v is not None]
    if not valid_indices:
        return [0.0] * n
    # valid 값 정렬해서 rank 부여
    valid_pairs = [(values[i], i) for i in valid_indices]
    # NOTE: 동률 처리 — average rank 대신 stable sort로 분할.
    # 같은 값이라도 입력 순서대로 1/m, 2/m, ... 로 unique rank 할당.
    # 이유: 동률 종목 다수(시장 정체) 시 일부를 배제하는 필터 효과 → 신호 신뢰도 낮은
    # 동률 케이스에서 ranking 분산을 줄여요. (Strategy 2와 동일한 정책으로 일관성 유지)
    sorted_pairs = sorted(valid_pairs, key=lambda x: (x[0], x[1]))
    ranks = [0.0] * n
    m = len(sorted_pairs)
    for rank_idx, (_v, orig_i) in enumerate(sorted_pairs):
        # 1/m..1.0 (작은 값 = 낮은 rank)
        ranks[orig_i] = (rank_idx + 1) / m
    # 결측은 0.0
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
    raw_by_key: dict[str, list] = {}
    for prio in cfg.priorities:
        raw = [_extract_metric(c, prio.key) for c in survivors]
        raw_by_key[prio.key] = raw
        rank = _percentile_rank(raw)
        if prio.direction == "lower_better":
            # 작은 값이 좋음 → 1 - rank. 결측은 0.0 (가산 회피, PR-A).
            rank = [
                (1.0 - r) if raw[i] is not None else 0.0
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
        cand_meta = cand.metadata or {}
        for prio in cfg.priorities:
            n = normalized[prio.key][i]
            contrib = n * prio.weight  # 0~weight 범위
            contributions[prio.key] = contrib
            norm_metrics[prio.key] = n
            # 결측 사유 기록 (PR-A 분기): metadata의 '<key>_negative' 플래그 활용.
            value = raw_by_key[prio.key][i]
            negative_flag = bool(cand_meta.get(f"{prio.key}_negative", False))
            reason = _classify_missing(value, negative_flag)
            if reason != "PRESENT":
                norm_metrics[f"{prio.key}_missing_reason"] = reason
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
