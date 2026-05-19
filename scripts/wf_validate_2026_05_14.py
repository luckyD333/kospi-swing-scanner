"""scripts/wf_validate_2026_05_14.py — 2026-05-14 파라미터 변경 12개 WF 검증.

Phase 4 (.claude/plans/active/2026-05-19-backtest-robustness-cpo.md).

목적: 2026-05-14 단일 90일 그리드 서치로 변경된 파라미터를 롤링 train/test
윈도우로 재검증해, 인접 윈도우 간 안정성과 OOS 성과 저하를 측정한다.

판정 (둘 다 PASS 시 유지):
  param_stability_score < 0.30  (각 파라미터의 CV ≤ 30%)
  oos_metric_decay      < 0.40  (OOS Sharpe 저하 ≤ 40%)

대상 (현재 step A — Strategy 1 only):
  S1: engulf_strict (True → False, 2026-05-14)

향후 step B 에서 S2~S5 evaluator 추가 예정.

데이터: .cache_wf/1D/*.parquet (scripts/collect_wf_history.py 로 1년치 수집).

사용:
    python scripts/wf_validate_2026_05_14.py \\
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

from backtest_engine.engine import BacktestConfig, BacktestEngine  # noqa: E402
from backtest_engine.strategy import StrategyD, StrategyDConfig  # noqa: E402
from backtest_engine.walk_forward import (  # noqa: E402
    WalkForwardConfig,
    WFReport,
    compute_sharpe,
    run_walk_forward,
)

logger = logging.getLogger(__name__)


# ---- 데이터 로드 -------------------------------------------------------------


def load_history(cache_root: Path) -> dict[str, pd.DataFrame]:
    """`{cache_root}/1D/*.parquet` → {ticker: df}.

    DataFrame index 는 DatetimeIndex 로 가정.
    """
    files = sorted((cache_root / "1D").glob("*.parquet"))
    data: dict[str, pd.DataFrame] = {}
    for f in files:
        df = pd.read_parquet(f)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        data[f.stem] = df
    return data


# ---- Strategy 1 evaluator ----------------------------------------------------


_LOOKBACK_BUFFER_DAYS = 45   # min_lookback_bars(25 거래일) + 여유


def _strategy_one_scorer(
    ohlcv_data: dict[str, pd.DataFrame],
    params: dict,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[float, int]:
    """Strategy 1 (StrategyD) WF scorer.

    윈도우 구간으로 ohlcv 슬라이스 → BacktestEngine.run_multi → Sharpe / 거래수.

    Lookback buffer (45 calendar days, 약 30 거래일) 를 추가로 포함해 BacktestEngine
    의 지표 계산이 시작점부터 거래 신호 생성 가능하도록 한다. start 이전 데이터는
    lookback 으로만 사용되고 실제 거래는 start 이후에만 발생 (StrategyD 내부에서
    min_lookback_bars=25 미달 시 check_entry 가 None 반환).
    """
    buffered_start = start - pd.Timedelta(days=_LOOKBACK_BUFFER_DAYS)
    sliced: dict[str, pd.DataFrame] = {}
    for ticker, df in ohlcv_data.items():
        sub = df[(df.index >= buffered_start) & (df.index <= end)]
        if len(sub) >= 30:
            sliced[ticker] = sub
    if not sliced:
        return float("nan"), 0

    strategy_cfg = StrategyDConfig(**params)
    strategy = StrategyD(config=strategy_cfg)
    bt_cfg = BacktestConfig()  # commission_pct=0.0030 (Phase 1 기본)
    engine = BacktestEngine(strategy=strategy, config=bt_cfg)

    try:
        result = engine.run_multi(sliced)
    except Exception as exc:
        logger.warning("BacktestEngine 실패 (params=%s, window=%s~%s): %s",
                       params, start.date(), end.date(), exc)
        return float("nan"), 0

    sharpe = compute_sharpe(result.equity_curve)
    return sharpe, result.total_trades


# ---- 메인 -------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="2026-05-14 변경 WF 검증")
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
    parser.add_argument(
        "--train-days", type=int, default=90,
        help="train 윈도우 거래일 (기본 90)",
    )
    parser.add_argument(
        "--test-days", type=int, default=30,
        help="test 윈도우 거래일 (기본 30)",
    )
    parser.add_argument(
        "--step-days", type=int, default=30,
        help="윈도우 이동 간격 (기본 30)",
    )
    parser.add_argument(
        "--min-trades", type=int, default=3,
        help="윈도우당 최소 거래 수 (이하 NaN 처리)",
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

    # 2) WF 실행 — Strategy 1 / engulf_strict 검증
    wf_cfg = WalkForwardConfig(
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        start_date=args.start_date,
        end_date=args.end_date,
        metric_name="sharpe",
        min_trades_for_metric=args.min_trades,
    )

    targets = [
        {
            "label": "S1_engulf_strict",
            "strategy_name": "strategy_one_d_v2",
            "param_grid": {"engulf_strict": [True, False]},
            "scorer": _strategy_one_scorer,
            "note": "2026-05-14 변경: True → False (의심도 🟡 중간)",
        },
    ]

    reports: list[WFReport] = []
    for tgt in targets:
        logger.info(f"=== {tgt['label']}: {tgt['note']} ===")
        report = run_walk_forward(
            strategy_name=tgt["strategy_name"],
            evaluator=tgt["scorer"],
            param_grid=tgt["param_grid"],
            ohlcv_data=data,
            config=wf_cfg,
        )
        reports.append(report)

        # 윈도우별 출력
        for i, w in enumerate(report.windows, 1):
            logger.info(
                f"  W{i}: train[{w.train_start.date()}~{w.train_end.date()}] "
                f"best={w.best_params} train_metric={w.train_metric:.3f} "
                f"test_metric={w.test_metric:.3f} (trades train={w.train_trades}, test={w.test_trades})"
            )
        logger.info(
            f"  → stability={report.param_stability_score}, "
            f"decay={report.oos_metric_decay:.3f}, verdict={report.verdict}"
        )

    # 3) 결과 JSON 저장
    summary = {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "train_days": args.train_days,
            "test_days": args.test_days,
            "step_days": args.step_days,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "min_trades_for_metric": args.min_trades,
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
                            if w.train_metric == w.train_metric  # NaN check
                            else None
                        ),
                        "test_metric": (
                            round(w.test_metric, 4)
                            if w.test_metric == w.test_metric
                            else None
                        ),
                        "train_trades": w.train_trades,
                        "test_trades": w.test_trades,
                    }
                    for w in rep.windows
                ],
            }
            for tgt, rep in zip(targets, reports)
        ],
    }
    out_json = output_dir / "wf_2026_05_14_results.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info(f"JSON 저장: {out_json}")


if __name__ == "__main__":
    main()
