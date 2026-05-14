"""
scripts/tune_strategy_three.py — Strategy Three 파라미터 그리드 서치

Donchian 채널 추세 추종 전략의 최적 파라미터를 탐색한다.
Walk-forward 백테스트로 신호 품질(PF, 평균PnL)을 최적화.

사용:
    python scripts/tune_strategy_three.py
    python scripts/tune_strategy_three.py --step 3 --top-n 20
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.strategy_base import ScanContext
from strategies.strategy_three_trend_following import StrategyThreeConfig, StrategyThreeTrendFollowing

CACHE_ROOT = Path(".cache")


# ─── 데이터 로딩 ──────────────────────────────────────────────────────────────

def load_data() -> tuple[dict[str, pd.DataFrame], dict]:
    manifest = json.loads((CACHE_ROOT / "manifest.json").read_text())
    tickers: list[str] = manifest.get("tickers", [])
    meta = manifest.get("tickers_meta", {})

    all_data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        path = CACHE_ROOT / "1D" / f"{ticker}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df = df[["open", "high", "low", "close", "volume"]]
        if len(df) >= 40:
            all_data[ticker] = df

    return all_data, meta


def get_scan_dates(all_data: dict[str, pd.DataFrame], step: int) -> list[pd.Timestamp]:
    all_dates: set[pd.Timestamp] = set()
    for df in all_data.values():
        all_dates.update(df.index.tolist())
    dates = sorted(all_dates)[:-5]   # 마지막 5일: forward return용 제외
    return dates[35::step]            # 35봉 lookback 보장


# ─── Exit 시뮬레이션 ──────────────────────────────────────────────────────────

def simulate_exit(
    full_df: pd.DataFrame,
    signal_date: pd.Timestamp,
    entry: float,
    stop: float,
    target: float,
    max_bars: int = 5,
) -> tuple[float, str]:
    future = full_df[full_df.index > signal_date].head(max_bars)
    if future.empty:
        return entry, "no_data"
    for _, bar in future.iterrows():
        if float(bar["open"]) <= stop:
            return stop, "gap_stop"
        if float(bar["low"]) <= stop:
            return stop, "stop_loss"
        if float(bar["high"]) >= target:
            return target, "target_1"
    return float(future.iloc[-1]["close"]), "time_stop"


# ─── 단일 파라미터 조합 백테스트 ──────────────────────────────────────────────

@dataclass
class RunResult:
    params: dict
    signals: int
    win_rate: float
    avg_pnl: float
    profit_factor: float
    avg_win: float
    avg_loss: float


# ─── 그리드 서치 ──────────────────────────────────────────────────────────────

GRID = {
    "lookback":               [15, 20, 25, 30],
    "atr_filter_multiplier":  [0.3, 0.5, 0.7, 1.0],
    "atr_stop_mult":          [1.0, 1.5, 2.0, 2.5],
    "atr_target_mult":        [2.5, 3.0, 3.5],
}

# 기본값 (변경 안 할 파라미터)
BASE = dict(
    atr_period=14,
    stop_loss_pct=0.025,
)


def build_config(
    lookback: int,
    atr_filter_mult: float,
    atr_stop_mult: float,
    atr_target_mult: float,
) -> StrategyThreeConfig:
    return StrategyThreeConfig(
        lookback=lookback,
        atr_period=BASE["atr_period"],
        atr_filter_multiplier=atr_filter_mult,
        stop_loss_pct=BASE["stop_loss_pct"],
        atr_stop_mult=atr_stop_mult,
        atr_target_mult=atr_target_mult,
    )


def run_grid(
    all_data: dict[str, pd.DataFrame],
    meta: dict,
    scan_dates: list[pd.Timestamp],
    top_n: int,
) -> list[RunResult]:
    keys = list(GRID.keys())
    values = list(GRID.values())
    combos = list(product(*values))
    total = len(combos)
    print(f"  파라미터 조합: {total}개")

    results: list[RunResult] = []

    for i, combo in enumerate(combos):
        params = dict(zip(keys, combo))
        cfg = build_config(
            lookback=int(params["lookback"]),
            atr_filter_mult=params["atr_filter_multiplier"],
            atr_stop_mult=params["atr_stop_mult"],
            atr_target_mult=params["atr_target_mult"],
        )
        strategy = StrategyThreeTrendFollowing(config=cfg, timeframe="1D")

        pnls: list[float] = []
        for scan_date in scan_dates:
            sliced = {
                t: df[df.index <= scan_date]
                for t, df in all_data.items()
                if len(df[df.index <= scan_date]) >= 35
            }
            if not sliced:
                continue
            tickers = list(sliced.keys())
            ctx = ScanContext(
                target_date=scan_date.strftime("%Y%m%d"),
                universe=tuple(tickers),
                ohlcv=sliced,
                names={t: t for t in tickers},
                market_caps={t: meta.get(t, {}).get("market_cap_bil", 0.0) or 0.0 for t in tickers},
                market="KOSPI",
            )
            try:
                candidates = strategy.scan(ctx, top_n=top_n)
            except Exception:
                continue

            for cand in candidates:
                full_df = all_data.get(cand.ticker)
                if full_df is None:
                    continue
                exit_price, _ = simulate_exit(
                    full_df, scan_date, cand.entry_price, cand.stop_loss, cand.target_1
                )
                pnl = (exit_price - cand.entry_price) / cand.entry_price * 100
                pnls.append(pnl)

        if not pnls:
            results.append(RunResult(params=params, signals=0, win_rate=0, avg_pnl=0, profit_factor=0, avg_win=0, avg_loss=0))
            continue

        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls) * 100
        avg_pnl = sum(pnls) / len(pnls)
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        total_win_amt = sum(wins)
        total_loss_amt = abs(sum(losses)) if losses else 0.0
        pf = total_win_amt / total_loss_amt if total_loss_amt > 0 else 99.0

        results.append(RunResult(
            params=params,
            signals=len(pnls),
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            profit_factor=pf,
            avg_win=avg_win,
            avg_loss=avg_loss,
        ))

        if (i + 1) % 40 == 0:
            print(f"    진행: {i+1}/{total}")

    return results


# ─── 결과 출력 ────────────────────────────────────────────────────────────────

def print_results(results: list[RunResult], top_n: int) -> None:
    # 신호 ≥ 10건인 결과만 (노이즈 제거)
    valid = [r for r in results if r.signals >= 10]

    if not valid:
        print("\n  [신호 ≥10건인 조합 없음] -- step을 줄이거나 top_n 늘리기 권장")
        # 신호 1건 이상 출력
        valid = [r for r in results if r.signals >= 1]
        if not valid:
            print("  신호 1건 이상인 조합도 없음.")
            return

    # PF 기준 정렬 (avg_pnl > 0 우선)
    valid.sort(key=lambda r: (r.avg_pnl > 0, r.profit_factor, r.win_rate), reverse=True)

    print(f"\n{'='*100}")
    print(f"  상위 {min(top_n, len(valid))}개 조합 (신호≥10건, PF 기준)")
    print(f"{'='*100}")
    print(f"  {'lookback':>8} {'atr_filt':>9} {'atr_stop':>9} {'atr_targ':>9} | {'신호':>5} {'승률':>7} {'avgPnL':>8} {'PF':>6} {'avgWin':>8} {'avgLoss':>8}")
    print(f"  {'-'*98}")

    for r in valid[:top_n]:
        p = r.params
        print(
            f"  {int(p['lookback']):>8}"
            f"  {p['atr_filter_multiplier']:>9.1f}"
            f"  {p['atr_stop_mult']:>9.1f}"
            f"  {p['atr_target_mult']:>9.1f}"
            f" | {r.signals:>5}"
            f"  {r.win_rate:>6.1f}%"
            f"  {r.avg_pnl:>+7.2f}%"
            f"  {r.profit_factor:>5.2f}"
            f"  {r.avg_win:>+7.2f}%"
            f"  {r.avg_loss:>+7.2f}%"
        )

    # 현재 기본값 결과 표시
    print(f"\n  ── 현재 기본값 (lookback=20, atr_filt=0.5, atr_stop=1.5, atr_targ=3.0) ──")
    baseline = next(
        (r for r in results
         if int(r.params["lookback"]) == 20
         and abs(r.params["atr_filter_multiplier"] - 0.5) < 0.001
         and abs(r.params["atr_stop_mult"] - 1.5) < 0.001
         and abs(r.params["atr_target_mult"] - 3.0) < 0.001),
        None,
    )
    if baseline:
        p = baseline.params
        print(
            f"  {int(p['lookback']):>8}"
            f"  {p['atr_filter_multiplier']:>9.1f}"
            f"  {p['atr_stop_mult']:>9.1f}"
            f"  {p['atr_target_mult']:>9.1f}"
            f" | {baseline.signals:>5}"
            f"  {baseline.win_rate:>6.1f}%"
            f"  {baseline.avg_pnl:>+7.2f}%"
            f"  {baseline.profit_factor:>5.2f}"
            f"  {baseline.avg_win:>+7.2f}%"
            f"  {baseline.avg_loss:>+7.2f}%"
        )

    # 추천 조합
    best = valid[0] if valid else None
    if best:
        p = best.params
        print(f"\n  ★ 추천 조합:")
        print(f"    lookback            = {int(p['lookback'])}")
        print(f"    atr_filter_multiplier = {p['atr_filter_multiplier']:.1f}")
        print(f"    atr_stop_mult        = {p['atr_stop_mult']:.1f}")
        print(f"    atr_target_mult      = {p['atr_target_mult']:.1f}")
        print(f"    → 신호 {best.signals}건, 승률 {best.win_rate:.1f}%, 평균PnL {best.avg_pnl:+.2f}%, PF {best.profit_factor:.2f}")


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy Three 파라미터 그리드 서치")
    parser.add_argument("--step", type=int, default=3, help="스캔 날짜 간격 (기본: 3일)")
    parser.add_argument("--top-n", type=int, default=20, help="전략당 top-N 신호 (기본: 20)")
    parser.add_argument("--top", type=int, default=20, help="출력 상위 N 조합 (기본: 20)")
    args = parser.parse_args()

    print("Strategy Three — 파라미터 그리드 서치")
    print(f"cache: {CACHE_ROOT.resolve()}")

    all_data, meta = load_data()
    print(f"종목: {len(all_data)}개")

    scan_dates = get_scan_dates(all_data, step=args.step)
    print(f"스캔 날짜: {len(scan_dates)}개 (step={args.step})")
    if not scan_dates:
        sys.exit("[ERROR] 스캔 날짜 없음. 데이터 재수집 필요.")

    print("\n[그리드 서치 실행 중...]")
    results = run_grid(all_data, meta, scan_dates, top_n=args.top_n)

    print_results(results, top_n=args.top)
    print(f"\n{'='*100}")
    print("  완료.")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    main()
