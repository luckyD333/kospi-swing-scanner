"""scripts/aggregate_holding_recommendations.py — 전략 × 상황별 최적 holding 추출.

plan: warm-percolating-cosmos.md
실행 흐름:
  1. .cache_wf 로드 + 매 거래일 universe-wide 라벨 cache 생성
       - market_regime: universe equal-weight 20D SMA slope → BULL/NEUTRAL/BEAR (proxy)
       - per_ticker_regime: build_per_ticker_regime_map (7-label)
       - atr_distribution: 각 ticker 의 ATR%(=ATR(14)/close)
  2. 9 WF 윈도우 × 5 전략 × holdings [1,3,5,7] BarTracker (emit_per_trade=True)
  3. trades 수집 후 라벨 부여 (signal_date + ticker 기준 lookup)
  4. Marginal aggregation:
       Primary: strategy × market_regime → best holding by mean PnL (min 30 trades)
       Modifier: fng/per_ticker/atr_bucket marginal delta vs primary baseline
  5. data/holding_recommendations.json 저장

사용:
    python scripts/aggregate_holding_recommendations.py \\
        --cache-root .cache_wf --output data/holding_recommendations.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest_engine.scan_adapter import (  # noqa: E402
    ScanBarConfig,
    make_scan_bartracker_scorer,
)
from backtest_engine.walk_forward import (  # noqa: E402
    WalkForwardConfig,
    _generate_windows,
)
from core.decision.atr_volatility import bucket_atr, compute_atr_pct  # noqa: E402
from core.decision.per_ticker_regime import (  # noqa: E402
    build_per_ticker_regime_map,
)
from scripts.wf_strategy_compare import STRATEGIES  # noqa: E402
from scripts.wf_validate_s2_to_s5 import load_history  # noqa: E402

logger = logging.getLogger(__name__)


# ---- 라벨 cache 생성 -------------------------------------------------------


def _market_regime_proxy(close_array: np.ndarray) -> str:
    """universe equal-weight 20D return slope → BULL/NEUTRAL/BEAR.

    KOSPI index 데이터 부재 시 fallback proxy.
    """
    if len(close_array) < 21:
        return "NEUTRAL"
    recent = close_array[-20:]
    older = close_array[-21:-1]
    ret = (recent.mean() - older.mean()) / older.mean()
    if ret > 0.005:
        return "BULL"
    if ret < -0.005:
        return "BEAR"
    return "NEUTRAL"


def build_label_cache(
    data: dict[str, pd.DataFrame],
    signal_dates: list[pd.Timestamp],
) -> dict[pd.Timestamp, dict]:
    """각 거래일별 universe-wide 라벨 cache."""
    logger.info(f"라벨 cache 생성: {len(signal_dates)}일 × {len(data)} ticker")

    # universe equal-weight close 시리즈 (market regime proxy 용)
    all_indices = sorted(set().union(*[df.index for df in data.values()]))
    aligned = pd.DataFrame(index=all_indices)
    for ticker, df in data.items():
        aligned[ticker] = df["close"]
    universe_close = aligned.mean(axis=1, skipna=True)

    cache: dict[pd.Timestamp, dict] = {}
    for d in signal_dates:
        # market regime proxy
        hist_close = universe_close[universe_close.index <= d].values
        market_regime = _market_regime_proxy(hist_close)

        # per-ticker slice (signal_date 이하)
        ohlcv_slice = {
            t: df[df.index <= d] for t, df in data.items()
            if len(df[df.index <= d]) >= 20
        }
        # per_ticker_regime map
        per_ticker = build_per_ticker_regime_map(ohlcv_slice, period=20)

        # ATR distribution
        atr_pct_dist = {}
        for t, sliced in ohlcv_slice.items():
            pct = compute_atr_pct(sliced, period=14)
            if not pd.isna(pct):
                atr_pct_dist[t] = pct

        cache[d] = {
            "market_regime": market_regime,
            "per_ticker": per_ticker,
            "atr_pct": atr_pct_dist,
        }
    logger.info(f"라벨 cache 완료: {len(cache)} 거래일")
    return cache


def label_trade(
    trade: dict,
    cache: dict[pd.Timestamp, dict],
) -> dict:
    """trade record 에 4축 라벨 부여."""
    d = trade["signal_date"]
    ticker = trade["ticker"]
    snap = cache.get(d)
    if snap is None:
        # 가장 가까운 캐시 키 찾기 (드물게 발생)
        keys = sorted(cache.keys())
        idx = np.searchsorted(keys, d, side="right") - 1
        if idx < 0:
            return {**trade, "market_regime": "NEUTRAL",
                    "per_ticker_regime": "MIXED", "atr_bucket": "MID",
                    "fng_label": None}
        snap = cache[keys[idx]]

    atr_pct = snap["atr_pct"].get(ticker)
    atr_b = bucket_atr(atr_pct, snap["atr_pct"])
    return {
        **trade,
        "market_regime": snap["market_regime"],
        "per_ticker_regime": snap["per_ticker"].get(ticker, "MIXED"),
        "atr_bucket": atr_b,
        "fng_label": None,  # 구형 출력 스키마 호환용. runtime 의사결정에는 미사용.
    }


# ---- WF 수집 ---------------------------------------------------------------


def collect_trades(
    data: dict[str, pd.DataFrame],
    windows: list,
    holdings: list[int],
    label_cache: dict[pd.Timestamp, dict],
) -> list[dict]:
    """5 전략 × holdings × WF OOS 윈도우 trade 수집."""
    all_trades: list[dict] = []
    for strat_name, factory in STRATEGIES:
        for hold in holdings:
            cfg = ScanBarConfig(
                holding_bars=hold, top_n=5, commission_pct=0.0030,
                lookback_buffer_days=60, emit_per_trade=True,
            )
            scorer = make_scan_bartracker_scorer(factory, cfg)
            for _ts, _te, test_start, test_end in windows:
                _ = scorer(data, {}, test_start, test_end)
                records = getattr(scorer, "per_trade_records", []) or []
                for r in records:
                    labeled = label_trade(r, label_cache)
                    labeled["strategy"] = strat_name
                    labeled["holding_bars_config"] = hold
                    all_trades.append(labeled)
            logger.info(f"  {strat_name} H={hold}: 누적 {len(all_trades)}")
    return all_trades


# ---- Marginal aggregation --------------------------------------------------


def primary_table(trades: list[dict], min_n: int = 30) -> dict:
    """strategy × market_regime → best holding by mean pnl (min_n trades)."""
    # group: (strategy, market_regime, holding_bars_config) → trades
    groups: dict[tuple, list[float]] = defaultdict(list)
    for t in trades:
        key = (t["strategy"], t["market_regime"], t["holding_bars_config"])
        groups[key].append(t["pnl_pct"])

    result: dict[str, dict[str, dict]] = defaultdict(dict)
    for (strat, regime, hold), pnls in groups.items():
        if len(pnls) < min_n:
            continue
        result[strat][regime] = result[strat].get(regime, {"candidates": []})
        result[strat][regime]["candidates"].append({
            "holding": hold,
            "n": len(pnls),
            "mean_pnl": float(np.mean(pnls)),
        })

    # best holding per (strategy, regime)
    final: dict = {}
    for strat, by_regime in result.items():
        final[strat] = {}
        for regime, info in by_regime.items():
            best = max(info["candidates"], key=lambda c: c["mean_pnl"])
            final[strat][regime] = {
                "best": best["holding"],
                "n_trades": best["n"],
                "mean_pnl": best["mean_pnl"],
                "candidates": info["candidates"],
            }
    return final


def modifier_table(
    trades: list[dict],
    label_key: str,
    baseline_holding: int,
    min_n: int = 30,
) -> dict[str, int]:
    """label_key 별 best holding - baseline_holding 의 delta (v1.0 flat marginal)."""
    # group: (label_value, holding) → pnls
    groups: dict[tuple, list[float]] = defaultdict(list)
    for t in trades:
        val = t.get(label_key)
        if val is None:
            continue
        groups[(val, t["holding_bars_config"])].append(t["pnl_pct"])

    # per label_value, find best holding
    by_label: dict[str, dict] = defaultdict(dict)
    for (val, hold), pnls in groups.items():
        if len(pnls) < min_n:
            continue
        by_label[val][hold] = float(np.mean(pnls))

    out: dict[str, int] = {}
    for val, hold_to_pnl in by_label.items():
        if not hold_to_pnl:
            continue
        best_hold = max(hold_to_pnl, key=hold_to_pnl.get)
        out[val] = int(best_hold - baseline_holding)
    return out


def modifier_table_by_regime(
    trades: list[dict],
    label_key: str,
    baseline_holding: int,
    min_n: int = 30,
) -> dict[str, dict[str, int]]:
    """market_regime 별로 modifier_table 산출. 반환: {regime: {label: delta}}.

    v1.0 의 strategy-aggregate marginal 은 cross-regime mixing 효과로 극단 delta
    유발 (BEAR 가 BULL marginal 끌어내림). regime 별로 segmenting 하여 조건부
    marginal 산출.
    """
    by_regime: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        regime = t.get("market_regime")
        if regime is None:
            continue
        by_regime[regime].append(t)

    out: dict[str, dict[str, int]] = {}
    for regime, sub_trades in by_regime.items():
        out[regime] = modifier_table(
            sub_trades, label_key, baseline_holding, min_n,
        )
    return out


# ---- 메인 -----------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="상황별 최적 holding 추천 집계")
    parser.add_argument("--cache-root", default=".cache_wf")
    parser.add_argument("--output", default="data/holding_recommendations.json")
    parser.add_argument("--start-date", default="2025-05-19")
    parser.add_argument("--end-date", default="2026-05-19")
    parser.add_argument("--holdings", default="1,3,5,7")
    parser.add_argument("--min-trades", type=int, default=30)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    )

    cache_root = Path(args.cache_root)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    holdings = [int(h) for h in args.holdings.split(",")]
    logger.info(f"holdings: {holdings}")

    data = load_history(cache_root)
    logger.info(f"로드 완료: {len(data)}개 ticker")

    wf_cfg = WalkForwardConfig(
        train_days=90, test_days=30, step_days=30,
        start_date=args.start_date, end_date=args.end_date,
        metric_name="sharpe", min_trades_for_metric=1,
    )
    windows = list(_generate_windows(wf_cfg))
    logger.info(f"WF 윈도우: {len(windows)}개")

    # OOS test 구간의 모든 거래일 union
    all_indices = sorted(set().union(*[df.index for df in data.values()]))
    test_dates: list[pd.Timestamp] = []
    for _ts, _te, test_start, test_end in windows:
        test_dates.extend([d for d in all_indices if test_start <= d <= test_end])
    test_dates = sorted(set(test_dates))
    logger.info(f"OOS 거래일: {len(test_dates)}일")

    # 라벨 cache 생성
    label_cache = build_label_cache(data, test_dates)

    # WF 수집
    logger.info("=== WF trade 수집 ===")
    trades = collect_trades(data, windows, holdings, label_cache)
    logger.info(f"총 trade 수: {len(trades)}")

    # Marginal aggregation
    primary = primary_table(trades, min_n=args.min_trades)
    # baseline_holding: primary 가 가장 자주 추천한 값 → modifier 기준
    baselines = [v["best"] for strat in primary.values() for v in strat.values()]
    baseline_holding = int(np.median(baselines)) if baselines else 5

    # v2.0: modifier_per_ticker / modifier_atr 는 regime-조건부 nested marginal.
    # modifier_fng 는 구형 파일 호환용으로만 유지한다. runtime 의사결정에는 사용하지 않는다.
    modifier_fng = modifier_table(trades, "fng_label", baseline_holding, args.min_trades)
    modifier_per_ticker = modifier_table_by_regime(
        trades, "per_ticker_regime", baseline_holding, args.min_trades,
    )
    modifier_atr = modifier_table_by_regime(
        trades, "atr_bucket", baseline_holding, args.min_trades,
    )

    # DOWNTREND_STRONG 은 "skip" 으로 override (regime 별 적용)
    for regime, sub in modifier_per_ticker.items():
        if "DOWNTREND_STRONG" in sub:
            sub["DOWNTREND_STRONG"] = "skip"  # type: ignore[assignment]

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "schema_version": "2.0",
        "windows": len(windows),
        "total_trades": len(trades),
        "min_trades_per_cell": args.min_trades,
        "baseline_holding": baseline_holding,
        "holdings_tested": holdings,
        "primary": primary,
        "modifier_fng": modifier_fng,
        "modifier_fng_status": "EMPTY_HISTORICAL_FNG",
        "modifier_per_ticker": modifier_per_ticker,
        "modifier_atr": modifier_atr,
    }
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    logger.info(f"JSON 저장: {output_path}")
    logger.info(f"Primary cells: {sum(len(v) for v in primary.values())} / 15")
    logger.info(f"Modifier fng cells: {len(modifier_fng)} (historical 부재 → NOOP)")
    per_cells = sum(len(v) for v in modifier_per_ticker.values())
    atr_cells = sum(len(v) for v in modifier_atr.values())
    logger.info(f"Modifier per_ticker cells: {per_cells} ({list(modifier_per_ticker.keys())})")
    logger.info(f"Modifier atr cells: {atr_cells} ({list(modifier_atr.keys())})")


if __name__ == "__main__":
    main()
