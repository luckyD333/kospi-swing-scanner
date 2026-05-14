"""scripts/backtest_ranking_oos.py

랭킹 적용 OOS 백테스트 그리드 서치.

목적: aggregator + regret_scorer 실제 호출로 랭킹 적용 후 상위 N개만 거래.
RegretWeights, 3-score 합성 가중치, top-N, S4+S2/S3 페널티 조합 그리드 서치.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, stdev

import pandas as pd

# 프로젝트 루트를 sys.path에 추가
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.decision.aggregator import aggregate_candidates
from core.decision.config import Priority, WeightConfig
from core.decision.regret_scorer import RegretWeights, compute_regret_scores
from core.strategy_base import ScanContext
from strategies.strategy_one_d_v2 import StrategyOneDv2
from strategies.strategy_two_cross_sectional_momentum import StrategyTwoCrossSectionalMomentum
from strategies.strategy_three_trend_following import StrategyThreeTrendFollowing
from strategies.strategy_four_pullback_ma import StrategyFourPullbackMa
from strategies.strategy_five_bull_flag import StrategyFiveBullFlag

import core.decision.regret_scorer as _rs_module

logging.basicConfig(level=logging.WARNING)
CACHE_ROOT = Path(".cache")
OOS_DAYS = 20
TOP_N_CANDIDATES = 20  # 전략당 스캔 top-N (30 → 20)
MIN_BARS = 30
SCAN_STEP = 3  # OOS 내 스캔 간격 (1=매일, 2=격일, 3=3일마다)

# 5개 base 전략 (1D 전용)
STRATEGIES = [
    StrategyOneDv2(timeframe="1D"),
    StrategyTwoCrossSectionalMomentum(timeframe="1D"),
    StrategyThreeTrendFollowing(timeframe="1D"),
    StrategyFourPullbackMa(timeframe="1D"),
    StrategyFiveBullFlag(timeframe="1D"),
]

# RegretWeights 그리드 (4가지)
REGRET_WEIGHTS = {
    "baseline": RegretWeights(
        bull_reward=0.40, max_drawdown=0.20, dist_to_stop=0.15, signal_freshness=0.25
    ),
    "fresh_off": RegretWeights(
        bull_reward=0.50, max_drawdown=0.20, dist_to_stop=0.25, signal_freshness=0.05
    ),
    "rr_focus": RegretWeights(
        bull_reward=0.55, max_drawdown=0.15, dist_to_stop=0.30, signal_freshness=0.00
    ),
    "risk_focus": RegretWeights(
        bull_reward=0.35, max_drawdown=0.35, dist_to_stop=0.20, signal_freshness=0.10
    ),
}

# Composite 가중치 그리드 (opp, pot, sig 합 = 1.0) (2가지)
COMPOSITE_WEIGHTS = {
    "default": (0.50, 0.30, 0.20),
    "opp_heavy": (0.70, 0.20, 0.10),
}

# Penalty factor
PENALTY_FACTORS = [1.0, 0.75]

# Top-N 그리드 (1가지)
TOP_N_VALUES = [5]


@dataclass
class GridResult:
    rw_name: str
    composite_name: str
    penalty_factor: float
    top_n: int
    trade_count: int
    win_count: int
    win_pct: float
    avg_pnl: float
    pf: float


def load_tickers() -> list[str]:
    manifest = json.loads((CACHE_ROOT / "manifest.json").read_text())
    return manifest.get("tickers", [])


def load_1d_data(tickers: list[str]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        path = CACHE_ROOT / "1D" / f"{ticker}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        df.columns = [c.lower() for c in df.columns]
        if {"open", "high", "low", "close", "volume"}.issubset(df.columns) and len(df) >= MIN_BARS:
            result[ticker] = df
    return result


def simulate_exit(
    df: pd.DataFrame,
    entry_idx: int,
    entry_price: float,
    stop_loss: float,
    target_1: float,
    max_hold: int = 5,
) -> dict:
    """T+1 ~ T+max_hold 봉에서 exit 시뮬레이션."""
    n = len(df)
    for i in range(1, max_hold + 1):
        idx = entry_idx + i
        if idx >= n:
            break
        row = df.iloc[idx]
        # gap down stop (open ≤ stop)
        if row["open"] <= stop_loss:
            pnl = (row["open"] - entry_price) / entry_price * 100
            return {"pnl_pct": pnl, "is_win": False, "exit_reason": "gap_stop", "exit_bar": i}
        # intra-bar stop
        if row["low"] <= stop_loss:
            pnl = (stop_loss - entry_price) / entry_price * 100
            return {"pnl_pct": pnl, "is_win": False, "exit_reason": "stop_loss", "exit_bar": i}
        # target hit
        if row["high"] >= target_1:
            pnl = (target_1 - entry_price) / entry_price * 100
            return {"pnl_pct": pnl, "is_win": True, "exit_reason": "target_1", "exit_bar": i}
    # time stop
    idx = min(entry_idx + max_hold, n - 1)
    close = df.iloc[idx]["close"]
    pnl = (close - entry_price) / entry_price * 100
    return {"pnl_pct": pnl, "is_win": pnl > 0, "exit_reason": "time_stop", "exit_bar": max_hold}


def compute_pf(pnls: list[float]) -> float:
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    return wins / losses if losses > 0 else 99.0


def run_ranked_backtest(
    all_strategies: list,
    all_data: dict[str, pd.DataFrame],
    dates: list,
    weight_cfg: WeightConfig,
    rw: RegretWeights,
    w_opp: float,
    w_pot: float,
    w_sig: float,
    penalty_factor: float,
    top_n: int,
) -> list[dict]:
    """랭킹 적용 백테스트 실행."""
    # Monkey-patch module constants
    _rs_module._W_OPP = w_opp
    _rs_module._W_POT = w_pot
    _rs_module._W_SIG_BASE = w_sig

    trades = []

    for scan_dt in dates:
        # Slice data up to scan_dt
        sliced: dict[str, pd.DataFrame] = {}
        for ticker, df in all_data.items():
            sub = df[df.index <= scan_dt]
            if len(sub) >= MIN_BARS:
                sliced[ticker] = sub

        if not sliced:
            continue

        # Create ScanContext
        ctx = ScanContext(
            target_date=scan_dt.strftime("%Y%m%d"),
            universe=tuple(sliced.keys()),
            ohlcv=sliced,
            ohlcv_by_tf={"1D": sliced},
            names={t: t for t in sliced},
            market_caps={t: 0.0 for t in sliced},
            market="KOSPI",
        )

        # Collect candidates from all strategies
        cands_by_strategy: dict[str, list] = {}
        for strat in all_strategies:
            try:
                cands = strat.scan(ctx, top_n=TOP_N_CANDIDATES)
                if cands:
                    cands_by_strategy[strat.name] = cands
            except Exception:
                continue

        if not cands_by_strategy:
            continue

        # Identify S4 and S2/S3 strategies
        s4_ids = {"strategy_four_pullback_ma"}
        s2s3_ids = {
            sid for sid in cands_by_strategy
            if any(x in sid for x in ["strategy_two", "strategy_three"])
        }

        # Get S4 tickers that also appear in S2/S3
        s4_tickers = {
            c.ticker for sid, cs in cands_by_strategy.items()
            if sid in s4_ids for c in cs
        }
        s2s3_tickers = {
            c.ticker for sid in s2s3_ids
            for c in cands_by_strategy.get(sid, [])
        }
        penalized_tickers = s4_tickers & s2s3_tickers

        # Deduplicate by ticker: keep best score candidate
        best: dict[str, object] = {}
        for sid, cs in cands_by_strategy.items():
            for c in cs:
                if c.ticker not in best or c.score > best[c.ticker].score:
                    best[c.ticker] = c

        # Run aggregator + regret_scorer
        ranked = aggregate_candidates(list(best.values()), weight_cfg, pool="STOCK")
        if not ranked:
            continue

        ranked = compute_regret_scores(ranked, weights=rw)

        # Apply penalty
        if penalty_factor < 1.0:
            for rc in ranked:
                if rc.candidate.ticker in penalized_tickers:
                    old = rc.normalized_metrics.get("composite_score", 0.0)
                    rc.normalized_metrics["composite_score"] = round(old * penalty_factor, 4)
            ranked.sort(
                key=lambda r: (
                    -r.normalized_metrics.get("composite_score", 0.0),
                    -r.final_score,
                    r.candidate.ticker,
                )
            )

        # Trade top_n candidates
        for rc in ranked[:top_n]:
            ticker = rc.candidate.ticker
            df_full = all_data.get(ticker)
            if df_full is None:
                continue

            try:
                entry_idx = df_full.index.get_loc(scan_dt)
            except KeyError:
                continue

            if entry_idx + 1 >= len(df_full):
                continue

            cand = rc.candidate
            result = simulate_exit(
                df_full,
                entry_idx,
                float(cand.entry_price),
                float(cand.stop_loss),
                float(cand.target_1),
            )
            trades.append({"ticker": ticker, **result})

    return trades


def main() -> None:
    print("=" * 90)
    print("  랭킹 적용 OOS 백테스트 그리드 서치")
    print("=" * 90)

    tickers = load_tickers()
    print(f"\n종목 로드 중... ({len(tickers)}개)")
    all_data = load_1d_data(tickers)
    print(f"1D 데이터 로드: {len(all_data)}개")

    # OOS 날짜 설정
    sample_df = next(iter(all_data.values()))
    all_dates = sample_df.index.tolist()
    train_cutoff = len(all_dates) - OOS_DAYS
    oos_dates = all_dates[train_cutoff : len(all_dates) - 5]  # 마지막 5일은 forward return
    scan_dates = oos_dates[::SCAN_STEP]  # 격일 스캔

    print(f"훈련 기간: {all_dates[0].date()} ~ {all_dates[train_cutoff - 1].date()}")
    print(f"OOS 기간:  {oos_dates[0].date()} ~ {oos_dates[-1].date()} ({len(oos_dates)}일)")
    print(f"스캔 일정: {len(scan_dates)}개 날짜 (step={SCAN_STEP})")

    # Base WeightConfig (score 100% 단독)
    base_cfg = WeightConfig(
        priorities=[Priority(key="score", weight=100.0, direction="higher_better", label="신호강도")]
    )

    # Grid search
    results: list[GridResult] = []
    total_combinations = (
        len(REGRET_WEIGHTS) * len(COMPOSITE_WEIGHTS) * len(PENALTY_FACTORS) * len(TOP_N_VALUES)
    )

    print(f"\n총 {total_combinations} 조합 백테스트 중...\n")

    combo_idx = 0
    for rw_name, rw in REGRET_WEIGHTS.items():
        for comp_name, (w_opp, w_pot, w_sig) in COMPOSITE_WEIGHTS.items():
            for penalty_factor in PENALTY_FACTORS:
                for top_n in TOP_N_VALUES:
                    combo_idx += 1
                    trades = run_ranked_backtest(
                        STRATEGIES,
                        all_data,
                        scan_dates,
                        base_cfg,
                        rw,
                        w_opp,
                        w_pot,
                        w_sig,
                        penalty_factor,
                        top_n,
                    )

                    if not trades:
                        continue

                    win_count = sum(1 for t in trades if t["is_win"])
                    pnls = [t["pnl_pct"] for t in trades]
                    pf = compute_pf(pnls)
                    avg_pnl = mean(pnls) if pnls else 0.0

                    result = GridResult(
                        rw_name=rw_name,
                        composite_name=comp_name,
                        penalty_factor=penalty_factor,
                        top_n=top_n,
                        trade_count=len(trades),
                        win_count=win_count,
                        win_pct=100.0 * win_count / len(trades) if trades else 0.0,
                        avg_pnl=avg_pnl,
                        pf=pf,
                    )
                    results.append(result)

    # Sort by PF (descending)
    results.sort(key=lambda r: (-r.pf, -r.win_pct, -r.avg_pnl))

    # Print results
    print("\n" + "=" * 90)
    print("  상위 20개 조합 (PF 기준)")
    print("=" * 90)
    print(
        f"{'rw_name':<15} {'composite':<12} {'penalty':<8} {'topN':<5} | "
        f"{'건수':<6} {'승률':<8} {'avgPnL':<9} {'PF':<8}"
    )
    print("-" * 90)

    for i, r in enumerate(results[:20]):
        print(
            f"{r.rw_name:<15} {r.composite_name:<12} {r.penalty_factor:<8.2f} {r.top_n:<5} | "
            f"{r.trade_count:<6} {r.win_pct:>6.1f}% {r.avg_pnl:>8.2f}% {r.pf:>7.2f}"
        )

    # 현재 기본값 (baseline, default, no_penalty, top5)
    baseline = next(
        (
            r for r in results
            if r.rw_name == "baseline"
            and r.composite_name == "default"
            and r.penalty_factor == 1.0
            and r.top_n == 5
        ),
        None,
    )

    print("\n" + "─" * 90)
    print("  현재 기본값 (baseline, default, penalty=1.0, topN=5)")
    print("─" * 90)
    if baseline:
        print(
            f"건수: {baseline.trade_count} | 승률: {baseline.win_pct:.1f}% | "
            f"평균PnL: {baseline.avg_pnl:.2f}% | PF: {baseline.pf:.2f}"
        )
        baseline_idx = results.index(baseline)
        print(f"순위: #{baseline_idx + 1} / {len(results)}")
    else:
        print("(데이터 없음)")

    # Key findings
    print("\n" + "=" * 90)
    print("  주요 발견")
    print("=" * 90)

    if results:
        top_result = results[0]
        print(f"\n최고 성과 조합:")
        print(f"  RegretWeights: {top_result.rw_name}")
        print(f"  Composite:     {top_result.composite_name}")
        print(f"  Penalty:       {top_result.penalty_factor:.2f}")
        print(f"  Top-N:         {top_result.top_n}")
        print(f"  결과:          {top_result.trade_count}건, {top_result.win_pct:.1f}% 승률, PF={top_result.pf:.2f}")

        # Penalty 효과 분석
        no_penalty_results = [r for r in results if r.penalty_factor == 1.0]
        with_penalty_results = [r for r in results if r.penalty_factor == 0.75]

        if no_penalty_results and with_penalty_results:
            no_penalty_pf = mean([r.pf for r in no_penalty_results])
            with_penalty_pf = mean([r.pf for r in with_penalty_results])
            penalty_impact = (with_penalty_pf - no_penalty_pf) / no_penalty_pf * 100 if no_penalty_pf > 0 else 0
            print(f"\nPenalty 효과 (0.75 vs 1.0):")
            print(f"  No penalty (avg PF):    {no_penalty_pf:.2f}")
            print(f"  With penalty (avg PF):  {with_penalty_pf:.2f}")
            print(f"  변화:                   {penalty_impact:+.1f}%")

        # Top-N 효과
        top5_results = [r for r in results if r.top_n == 5]
        top10_results = [r for r in results if r.top_n == 10]

        if top5_results and top10_results:
            top5_pf = mean([r.pf for r in top5_results])
            top10_pf = mean([r.pf for r in top10_results])
            topn_impact = (top10_pf - top5_pf) / top5_pf * 100 if top5_pf > 0 else 0
            print(f"\nTop-N 효과 (5 vs 10):")
            print(f"  Top-5 (avg PF):  {top5_pf:.2f}")
            print(f"  Top-10 (avg PF): {top10_pf:.2f}")
            print(f"  변화:            {topn_impact:+.1f}%")

    print("\n" + "=" * 90)
    print("  완료")
    print("=" * 90)


if __name__ == "__main__":
    main()
