#!/usr/bin/env python3
"""Phase 2 Step 4.5: score percentile intra-strategy variance audit (Go/No-Go).

trade_plan_calc.compute_trade_plan() 의 k_adj 동적 곡선은 score_percentile 이 한
전략 안에서 0~1 범위로 골고루 퍼져야 의미 있음. 한 전략 안에서 score 가 클러스터
되면 k_adj 변동 폭이 너무 작아 동적 조정이 장식이 됨.

규칙:
  - σ ≥ 0.15: k 동적 곡선 적용 (Step 5 진행)
  - σ < 0.15: 해당 전략은 k_adj = base_k 고정 (score_pct=0.5 전달)
  - per-scan 평균 신호 수도 출력 (runtime σ 의 대리 지표)

timing-study 와 동일한 HistoricalSignalGenerator 사용 (라이브 게이트 완화).
사용: python scripts/audit_score_variance.py --top-n 500
"""
import argparse
import pathlib
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import numpy as np
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


def percentile_of(values: list[float], v: float) -> float:
    """v 가 values 안에서 차지하는 percentile (0~1)."""
    if not values:
        return 0.5
    n = len(values)
    less = sum(1 for x in values if x < v)
    equal = sum(1 for x in values if x == v)
    return (less + equal / 2) / n


def main() -> None:
    ap = argparse.ArgumentParser(description="score percentile variance audit")
    ap.add_argument("--top-n", type=int, default=500)
    ap.add_argument("--cutoff", type=float, default=0.15, help="sigma >= cutoff -> dynamic k OK")
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--output", default="data/score_variance_report.md")
    args = ap.parse_args()

    cache_dir = pathlib.Path(args.cache_dir)
    if not cache_dir.exists():
        print(f"[error] cache dir not found: {cache_dir}")
        return

    print(f"loading top-{args.top_n} tickers ...")
    ohlcv_map = load_ohlcv(cache_dir, args.top_n)
    print(f"{len(ohlcv_map)} tickers loaded")

    gen = HistoricalSignalGenerator(min_lookback=25)

    # 전략별 모든 신호의 raw score 수집 + signal_date 별 그룹 (per-scan 평균 신호 수용)
    raw_scores: dict[str, list[float]] = defaultdict(list)
    signals_per_date: dict[str, dict[pd.Timestamp, int]] = defaultdict(lambda: defaultdict(int))

    for sname in STRATEGIES:
        print(f"extracting {sname} ...", end=" ", flush=True)
        signals = gen.extract(sname, ohlcv_map)
        print(f"{len(signals)} signals")
        for sig in signals:
            raw_scores[sname].append(sig.score)
            signals_per_date[sname][sig.signal_date] += 1

    # 분석 — percentile 변환 후 σ 계산
    lines = [
        "# Score percentile variance audit (Phase 2 Step 4.5)",
        "",
        f"- cache: top {args.top_n} tickers, {len(ohlcv_map)} loaded",
        f"- cutoff: sigma >= {args.cutoff} -> dynamic k OK, otherwise fix to base_k",
        "",
        "## 전략별 σ + per-scan 평균 신호 수",
        "",
        "| strategy | n_total | n_unique_dates | avg_per_scan | raw_score_sigma | percentile_sigma | dynamic_k |",
        "|---|---:|---:|---:|---:|---:|:---:|",
    ]
    decisions: dict[str, str] = {}
    for sname in STRATEGIES:
        raws = raw_scores[sname]
        if len(raws) < 5:
            lines.append(f"| {sname} | {len(raws)} | — | — | — | — | FIX (n<5) |")
            decisions[sname] = "fixed"
            continue
        # raw σ
        raw_sigma = float(statistics.pstdev(raws))
        # percentile σ — 각 신호를 자기 전략 분포 안에서의 percentile 로 변환 후 σ
        pcts = [percentile_of(raws, v) for v in raws]
        pct_sigma = float(statistics.pstdev(pcts))
        # per-scan 평균
        per_scan_counts = list(signals_per_date[sname].values())
        avg_per_scan = float(np.mean(per_scan_counts)) if per_scan_counts else 0.0
        decision = "DYNAMIC" if pct_sigma >= args.cutoff else "FIX"
        decisions[sname] = "dynamic" if pct_sigma >= args.cutoff else "fixed"
        lines.append(
            f"| {sname} | {len(raws)} | {len(per_scan_counts)} | "
            f"{avg_per_scan:.1f} | {raw_sigma:.4f} | {pct_sigma:.4f} | {decision} |"
        )

    lines += ["", "## 채택 결정", ""]
    for sname, d in decisions.items():
        if d == "dynamic":
            lines.append(f"- **{sname}**: k 동적 적용 — score_percentile 그대로 전달")
        elif d == "fixed":
            lines.append(f"- **{sname}**: k 고정 — score_percentile=0.5 전달 (k_adj = base_k)")
        else:
            lines.append(f"- **{sname}**: 표본 부족 — k 고정")

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport: {output}")
    print("decisions:")
    for sname, d in decisions.items():
        print(f"  {sname}: {d}")


if __name__ == "__main__":
    main()
