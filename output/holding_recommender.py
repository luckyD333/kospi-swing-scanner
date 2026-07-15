"""output/holding_recommender.py — 상황별 holding 추천 lookup.

aggregate_holding_recommendations.py 가 생성한 data/holding_recommendations.json
를 로드해 (strategy, market_regime, per_ticker_regime, atr_bucket)
조합에 대해 추천 보유 봉 수 + 신뢰도 반환.

결합 규칙:
  1. per_ticker_regime == "DOWNTREND_STRONG" → SKIP (진입 비추천)
  2. primary[strategy][market_regime] 결측/n<min_n → LOW_CONFIDENCE
  3. final = clamp(primary.best + sum(modifiers), 1, 7), confidence = n/100 clamp [0,1]

스키마 버전:
  - v2.0: modifier_per_ticker / modifier_atr 가 {regime: {label: delta}} nested.
  - v1.0: 동 modifier 가 {label: delta} flat. 로드 시 deprecation warning + fallback.
  - modifier_fng / fng_label 은 구형 파일·호출 호환용이며 의사결정에는 사용하지 않음.
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

_BACKTEST_STRATEGY_KEYS = {
    "S1_MeanReversion",
    "S2_CrossSectional",
    "S3_TrendFollowing",
    "S4_PullbackMA",
    "S5_BullFlag",
}

_RUNTIME_TO_BACKTEST_STRATEGY: tuple[tuple[str, str], ...] = (
    ("strategy_one_", "S1_MeanReversion"),
    ("strategy_two", "S2_CrossSectional"),
    ("strategy_three", "S3_TrendFollowing"),
    ("strategy_four", "S4_PullbackMA"),
    ("strategy_five", "S5_BullFlag"),
)


@dataclass
class HoldingRecommendation:
    """단일 종목에 대한 추천 결과."""
    recommended_bars: Optional[int]
    confidence: float
    status: Status


def canonical_holding_strategy(
    strategy: str,
    timeframe: str | None = None,
) -> str | None:
    """런타임 strategy id 를 holding 백테스트 strategy key 로 변환.

    현재 data/holding_recommendations.json 은 1D 백테스트 기반 전략군 key
    (S1_MeanReversion 등) 만 가진다. 1h/30m/1W 신호에는 같은 값을 억지
    환산하지 않기 위해 None 을 반환한다.
    """
    if timeframe is not None and timeframe != "1D":
        return None
    if strategy in _BACKTEST_STRATEGY_KEYS:
        return strategy
    for prefix, backtest_key in _RUNTIME_TO_BACKTEST_STRATEGY:
        if strategy.startswith(prefix):
            return backtest_key
    return strategy


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
    timeframe: str | None = None,
) -> HoldingRecommendation:
    """결합 규칙 적용 후 추천 결과 반환.

    ``fng_label``은 구형 호출 호환을 위해 받지만 정보 지표이므로 무시한다.
    """
    if not recs:
        return HoldingRecommendation(None, 0.0, "LOW_CONFIDENCE")

    strategy_key = canonical_holding_strategy(strategy, timeframe)
    if strategy_key is None:
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
    primary = recs.get("primary", {}).get(strategy_key, {}).get(market_regime)
    min_n = int(recs.get("min_trades_per_cell", MIN_TRADES_DEFAULT))
    if not primary or primary.get("n_trades", 0) < min_n:
        return HoldingRecommendation(None, 0.0, "LOW_CONFIDENCE")

    base = int(primary["best"])

    # 3) modifier sum
    delta = 0
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
