"""output/holding_recommender.py — 상황별 holding 추천 lookup.

aggregate_holding_recommendations.py 가 생성한 data/holding_recommendations.json
를 로드해 (strategy, market_regime, fng_label, per_ticker_regime, atr_bucket)
조합에 대해 추천 보유 봉 수 + 신뢰도 반환.

결합 규칙:
  1. per_ticker_regime == "DOWNTREND_STRONG" → SKIP (진입 비추천)
  2. primary[strategy][market_regime] 결측/n<min_n → LOW_CONFIDENCE
  3. final = clamp(primary.best + sum(modifiers), 1, 7), confidence = n/100 clamp [0,1]
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

Status = Literal["OK", "SKIP", "LOW_CONFIDENCE"]
MIN_TRADES_DEFAULT = 30
HOLDING_MIN = 1
HOLDING_MAX = 7


@dataclass
class HoldingRecommendation:
    """단일 종목에 대한 추천 결과."""
    recommended_bars: Optional[int]
    confidence: float
    status: Status


def load_recommendations(path: str | Path) -> dict:
    """JSON 파일 로드. 파일 부재 시 빈 dict (lookup 시 LOW_CONFIDENCE)."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def recommend_holding(
    recs: dict,
    strategy: str,
    market_regime: str,
    fng_label: Optional[str],
    per_ticker_regime: Optional[str],
    atr_bucket: Optional[str],
) -> HoldingRecommendation:
    """결합 규칙 적용 후 추천 결과 반환."""
    if not recs:
        return HoldingRecommendation(None, 0.0, "LOW_CONFIDENCE")

    # 1) DOWNTREND_STRONG → 진입 비추천
    if per_ticker_regime == "DOWNTREND_STRONG":
        return HoldingRecommendation(None, 0.0, "SKIP")
    mod_per = recs.get("modifier_per_ticker", {})
    if per_ticker_regime is not None and mod_per.get(per_ticker_regime) == "skip":
        return HoldingRecommendation(None, 0.0, "SKIP")

    # 2) primary lookup
    primary = recs.get("primary", {}).get(strategy, {}).get(market_regime)
    min_n = int(recs.get("min_trades_per_cell", MIN_TRADES_DEFAULT))
    if not primary or primary.get("n_trades", 0) < min_n:
        return HoldingRecommendation(None, 0.0, "LOW_CONFIDENCE")

    base = int(primary["best"])

    # 3) modifier sum
    delta = 0
    if fng_label is not None:
        v = recs.get("modifier_fng", {}).get(fng_label)
        if isinstance(v, (int, float)):
            delta += int(v)
    if per_ticker_regime is not None:
        v = mod_per.get(per_ticker_regime)
        if isinstance(v, (int, float)):
            delta += int(v)
    if atr_bucket is not None:
        v = recs.get("modifier_atr", {}).get(atr_bucket)
        if isinstance(v, (int, float)):
            delta += int(v)

    final = max(HOLDING_MIN, min(HOLDING_MAX, base + delta))
    n = int(primary["n_trades"])
    confidence = max(0.0, min(1.0, n / 100.0))
    return HoldingRecommendation(final, confidence, "OK")
