"""
output/comparison.py — 멀티 전략 비교 테이블.

같은 날 N개 전략의 top K 결과를 한눈에 비교하기 위한 markdown/csv 출력.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Dict, List

from core.strategy_base import Candidate


def _normalize(results: Dict[str, List[Candidate]]) -> Dict[str, List[Candidate]]:
    """전략명 정렬 + None 제거."""
    return {k: list(v or []) for k, v in sorted(results.items())}


def overlap_summary(results: Dict[str, List[Candidate]]) -> Dict[str, List[str]]:
    """
    전략 간 ticker 교집합 요약.

    Returns:
      {ticker: [strategy_name, ...]}  — 2개 이상 전략에서 등장한 ticker 만
    """
    by_ticker: Dict[str, List[str]] = {}
    for strat, cands in results.items():
        for c in cands:
            by_ticker.setdefault(c.ticker, []).append(strat)
    return {t: sorted(set(s)) for t, s in by_ticker.items() if len(set(s)) >= 2}


def format_markdown_comparison(
    results: Dict[str, List[Candidate]],
    target_date: str,
    top_n: int = 10,
) -> str:
    """전략 × 종목 비교 markdown."""
    norm = _normalize(results)
    strategies = list(norm.keys())
    if not strategies:
        return f"# {target_date} 멀티 전략 결과 없음\n"

    lines = [
        f"# {target_date} 멀티 전략 비교 (top {top_n})",
        "",
        "## 전략별 Top",
        "",
        "| 순위 | " + " | ".join(strategies) + " |",
        "|---:|" + "|".join([":---" for _ in strategies]) + "|",
    ]
    for i in range(top_n):
        cells = []
        for strat in strategies:
            cands = norm[strat]
            if i < len(cands):
                c = cands[i]
                cells.append(f"{c.ticker} {c.name} ({c.score:.2f})")
            else:
                cells.append("—")
        lines.append(f"| {i+1} | " + " | ".join(cells) + " |")

    overlap = overlap_summary(norm)
    if overlap:
        lines.append("")
        lines.append("## 다중 전략 교집합 (≥ 2 전략에서 등장)")
        lines.append("")
        for ticker, strats in sorted(overlap.items()):
            name = next(
                (c.name for cands in norm.values() for c in cands if c.ticker == ticker),
                ticker,
            )
            lines.append(f"- **{ticker}** {name} — {', '.join(strats)}")

    return "\n".join(lines) + "\n"


def format_csv_comparison(
    results: Dict[str, List[Candidate]],
    target_date: str,
) -> str:
    """flat CSV: 행 = 전략 × 후보."""
    norm = _normalize(results)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "target_date", "strategy", "rank", "ticker", "name", "score",
        "entry_price", "stop_loss", "target_1", "target_2",
    ])
    for strat, cands in norm.items():
        for i, c in enumerate(cands, 1):
            writer.writerow([
                target_date, strat, i, c.ticker, c.name, round(c.score, 4),
                round(c.entry_price, 2), round(c.stop_loss, 2),
                round(c.target_1, 2), round(c.target_2, 2),
            ])
    return buf.getvalue()


def format_json_comparison(
    results: Dict[str, List[Candidate]],
    target_date: str,
    indent: int = 2,
) -> str:
    """JSON 비교 — 전략별 후보 + 교집합."""
    norm = _normalize(results)
    payload = {
        "target_date": target_date,
        "strategies": {
            strat: [
                {
                    "rank": i + 1,
                    "ticker": c.ticker,
                    "name": c.name,
                    "score": round(c.score, 4),
                    "entry_price": round(c.entry_price, 2),
                    "stop_loss": round(c.stop_loss, 2),
                    "target_1": round(c.target_1, 2),
                    "target_2": round(c.target_2, 2),
                }
                for i, c in enumerate(cands)
            ]
            for strat, cands in norm.items()
        },
        "overlap": overlap_summary(norm),
    }
    return json.dumps(payload, ensure_ascii=False, indent=indent)
