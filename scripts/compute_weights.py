"""
scripts/compute_weights.py — 동적 가중치 주기 계산 Job.

사용:
    python scripts/compute_weights.py \
        --cache-root .cache \
        --scan-root scan_results \
        --output .cache/dynamic_weights.json

실패해도 종료 코드 0 (수집 파이프라인에서 호출 시 수집 성공에 영향 없음).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.decision.config import WeightConfig
from core.decision.factor_performance import (
    correlations_to_weights,
    measure_factor_correlations,
    update_factor_records,
)
from core.decision.market_regime import RegimeAnalysis, analyze_regime, apply_regime_overlay

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_WEIGHTS_YML = Path("weights.yml")


def compute_dynamic_weights(
    cache_root: Path,
    scan_root: Path,
    weights_yml: Path = _DEFAULT_WEIGHTS_YML,
) -> dict:
    """동적 가중치 계산 → dict 반환.

    1) weights.yml 로드 (없으면 에러 propagate)
    2) HMM regime 분석 (실패 시 regime_score=50)
    3) Factor Momentum 상관계수 계산 (비활성 시 skip)
    4) regime overlay 적용
    5) factor momentum 적용 (활성 시)
    반환 dict는 dynamic_weights.json 스키마와 일치.
    """
    # 1. base weights
    base_config = WeightConfig.load(weights_yml)

    # 2. HMM regime
    regime_score = 50
    hmm_meta: dict = {}
    try:
        analysis: RegimeAnalysis = analyze_regime(cache_root)
        regime_score = analysis.current_score
        hmm_meta = {
            "n_components": 2,
            "n_tickers": analysis.n_tickers,
            "n_days": analysis.n_days,
            "bull_state_mean_return": analysis.bull_state_mean_return,
            "bear_state_mean_return": analysis.bear_state_mean_return,
        }
        logger.info(f"HMM regime_score={regime_score}")
    except (ValueError, Exception) as e:
        logger.warning(f"HMM 분석 실패 (regime_score=50 fallback): {e}")

    # 3. Factor Momentum
    correlations: dict[str, float] = {}
    factor_momentum_active = False
    n_samples = 0
    try:
        records = update_factor_records(scan_root, cache_root)
        n_samples = len(records)
        correlations = measure_factor_correlations(records)
        factor_momentum_active = bool(correlations)
        if factor_momentum_active:
            logger.info(f"Factor Momentum 활성: {correlations}")
    except Exception as e:
        logger.warning(f"Factor Momentum 계산 실패 (skip): {e}")

    # 4. regime overlay
    adjusted_config = apply_regime_overlay(base_config, regime_score)

    # 5. factor momentum overlay
    if factor_momentum_active:
        adjusted_config = correlations_to_weights(correlations, adjusted_config)

    result = {
        "computed_at": datetime.now().isoformat(),
        "regime_score": regime_score,
        "factor_momentum_active": factor_momentum_active,
        "weight_config": {
            "priorities": [
                {
                    "key": p.key,
                    "weight": p.weight,
                    "direction": p.direction,
                    "label": p.label,
                }
                for p in adjusted_config.priorities
            ],
            "must_have": list(adjusted_config.must_have),
            "strategy_weights": dict(adjusted_config.strategy_weights),
        },
        "meta": {
            "n_samples": n_samples,
            "correlations": correlations,
            "regime_adjustment_applied": regime_score != 50,
            "hmm_n_tickers": hmm_meta.get("n_tickers", 0),
            "hmm_n_days": hmm_meta.get("n_days", 0),
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="동적 가중치 계산 Job")
    parser.add_argument("--cache-root", default=".cache")
    parser.add_argument("--scan-root", default="scan_results")
    parser.add_argument("--output", default=None, help="출력 경로 (기본: {cache_root}/dynamic_weights.json)")
    parser.add_argument("--weights-yml", default="weights.yml")
    args = parser.parse_args()

    cache_root = Path(args.cache_root)
    scan_root = Path(args.scan_root)
    output_path = Path(args.output) if args.output else cache_root / "dynamic_weights.json"
    weights_yml = Path(args.weights_yml)

    try:
        result = compute_dynamic_weights(cache_root, scan_root, weights_yml)
    except Exception as e:
        logger.error(f"동적 가중치 계산 실패: {e}")
        sys.exit(0)  # 수집 파이프라인에 영향 없음

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    logger.info(f"dynamic_weights 저장: {output_path} (regime_score={result['regime_score']})")

    # regime_analysis.json (UI용)
    regime_path = cache_root / "regime_analysis.json"
    regime_data = {
        "computed_at": result["computed_at"],
        "current_score": result["regime_score"],
        "history": [],
        "hmm_meta": result["meta"],
    }
    regime_path.write_text(json.dumps(regime_data, ensure_ascii=False, indent=2))
    logger.info(f"regime_analysis 저장: {regime_path}")


if __name__ == "__main__":
    main()
