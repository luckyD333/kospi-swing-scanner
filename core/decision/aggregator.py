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

from dataclasses import dataclass, field, replace

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

    NOT_APPLICABLE 은 풀 단위 결정 (PR-B) — aggregate_candidates 에서 별도 주입.
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
    pool: str = "STOCK",
) -> list[RankedCandidate]:
    """후보 리스트 + WeightConfig + Pool → RankedCandidate (final_score 내림차순).

    PR-B (P0-2): pool 인자에 따라 cfg.priorities 의 applies_to_pools 와 매칭하지
    않는 priority 는 NOT_APPLICABLE 처리되어 가중치가 0 으로 빠지고, 적용 priority
    만으로 가중치가 동적 정규화 (sum=100 유지). 풀별 ranking 분리는 호출자가 풀별
    candidates 를 분리해 별도 호출.
    """
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

    # 2) PR-B: pool 별 priority 필터링 + 가중치 동적 정규화
    active = [p for p in cfg.priorities if pool in p.applies_to_pools]
    excluded_keys = [p.key for p in cfg.priorities if pool not in p.applies_to_pools]
    if not active:
        return []  # 적용 가능 priority 없으면 ranking 불가
    active_total = sum(p.weight for p in active)
    if active_total <= 0:
        return []
    scale = 100.0 / active_total
    scaled = [replace(p, weight=p.weight * scale) for p in active]

    # 3) priority 별 percentile rank 정규화 (active 만)
    normalized: dict[str, list[float]] = {}
    raw_by_key: dict[str, list] = {}
    for prio in scaled:
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

    # 4) 가중 합산
    # 스케일: contribution = (정규화 점수 0~1) × (정규화된 가중치) → 합 100 보장.
    # final_score = sum(contributions) → 0~100 범위.
    # 제외된 priority 는 normalized_metrics 에 NOT_APPLICABLE 사유로 기록 (가산 0).
    ranked: list[RankedCandidate] = []
    for i, cand in enumerate(survivors):
        contributions: dict[str, float] = {}
        norm_metrics: dict[str, float | int | str] = {}
        total = 0.0
        cand_meta = cand.metadata or {}
        for prio in scaled:
            n = normalized[prio.key][i]
            contrib = n * prio.weight
            contributions[prio.key] = contrib
            norm_metrics[prio.key] = n
            # PR-A: 결측 사유 (NEGATIVE_EARNINGS / DATA_MISSING)
            value = raw_by_key[prio.key][i]
            negative_flag = bool(cand_meta.get(f"{prio.key}_negative", False))
            reason = _classify_missing(value, negative_flag)
            if reason != "PRESENT":
                norm_metrics[f"{prio.key}_missing_reason"] = reason
            total += contrib
        # PR-B: 풀 미적용 priority 는 NOT_APPLICABLE
        for k in excluded_keys:
            contributions[k] = 0.0
            norm_metrics[k] = 0.0
            norm_metrics[f"{k}_missing_reason"] = "NOT_APPLICABLE"
        ranked.append(RankedCandidate(
            candidate=cand,
            final_score=round(total, 4),
            contributions={k: round(v, 4) for k, v in contributions.items()},
            normalized_metrics=norm_metrics,
        ))

    # 4.5) tradability_score (PR-K): volume·stop_pct·atr_pct 백분위 합산 (0~100).
    #      final_score 와 독립된 거래 용이성 차원. final_score 미변경 (D2 결정).
    vol_raw  = [float(c.volume_20d_avg or 0.0) for c in survivors]
    stop_raw = [
        (c.entry_price - c.stop_loss) / max(c.entry_price, 1) * 100
        for c in survivors
    ]
    atr_pct_raw = [
        ((c.metadata or {}).get("atr_14") or 0.0) / max(c.entry_price, 1) * 100
        for c in survivors
    ]
    vol_rank  = _percentile_rank(vol_raw)
    stop_rank = _percentile_rank(stop_raw)
    atr_rank  = _percentile_rank(atr_pct_raw)
    for i, rc in enumerate(ranked):
        ts = (
            vol_rank[i]          * 0.4  # 거래대금: 높을수록 좋음
            + (1 - stop_rank[i]) * 0.3  # 손절폭%: 낮을수록 좋음 → 역백분위
            + (1 - atr_rank[i])  * 0.3  # ATR/가격%: 낮을수록 안정적 → 역백분위
        ) * 100
        rc.normalized_metrics["tradability_score"] = round(ts, 2)

    # 5) final_score 내림차순. 동률 시 ticker 알파벳 순 (결정론).
    ranked.sort(key=lambda r: (-r.final_score, r.candidate.ticker))
    return ranked
