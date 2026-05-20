"""output/holding_recommender.py — 상황별 holding 추천 lookup.

aggregate_holding_recommendations.py 가 생성한 data/holding_recommendations.json
를 로드해 (strategy, market_regime, fng_label, per_ticker_regime, atr_bucket)
조합에 대해 추천 보유 봉 수 + 신뢰도 반환.

결합 규칙:
  1. per_ticker_regime == "DOWNTREND_STRONG" → SKIP (진입 비추천)
  2. primary[strategy][market_regime] 결측/n<min_n → LOW_CONFIDENCE
  3. final = clamp(primary.best + sum(modifiers), 1, 7), confidence = n/100 clamp [0,1]

스키마 버전:
  - v2.0: modifier_per_ticker / modifier_atr 가 {regime: {label: delta}} nested.
  - v1.0: 동 modifier 가 {label: delta} flat. 로드 시 deprecation warning + fallback.
  - modifier_fng 는 두 버전 모두 flat (historical F&G 부재로 NOOP, runtime 만 작동).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

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
    """JSON 파일 로드. 파일 부재 시 빈 dict (lookup 시 LOW_CONFIDENCE).

    v1.0 스키마 감지 시 deprecation warning. lookup 은 schema_version 에 따라
    nested(v2.0) / flat(v1.0) 자동 분기.
    """
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    version = str(data.get("schema_version", "1.0"))
    if version.startswith("1."):
        logger.warning(
            "holding_recommendations.json schema v%s deprecated — "
            "v2.0 으로 재생성하세요 (scripts/aggregate_holding_recommendations.py)",
            version,
        )
    return data


def _lookup_modifier(table: dict, market_regime: str, label: str):
    """schema-aware modifier lookup.

    v2.0 nested ({regime: {label: delta}}) 우선, v1.0 flat ({label: delta}) fallback.
    값이 dict 면 nested, 그 외(int/str/None) 면 flat 로 간주.
    """
    if not isinstance(table, dict) or not table:
        return None
    # nested 판정: 최소 하나의 값이 dict 면 v2.0
    sample = next(iter(table.values()), None)
    if isinstance(sample, dict):
        return table.get(market_regime, {}).get(label)
    return table.get(label)


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

    # 1) DOWNTREND_STRONG → 진입 비추천 (per_ticker_regime 라벨 자체로 게이트)
    if per_ticker_regime == "DOWNTREND_STRONG":
        return HoldingRecommendation(None, 0.0, "SKIP")
    mod_per_raw = recs.get("modifier_per_ticker", {})
    # nested skip lookup (v2.0) + flat fallback (v1.0)
    if per_ticker_regime is not None:
        if _lookup_modifier(mod_per_raw, market_regime, per_ticker_regime) == "skip":
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
        # modifier_fng 는 historical 부재로 flat 유지 (NOOP). runtime 만 작동.
        v = recs.get("modifier_fng", {}).get(fng_label)
        if isinstance(v, (int, float)):
            delta += int(v)
    if per_ticker_regime is not None:
        v = _lookup_modifier(mod_per_raw, market_regime, per_ticker_regime)
        if isinstance(v, (int, float)):
            delta += int(v)
    if atr_bucket is not None:
        v = _lookup_modifier(recs.get("modifier_atr", {}), market_regime, atr_bucket)
        if isinstance(v, (int, float)):
            delta += int(v)

    final = max(HOLDING_MIN, min(HOLDING_MAX, base + delta))
    n = int(primary["n_trades"])
    confidence = max(0.0, min(1.0, n / 100.0))
    return HoldingRecommendation(final, confidence, "OK")
