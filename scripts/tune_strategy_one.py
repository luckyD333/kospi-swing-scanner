"""
scripts/tune_strategy_one.py — Strategy One (Strategy D v2) 파라미터 그리드 서치

각 파라미터 조합으로 Walk-forward 백테스트를 실행해 최적 임계값을 탐색한다.

사용:
    python scripts/tune_strategy_one.py
    python scripts/tune_strategy_one.py --step 3 --top-n 20
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
from strategies.strategy_one_d_v2 import StrategyOneDv2, StrategyOneDv2Config

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
    cfg: StrategyOneDv2Config,
    top_n: int,
) -> tuple[int, float, float, float, float, float]:
    """신호 수, 승률, 평균PnL, PF, 평균승PnL, 평균패PnL 반환."""
    tickers = list(all_data.keys())
    names = {t: t for t in tickers}
    market_caps = {t: meta.get(t, {}).get("market_cap_bil", 0.0) or 0.0 for t in tickers}
    strategy = StrategyOneDv2(config=cfg)

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
    "engulf_strict":      [True, False],
    "db_freshness":       [2, 3, 4, 5],
    "db_price_tolerance": [0.02, 0.03, 0.04, 0.05],
    "detector_name":      ["simple", "fractal"],
}

# 기본값 (변경 안 할 파라미터)
BASE = dict(
    min_lookback_bars=25,
    min_daily_volume=100_000,
    use_rr_filter=True,
)


def build_config(
    engulf_strict: bool,
    db_freshness: int,
    db_price_tolerance: float,
    detector_name: str,
) -> StrategyOneDv2Config:
    return StrategyOneDv2Config(
        min_lookback_bars=BASE["min_lookback_bars"],
        min_daily_volume=BASE["min_daily_volume"],
        use_rr_filter=BASE["use_rr_filter"],
        engulf_strict=engulf_strict,
        db_freshness=db_freshness,
        db_price_tolerance=db_price_tolerance,
        detector_name=detector_name,
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
            engulf_strict=params["engulf_strict"],
            db_freshness=params["db_freshness"],
            db_price_tolerance=params["db_price_tolerance"],
            detector_name=params["detector_name"],
        )

        pnls: list[float] = []
        tickers = list(all_data.keys())
        market_caps = {t: meta.get(t, {}).get("market_cap_bil", 0.0) or 0.0 for t in tickers}
        strategy = StrategyOneDv2(config=cfg)

        for scan_date in scan_dates:
            sliced = {
                t: df[df.index <= scan_date]
                for t, df in all_data.items()
                if len(df[df.index <= scan_date]) >= 35
            }
            if not sliced:
                continue
            tickers_sliced = list(sliced.keys())
            ctx = ScanContext(
                target_date=scan_date.strftime("%Y%m%d"),
                universe=tuple(tickers_sliced),
                ohlcv=sliced,
                names={t: t for t in tickers_sliced},
                market_caps={t: market_caps.get(t, 0.0) for t in tickers_sliced},
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

        if (i + 1) % 16 == 0:
            print(f"    진행: {i+1}/{total}")

    return results


# ─── 결과 출력 ────────────────────────────────────────────────────────────────

def print_results(results: list[RunResult], top_n: int) -> None:
    # 신호 ≥ 3건인 결과만 (노이즈 제거)
    valid = [r for r in results if r.signals >= 3]

    if not valid:
        print("\n  [신호 ≥3건인 조합 없음] -- step을 줄이거나 top_n 늘리기 권장")
        # 신호 1건 이상 출력
        valid = [r for r in results if r.signals >= 1]
        if not valid:
            print("  신호 1건 이상인 조합도 없음.")
            return

    # PF 기준 정렬 (avg_pnl > 0 우선)
    valid.sort(key=lambda r: (r.avg_pnl > 0, r.profit_factor, r.win_rate), reverse=True)

    print(f"\n{'='*110}")
    print(f"  상위 {min(top_n, len(valid))}개 조합 (신호≥3건, PF 기준)")
    print(f"{'='*110}")
    print(f"  {'strict':>6} {'fresh':>6} {'tol':>6} {'detector':>8} | {'신호':>5} {'승률':>7} {'avgPnL':>8} {'PF':>6} {'avgWin':>8} {'avgLoss':>8}")
    print(f"  {'-'*108}")

    for r in valid[:top_n]:
        p = r.params
        strict_str = "Y" if p["engulf_strict"] else "N"
        print(
            f"  {strict_str:>6}"
            f"  {p['db_freshness']:>6}"
            f"  {p['db_price_tolerance']:>6.2f}"
            f"  {p['detector_name']:>8}"
            f" | {r.signals:>5}"
            f"  {r.win_rate:>6.1f}%"
            f"  {r.avg_pnl:>+7.2f}%"
            f"  {r.profit_factor:>5.2f}"
            f"  {r.avg_win:>+7.2f}%"
            f"  {r.avg_loss:>+7.2f}%"
        )

    # 현재 기본값 결과 표시
    print("\n  ── 현재 기본값 (strict=True, fresh=2, tol=0.03, detector=simple) ──")
    baseline = next(
        (r for r in results
         if r.params["engulf_strict"] is True
         and r.params["db_freshness"] == 2
         and abs(r.params["db_price_tolerance"] - 0.03) < 0.001
         and r.params["detector_name"] == "simple"),
        None,
    )
    if baseline:
        p = baseline.params
        strict_str = "Y" if p["engulf_strict"] else "N"
        print(
            f"  {strict_str:>6}"
            f"  {p['db_freshness']:>6}"
            f"  {p['db_price_tolerance']:>6.2f}"
            f"  {p['detector_name']:>8}"
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
        print("\n  ★ 추천 조합:")
        print(f"    engulf_strict      = {p['engulf_strict']}")
        print(f"    db_freshness       = {p['db_freshness']}")
        print(f"    db_price_tolerance = {p['db_price_tolerance']:.2f}")
        print(f"    detector_name      = '{p['detector_name']}'")
        print(f"    → 신호 {best.signals}건, 승률 {best.win_rate:.1f}%, 평균PnL {best.avg_pnl:+.2f}%, PF {best.profit_factor:.2f}")


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy One (Strategy D v2) 파라미터 그리드 서치")
    parser.add_argument("--step", type=int, default=3, help="스캔 날짜 간격 (기본: 3일)")
    parser.add_argument("--top-n", type=int, default=20, help="전략당 top-N 신호 (기본: 20)")
    parser.add_argument("--top", type=int, default=20, help="출력 상위 N 조합 (기본: 20)")
    args = parser.parse_args()

    print("Strategy One (Strategy D v2) — 파라미터 그리드 서치")
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
    print(f"\n{'='*110}")
    print("  완료.")
    print(f"{'='*110}\n")


if __name__ == "__main__":
    main()
