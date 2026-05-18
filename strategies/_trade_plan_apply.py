"""5 전략 공용 — scan() 종료 시점에 intra-strategy score percentile 기반 trade_plan
재산정 (Phase 2 Step 5).

candidate.metadata 에서 atr_14 / trade_plan_support_floor 를 읽어 ATR 기반 stop/target
재계산. score 분포가 클러스터된 전략 (audit Step 4.5: strategy_one) 은 score_pct=0.5
고정 (k_adj = base_k).
"""
from __future__ import annotations

import statistics

from core.strategy_base import Candidate
from core.trade_plan_calc import (
    compute_trade_plan,
    resolve_base_strategy_id,
)

from .price_utils import floor_to_tick, round_to_tick

# Step 4.5 audit (2026-05-18) 결과 — σ<0.15 전략은 score_pct 고정 (k 동적 무효화).
# 운영 후 walk-forward 데이터로 audit 재실행해 갱신.
_FIXED_SCORE_PCT_STRATEGIES: set[str] = {"strategy_one"}


def _intra_strategy_percentiles(scores: list[float]) -> list[float]:
    """raw scores → 자기 분포 안에서의 percentile [0, 1]. 동률은 평균 rank."""
    n = len(scores)
    if n == 0:
        return []
    if n == 1:
        return [0.5]
    sigma = statistics.pstdev(scores)
    if sigma == 0:
        return [0.5] * n
    indexed = sorted(range(n), key=lambda i: scores[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and scores[indexed[j]] == scores[indexed[i]]:
            j += 1
        avg = (i + 1 + j) / 2.0 / n
        for k in range(i, j):
            out[indexed[k]] = avg
        i = j
    return out


def apply_dynamic_trade_plan(
    candidates: list[Candidate],
    strategy_id: str,
) -> None:
    """In-place: candidates 의 stop_loss/target_1/target_2 를 ATR 기반 산식으로 갱신.

    candidate.metadata 요구사항:
      - "atr_14": float (없거나 0 이하면 skip — 기존 산식 유지)
      - "trade_plan_support_floor": float | None (선택; 차트 지지선)

    metadata 에 추가 저장:
      - "k_used": 최종 k_adj
      - "trade_plan_method": "atr_dynamic" (성공) 또는 "legacy_fallback" (skip)

    invariant 위반 시 (e.g. stop >= entry) skip — Candidate.__post_init__ 와 일관.
    """
    if not candidates:
        return
    try:
        base = resolve_base_strategy_id(strategy_id)
    except KeyError:
        # unknown strategy_id — 모두 legacy
        for c in candidates:
            c.metadata["trade_plan_method"] = "legacy_fallback"
        return

    use_fixed = base in _FIXED_SCORE_PCT_STRATEGIES
    if use_fixed:
        score_pcts = [0.5] * len(candidates)
    else:
        score_pcts = _intra_strategy_percentiles([c.score for c in candidates])

    for c, pct in zip(candidates, score_pcts):
        atr = c.metadata.get("atr_14")
        if atr is None or atr <= 0:
            c.metadata["trade_plan_method"] = "legacy_fallback"
            continue

        support_floor = c.metadata.get("trade_plan_support_floor")
        # entry/atr_14 는 위에서 검증 (>0), strategy_id 는 line 68 에서 검증.
        # compute_trade_plan 의 ValueError/KeyError 는 logic bug 신호 → silent fallback 금지.
        tp = compute_trade_plan(
            entry=c.entry_price,
            atr_14=float(atr),
            strategy_id=strategy_id,
            score_percentile=pct,
            support_floor=support_floor,
        )

        new_stop = floor_to_tick(tp.stop)
        new_t1 = round_to_tick(tp.target_1)
        new_t2 = round_to_tick(max(tp.target_2, tp.target_1))

        # Candidate.__post_init__ invariant: stop < entry < t1 <= t2
        if not (0 < new_stop < c.entry_price < new_t1 <= new_t2):
            c.metadata["trade_plan_method"] = "legacy_fallback"
            continue

        c.stop_loss = new_stop
        c.target_1 = new_t1
        c.target_2 = new_t2
        c.metadata["k_used"] = round(tp.k_used, 4)
        c.metadata["score_percentile"] = round(pct, 4)
        c.metadata["trade_plan_method"] = "atr_dynamic"
