"""
core/decision/runner.py — 의사결정 엔진 entry point.

scan_results manifest에서 후보 로드 → aggregator + ensemble → markdown 출력.

사용 흐름:
  1. cli.py --strategy all 실행 후 scan_results/* 갱신됨
  2. cli.py --decide --top-n N → run_decide_ranking → decision_top{N}.md
  3. cli.py --decide --select TICKERS --notes "..." → run_decide_journal
       → journal_{ticker}.md 파일들
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from core.strategy_base import Candidate

from .aggregator import aggregate_candidates
from .config import WeightConfig
from .ensemble import (
    apply_minimax_regret,
    auto_volatility_scenarios,
    compute_weighted_ensemble_score,
)

logger = logging.getLogger(__name__)


def load_candidates_from_manifest(
    scan_root: Path,
) -> dict[str, list[Candidate]]:
    """
    scan_results/manifest.json → {strategy_name: [Candidate, ...]}.

    각 manifest entry 의 latest_file (JSON 형식) 을 읽어 Candidate 객체로 복원.
    JSON 파일이 없거나 파싱 실패하면 해당 전략 skip.
    """
    manifest_path = scan_root / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"manifest 읽기 실패: {e}")
        return {}

    by_strategy: dict[str, list[Candidate]] = {}
    for key, entry in manifest.items():
        # key 형태: "{strategy_name}__{timeframe}"
        if "__" not in key:
            continue
        strategy_name, _tf = key.rsplit("__", 1)
        latest = entry.get("latest_file", "")
        if not latest.endswith(".json"):
            continue
        json_path = scan_root / latest
        if not json_path.exists():
            logger.warning(f"latest_file 없음: {json_path}")
            continue
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"scan JSON 읽기 실패 {json_path}: {e}")
            continue
        cands = []
        for obj in payload.get("candidates", []):
            try:
                cands.append(_candidate_from_json(obj, default_strategy=strategy_name))
            except (KeyError, ValueError) as e:
                logger.debug(f"Candidate 복원 실패 {obj.get('ticker')}: {e}")
                continue
        if cands:
            # 같은 전략이 여러 entry 면 합집합 (multi-tf 케이스)
            by_strategy.setdefault(strategy_name, []).extend(cands)
    return by_strategy


def _candidate_from_json(obj: dict, default_strategy: str) -> Candidate:
    metrics = obj.get("metrics", {}) or {}
    metadata = {
        k: v for k, v in metrics.items()
        if k not in {
            "strategy", "signal_date",
            "current_price", "entry_price", "stop_loss", "target_1", "target_2",
            "market_cap_bil", "volume_20d_avg",
            "risk_pct", "reward_pct_t1", "reward_pct_t2",
            "conditions_met",
        }
    }
    conditions_met = metrics.get("conditions_met") or {}
    # score 필드 누락은 명시적으로 경고 (무음으로 0.0 부여 시 의도치 않은 최하위 랭킹 위험)
    score_val = obj.get("score")
    if score_val is None:
        logger.warning(
            f"score 필드 누락 {obj.get('ticker', '?')}: 기본값 0.0 사용 — "
            "JSON 형식이 변경됐는지 확인하세요."
        )
        score_val = 0.0
    return Candidate(
        ticker=obj["ticker"],
        name=obj.get("name", obj["ticker"]),
        strategy=metrics.get("strategy", default_strategy),
        signal_date=pd.Timestamp(metrics.get("signal_date", "1970-01-01")),
        score=float(score_val),
        entry_price=float(metrics["entry_price"]),
        stop_loss=float(metrics["stop_loss"]),
        target_1=float(metrics["target_1"]),
        target_2=float(metrics["target_2"]),
        current_price=float(metrics["current_price"]) if metrics.get("current_price") is not None else 0.0,
        market_cap_bil=float(metrics.get("market_cap_bil", 0.0)),
        volume_20d_avg=float(metrics.get("volume_20d_avg", 0.0)),
        conditions_met=dict(conditions_met),
        metadata=metadata,
    )


def _build_unique_pool(
    by_strategy: dict[str, list[Candidate]],
    strategy_weights: dict[str, float] | None = None,
) -> list[Candidate]:
    """ticker별 1개 후보만 유지 (가장 높은 score 우선). ensemble 메타 주입."""
    sw = strategy_weights or {}
    weighted_scores = compute_weighted_ensemble_score(by_strategy, sw)
    chosen: dict[str, Candidate] = {}
    for cands in by_strategy.values():
        for c in cands:
            existing = chosen.get(c.ticker)
            if existing is None or c.score > existing.score:
                chosen[c.ticker] = c
    for ticker, cand in chosen.items():
        ws = weighted_scores.get(ticker, 1.0)
        cand.metadata = {
            **(cand.metadata or {}),
            "ensemble_count": int(round(ws)),   # 표시용 (decision_journal.py 기존 코드 호환)
            "ensemble_score": ws,               # aggregator percentile 정렬용 (float)
        }
    return list(chosen.values())


def run_decide_ranking(
    scan_root: Path,
    target_date: str,
    top_n: int,
    weight_config: WeightConfig,
    *,
    dynamic_weights_path: Path | None = None,
) -> Path:
    """후보 통합 ranking → scan_results/{date}/decision_top{N}.md 저장."""
    from output.decision_journal import format_ranking_report

    if dynamic_weights_path is not None and dynamic_weights_path.exists():
        try:
            weight_config = WeightConfig.load_dynamic(dynamic_weights_path)
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"dynamic_weights 로드 실패, static fallback: {e}")

    by_strategy = load_candidates_from_manifest(scan_root)
    pool = _build_unique_pool(by_strategy, strategy_weights=weight_config.strategy_weights)
    ranked = aggregate_candidates(pool, weight_config)
    # Minimax Regret (자동 변동성 시나리오) 보조 정렬
    if ranked:
        regret_fn = auto_volatility_scenarios(ranked)
        ranked = apply_minimax_regret(ranked, regret_fn)

    md = format_ranking_report(ranked, target_date, top_n, weight_config)
    out_path = scan_root / target_date / f"decision_top{top_n}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    logger.info(f"📝 ranking 저장: {out_path}")
    return out_path


def run_decide_journal(
    scan_root: Path,
    target_date: str,
    tickers: list[str],
    weight_config: WeightConfig,
    notes: str | None = None,
    *,
    dynamic_weights_path: Path | None = None,
) -> list[Path]:
    """선택 ticker별 Decision Journal 파일 생성."""
    from output.decision_journal import format_decision_journal

    if dynamic_weights_path is not None and dynamic_weights_path.exists():
        try:
            weight_config = WeightConfig.load_dynamic(dynamic_weights_path)
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"dynamic_weights 로드 실패, static fallback: {e}")

    by_strategy = load_candidates_from_manifest(scan_root)
    pool = _build_unique_pool(by_strategy, strategy_weights=weight_config.strategy_weights)
    ranked = aggregate_candidates(pool, weight_config)
    if ranked:
        regret_fn = auto_volatility_scenarios(ranked)
        ranked = apply_minimax_regret(ranked, regret_fn)

    by_ticker = {r.candidate.ticker: r for r in ranked}
    paths: list[Path] = []
    out_dir = scan_root / target_date
    out_dir.mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        rc = by_ticker.get(ticker)
        if rc is None:
            logger.warning(f"후보 풀에 없는 ticker skip: {ticker}")
            continue
        md = format_decision_journal(rc, weight_config, notes=notes)
        p = out_dir / f"journal_{ticker}.md"
        p.write_text(md, encoding="utf-8")
        paths.append(p)
        logger.info(f"📝 journal 저장: {p}")
    return paths
