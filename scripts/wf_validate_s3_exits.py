"""scripts/wf_validate_s3_exits.py — S3 청산 파라미터 BarTracker WF 검증.

기존 `wf_validate_s2_to_s5.py` 의 N봉 PnL scorer 는 Candidate.stop_loss/target_2
를 무시 → S3 atr_stop_mult × atr_target_mult 그리드에서 셀별 동일 metric 산출
(Finding 7, 2026-05-19 본 세션 기록).

본 스크립트는 `make_scan_bartracker_scorer` 로 같은 그리드를 재실행해서
어댑터 한계 해소를 확인하고 청산 파라미터 결정 근거를 만든다.

대상:
  S3 atr_stop_mult   × atr_target_mult   (5×4 = 20셀)
  옵션: S1 atr_stop_mult × atr_target_mult (--include-s1)

사용:
    python scripts/wf_validate_s3_exits.py \\
        --cache-root .cache_wf \\
        --output results/wf_validation/s3_exits/

판정:
  - 셀별 train/test metric 이 **서로 다른** 값으로 채워져야 PASS
    (모두 동일 값 -0.334 면 어댑터 한계 미해소)
  - exit_reason 분포가 STOP/TARGET/TIME 에 합리적으로 분산되어야 PASS
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest_engine.scan_adapter import (  # noqa: E402
    ScanBarConfig,
    make_scan_bartracker_scorer,
)
from backtest_engine.walk_forward import (  # noqa: E402
    WalkForwardConfig,
    WFReport,
    run_walk_forward,
)
from scripts.wf_validate_s2_to_s5 import (  # noqa: E402
    _s2_factory,
    _s3_factory,
    _s4_factory,
    load_history,
)
from strategies.strategy_one_d_v2 import (  # noqa: E402
    StrategyOneDv2,
    StrategyOneDv2Config,
)

logger = logging.getLogger(__name__)


def _s1_factory(params: dict):
    """S1 factory — wf_validate_s2_to_s5 에는 없어 본 스크립트에서 정의."""
    base = StrategyOneDv2Config()
    merged = {**base.__dict__, **params}
    return StrategyOneDv2(config=StrategyOneDv2Config(**merged), timeframe="1D")


def build_targets(include_s1: bool) -> list[dict]:
    """2D 그리드 (stop × target) 정의."""
    targets: list[dict] = [
        {
            "label": "S3_exits_2d",
            "factory": _s3_factory,
            "param_grid": {
                "atr_stop_mult": [1.0, 1.5, 2.0, 2.5, 3.0],
                "atr_target_mult": [2.0, 2.5, 3.0, 3.5],
            },
            "note": (
                "S3 청산 2D 그리드 — BarTracker scorer 로 Finding 7 해소 검증. "
                "셀별 동일값 (N봉 scorer 결과 -0.334) → 다른값 으로 변동되면 PASS."
            ),
        },
        {
            "label": "S3_exits_2d_ext",
            "factory": _s3_factory,
            "param_grid": {
                "atr_stop_mult": [0.5, 0.75, 1.0, 1.25, 1.5],
                "atr_target_mult": [1.0, 1.5, 2.0, 2.5],
            },
            "note": (
                "Grid 확장 — 1라운드 best (1.0, 2.0) 가 양쪽 차원 모두 grid "
                "가장자리. interior best 또는 edge 재확인 목적 (advisor 권고)."
            ),
        },
        {
            "label": "S2_atr_target_mult_bt",
            "factory": _s2_factory,
            "param_grid": {"atr_target_mult": [2.0, 2.5, 3.0, 3.5, 4.0]},
            "note": (
                "S2 atr_target_mult — t2 = entry + ATR × mult (live param). "
                "BarTracker 어댑터 가치 검증: 1D 그리드에서 셀별 다른 metric 나와야 정상."
            ),
        },
        {
            "label": "S4_atr_target_mult_bt",
            "factory": _s4_factory,
            "param_grid": {"atr_target_mult": [2.0, 2.5, 3.0, 3.5, 4.0]},
            "note": (
                "S4 atr_target_mult — t2 = entry + ATR × mult (live param). "
                "BarTracker 어댑터 가치 검증 동일."
            ),
        },
    ]
    if include_s1:
        targets.append({
            "label": "S1_exits_2d",
            "factory": _s1_factory,
            "param_grid": {
                "atr_stop_mult": [1.0, 1.5, 2.0, 2.5],
                "atr_target_mult": [2.0, 2.5, 3.0, 3.5],
            },
            "note": "S1 청산 2D 그리드 — atr 기반 stop/target 영향 측정.",
        })
    return targets


def main() -> None:
    parser = argparse.ArgumentParser(description="S3 청산 BarTracker WF 검증")
    parser.add_argument("--cache-root", default=".cache_wf")
    parser.add_argument("--output", default="results/wf_validation/s3_exits")
    parser.add_argument("--start-date", default="2025-05-19")
    parser.add_argument("--end-date", default="2026-05-19")
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=30)
    parser.add_argument("--min-trades", type=int, default=3)
    parser.add_argument(
        "--holding-bars", type=int, default=3,
        help="최대 보유 봉 수 (조기 stop/target 도달 시 단축)",
    )
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument(
        "--include-s1", action="store_true",
        help="S1 atr_stop × atr_target 2D 그리드도 검증",
    )
    parser.add_argument("--only", help="단일 target label만 실행")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    cache_root = Path(args.cache_root)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"로드: {cache_root}/1D/*.parquet")
    data = load_history(cache_root)
    logger.info(f"로드 완료: {len(data)}개 ticker")

    wf_cfg = WalkForwardConfig(
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        start_date=args.start_date,
        end_date=args.end_date,
        metric_name="sharpe",
        min_trades_for_metric=args.min_trades,
    )

    scan_cfg = ScanBarConfig(
        holding_bars=args.holding_bars,
        top_n=args.top_n,
        commission_pct=0.0030,
        lookback_buffer_days=60,
        emit_stats=True,
    )

    targets = build_targets(include_s1=args.include_s1)
    if args.only:
        targets = [t for t in targets if t["label"] == args.only]
        if not targets:
            logger.error(f"--only={args.only}: 매칭 label 없음")
            sys.exit(1)

    reports: list[tuple[dict, WFReport, dict]] = []
    for tgt in targets:
        logger.info(f"=== {tgt['label']}: {tgt['note']} ===")
        scorer = make_scan_bartracker_scorer(tgt["factory"], scan_cfg)
        report = run_walk_forward(
            strategy_name=tgt["label"],
            evaluator=scorer,
            param_grid=tgt["param_grid"],
            ohlcv_data=data,
            config=wf_cfg,
        )
        # 마지막 호출의 exit_reason 분포 (대표값 — emit_stats=True 의 부산물)
        last_stats = getattr(scorer, "last_stats", {})
        reports.append((tgt, report, last_stats))

        for i, w in enumerate(report.windows, 1):
            logger.info(
                f"  W{i}: train[{w.train_start.date()}~{w.train_end.date()}] "
                f"best={w.best_params} "
                f"train={w.train_metric:.3f} test={w.test_metric:.3f} "
                f"(trades train={w.train_trades}, test={w.test_trades})"
            )
        logger.info(
            f"  → stability={report.param_stability_score}, "
            f"decay={report.oos_metric_decay:.3f}, verdict={report.verdict}"
        )
        if last_stats:
            logger.info(f"  → exit_reason (last window): {last_stats}")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "scorer": "BarTracker (stop/target 추적)",
        "config": {
            "train_days": args.train_days,
            "test_days": args.test_days,
            "step_days": args.step_days,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "min_trades_for_metric": args.min_trades,
            "holding_bars": args.holding_bars,
            "top_n": args.top_n,
            "commission_pct": scan_cfg.commission_pct,
        },
        "reports": [
            {
                "label": tgt["label"],
                "strategy_name": rep.strategy_name,
                "param_grid": {k: list(map(str, v)) for k, v in rep.param_grid.items()},
                "note": tgt["note"],
                "n_windows": len(rep.windows),
                "param_stability_score": rep.param_stability_score,
                "oos_metric_decay": rep.oos_metric_decay,
                "passed_stability": rep.passed_stability,
                "passed_decay": rep.passed_decay,
                "verdict": rep.verdict,
                "exit_reason_last_window": stats,
                "windows": [
                    {
                        "train_start": str(w.train_start.date()),
                        "train_end": str(w.train_end.date()),
                        "test_start": str(w.test_start.date()),
                        "test_end": str(w.test_end.date()),
                        "best_params": {k: str(v) for k, v in w.best_params.items()},
                        "train_metric": (
                            round(w.train_metric, 4)
                            if w.train_metric == w.train_metric else None
                        ),
                        "test_metric": (
                            round(w.test_metric, 4)
                            if w.test_metric == w.test_metric else None
                        ),
                        "train_trades": w.train_trades,
                        "test_trades": w.test_trades,
                    }
                    for w in rep.windows
                ],
            }
            for tgt, rep, stats in reports
        ],
    }
    out_json = output_dir / "wf_s3_exits_results.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info(f"JSON 저장: {out_json}")


if __name__ == "__main__":
    main()
