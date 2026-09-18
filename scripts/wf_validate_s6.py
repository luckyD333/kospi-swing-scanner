"""
scripts/wf_validate_s6.py — Strategy Six 워크포워드 검증 (bar tracker, stop/target 추적).

python scripts/wf_validate_s6.py --cache-root .cache_wf --start-date 2025-05-19 --end-date 2026-05-19
결과: results/wf_validation/wf_s6_results.json

주의: lookback_buffer_days 는 캘린더 일수. S6 는 min_bars=80 이라 150 이상이어야 한다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest_engine.scan_adapter import ScanBarConfig, make_scan_bartracker_scorer  # noqa: E402
from backtest_engine.walk_forward import WalkForwardConfig, run_walk_forward  # noqa: E402
from scripts.wf_validate_s2_to_s5 import _s6_factory, load_history  # noqa: E402

logger = logging.getLogger(__name__)


def build_targets() -> list[dict]:
    return [
        {"label": "S6_default", "factory": _s6_factory, "param_grid": {"touch_atr_mult": [0.3]},
         "note": "기본값 기준선"},
        {"label": "S6_touch_atr_mult", "factory": _s6_factory,
         "param_grid": {"touch_atr_mult": [0.2, 0.3, 0.4, 0.5]}, "note": "터치 허용폭 민감도"},
        {"label": "S6_min_rr", "factory": _s6_factory,
         "param_grid": {"min_rr": [0.8, 1.0, 1.2, 1.5]}, "note": "손익비 하한 민감도"},
        {"label": "S6_breakout_window", "factory": _s6_factory,
         "param_grid": {"breakout_window_bars": [15, 30, 45]}, "note": "돌파 후 유효 기간"},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy Six WF 검증")
    parser.add_argument("--cache-root", default=".cache_wf")
    parser.add_argument("--output", default="results/wf_validation")
    # .cache_wf 이력은 2025-05-19 부터. 버퍼 150 캘린더일이 앞에 필요해 시작일을 뒤로 민다.
    parser.add_argument("--start-date", default="2025-10-20")
    parser.add_argument("--end-date", default="2026-05-19")
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=30)
    parser.add_argument("--holding-bars", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--lookback-buffer-days", type=int, default=150)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    data = load_history(Path(args.cache_root))          # 시그니처: (cache_root: Path) 인자 1개
    scan_cfg = ScanBarConfig(holding_bars=args.holding_bars, top_n=args.top_n,
                             lookback_buffer_days=args.lookback_buffer_days, emit_stats=True)
    wf_cfg = WalkForwardConfig(start_date=args.start_date, end_date=args.end_date,
                               train_days=args.train_days, test_days=args.test_days,
                               step_days=args.step_days)

    reports = []
    for tgt in build_targets():
        logger.info(f"=== {tgt['label']}: {tgt['note']} ===")
        scorer = make_scan_bartracker_scorer(tgt["factory"], scan_cfg)
        report = run_walk_forward(strategy_name=tgt["label"], evaluator=scorer,
                                  param_grid=tgt["param_grid"], ohlcv_data=data, config=wf_cfg)
        reports.append((tgt, report))

    def _num(x):
        return round(x, 4) if x == x else None        # NaN → None

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_json = output_dir / "wf_s6_results.json"
    out_json.write_text(json.dumps({
        "targets": [
            {
                "label": tgt["label"],
                "note": tgt["note"],
                **rep.summary(),                          # WFReport.summary() (walk_forward.py:166)
                "windows": [
                    {
                        "train_start": str(w.train_start.date()), "train_end": str(w.train_end.date()),
                        "test_start": str(w.test_start.date()), "test_end": str(w.test_end.date()),
                        "best_params": {k: str(v) for k, v in w.best_params.items()},
                        "train_metric": _num(w.train_metric), "test_metric": _num(w.test_metric),
                        "train_trades": w.train_trades, "test_trades": w.test_trades,
                    }
                    for w in rep.windows
                ],
            }
            for tgt, rep in reports
        ],
    }, indent=2, ensure_ascii=False))
    logger.info(f"JSON 저장: {out_json}")


if __name__ == "__main__":
    main()
