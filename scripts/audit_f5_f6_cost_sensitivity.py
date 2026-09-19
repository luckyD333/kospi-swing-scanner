"""
audit_f5_f6_cost_sensitivity.py — 감사 F5/F6 후속: 비용·갭상승 체결 민감도 표 (§13-3).

5전략 default config 를 9 OOS 윈도우에서 scan 1회 수집(per-trade gross·gap%) 후,
비용·갭 제한 시나리오를 후처리로 적용한다. 청산은 BarTracker (stop/target 반영).

시나리오:
  비용 — 현행 0.30% / 세금·수수료 0.23% + 슬리피지 0.1/0.2/0.3% = 0.33/0.43/0.53%
  갭   — T+1 open 이 시그널 봉 close 대비 +3%/+10% 초과 갭상승 시 체결 skip (F6)

실행:
    .venv/bin/python scripts/audit_f5_f6_cost_sensitivity.py --cache-root .cache_wf
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest_engine.scan_adapter import (  # noqa: E402
    ScanBarConfig,
    _build_ctx,
    _track_position,
)
from backtest_engine.walk_forward import (  # noqa: E402
    WalkForwardConfig,
    _generate_windows,
)
from core.decision.per_ticker_regime import build_regime_grid  # noqa: E402
from scripts.wf_strategy_compare import STRATEGIES  # noqa: E402
from scripts.wf_validate_s2_to_s5 import load_history  # noqa: E402

logger = logging.getLogger(__name__)

_FIXED_FEES = 0.0023  # 2026 세제: 매도 0.20% + 위탁수수료 0.015%×2 (감사 F5)

COST_SCENARIOS = [
    ("현행 0.30%", 0.0030),
    ("slip0.1 (0.33%)", _FIXED_FEES + 0.0010),
    ("slip0.2 (0.43%)", _FIXED_FEES + 0.0020),
    ("slip0.3 (0.53%)", _FIXED_FEES + 0.0030),
]

GAP_SCENARIOS = [
    ("갭 무제한", None),
    ("갭>+3% skip", 0.03),
    ("갭>+10% skip", 0.10),
]


def collect_trades(
    factory,
    ohlcv_data: dict[str, pd.DataFrame],
    windows: list,
    cfg: ScanBarConfig,
    regime_grid: dict | None = None,
) -> list[dict]:
    """전략 default 로 OOS 윈도우 전체 trade 수집 (비용 미적용 gross + 진입 갭%).

    wf_strategy_compare.evaluate_strategy 와 동일 평가 경로 — 비용·갭 제한을
    후처리로 적용하기 위해 per-trade 기록만 반환.
    """
    strategy = factory({})
    trades: list[dict] = []

    for _train_start, _train_end, test_start, test_end in windows:
        buffered_start = test_start - pd.Timedelta(days=cfg.lookback_buffer_days)
        sliced = {
            t: df[(df.index >= buffered_start) & (df.index <= test_end)]
            for t, df in ohlcv_data.items()
        }
        sliced = {t: df for t, df in sliced.items() if len(df) > 0}
        if not sliced:
            continue
        all_dates = sorted(set().union(*[df.index for df in sliced.values()]))
        signal_dates = [d for d in all_dates if test_start <= d <= test_end]

        for d in signal_dates:
            ctx = _build_ctx(d, sliced, market=cfg.market, regime_grid=regime_grid)
            try:
                candidates = strategy.scan(ctx, top_n=cfg.top_n)
            except Exception:
                continue

            for cand in candidates[: cfg.top_n]:
                full_df = ohlcv_data.get(cand.ticker)
                if full_df is None:
                    continue
                future = full_df[full_df.index > d]
                if len(future) < cfg.holding_bars:
                    continue
                entry = float(future.iloc[0]["open"])
                if entry <= 0:
                    continue
                # 갭%: 시그널 시점 마지막 close 대비 T+1 open
                prior = full_df[full_df.index <= d]
                signal_close = float(prior.iloc[-1]["close"])
                if signal_close <= 0:
                    continue
                gap_pct = entry / signal_close - 1.0
                exit_p, bars, reason = _track_position(
                    future,
                    entry_price=entry,
                    stop_loss=cand.stop_loss,
                    target=cand.target_2,
                    max_holding_bars=cfg.holding_bars,
                )
                if reason == "INSUFFICIENT":
                    continue
                gross = (exit_p - entry) / entry
                trades.append({"gross": gross, "gap_pct": gap_pct})

    return trades


def aggregate(trades: list[dict], cost: float, max_gap: float | None) -> dict:
    sel = [t for t in trades if max_gap is None or t["gap_pct"] <= max_gap]
    if not sel:
        return {"n": 0, "total": 0.0, "mean": float("nan"), "win": float("nan")}
    arr = np.array([t["gross"] - cost for t in sel])
    return {
        "n": len(sel),
        "total": float(arr.sum() * 100),
        "mean": float(arr.mean() * 100),
        "win": float((arr > 0).mean() * 100),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="5 전략 비용·갭 민감도 표 (감사 F5/F6)")
    parser.add_argument("--cache-root", default=".cache_wf")
    parser.add_argument("--start-date", default="2025-05-19")
    parser.add_argument("--end-date", default="2026-05-19")
    parser.add_argument("--train-days", type=int, default=90)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=30)
    parser.add_argument("--holding-bars", type=int, default=3)
    parser.add_argument("--top-n", type=int, default=5)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    )

    data = load_history(Path(args.cache_root))
    logger.info(f"로드 완료: {len(data)}개 ticker")

    wf_cfg = WalkForwardConfig(
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        start_date=args.start_date,
        end_date=args.end_date,
        metric_name="sharpe",
        min_trades_for_metric=1,
    )
    windows = list(_generate_windows(wf_cfg))
    logger.info(f"WF 윈도우: {len(windows)}개 (OOS test 만 측정)")

    scan_cfg = ScanBarConfig(
        holding_bars=args.holding_bars,
        top_n=args.top_n,
        lookback_buffer_days=60,
    )

    grid = build_regime_grid(data)

    per_strategy: dict[str, list[dict]] = {}
    for name, factory in STRATEGIES:
        logger.info(f"=== {name} 수집 ===")
        trades = collect_trades(factory, data, windows, scan_cfg, regime_grid=grid)
        per_strategy[name] = trades
        logger.info(f"  {len(trades)} trades")

    # 표 1: 비용 민감도 (갭 무제한) — cell = total% (mean%)
    print()
    print("표 1. 비용 민감도 — 누적 수익률% (평균 pnl%)")
    header = f"{'전략':<22}" + "".join(f"{label:>20}" for label, _ in COST_SCENARIOS)
    print(header)
    print("-" * len(header))
    for name, trades in per_strategy.items():
        cells = []
        for _label, cost in COST_SCENARIOS:
            r = aggregate(trades, cost, max_gap=None)
            cells.append(f"{r['total']:>+10.2f} ({r['mean']:+.3f})")
        print(f"{name:<22}" + "".join(f"{c:>20}" for c in cells))

    # 표 2: 갭상승 체결 제한 (현행 비용 0.30%) — cell = total% (n)
    print()
    print("표 2. 갭상승 체결 제한 민감도 (비용 0.30%) — 누적 수익률% (trades)")
    header = f"{'전략':<22}" + "".join(f"{label:>20}" for label, _ in GAP_SCENARIOS)
    print(header)
    print("-" * len(header))
    for name, trades in per_strategy.items():
        cells = []
        for _label, max_gap in GAP_SCENARIOS:
            r = aggregate(trades, 0.0030, max_gap=max_gap)
            cells.append(f"{r['total']:>+10.2f} ({r['n']})")
        print(f"{name:<22}" + "".join(f"{c:>20}" for c in cells))


if __name__ == "__main__":
    main()
