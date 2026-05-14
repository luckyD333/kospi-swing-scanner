"""
core/decision/regret_scorer.py — 비대칭 후회 점수 산출.

"지금 진입할 만한 R:R 비대칭" 식별을 위한 4축 가중합 점수.
각 축은 cross-sectional percentile (0~1) 로 정규화 후 가중합 → 0~100:

  - bull_reward (+):       Candidate.reward_pct_t2     — 목표 수익률
  - max_drawdown (-):      Candidate.risk_pct          — 손절 위험 (역, lower_better)
  - dist_to_stop (+):      (current - stop)/current    — 손절까지 여유
  - signal_freshness (+):  bars_since_trigger 기반    — 신호 freshness (exponential decay)

설계:
  - aggregator._percentile_rank 패턴 재사용 (결정론적 unique rank)
  - lower_better 축 (max_drawdown, signal_freshness의 decay) 은 (1 - rank) 적용
  - 후보 1개 이하면 regret_score = 0
  - 동률 시 final_score 큰 순 → ticker 알파벳 (결정론)
"""
from __future__ import annotations

from dataclasses import dataclass

from core.strategy_base import Candidate

from .aggregator import RankedCandidate
from .factors.signal_freshness import compute_signal_freshness


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
    """R:R 비대칭 + freshness 기반 기회 점수 가중치. 합 = 1.0."""
    bull_reward: float = 0.40
    max_drawdown: float = 0.20
    dist_to_stop: float = 0.15
    signal_freshness: float = 0.25


DEFAULT_WEIGHTS = RegretWeights()

# TF별 신호강도 가중치 배율 (1D 기준 1.0)
_TF_SIGNAL_FACTOR: dict[str, float] = {
    "1D": 1.0, "1W": 1.0, "1h": 0.7, "30m": 0.5,
}
# 3-Score 합성 기본 가중치
_W_OPP: float = 0.50    # 기회 (regret_score)
_W_POT: float = 0.30    # 잠재력 (final_score)
_W_SIG_BASE: float = 0.20   # 신호 강도 (c.score percentile, TF 배율 적용)


def _infer_tf(strategy_id: str) -> str:
    """strategy_id 토큰으로 timeframe 추정 (signals_builder._infer_timeframe_from_id 동일 로직)."""
    sid = (strategy_id or "").lower()
    if "_30m" in sid:
        return "30m"
    if "_1h" in sid:
        return "1h"
    if "_w_v2" in sid or sid.endswith("_w") or "_1w" in sid:
        return "1W"
    return "1D"


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


def _signal_freshness(cand: Candidate) -> float | None:
    """신호 freshness score (exponential decay).

    candidate.metadata 에 'bars_since_trigger' 가 있으면 그것 사용.
    없으면 0 (즉시 신호, fallback).
    """
    bars = cand.metadata.get("bars_since_trigger", 0) if cand.metadata else 0
    return compute_signal_freshness(bars)


def compute_regret_scores(
    ranked: list[RankedCandidate],
    ensemble_scores: dict[str, float] | None = None,
    weights: RegretWeights | None = None,
) -> list[RankedCandidate]:
    """R:R 비대칭 + freshness 기반 기회 점수 + rank 부여 후 정렬된 리스트 반환.

    각 RankedCandidate.normalized_metrics 에 다음 키 주입:
      regret_score  (float, 0~100)
      regret_rank   (int,   1-based)
      regret_total  (int,   전체 수)

    4 factor (신규):
      - bull_reward (40%): Candidate.reward_pct_t2
      - max_drawdown (20%): Candidate.risk_pct (lower_better)
      - dist_to_stop (15%): (current - stop)/current
      - signal_freshness (25%): metadata['bars_since_trigger'] 기반 exponential decay

    - ensemble_scores: 이제 사용하지 않음 (하위호환 위해 매개변수만 유지)
    - weights: None 이면 DEFAULT_WEIGHTS.
    """
    w = weights or DEFAULT_WEIGHTS

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
    freshs: list[float | None] = [_signal_freshness(rc.candidate) for rc in ranked]

    bull_rank = _avg_percentile_rank(bulls)
    dd_rank = _avg_percentile_rank(dds)
    dist_rank = _avg_percentile_rank(dists)
    fresh_rank = _avg_percentile_rank(freshs)

    # max_drawdown 은 lower_better → 1 - r, 결측은 0.5 유지
    dd_norm = [
        (1.0 - r) if dds[i] is not None else 0.5
        for i, r in enumerate(dd_rank)
    ]

    annotated: list[tuple[float, RankedCandidate]] = []
    for i, rc in enumerate(ranked):
        score01 = (
            w.bull_reward * bull_rank[i]
            + w.max_drawdown * dd_norm[i]
            + w.dist_to_stop * dist_rank[i]
            + w.signal_freshness * fresh_rank[i]
        )
        score = round(score01 * 100, 4)
        rc.normalized_metrics["regret_score"] = score
        rc.normalized_metrics["regret_total"] = n
        # 4축 개별 normalized 값 저장 (UI factor breakdown 용).
        # max_drawdown 은 dd_norm(=1-rank, 반전 후) 을 저장해 contribution 합산이
        # regret_score 와 일치하도록 한다.
        rc.normalized_metrics["regret_bull_reward"] = round(bull_rank[i], 4)
        rc.normalized_metrics["regret_max_drawdown"] = round(dd_norm[i], 4)
        rc.normalized_metrics["regret_dist_to_stop"] = round(dist_rank[i], 4)
        rc.normalized_metrics["regret_signal_freshness"] = round(fresh_rank[i], 4)
        annotated.append((score, rc))

    # composite_score: 3-score 합성 + TF 배율 적용
    raw_scores = [rc.candidate.score for rc in ranked]
    signal_ranks = _avg_percentile_rank(raw_scores)   # c.score pool percentile (0~1)

    for i, rc in enumerate(ranked):
        tf = _infer_tf(rc.candidate.strategy)
        tf_factor = _TF_SIGNAL_FACTOR.get(tf, 1.0)
        w_sig = _W_SIG_BASE * tf_factor
        scale = 1.0 / (_W_OPP + _W_POT + w_sig)
        rs = rc.normalized_metrics.get("regret_score", 0.0)
        composite = (
            _W_OPP * rs / 100.0
            + _W_POT * rc.final_score / 100.0
            + w_sig * signal_ranks[i]
        ) * scale * 100.0
        rc.normalized_metrics["composite_score"] = round(composite, 4)
        rc.normalized_metrics["signal_rank"] = round(signal_ranks[i], 4)

    # composite_score 내림차순 → final_score → ticker (결정론)
    annotated.sort(
        key=lambda t: (
            -t[1].normalized_metrics.get("composite_score", 0.0),
            -t[1].final_score,
            t[1].candidate.ticker,
        )
    )
    for rank_idx, (_, rc) in enumerate(annotated, start=1):
        rc.normalized_metrics["composite_rank"] = rank_idx
        rc.normalized_metrics["composite_total"] = len(annotated)
        rc.normalized_metrics["regret_rank"] = rank_idx  # backward compat

    return [rc for _s, rc in annotated]
