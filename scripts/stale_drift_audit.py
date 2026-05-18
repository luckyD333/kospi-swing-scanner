#!/usr/bin/env python3
"""STALE 임계 audit — signal_date 후 N거래일 시점의 price_drift 분포 측정.

목적: |drift|≥5% 비율이 operator-tunable cutoff(초기 30%) 를 처음 넘는 N 을 STALE
임계로 채택. timing-study 와 동일한 HistoricalSignalGenerator 사용 (라이브 게이트
완화 데이터, 운영 1주 후 walk-forward 로 재검증 예정).

사용: python scripts/stale_drift_audit.py --top-n 500 --cutoff 0.30
"""
import argparse
import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

from backtest_engine.historical_signals import HistoricalSignalGenerator

CACHE_DIR = pathlib.Path(".cache/1D")
STRATEGIES = [
    "strategy_one",
    "strategy_two",
    "strategy_three",
    "strategy_four",
    "strategy_five",
]
HORIZONS = [1, 2, 3, 4, 5]
DRIFT_THRESHOLD_PCT = 5.0  # |drift|≥5% 를 "큰 괴리" 로 정의


def load_ohlcv(cache_dir: pathlib.Path, top_n: int) -> dict[str, pd.DataFrame]:
    files = sorted(cache_dir.glob("*.parquet"))
    out: dict[str, pd.DataFrame] = {}
    for f in files[:top_n]:
        try:
            df = pd.read_parquet(f)
            if len(df) >= 30:
                out[f.stem] = df
        except Exception as e:
            print(f"[skip] {f.stem}: {e}")
    return out


def drift_at_horizon(
    df: pd.DataFrame, signal_date: pd.Timestamp, entry: float, n_bars: int
) -> float | None:
    if entry <= 0:
        return None  # entry=0 divide-by-zero 방어
    try:
        idx = df.index.get_loc(signal_date)
    except KeyError:
        return None
    out_idx = idx + n_bars
    if out_idx >= len(df):
        return None
    return float((df["close"].iloc[out_idx] - entry) / entry * 100.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="STALE 임계 audit")
    ap.add_argument("--top-n", type=int, default=500)
    ap.add_argument("--cutoff", type=float, default=0.30, help="|drift| >= 5pct ratio threshold")
    ap.add_argument("--output", default="data/stale_drift_report.md")
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    args = ap.parse_args()

    cache_dir = pathlib.Path(args.cache_dir)
    if not cache_dir.exists():
        print(f"[error] cache dir not found: {cache_dir}")
        return

    print(f"loading top-{args.top_n} tickers ...")
    ohlcv_map = load_ohlcv(cache_dir, args.top_n)
    print(f"{len(ohlcv_map)} tickers loaded")

    gen = HistoricalSignalGenerator(min_lookback=25)
    # horizon → list of drift_pct
    drifts: dict[int, list[float]] = defaultdict(list)
    drifts_by_strategy: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for sname in STRATEGIES:
        print(f"extracting {sname} ...", end=" ", flush=True)
        signals = gen.extract(sname, ohlcv_map)
        print(f"{len(signals)} signals")
        for sig in signals:
            df = ohlcv_map.get(sig.ticker)
            if df is None or sig.signal_date not in df.index:
                continue
            for h in HORIZONS:
                d = drift_at_horizon(df, sig.signal_date, sig.entry_price, h)
                if d is None:
                    continue
                drifts[h].append(d)
                drifts_by_strategy[sname][h].append(d)

    # 분석
    lines = [
        "# STALE drift audit",
        "",
        f"- cache: top {args.top_n} tickers, {len(ohlcv_map)} loaded",
        f"- cutoff: |drift|≥{DRIFT_THRESHOLD_PCT}% 비율 임계 = {args.cutoff:.0%}",
        "",
        "## 전체 (전략 합산)",
        "",
        "| horizon (거래일) | n | |drift|≥5% 비율 | mean drift | median |",
        "|---:|---:|---:|---:|---:|",
    ]
    chosen_n: int | None = None
    for h in HORIZONS:
        ds = drifts[h]
        if not ds:
            lines.append(f"| {h} | 0 | — | — | — |")
            continue
        big = sum(1 for d in ds if abs(d) >= DRIFT_THRESHOLD_PCT)
        ratio = big / len(ds)
        mean = sum(ds) / len(ds)
        median = sorted(ds)[len(ds) // 2]
        marker = ""
        if chosen_n is None and ratio >= args.cutoff:
            chosen_n = h
            marker = " ★"
        lines.append(
            f"| {h} | {len(ds)} | {ratio:.1%}{marker} | {mean:+.2f}% | {median:+.2f}% |"
        )

    lines += ["", f"**채택 STALE_THRESHOLD_1D = {chosen_n if chosen_n is not None else 'N/A'}** "
              f"(처음으로 |drift|≥{DRIFT_THRESHOLD_PCT}% 비율이 {args.cutoff:.0%} 넘는 horizon)"]
    lines += ["", "## 전략별 분포", ""]
    for sname in STRATEGIES:
        lines.append(f"### {sname}")
        lines += [
            "",
            "| horizon | n | |drift|≥5% 비율 | mean drift |",
            "|---:|---:|---:|---:|",
        ]
        for h in HORIZONS:
            ds = drifts_by_strategy[sname][h]
            if not ds:
                lines.append(f"| {h} | 0 | — | — |")
                continue
            big = sum(1 for d in ds if abs(d) >= DRIFT_THRESHOLD_PCT)
            ratio = big / len(ds)
            mean = sum(ds) / len(ds)
            lines.append(f"| {h} | {len(ds)} | {ratio:.1%} | {mean:+.2f}% |")
        lines.append("")

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport: {output}")
    print(f"chosen STALE_THRESHOLD_1D: {chosen_n if chosen_n is not None else 'N/A (cutoff 도달 못함, 기본 3 유지)'}")


if __name__ == "__main__":
    main()
