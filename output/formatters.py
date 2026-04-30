"""
output/formatters.py — Candidate 리스트 출력 포맷터.

지원 포맷:
  - table   : stdout 한국어 테이블 (기존 daily_only_scanner.print_results 와 유사)
  - json    : 직렬화 가능한 dict 구조
  - csv     : 헤더 + 행
  - markdown: 멀티 전략 비교용 (ComparisonTable 에서 활용, 본 모듈은 단일 전략만)
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from typing import Iterable, List

import pandas as pd

from core.strategy_base import Candidate


_CSV_FIELDS = [
    "rank", "ticker", "name", "strategy", "signal_date", "score",
    "entry_price", "stop_loss", "target_1", "target_2",
    "market_cap_bil", "volume_20d_avg", "risk_pct", "reward_pct_t1", "reward_pct_t2",
]


def _candidate_to_row(c: Candidate, rank: int) -> dict:
    return {
        "rank": rank,
        "ticker": c.ticker,
        "name": c.name,
        "strategy": c.strategy,
        "signal_date": str(c.signal_date)[:10],
        "score": round(c.score, 4),
        "entry_price": round(c.entry_price, 2),
        "stop_loss": round(c.stop_loss, 2),
        "target_1": round(c.target_1, 2),
        "target_2": round(c.target_2, 2),
        "market_cap_bil": round(c.market_cap_bil, 0),
        "volume_20d_avg": round(c.volume_20d_avg, 0),
        "risk_pct": round(c.risk_pct, 2),
        "reward_pct_t1": round(c.reward_pct_t1, 2),
        "reward_pct_t2": round(c.reward_pct_t2, 2),
    }


# ============================================================================
# table (stdout)
# ============================================================================

def format_table(candidates: List[Candidate], target_date: str) -> str:
    """기존 print_results 와 유사한 stdout 형식."""
    if not candidates:
        return f"\n  ⚠️  {target_date} 진입 조건 충족 종목 없음\n"

    lines = []
    lines.append("\n" + "=" * 90)
    lines.append(f"  🎯 {target_date} 매수 후보 {len(candidates)}개")
    lines.append("=" * 90)
    lines.append("")
    lines.append(
        f"  {'순위':>4}  {'종목코드':<8}  {'종목명':<15}  "
        f"{'시총(억)':>10}  {'Score':>6}  {'손절':>8}  {'목표1':>8}  {'목표2':>8}"
    )
    lines.append("  " + "─" * 86)

    for i, c in enumerate(candidates, 1):
        lines.append(
            f"  {i:>4}  {c.ticker:<8}  {c.name[:15]:<15}  "
            f"{c.market_cap_bil:>10,.0f}  {c.score:>6.3f}  "
            f"{-c.risk_pct:>7.2f}%  +{c.reward_pct_t1:>6.2f}%  +{c.reward_pct_t2:>6.2f}%"
        )

    # 상위 5 개 상세 정보
    lines.append("")
    lines.append("─" * 90)
    lines.append("  📋 상세 매수 정보 (상위 5개)")
    lines.append("─" * 90)

    for i, c in enumerate(candidates[:5], 1):
        lines.append(f"\n  ────── #{i}  [{c.ticker}] {c.name} ({c.strategy})  ──────")
        lines.append(f"     Score                : {c.score:>12.1%}")
        lines.append(f"     시총                 : {c.market_cap_bil:>12,.0f} 억원")
        lines.append(f"     20일 평균 거래량      : {c.volume_20d_avg:>12,.0f} 주")
        lines.append(f"     💰 진입가            : {c.entry_price:>12,.2f}")
        lines.append(f"     🛑 손절가            : {c.stop_loss:>12,.2f}  ({-c.risk_pct:+.2f}%)")
        lines.append(f"     🎯 1차 목표          : {c.target_1:>12,.2f}  (+{c.reward_pct_t1:.2f}%)")
        lines.append(f"     🎯 2차 목표          : {c.target_2:>12,.2f}  (+{c.reward_pct_t2:.2f}%)")
        conds = [k for k, v in c.conditions_met.items() if v]
        if conds:
            lines.append(
                f"     ✓ 충족 조건 ({len(conds)}): "
                f"{', '.join(conds[:6])}{'...' if len(conds) > 6 else ''}"
            )

    lines.append("\n" + "=" * 90 + "\n")
    return "\n".join(lines)


# ============================================================================
# json
# ============================================================================

def format_json(candidates: List[Candidate], target_date: str, indent: int = 2) -> str:
    """JSON 직렬화. signal_date 와 conditions_met 포함, metadata 는 평문."""
    payload = {
        "target_date": target_date,
        "count": len(candidates),
        "candidates": [
            {
                **_candidate_to_row(c, rank=i + 1),
                "conditions_met": {k: bool(v) for k, v in sorted(c.conditions_met.items())},
                "metadata": dict(c.metadata),
            }
            for i, c in enumerate(candidates)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent)


# ============================================================================
# csv
# ============================================================================

def format_csv(candidates: List[Candidate], target_date: str) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["target_date"] + _CSV_FIELDS)
    writer.writeheader()
    for i, c in enumerate(candidates, 1):
        row = _candidate_to_row(c, rank=i)
        row["target_date"] = target_date
        writer.writerow(row)
    return buf.getvalue()


# ============================================================================
# markdown (단일 전략)
# ============================================================================

def format_markdown(candidates: List[Candidate], target_date: str) -> str:
    """단일 전략 결과 markdown 테이블."""
    if not candidates:
        return f"# {target_date} 매수 후보 없음\n"

    lines = [
        f"# {target_date} 매수 후보 ({len(candidates)}건)",
        "",
        "| 순위 | 종목 | 이름 | Score | 진입 | 손절 | 목표1 | 목표2 | R:R |",
        "|---:|:---|:---|---:|---:|---:|---:|---:|---:|",
    ]
    for i, c in enumerate(candidates, 1):
        rr = c.reward_pct_t2 / c.risk_pct if c.risk_pct > 0 else 0
        lines.append(
            f"| {i} | {c.ticker} | {c.name} | {c.score:.3f} | "
            f"{c.entry_price:,.2f} | {c.stop_loss:,.2f} | "
            f"{c.target_1:,.2f} | {c.target_2:,.2f} | 1:{rr:.1f} |"
        )
    return "\n".join(lines) + "\n"


FORMATTERS = {
    "table": format_table,
    "json": format_json,
    "csv": format_csv,
    "markdown": format_markdown,
}
