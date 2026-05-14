"""
scripts/tune_strategy_four.py — Strategy Four 파라미터 그리드 서치

각 파라미터 조합으로 Walk-forward 백테스트를 실행해 최적 임계값을 탐색한다.

사용:
    python scripts/tune_strategy_four.py
    python scripts/tune_strategy_four.py --step 3 --top-n 20
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
from strategies.strategy_four_pullback_ma import StrategyFourConfig, StrategyFourPullbackMa

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


def run_one(
    all_data: dict[str, pd.DataFrame],
    meta: dict,
    scan_dates: list[pd.Timestamp],
    cfg: StrategyFourConfig,
) -> tuple[int, float, float, float, float, float]:
    """신호 수, 승률, 평균PnL, PF, 평균승PnL, 평균패PnL 반환."""
    tickers = list(all_data.keys())
    names = {t: t for t in tickers}
    market_caps = {t: meta.get(t, {}).get("market_cap_bil", 0.0) or 0.0 for t in tickers}
    strategy = StrategyFourPullbackMa(config=cfg)

    pnls: list[float] = []

    for scan_date in scan_dates:
        sliced = {
            t: df[df.index <= scan_date]
            for t, df in all_data.items()
            if len(df[df.index <= scan_date]) >= 35
        }
        if not sliced:
            continue

        ctx = ScanContext(
            target_date=scan_date.strftime("%Y%m%d"),
            universe=tuple(sliced.keys()),
            ohlcv=sliced,
            names=names,
            market_caps=market_caps,
            market="KOSPI",
        )
        try:
            candidates = strategy.scan(ctx, top_n=20)
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
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) * 100
    avg_pnl = sum(pnls) / len(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    total_win = sum(wins)
    total_loss = abs(sum(losses)) if losses else 0.0
    pf = (total_win / total_loss) if total_loss > 0 else float("inf")
    return len(pnls), win_rate, avg_pnl, pf, avg_win, avg_loss


# ─── 그리드 서치 ──────────────────────────────────────────────────────────────

GRID = {
    "ma_trend":          [15, 20, 30],
    "ma_pullback":       [3, 5, 8],
    "pullback_lookback": [3, 5, 7],
    "min_vol_ratio":     [0.6, 0.8, 1.0, 1.2],
}

# 기본값 (변경 안 할 파라미터)
BASE = dict(
    stop_loss_pct=0.025,
    target_1_pct=0.03,
    target_2_pct=0.05,
    atr_target_mult=3.0,
    min_bars=25,
    min_daily_volume=100_000,
)


def build_config(
    ma_trend: int,
    ma_pullback: int,
    pullback_lookback: int,
    min_vol_ratio: float,
) -> StrategyFourConfig:
    return StrategyFourConfig(
        ma_trend=ma_trend,
        ma_pullback=ma_pullback,
        pullback_lookback=pullback_lookback,
        min_vol_ratio=min_vol_ratio,
        stop_loss_pct=BASE["stop_loss_pct"],
        target_1_pct=BASE["target_1_pct"],
        target_2_pct=BASE["target_2_pct"],
        atr_target_mult=BASE["atr_target_mult"],
        min_bars=BASE["min_bars"],
        min_daily_volume=BASE["min_daily_volume"],
    )


def run_grid(
    all_data: dict[str, pd.DataFrame],
    meta: dict,
    scan_dates: list[pd.Timestamp],
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
            ma_trend=params["ma_trend"],
            ma_pullback=params["ma_pullback"],
            pullback_lookback=params["pullback_lookback"],
            min_vol_ratio=params["min_vol_ratio"],
        )

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
            strategy = StrategyFourPullbackMa(config=cfg)
            try:
                candidates = strategy.scan(ctx, top_n=20)
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

        if (i + 1) % 10 == 0:
            print(f"    진행: {i+1}/{total}")

    return results


# ─── 결과 출력 ────────────────────────────────────────────────────────────────

def print_results(results: list[RunResult], top_n: int) -> None:
    # 신호 ≥ 5건인 결과만 (노이즈 제거)
    valid = [r for r in results if r.signals >= 5]

    if not valid:
        print("\n  [신호 ≥5건인 조합 없음] -- step을 줄이거나 top_n 늘리기 권장")
        # 신호 1건 이상 출력
        valid = [r for r in results if r.signals >= 1]
        if not valid:
            print("  신호 1건 이상인 조합도 없음.")
            return

    # PF 기준 정렬 (avg_pnl > 0 우선)
    valid.sort(key=lambda r: (r.avg_pnl > 0, r.profit_factor, r.win_rate), reverse=True)

    print(f"\n{'='*100}")
    print(f"  상위 {min(top_n, len(valid))}개 조합 (신호≥5건, PF 기준)")
    print(f"{'='*100}")
    print(f"  {'ma20':>5} {'ma5':>4} {'lb':>3} {'vol':>5} | {'신호':>5} {'승률':>7} {'avgPnL':>8} {'PF':>6} {'avgWin':>8} {'avgLoss':>8}")
    print(f"  {'-'*96}")

    for r in valid[:top_n]:
        p = r.params
        print(
            f"  {p['ma_trend']:>5}"
            f"  {p['ma_pullback']:>4}"
            f"  {p['pullback_lookback']:>3}"
            f"  {p['min_vol_ratio']:>5.2f}"
            f" | {r.signals:>5}"
            f"  {r.win_rate:>6.1f}%"
            f"  {r.avg_pnl:>+7.2f}%"
            f"  {r.profit_factor:>5.2f}"
            f"  {r.avg_win:>+7.2f}%"
            f"  {r.avg_loss:>+7.2f}%"
        )

    # 현재 기본값 결과 표시
    print(f"\n  ── 현재 기본값 (ma20=20, ma5=5, lb=5, vol=0.8) ──")
    baseline = next(
        (r for r in results
         if r.params["ma_trend"] == 20
         and r.params["ma_pullback"] == 5
         and r.params["pullback_lookback"] == 5
         and abs(r.params["min_vol_ratio"] - 0.8) < 0.001),
        None,
    )
    if baseline:
        p = baseline.params
        print(
            f"  {p['ma_trend']:>5}"
            f"  {p['ma_pullback']:>4}"
            f"  {p['pullback_lookback']:>3}"
            f"  {p['min_vol_ratio']:>5.2f}"
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
        print(f"    ma_trend         = {p['ma_trend']}")
        print(f"    ma_pullback      = {p['ma_pullback']}")
        print(f"    pullback_lookback = {p['pullback_lookback']}")
        print(f"    min_vol_ratio    = {p['min_vol_ratio']:.2f}")
        print(f"    → 신호 {best.signals}건, 승률 {best.win_rate:.1f}%, 평균PnL {best.avg_pnl:+.2f}%, PF {best.profit_factor:.2f}")


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy Four 파라미터 그리드 서치")
    parser.add_argument("--step", type=int, default=3, help="스캔 날짜 간격 (기본: 3일)")
    parser.add_argument("--top-n", type=int, default=20, help="출력 상위 N 조합 (기본: 20)")
    args = parser.parse_args()

    print("Strategy Four — 파라미터 그리드 서치")
    print(f"cache: {CACHE_ROOT.resolve()}")

    all_data, meta = load_data()
    print(f"종목: {len(all_data)}개")

    scan_dates = get_scan_dates(all_data, step=args.step)
    print(f"스캔 날짜: {len(scan_dates)}개 (step={args.step})")
    if not scan_dates:
        sys.exit("[ERROR] 스캔 날짜 없음. 데이터 재수집 필요.")

    print("\n[그리드 서치 실행 중...]")
    results = run_grid(all_data, meta, scan_dates)

    print_results(results, top_n=args.top_n)
    print(f"\n{'='*100}")
    print("  완료.")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    main()
