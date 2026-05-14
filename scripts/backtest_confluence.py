"""scripts/backtest_confluence.py

OOS hold-out confluence 백테스트.

목적: 여러 전략에 동시 선택된 종목이 단독 전략 선택보다 승률/수익률이 높은지 검증.

구조:
  - 훈련 window: 1D 데이터 전체 중 처음 N-20 일 (파라미터 튜닝 already in-sample)
  - OOS hold-out: 마지막 20 거래일
  - 각 OOS 날짜에서 5개 base 전략(1D) 스캔 → ticker별 등장 전략 수 집계
  - 진입가·손절가·목표가 기록 후 T+1~T+5 forward bars에서 exit 시뮬레이션
  - 결과: confluence bucket (1-전략 / 2-전략 / 3+-전략) 별 승률·평균PnL·PF 비교

주의:
  - TF 변형(1h/30m)은 포함하지 않음 — base strategy(1D)만 카운트
  - 동일 종목이 같은 전략에서 중복 신호 시 1회만 카운트
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import mean, stdev

import pandas as pd

# 프로젝트 루트를 sys.path에 추가
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.strategy_base import ScanContext
from strategies.strategy_one_d_v2 import StrategyOneDv2
from strategies.strategy_two_cross_sectional_momentum import StrategyTwoCrossSectionalMomentum
from strategies.strategy_three_trend_following import StrategyThreeTrendFollowing
from strategies.strategy_four_pullback_ma import StrategyFourPullbackMa
from strategies.strategy_five_bull_flag import StrategyFiveBullFlag

logging.basicConfig(level=logging.WARNING)
CACHE_ROOT = Path(".cache")
OOS_DAYS = 20      # hold-out 마지막 N 거래일
SCAN_STEP = 2      # OOS window 내 스캔 간격 (1=매일, 2=격일)
TOP_N = 30         # 전략당 상위 N 후보
MIN_BARS = 30      # 최소 데이터 봉 수


# 5개 base 전략 (1D 전용 — TF 변형 제외)
STRATEGIES = [
    StrategyOneDv2(timeframe="1D"),
    StrategyTwoCrossSectionalMomentum(timeframe="1D"),
    StrategyThreeTrendFollowing(timeframe="1D"),
    StrategyFourPullbackMa(timeframe="1D"),
    StrategyFiveBullFlag(timeframe="1D"),
]


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
    """T+1 ~ T+max_hold 봉에서 exit 시뮬레이션.

    반환: {pnl_pct, is_win, exit_reason, exit_bar}
    """
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


def run() -> None:
    print("=" * 70)
    print("  Confluence OOS Backtest — 마지막 20 거래일 hold-out")
    print(f"  전략: {len(STRATEGIES)}개 (1D base 전략만, TF 변형 제외)")
    print("=" * 70)

    tickers = load_tickers()
    print(f"\n종목 로드 중... ({len(tickers)}개)")
    all_data = load_1d_data(tickers)
    print(f"1D 데이터 로드: {len(all_data)}개")

    # OOS 날짜: 전체 데이터 중 마지막 OOS_DAYS 거래일 (모든 종목 공통 날짜축)
    sample_df = next(iter(all_data.values()))
    all_dates = sample_df.index.tolist()
    train_cutoff = len(all_dates) - OOS_DAYS
    oos_dates = all_dates[train_cutoff: len(all_dates) - 5]  # 마지막 5일은 forward return용

    scan_dates = oos_dates[::SCAN_STEP]
    print(f"훈련 기간: {all_dates[0].date()} ~ {all_dates[train_cutoff-1].date()} ({train_cutoff}일)")
    print(f"OOS 기간:  {oos_dates[0].date()} ~ {oos_dates[-1].date()} ({len(oos_dates)}일)")
    print(f"스캔 날짜: {len(scan_dates)}개 (step={SCAN_STEP})\n")

    # 날짜별 ticker 메타 (시가총액 등 — manifest에서)
    manifest = json.loads((CACHE_ROOT / "manifest.json").read_text())
    ticker_meta = manifest.get("tickers_meta", {})

    # --- 메인 루프 ---
    # trade_records: list of {ticker, strategy_names, confluence, pnl_pct, is_win, scan_date}
    trade_records: list[dict] = []

    for scan_dt in scan_dates:
        scan_date_str = scan_dt.strftime("%Y%m%d")
        print(f"  스캔: {scan_dt.date()}", end="  ")

        # 해당 날짜까지의 데이터 슬라이스
        sliced: dict[str, pd.DataFrame] = {}
        for ticker, df in all_data.items():
            sub = df[df.index <= scan_dt]
            if len(sub) >= MIN_BARS:
                sliced[ticker] = sub

        if not sliced:
            print("데이터 없음")
            continue

        meta_caps = {t: (ticker_meta.get(t, {}).get("market_cap_bil", 0.0) or 0.0) * 1e8
                     for t in sliced}
        meta_names = {t: t for t in sliced}

        ctx = ScanContext(
            target_date=scan_date_str,
            universe=tuple(sliced.keys()),
            ohlcv=sliced,
            ohlcv_by_tf={"1D": sliced},
            names=meta_names,
            market_caps=meta_caps,
            market="KOSPI",
        )

        # 전략별 후보 수집
        ticker_to_strategies: dict[str, set[str]] = {}
        ticker_to_candidate: dict[str, dict] = {}

        for strategy in STRATEGIES:
            try:
                candidates = strategy.scan(ctx, top_n=TOP_N)
            except Exception:
                continue
            base_name = strategy.name  # e.g. "strategy_one_d_v2"
            for cand in candidates:
                if cand.ticker not in ticker_to_strategies:
                    ticker_to_strategies[cand.ticker] = set()
                    ticker_to_candidate[cand.ticker] = {
                        "entry_price": float(cand.entry_price),
                        "stop_loss": float(cand.stop_loss),
                        "target_1": float(cand.target_1),
                    }
                ticker_to_strategies[cand.ticker].add(base_name)

        total_signals = sum(1 for _ in ticker_to_strategies)
        print(f"{total_signals}개 신호", end="  ")

        # exit 시뮬레이션
        exits = 0
        for ticker, strategy_set in ticker_to_strategies.items():
            df_full = all_data.get(ticker)
            if df_full is None:
                continue
            # scan_dt의 인덱스 찾기
            try:
                entry_idx = df_full.index.get_loc(scan_dt)
            except KeyError:
                continue
            if entry_idx + 1 >= len(df_full):
                continue

            cand_info = ticker_to_candidate[ticker]
            result = simulate_exit(
                df_full,
                entry_idx,
                cand_info["entry_price"],
                cand_info["stop_loss"],
                cand_info["target_1"],
            )

            confluence = len(strategy_set)
            trade_records.append({
                "ticker": ticker,
                "scan_date": scan_dt.date(),
                "strategy_names": sorted(strategy_set),
                "confluence": confluence,
                **result,
            })
            exits += 1

        print(f"→ {exits}건 exit 기록")

    # --- 결과 집계 ---
    if not trade_records:
        print("\n거래 기록 없음. OOS 기간에 신호가 발생하지 않았어요.")
        return

    print(f"\n{'=' * 70}")
    print(f"  총 거래: {len(trade_records)}건")
    print(f"{'=' * 70}")

    # Confluence bucket별 분석
    buckets: dict[str, list[dict]] = {"1-전략": [], "2-전략": [], "3+-전략": []}
    for r in trade_records:
        if r["confluence"] == 1:
            buckets["1-전략"].append(r)
        elif r["confluence"] == 2:
            buckets["2-전략"].append(r)
        else:
            buckets["3+-전략"].append(r)

    print(f"\n{'Confluence':<12} {'건수':>5} {'승률':>7} {'avgPnL':>8} {'PF':>6} {'stdPnL':>8}")
    print("-" * 50)
    for bucket_name, records in buckets.items():
        if not records:
            print(f"  {bucket_name:<10} {'0':>5}  {'N/A':>7}  {'N/A':>8}  {'N/A':>6}")
            continue
        pnls = [r["pnl_pct"] for r in records]
        win_rate = sum(1 for r in records if r["is_win"]) / len(records) * 100
        avg_pnl = mean(pnls)
        pf = compute_pf(pnls)
        std_pnl = stdev(pnls) if len(pnls) > 1 else 0.0
        print(f"  {bucket_name:<10} {len(records):>5}  {win_rate:>6.1f}%  {avg_pnl:>+7.2f}%  {pf:>5.2f}  ±{std_pnl:.2f}%")

    # 전략 조합별 상세
    print(f"\n{'─' * 70}")
    print("  전략 조합별 상세 (confluence ≥ 2, 건수 ≥ 2)")
    combo_stats: dict[str, list[float]] = {}
    for r in trade_records:
        if r["confluence"] < 2:
            continue
        combo_key = "+".join(s.replace("strategy_", "s") for s in r["strategy_names"])
        if combo_key not in combo_stats:
            combo_stats[combo_key] = []
        combo_stats[combo_key].append(r["pnl_pct"])

    sorted_combos = sorted(combo_stats.items(), key=lambda x: -mean(x[1]))
    for combo, pnls in sorted_combos:
        if len(pnls) < 2:
            continue
        win_rate = sum(1 for p in pnls if p > 0) / len(pnls) * 100
        print(f"  {combo:<40} {len(pnls):>3}건  승률 {win_rate:.0f}%  avg {mean(pnls):+.2f}%  PF {compute_pf(pnls):.2f}")

    # Exit reason 분포
    print(f"\n{'─' * 70}")
    print("  Exit reason 분포")
    reason_counts: dict[str, int] = {}
    for r in trade_records:
        reason_counts[r["exit_reason"]] = reason_counts.get(r["exit_reason"], 0) + 1
    for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
        pct = cnt / len(trade_records) * 100
        print(f"  {reason:<15} {cnt:>4}건 ({pct:.1f}%)")

    # 전체 통계
    all_pnls = [r["pnl_pct"] for r in trade_records]
    overall_win = sum(1 for r in trade_records if r["is_win"]) / len(trade_records) * 100
    print(f"\n  전체: 건수 {len(all_pnls)}, 승률 {overall_win:.1f}%, avgPnL {mean(all_pnls):+.2f}%, PF {compute_pf(all_pnls):.2f}")
    print(f"\n{'=' * 70}")
    print("  완료.")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    run()
