"""scripts/wf_validate_s2_to_s5.py — Phase 4 step B: S2~S5 2026-05-14 변경 WF 검증.

Phase 4 step A 에서 S1 engulf_strict 만 검증 (BacktestEngine 직접 호환).
S2~S5 는 Strategy Protocol(scan) 인터페이스만 노출하므로 backtest_engine.scan_adapter
의 N봉 PnL evaluator 를 통해 WF 검증.

검증 대상 (11개 파라미터, 2026-05-14 그리드 서치 변경):
  S5 tight_range_mult  1.5 → 2.5  🔴 매우 높음 (PF 0.81→4.57 jump on n=4)
  S5 vol_shrink_ratio  0.7 → 0.9  🔴 매우 높음 (signal 4→35건)
  S5 min_pole_pct      0.08 → 0.07  🟢 낮음
  S3 lookback          20 → 30      🔴 매우 높음
  S3 atr_filter_mult   0.5 → 0.7    🔴 매우 높음
  S3 atr_stop_mult     1.5 → 2.5    🔴 매우 높음
  S3 atr_target_mult   3.0 → 2.5    🔴 매우 높음
  S4 ma_trend          20 → 30      🟡 높음 (승률 44.9%→54.9%)
  S4 pullback_lookback 5 → 3        🟡 높음 (avgPnL 부호 뒤집힘)
  S2 lookback          15 → 20      🟢 낮음
  S2 entry_percentile  0.75 → 0.80  🟢 낮음

판정 (둘 다 PASS 시 유지):
  param_stability_score < 0.30   (각 파라미터 CV ≤ 30%)
  oos_metric_decay      < 0.40   (OOS Sharpe 저하 ≤ 40%)

사용:
    python scripts/wf_validate_s2_to_s5.py \\
        --cache-root .cache_wf \\
        --output results/wf_validation
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from backtest_engine.scan_adapter import ScanPnlConfig, make_scan_pnl_scorer  # noqa: E402
from backtest_engine.walk_forward import (  # noqa: E402
    WalkForwardConfig,
    WFReport,
    run_walk_forward,
)
from strategies.strategy_five_bull_flag import (  # noqa: E402
    StrategyFiveBullFlag,
    StrategyFiveConfig,
)
from strategies.strategy_four_pullback_ma import (  # noqa: E402
    StrategyFourConfig,
    StrategyFourPullbackMa,
)
from strategies.strategy_six_channel_grid import (  # noqa: E402
    StrategySixChannelGrid,
    StrategySixConfig,
)
from strategies.strategy_three_trend_following import (  # noqa: E402
    StrategyThreeConfig,
    StrategyThreeTrendFollowing,
)
from strategies.strategy_two_cross_sectional_momentum import (  # noqa: E402
    StrategyTwoConfig,
    StrategyTwoCrossSectionalMomentum,
)

logger = logging.getLogger(__name__)


# ---- 데이터 로드 -------------------------------------------------------------


def load_history(cache_root: Path) -> dict[str, pd.DataFrame]:
    """`{cache_root}/1D/*.parquet` → {ticker: df}."""
    files = sorted((cache_root / "1D").glob("*.parquet"))
    data: dict[str, pd.DataFrame] = {}
    for f in files:
        df = pd.read_parquet(f)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        data[f.stem] = df
    return data


# ---- Strategy factories ------------------------------------------------------


def _s2_factory(params: dict):
    base = StrategyTwoConfig()
    # rsi_max=None 운영 cfg 반영 (strategies/__init__.py)
    merged = {**base.__dict__, "rsi_max": None, **params}
    return StrategyTwoCrossSectionalMomentum(
        config=StrategyTwoConfig(**merged), timeframe="1D",
    )


def _s3_factory(params: dict):
    base = StrategyThreeConfig()
    merged = {**base.__dict__, **params}
    return StrategyThreeTrendFollowing(
        config=StrategyThreeConfig(**merged), timeframe="1D",
    )


def _s4_factory(params: dict):
    base = StrategyFourConfig()
    merged = {**base.__dict__, **params}
    return StrategyFourPullbackMa(
        config=StrategyFourConfig(**merged), timeframe="1D",
    )


def _s5_factory(params: dict):
    base = StrategyFiveConfig()
    merged = {**base.__dict__, **params}
    return StrategyFiveBullFlag(
        config=StrategyFiveConfig(**merged), timeframe="1D",
    )


def _s6_factory(params: dict):
    base = StrategySixConfig()
    merged = {**base.__dict__, **params}
    return StrategySixChannelGrid(config=StrategySixConfig(**merged), timeframe="1D")


# ---- 검증 대상 ---------------------------------------------------------------


def build_targets() -> list[dict]:
    """11개 변경에 대한 (factory, single-param grid) 정의."""
    return [
        # ----- S5 -----
        {
            "label": "S5_tight_range_mult",
            "factory": _s5_factory,
            "param_grid": {"tight_range_mult": [1.0, 1.5, 2.0, 2.5, 3.0]},
            "note": "2026-05-14: 1.5 → 2.5 (PF 0.81→4.57 jump on n=4) — 의심도 🔴",
        },
        {
            "label": "S5_vol_shrink_ratio",
            "factory": _s5_factory,
            "param_grid": {"vol_shrink_ratio": [0.5, 0.7, 0.8, 0.9, 1.0]},
            "note": "2026-05-14: 0.7 → 0.9 (signal 4→35) — 의심도 🔴",
        },
        {
            "label": "S5_min_pole_pct",
            "factory": _s5_factory,
            "param_grid": {"min_pole_pct": [0.05, 0.06, 0.07, 0.08, 0.10]},
            "note": "2026-05-14: 0.08 → 0.07 — 의심도 🟢",
        },
        # ----- S3 -----
        {
            "label": "S3_lookback",
            "factory": _s3_factory,
            "param_grid": {"lookback": [15, 20, 25, 30, 40]},
            "note": "2026-05-14: 20 → 30 — 의심도 🔴",
        },
        {
            "label": "S3_atr_filter_multiplier",
            "factory": _s3_factory,
            "param_grid": {"atr_filter_multiplier": [0.0, 0.3, 0.5, 0.7, 1.0]},
            "note": "2026-05-14: 0.5 → 0.7 — 의심도 🔴",
        },
        {
            "label": "S3_atr_stop_mult",
            "factory": _s3_factory,
            "param_grid": {"atr_stop_mult": [1.0, 1.5, 2.0, 2.5, 3.0]},
            "note": "2026-05-14: 1.5 → 2.5 — 의심도 🔴",
        },
        {
            "label": "S3_atr_target_mult",
            "factory": _s3_factory,
            "param_grid": {"atr_target_mult": [2.0, 2.5, 3.0, 3.5, 4.0]},
            "note": "2026-05-14: 3.0 → 2.5 — 의심도 🔴",
        },
        # ----- S4 -----
        {
            "label": "S4_ma_trend",
            "factory": _s4_factory,
            "param_grid": {"ma_trend": [15, 20, 25, 30, 40]},
            "note": "2026-05-14: 20 → 30 (승률 44.9%→54.9%) — 의심도 🟡",
        },
        {
            "label": "S4_pullback_lookback",
            "factory": _s4_factory,
            "param_grid": {"pullback_lookback": [2, 3, 4, 5, 7]},
            "note": "2026-05-14: 5 → 3 (avgPnL 부호 뒤집힘) — 의심도 🟡",
        },
        # ----- S2 -----
        {
            "label": "S2_lookback",
            "factory": _s2_factory,
            "param_grid": {"lookback": [10, 15, 20, 25, 30]},
            "note": "2026-05-14: 15 → 20 — 의심도 🟢",
        },
        {
            "label": "S2_entry_percentile",
            "factory": _s2_factory,
            "param_grid": {"entry_percentile": [0.70, 0.75, 0.80, 0.85, 0.90]},
            "note": "2026-05-14: 0.75 → 0.80 — 의심도 🟢",
        },
        # ----- Grid 확장 재검증 (advisor 지적: 기존 grid 가장자리 PASS) -----
        {
            "label": "S3_atr_stop_mult_ext",
            "factory": _s3_factory,
            "param_grid": {"atr_stop_mult": [0.5, 0.75, 1.0, 1.5, 2.0]},
            "note": "Grid 확장: 기존 1.0 best 9/9 — 더 낮은 값까지 탐색",
        },
        {
            "label": "S3_atr_target_mult_ext",
            "factory": _s3_factory,
            "param_grid": {"atr_target_mult": [1.0, 1.5, 2.0, 2.5, 3.0]},
            "note": "Grid 확장: 기존 2.0 best 9/9 — 더 낮은 값까지 탐색",
        },
    ]


# ---- 메인 -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="S2~S5 2026-05-14 변경 WF 검증")
    parser.add_argument("--cache-root", default=".cache_wf")
    parser.add_argument("--output", default="results/wf_validation")
    parser.add_argument(
        "--start-date", default="2025-05-19",
        help="WF 시작일 (yyyy-mm-dd)",
    )
    parser.add_argument(
        "--end-date", default="2026-05-19",
        help="WF 종료일 (yyyy-mm-dd)",
    )
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=30)
    parser.add_argument(
        "--min-trades", type=int, default=3,
        help="윈도우당 최소 거래 수 (이하 NaN 처리)",
    )
    parser.add_argument(
        "--holding-bars", type=int, default=3,
        help="N봉 PnL 청산 (1~7일 spec, default 3)",
    )
    parser.add_argument(
        "--top-n", type=int, default=5,
        help="scan() 호출당 채택 후보 수",
    )
    parser.add_argument(
        "--only",
        help="단일 target label만 실행 (예: S5_tight_range_mult)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    cache_root = Path(args.cache_root)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1) 데이터 로드
    logger.info(f"로드: {cache_root}/1D/*.parquet")
    data = load_history(cache_root)
    logger.info(f"로드 완료: {len(data)}개 ticker")

    # 2) WF config
    wf_cfg = WalkForwardConfig(
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        start_date=args.start_date,
        end_date=args.end_date,
        metric_name="sharpe",
        min_trades_for_metric=args.min_trades,
    )

    scan_cfg = ScanPnlConfig(
        holding_bars=args.holding_bars,
        top_n=args.top_n,
        commission_pct=0.0030,
        lookback_buffer_days=60,
    )

    targets = build_targets()
    if args.only:
        targets = [t for t in targets if t["label"] == args.only]
        if not targets:
            logger.error(f"--only={args.only}: 매칭 label 없음")
            sys.exit(1)

    # 3) 각 target WF 실행
    reports: list[tuple[dict, WFReport]] = []
    for tgt in targets:
        logger.info(f"=== {tgt['label']}: {tgt['note']} ===")
        scorer = make_scan_pnl_scorer(tgt["factory"], scan_cfg)
        report = run_walk_forward(
            strategy_name=tgt["label"],
            evaluator=scorer,
            param_grid=tgt["param_grid"],
            ohlcv_data=data,
            config=wf_cfg,
        )
        reports.append((tgt, report))

        for i, w in enumerate(report.windows, 1):
            logger.info(
                f"  W{i}: train[{w.train_start.date()}~{w.train_end.date()}] "
                f"best={w.best_params} train={w.train_metric:.3f} "
                f"test={w.test_metric:.3f} (trades train={w.train_trades}, test={w.test_trades})"
            )
        logger.info(
            f"  → stability={report.param_stability_score}, "
            f"decay={report.oos_metric_decay:.3f}, verdict={report.verdict}"
        )

    # 4) JSON 저장
    summary = {
        "generated_at": datetime.now().isoformat(),
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
            for tgt, rep in reports
        ],
    }
    out_json = output_dir / "wf_s2_to_s5_results.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info(f"JSON 저장: {out_json}")


if __name__ == "__main__":
    main()
