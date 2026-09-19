"""scripts/wf_strategy_compare.py — 7 전략 default config OOS 수익률 비교.

본 세션의 BarTracker scan_adapter 를 사용해 S1~S7 의 default config 를 같은
9 OOS 윈도우에서 동일 조건으로 평가. 표 형식 출력.

사용:
    python scripts/wf_strategy_compare.py --cache-root .cache_wf
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
from scripts.wf_validate_s2_to_s5 import (  # noqa: E402
    _s2_factory,
    _s3_factory,
    _s4_factory,
    _s5_factory,
    _s6_factory,
    _s7_factory,
    load_history,
)
from strategies.strategy_one_d_v2 import (  # noqa: E402
    StrategyOneDv2,
    StrategyOneDv2Config,
)

logger = logging.getLogger(__name__)


def _s1_factory(_params: dict):
    return StrategyOneDv2(config=StrategyOneDv2Config(), timeframe="1D")


STRATEGIES = [
    ("S1_MeanReversion", _s1_factory),
    ("S2_CrossSectional", _s2_factory),
    ("S3_TrendFollowing", _s3_factory),
    ("S4_PullbackMA",     _s4_factory),
    ("S5_BullFlag",       _s5_factory),
    ("S6_ChannelGrid",    _s6_factory),
    ("S7_CfiReversal",    _s7_factory),
]


def evaluate_strategy(
    factory,
    ohlcv_data: dict[str, pd.DataFrame],
    windows: list,
    cfg: ScanBarConfig,
) -> dict:
    """전략 default 로 windows 안 모든 trade 누적 → 집계 통계."""
    strategy = factory({})  # default config
    all_trades: list[float] = []
    bars_held_all: list[int] = []
    stats = {"STOP": 0, "TARGET": 0, "TIME": 0, "GAP_DOWN": 0}

    for _train_start, _train_end, test_start, test_end in windows:
        # test 구간만 (OOS) — train 은 default 라 fit 안 함
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
            ctx = _build_ctx(d, sliced, market=cfg.market)
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
                pnl = gross - cfg.commission_pct
                all_trades.append(pnl)
                bars_held_all.append(bars)
                stats[reason] += 1

    n = len(all_trades)
    if n == 0:
        return {"n_trades": 0, "sharpe": float("nan"), "win_rate": float("nan"),
                "total_return_pct": 0.0, "mean_pnl_pct": float("nan"),
                "avg_bars_held": float("nan"), **stats}

    arr = np.array(all_trades)
    wins = int((arr > 0).sum())
    mean = float(arr.mean())
    std = float(arr.std(ddof=0))
    avg_bars = float(np.mean(bars_held_all))
    sharpe = (
        mean / std * np.sqrt(252.0 / max(avg_bars, 1.0)) if std > 1e-9 else 0.0
    )
    return {
        "n_trades": n,
        "wins": wins,
        "win_rate": wins / n * 100,
        "total_return_pct": float(arr.sum() * 100),
        "mean_pnl_pct": mean * 100,
        "sharpe": sharpe,
        "avg_bars_held": avg_bars,
        **stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="5 전략 default WF OOS 비교")
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

    cache_root = Path(args.cache_root)
    data = load_history(cache_root)
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
        commission_pct=0.0030,
        lookback_buffer_days=150,  # S6 min_bars=80(거래일) — 캘린더 150일 필요
        emit_stats=False,
    )

    results = []
    for name, factory in STRATEGIES:
        logger.info(f"=== {name} ===")
        r = evaluate_strategy(factory, data, windows, scan_cfg)
        r["name"] = name
        results.append(r)
        logger.info(
            f"  trades={r['n_trades']}, win={r.get('win_rate', float('nan')):.1f}%, "
            f"total={r['total_return_pct']:+.2f}%, mean={r.get('mean_pnl_pct', float('nan')):+.3f}%, "
            f"sharpe={r['sharpe']:.3f}"
        )

    # 표 형식 출력
    print()
    print("=" * 100)
    print(
        f"{'전략':<22} {'trades':>7} {'win%':>7} {'total%':>9} "
        f"{'mean%':>8} {'sharpe':>7} {'avgBars':>8} "
        f"{'STOP':>5} {'TGT':>5} {'TIME':>5} {'GAP':>5}"
    )
    print("-" * 100)
    for r in results:
        print(
            f"{r['name']:<22} {r['n_trades']:>7} "
            f"{r.get('win_rate', float('nan')):>7.1f} "
            f"{r['total_return_pct']:>+9.2f} "
            f"{r.get('mean_pnl_pct', float('nan')):>+8.3f} "
            f"{r['sharpe']:>7.3f} "
            f"{r.get('avg_bars_held', float('nan')):>8.2f} "
            f"{r['STOP']:>5} {r['TARGET']:>5} {r['TIME']:>5} {r['GAP_DOWN']:>5}"
        )
    print("=" * 100)


if __name__ == "__main__":
    main()
