"""scripts/optimize_market_separate.py — KOSPI/KOSDAQ 각각 독립 최적화.

각 시장별 자체 train/val/OOS split:
  - train: bars 30-50 (step=3, ~7 스캔일)
  - val:   bars 50-65 (step=2, ~7 스캔일)
  - OOS:   bars 65-80 (step=2, ~7 스캔일)
    * KOSPI OOS = bb54d17 와 동일 윈도우 → 오염 한정 (보고서에 명시)
    * KOSDAQ OOS = 본 세션 최초 노출 → fresh OOS

Phase: 300 train sample → top-30 val → top-5 OOS + 3-way 게이트
"""
from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.optimize_full import (
    sample_config, make_default_config,
    evaluate_config, load_data,
    compute_pbo, deflated_sharpe,
    RUN_DIR_ROOT,
)

# 시장 분리 전용 설정
N_TRIALS = 300
N_TOP_B = 30
N_TOP_C = 5
SCAN_STEP_TRAIN = 3
SCAN_STEP_VAL = 2
SCAN_STEP_OOS = 2


def split_market_separate(data: dict[str, pd.DataFrame]):
    """단일 시장 데이터 → train/val/OOS 분할."""
    sample_df = next(iter(data.values()))
    dates = sample_df.index.tolist()
    n = len(dates)
    train_end = min(50, n - 5)
    val_end = min(65, n - 5)
    oos_end = min(80, n - 5)
    train_dates = dates[30:train_end:SCAN_STEP_TRAIN]
    val_dates = dates[train_end:val_end:SCAN_STEP_VAL]
    oos_dates = dates[val_end:oos_end:SCAN_STEP_OOS]
    return train_dates, val_dates, oos_dates


def optimize_one_market(market: str, run_dir: Path) -> dict:
    """단일 시장 전체 최적화 파이프라인."""
    print(f"\n{'=' * 70}\n  [{market}] 독립 최적화\n{'=' * 70}")

    data = load_data(market)
    print(f"  데이터: {len(data)} ticker")
    if len(data) < 30:
        print(f"  ⚠ {market} 데이터 부족, skip")
        return {"market": market, "skipped": True}

    train_dates, val_dates, oos_dates = split_market_separate(data)
    print(f"  Train: {len(train_dates)} 스캔일 ({train_dates[0].date()}~{train_dates[-1].date()})")
    print(f"  Val:   {len(val_dates)} 스캔일 ({val_dates[0].date()}~{val_dates[-1].date()})")
    print(f"  OOS:   {len(oos_dates)} 스캔일 ({oos_dates[0].date()}~{oos_dates[-1].date()})")

    # Phase A: train
    print(f"\n  [Phase A] {N_TRIALS} random samples on train...")
    t0 = time.time()
    results_train = []
    for i in range(N_TRIALS):
        c = sample_config()
        try:
            m = evaluate_config(c, data, train_dates)
        except Exception as e:
            m = {"n": 0, "pf": 0.0, "sharpe": -99.0, "max_dd": 0.0, "win_rate": 0.0, "error": str(e)}
        results_train.append((c, m))
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_TRIALS - i - 1)
            print(f"    {i+1}/{N_TRIALS} ({elapsed:.0f}s, ETA {eta:.0f}s)")

    # Phase B: top-30 val
    top_n_b = sorted([r for r in results_train if r[1]["n"] >= 5],
                     key=lambda x: -x[1]["sharpe"])[:N_TOP_B]
    print(f"\n  [Phase B] train n>=5: {len([r for r in results_train if r[1]['n']>=5])}, top-{N_TOP_B} val 평가...")
    results_val = []
    for c, m_train in top_n_b:
        try:
            m_val = evaluate_config(c, data, val_dates)
        except Exception as e:
            m_val = {"n": 0, "pf": 0.0, "sharpe": -99.0, "max_dd": 0.0, "win_rate": 0.0, "error": str(e)}
        results_val.append((c, m_train, m_val))

    train_sr = [m["sharpe"] for _, m, _ in results_val]
    val_sr = [m["sharpe"] for _, _, m in results_val]
    pbo = compute_pbo(train_sr, val_sr)
    print(f"    PBO (top-{N_TOP_B}): {pbo:.3f} {'< 0.5 ✓' if pbo < 0.5 else '≥ 0.5 ✗'}")

    # top-5
    top5 = sorted([r for r in results_val if r[2]["n"] >= 5],
                  key=lambda x: -x[2]["sharpe"])[:N_TOP_C]

    # Phase C: OOS + default 비교
    print(f"\n  [Phase C] top-{N_TOP_C} + default on OOS...")
    default_c = make_default_config()
    m_default_oos = evaluate_config(default_c, data, oos_dates)
    print(f"    default OOS: PF={m_default_oos['pf']:.2f}, win={m_default_oos['win_rate']:.1%}, "
          f"DD={m_default_oos['max_dd']:.1f}%, n={m_default_oos['n']}")

    results_oos = []
    for rank_idx, (c, m_train, m_val) in enumerate(top5, start=1):
        m_oos = evaluate_config(c, data, oos_dates)
        pf_up = m_oos["pf"] > m_default_oos["pf"]
        win_up = m_oos["win_rate"] > m_default_oos["win_rate"]
        dd_down = m_oos["max_dd"] < m_default_oos["max_dd"]
        passed = pf_up and win_up and dd_down
        dsr = deflated_sharpe(m_oos["sharpe"], N_TRIALS)
        results_oos.append({
            "rank": rank_idx, "config": asdict(c),
            "train_metrics": m_train, "val_metrics": m_val, "oos_metrics": m_oos,
            "gate": {"pf_up": pf_up, "win_up": win_up, "dd_down": dd_down, "passed": passed},
            "dsr": round(dsr, 3),
        })
        gate_str = "✓" if passed else "✗"
        print(f"    rank {rank_idx}: PF={m_oos['pf']:.2f}({'↑' if pf_up else '↓'}) "
              f"win={m_oos['win_rate']:.1%}({'↑' if win_up else '↓'}) "
              f"DD={m_oos['max_dd']:.1f}%({'↓' if dd_down else '↑'}) "
              f"n={m_oos['n']} DSR={dsr:.2f} → {gate_str}")

    summary = {
        "market": market,
        "default_oos": m_default_oos,
        "pbo": pbo,
        "top5": results_oos,
        "train_dates_n": len(train_dates),
        "val_dates_n": len(val_dates),
        "oos_dates_n": len(oos_dates),
    }
    (run_dir / f"{market.lower()}_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str)
    )
    (run_dir / f"{market.lower()}_train.json").write_text(json.dumps(
        [{"config": asdict(c), "metrics": m} for c, m in results_train],
        ensure_ascii=False, indent=1, default=str,
    ))
    return summary


def write_report(run_dir: Path, kospi: dict, kosdaq: dict):
    lines = ["# 시장 분리 최적화 — KOSPI vs KOSDAQ\n"]
    lines.append("## 메서드\n")
    lines.append("- 각 시장 자체 train/val/OOS 분할 (bars 30-50 / 50-65 / 65-80)")
    lines.append("- 300 random samples → top-30 val → top-5 OOS + default 비교")
    lines.append("- **KOSPI OOS = bb54d17 윈도우와 동일 → 결과 신뢰도 한정**")
    lines.append("- **KOSDAQ OOS = 본 세션 fresh** (이전 튜닝 노출 없음)\n")

    for label, s in [("KOSPI (OOS 오염)", kospi), ("KOSDAQ (fresh OOS)", kosdaq)]:
        if s.get("skipped"):
            lines.append(f"## {label}: 데이터 부족 skip\n")
            continue
        d = s["default_oos"]
        lines.append(f"## {label}\n")
        lines.append(f"- PBO (top-{N_TOP_B}): **{s['pbo']:.3f}**")
        lines.append(f"- Default OOS: PF={d['pf']:.2f}, win={d['win_rate']:.1%}, "
                     f"max DD={d['max_dd']:.1f}%, trades={d['n']}")
        lines.append("\n### Top-5 OOS\n")
        lines.append("| Rank | top_n | penalty | s1 | s2 | s3 | s4 | s5 | PF | win% | DD | DSR | 게이트 |")
        lines.append("|------|-------|---------|----|----|----|----|----|-----|------|-----|-----|--------|")
        for r in s["top5"]:
            c = r["config"]
            m = r["oos_metrics"]
            gate = "✓" if r["gate"]["passed"] else "✗"
            lines.append(f"| {r['rank']} | {c['top_n']} | {c['confluence_penalty']:.2f} | "
                         f"{c['w_s1']:.1f} | {c['w_s2']:.1f} | {c['w_s3']:.1f} | {c['w_s4']:.1f} | {c['w_s5']:.1f} | "
                         f"{m['pf']:.2f} | {m['win_rate']:.1%} | {m['max_dd']:.1f}% | {r['dsr']:.2f} | {gate} |")
        # 전략 가중치 평균
        ws_avg = {k: sum(r["config"][k] for r in s["top5"]) / len(s["top5"])
                  for k in ["w_s1", "w_s2", "w_s3", "w_s4", "w_s5"]}
        lines.append("\n### 평균 strategy weights\n")
        lines.append(f"- s1={ws_avg['w_s1']:.2f}, s2={ws_avg['w_s2']:.2f}, "
                     f"s3={ws_avg['w_s3']:.2f}, s4={ws_avg['w_s4']:.2f}, s5={ws_avg['w_s5']:.2f}")
        accepted = sum(1 for r in s["top5"] if r["gate"]["passed"])
        lines.append(f"- 채택: {accepted} / {len(s['top5'])}\n")

    # 비교 분석
    lines.append("## 시장 간 비교\n")
    if not (kospi.get("skipped") or kosdaq.get("skipped")):
        kp_ws = {k: sum(r["config"][k] for r in kospi["top5"]) / len(kospi["top5"])
                 for k in ["w_s1", "w_s2", "w_s3", "w_s4", "w_s5"]}
        kd_ws = {k: sum(r["config"][k] for r in kosdaq["top5"]) / len(kosdaq["top5"])
                 for k in ["w_s1", "w_s2", "w_s3", "w_s4", "w_s5"]}
        lines.append("| Strategy | KOSPI avg w | KOSDAQ avg w | 차이 |")
        lines.append("|----------|-------------|--------------|------|")
        for k in ["w_s1", "w_s2", "w_s3", "w_s4", "w_s5"]:
            diff = kp_ws[k] - kd_ws[k]
            lines.append(f"| {k.upper()} | {kp_ws[k]:.2f} | {kd_ws[k]:.2f} | {diff:+.2f} |")

    (run_dir / "market_separate_report.md").write_text("\n".join(lines))


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUN_DIR_ROOT / f"market_separate_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 70}\n  시장 분리 최적화 — KOSPI vs KOSDAQ\n  Run dir: {run_dir}\n{'=' * 70}")

    random.seed(42)
    kospi = optimize_one_market("KOSPI", run_dir)
    kosdaq = optimize_one_market("KOSDAQ", run_dir)

    write_report(run_dir, kospi, kosdaq)
    print(f"\n{'=' * 70}\n  완료. cat {run_dir}/market_separate_report.md\n{'=' * 70}")


if __name__ == "__main__":
    main()
