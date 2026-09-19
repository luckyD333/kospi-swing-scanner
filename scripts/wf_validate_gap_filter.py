"""
wf_validate_gap_filter.py — 갭상승 진입 필터 (max_entry_gap_pct) WF 검증.

감사 F6 후속 측정(audit_f5_f6_cost_sensitivity)에서 갭>+3% skip 이 S2/S3/S4 를
일관 개선하는 부수 발견 → 운영 반영 전 정식 WF 검증 (2026-05-14 단일 그리드 교훈).

방법: per-trade(date·gross·gap%·bars) 전 기간 1회 수집 (BarTracker 청산, default
config) 후,
  (a) 고정 +3% 필터 vs 무필터 — 윈도우별 OOS sharpe·수익률 비교 (운영 규칙 직접 검증)
  (b) threshold grid WF — train best 선택 → OOS decay·stability
      (backtest_engine.walk_forward.WFReport 기준: CV<0.30, decay<0.40)

실행:
    .venv/bin/python scripts/wf_validate_gap_filter.py --cache-root .cache_wf
"""
from __future__ import annotations

import argparse
import logging
import math
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
    WFReport,
    WFWindow,
    _generate_windows,
)
from core.decision.per_ticker_regime import build_regime_grid  # noqa: E402
from scripts.wf_strategy_compare import STRATEGIES  # noqa: E402
from scripts.wf_validate_s2_to_s5 import load_history  # noqa: E402

logger = logging.getLogger(__name__)

_NO_FILTER = 10.0  # 무제한 sentinel (갭 +1000% = 필터 없음)
GAP_GRID = [0.01, 0.03, 0.05, 0.10, _NO_FILTER]
_COMMISSION = 0.0030
_MIN_TRAIN_TRADES = 5  # walk_forward.WalkForwardConfig.min_trades_for_metric 기본


def collect_trades_full(
    factory,
    ohlcv_data: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
    cfg: ScanBarConfig,
    regime_grid: dict | None = None,
) -> list[dict]:
    """전략 default 로 [start, end] 전 거래일 scan → per-trade 기록 (비용 미적용)."""
    strategy = factory({})
    all_dates = sorted(set().union(*[df.index for df in ohlcv_data.values()]))
    signal_dates = [d for d in all_dates if start <= d <= end]
    trades: list[dict] = []

    for d in signal_dates:
        ctx = _build_ctx(d, ohlcv_data, market=cfg.market, regime_grid=regime_grid)
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
            trades.append({"date": d, "gross": gross, "gap_pct": gap_pct, "bars": bars})

    return trades


def _window_metric(
    trades: list[dict],
    start: pd.Timestamp,
    end: pd.Timestamp,
    max_gap: float,
) -> tuple[float, int, float]:
    """(sharpe, n_trades, total_pnl%) — wf_strategy_compare 와 동일 sharpe 산식."""
    sel = [t for t in trades if start <= t["date"] <= end and t["gap_pct"] <= max_gap]
    if not sel:
        return float("nan"), 0, 0.0
    arr = np.array([t["gross"] - _COMMISSION for t in sel])
    mean = float(arr.mean())
    std = float(arr.std(ddof=0))
    avg_bars = float(np.mean([t["bars"] for t in sel]))
    sharpe = mean / std * np.sqrt(252.0 / max(avg_bars, 1.0)) if std > 1e-9 else 0.0
    return float(sharpe), len(sel), float(arr.sum() * 100)


def main() -> None:
    parser = argparse.ArgumentParser(description="갭상승 진입 필터 WF 검증 (감사 F6 후속)")
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
        min_trades_for_metric=_MIN_TRAIN_TRADES,
    )
    windows = list(_generate_windows(wf_cfg))
    logger.info(f"WF 윈도우: {len(windows)}개")

    scan_cfg = ScanBarConfig(
        holding_bars=args.holding_bars,
        top_n=args.top_n,
        lookback_buffer_days=60,
    )

    collect_start = pd.Timestamp(args.start_date)
    collect_end = pd.Timestamp(args.end_date)
    grid = build_regime_grid(data)

    for name, factory in STRATEGIES:
        logger.info(f"=== {name} 수집 ===")
        trades = collect_trades_full(
            factory, data, collect_start, collect_end, scan_cfg, regime_grid=grid,
        )
        logger.info(f"  {len(trades)} trades (전 기간)")

        # (a) 고정 +3% 필터 vs 무필터 — 윈도우별 OOS 비교
        improved = 0
        compared = 0
        tot_no, tot_f3 = 0.0, 0.0
        for _tr_s, _tr_e, te_s, te_e in windows:
            m_no, n_no, p_no = _window_metric(trades, te_s, te_e, _NO_FILTER)
            m_f3, n_f3, p_f3 = _window_metric(trades, te_s, te_e, 0.03)
            tot_no += p_no
            tot_f3 += p_f3
            if n_no > 0:
                compared += 1
                if p_f3 > p_no:
                    improved += 1
        print(f"\n[{name}] (a) 고정 갭>+3% skip vs 무필터 — OOS {len(windows)}윈도우")
        print(f"  OOS 누적 pnl: 무필터 {tot_no:+.2f}% → 필터 {tot_f3:+.2f}% "
              f"(개선 윈도우 {improved}/{compared})")

        # (b) threshold grid WF — train best 선택 → OOS
        wf_windows: list[WFWindow] = []
        for tr_s, tr_e, te_s, te_e in windows:
            best: tuple[float, float, int] | None = None  # (g, metric, n)
            for g in GAP_GRID:
                m, n, _p = _window_metric(trades, tr_s, tr_e, g)
                if n < _MIN_TRAIN_TRADES or math.isnan(m):
                    continue
                if best is None or m > best[1]:
                    best = (g, m, n)
            if best is None:
                continue
            g_best, train_m, train_n = best
            test_m, test_n, _ = _window_metric(trades, te_s, te_e, g_best)
            wf_windows.append(WFWindow(
                train_start=tr_s, train_end=tr_e,
                test_start=te_s, test_end=te_e,
                best_params={"max_entry_gap_pct": g_best},
                train_metric=train_m, test_metric=test_m,
                train_trades=train_n, test_trades=test_n,
            ))

        report = WFReport(
            strategy_name=name,
            param_grid={"max_entry_gap_pct": GAP_GRID},
            windows=wf_windows,
            config=wf_cfg,
        )
        best_series = [w.best_params["max_entry_gap_pct"] for w in wf_windows]
        best_str = ", ".join("무제한" if g == _NO_FILTER else f"{g:.2f}" for g in best_series)
        stability = report.param_stability_score.get("max_entry_gap_pct", float("nan"))
        print(f"  (b) grid WF — 유효 윈도우 {len(wf_windows)}/{len(windows)}")
        print(f"      best 시계열: [{best_str}]")
        print(f"      stability CV={stability:.3f}, OOS decay={report.oos_metric_decay:.3f}, "
              f"verdict={report.verdict}")


if __name__ == "__main__":
    main()
