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
from datetime import datetime
from zoneinfo import ZoneInfo

from core.strategy_base import Candidate


def _json_default(obj):
    """numpy scalar / pandas Timestamp 등 JSON 비-호환 객체를 native python으로 변환.

    metadata에는 전략 코드가 numpy.bool_ / numpy.float64 같은 값을 넣을 수 있어
    fallback 핸들러로 보호한다.
    """
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except (ValueError, AttributeError):
            pass
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")

_CSV_FIELDS = [
    "rank", "ticker", "name", "strategy", "signal_date", "score",
    "current_price", "entry_price", "stop_loss", "target_1", "target_2",
    "market_cap_bil", "volume_20d_avg", "risk_pct", "reward_pct_t1", "reward_pct_t2",
    # 신규 metric (PR #1)
    "rr_ratio", "rr_band", "atr_14", "source_strategy",
    # 펀더멘털 (Phase 1, runner 사후 주입). UI에서 활용.
    "per", "roe", "foreign_pct", "naver_url",
]


def _candidate_to_row(c: Candidate, rank: int) -> dict:
    meta = c.metadata or {}
    rr_ratio_val = meta.get("rr_ratio")
    atr_14_val = meta.get("atr_14")
    return {
        "rank": rank,
        "ticker": c.ticker,
        "name": c.name,
        "strategy": c.strategy,
        "signal_date": str(c.signal_date)[:10],
        "score": round(c.score, 1),
        "current_price": int(round(c.current_price)) if c.current_price else None,
        "entry_price": int(round(c.entry_price)),
        "stop_loss": int(round(c.stop_loss)),
        "target_1": int(round(c.target_1)),
        "target_2": int(round(c.target_2)),
        "market_cap_bil": round(c.market_cap_bil, 0),
        "volume_20d_avg": round(c.volume_20d_avg, 0),
        "risk_pct": round(c.risk_pct, 2),
        "reward_pct_t1": round(c.reward_pct_t1, 2),
        "reward_pct_t2": round(c.reward_pct_t2, 2),
        "rr_ratio": round(rr_ratio_val, 2) if rr_ratio_val is not None else "",
        "rr_band": meta.get("rr_band", ""),
        "atr_14": round(atr_14_val, 2) if atr_14_val is not None else "",
        "source_strategy": meta.get("source_strategy", ""),
        "per": meta.get("per"),
        "roe": meta.get("roe"),
        "foreign_pct": meta.get("foreign_pct"),
        "naver_url": meta.get("naver_url"),
    }


# ============================================================================
# table (stdout)
# ============================================================================

def format_table(candidates: list[Candidate], target_date: str) -> str:
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
            f"{c.market_cap_bil:>10,.0f}  {c.score:>7.1f}  "
            f"{-c.risk_pct:>7.2f}%  +{c.reward_pct_t1:>6.2f}%  +{c.reward_pct_t2:>6.2f}%"
        )

    # 상위 5 개 상세 정보
    lines.append("")
    lines.append("─" * 90)
    lines.append("  📋 상세 매수 정보 (상위 5개)")
    lines.append("─" * 90)

    for i, c in enumerate(candidates[:5], 1):
        lines.append(f"\n  ────── #{i}  [{c.ticker}] {c.name} ({c.strategy})  ──────")
        lines.append(f"     Score                : {c.score:>12.1f} pt")
        lines.append(f"     시총                 : {c.market_cap_bil:>12,.0f} 억원")
        lines.append(f"     20일 평균 거래량      : {c.volume_20d_avg:>12,.0f} 주")
        if c.current_price:
            lines.append(f"     📌 현재가            : {c.current_price:>12,.0f}")
        lines.append(f"     💰 진입가            : {c.entry_price:>12,.0f}")
        lines.append(f"     🛑 손절가            : {c.stop_loss:>12,.0f}  ({-c.risk_pct:+.2f}%)")
        lines.append(f"     🎯 1차 목표          : {c.target_1:>12,.0f}  (+{c.reward_pct_t1:.2f}%)")
        lines.append(f"     🎯 2차 목표          : {c.target_2:>12,.0f}  (+{c.reward_pct_t2:.2f}%)")
        # 펀더멘털 — Phase 1 사후 주입 (값 없으면 표시 생략)
        meta = c.metadata or {}
        per, roe, fp = meta.get("per"), meta.get("roe"), meta.get("foreign_pct")
        if any(v is not None for v in (per, roe, fp)):
            parts = []
            if per is not None:
                parts.append(f"PER {per:.2f}")
            if roe is not None:
                parts.append(f"ROE {roe:.2f}")
            if fp is not None:
                parts.append(f"외인비율 {fp:.2f}%")
            lines.append(f"     📊 펀더멘털          : {' · '.join(parts)}")
        if meta.get("naver_url"):
            lines.append(f"     🔗 네이버            : {meta['naver_url']}")
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

def format_json(
    candidates: list[Candidate],
    target_date: str,
    strategy_name: str | None = None,
    timeframe: str = "1D",
    filters: dict | None = None,
    indent: int = 2,
) -> str:
    """JSON 직렬화 (표준화된 schema).

    Args:
        candidates: Candidate 리스트
        target_date: 기준일 (YYYYMMDD)
        strategy_name: 전략명 (None이면 키 생략)
        timeframe: 타임프레임 (기본값 "1D")
        filters: 적용된 필터 dict (기본값 {})
        indent: JSON 들여쓰기
    """
    # generated_at: timezone-aware ISO8601 (KST)
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

    candidates_data = []
    for i, c in enumerate(candidates, 1):
        row = _candidate_to_row(c, rank=i)
        # rank, ticker, name, score 를 최상위에, 나머지는 metrics 로 이동
        rank = row.pop("rank")
        ticker = row.pop("ticker")
        name = row.pop("name")
        score = row.pop("score")
        metrics = row
        # 전략별 고유 metadata(momentum_pct, channel_high 등)와 진입 근거(conditions_met)
        # 를 metrics에 merge — UI가 "왜 후보인지" 표시 가능. _candidate_to_row가
        # 이미 추출한 펀더멘털 키는 동일 값으로 덮어써짐 (의미 변동 없음).
        if c.metadata:
            metrics.update(c.metadata)
        metrics["conditions_met"] = dict(c.conditions_met) if c.conditions_met else {}
        candidates_data.append({
            "rank": rank,
            "ticker": ticker,
            "name": name,
            "score": score,
            "metrics": metrics,
        })

    payload = {
        "date": target_date,
        "timeframe": timeframe,
        "generated_at": generated_at,
        "candidates": candidates_data,
        "summary": {
            "count": len(candidates),
            "filters": filters or {},
        },
    }

    # strategy_name이 None이 아니면 최상위에 추가
    if strategy_name is not None:
        payload = {"strategy": strategy_name, **payload}

    return json.dumps(payload, ensure_ascii=False, indent=indent, default=_json_default)


# ============================================================================
# csv
# ============================================================================

def format_csv(candidates: list[Candidate], target_date: str) -> str:
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

def format_markdown(candidates: list[Candidate], target_date: str) -> str:
    """단일 전략 결과 markdown 테이블 (펀더멘털 + RR/ATR 컬럼 포함)."""
    if not candidates:
        return f"# {target_date} 매수 후보 없음\n"

    def _meta_num(meta: dict, key: str, fmt: str = "{:.2f}") -> str:
        v = (meta or {}).get(key)
        if v is None:
            return "N/A"
        try:
            return fmt.format(float(v))
        except (TypeError, ValueError):
            return "N/A"

    lines = [
        f"# {target_date} 매수 후보 ({len(candidates)}건)",
        "",
        "| 순위 | 종목 | 이름 | Score | PER | ROE | 외인% | R:R | ATR14 | RR대역 | 전략 | 현재가 | 진입 | 손절 | 목표1 | 목표2 |",
        "|---:|:---|:---|---:|---:|---:|---:|---:|---:|:---|:---|---:|---:|---:|---:|---:|",
    ]
    for i, c in enumerate(candidates, 1):
        rr = c.reward_pct_t2 / c.risk_pct if c.risk_pct > 0 else 0
        cur = f"{c.current_price:,.0f}" if c.current_price else "-"
        per = _meta_num(c.metadata, "per")
        roe = _meta_num(c.metadata, "roe")
        fp = _meta_num(c.metadata, "foreign_pct")
        atr_14 = _meta_num(c.metadata, "atr_14", "{:.0f}")
        rr_band = (c.metadata or {}).get("rr_band", "N/A")
        source_strat = (c.metadata or {}).get("source_strategy", "")
        lines.append(
            f"| {i} | {c.ticker} | {c.name} | {c.score:.1f} | "
            f"{per} | {roe} | {fp} | "
            f"1:{rr:.1f} | {atr_14} | {rr_band} | {source_strat} | "
            f"{cur} | {c.entry_price:,.0f} | {c.stop_loss:,.0f} | "
            f"{c.target_1:,.0f} | {c.target_2:,.0f} |"
        )
    return "\n".join(lines) + "\n"


# ============================================================================
# summary (실행 funnel 요약)
# ============================================================================

def format_run_summary(result, market: str) -> str:
    """실행 요약 — funnel + strategies 텍스트 블록."""
    from core.runner import RunResult

    if not isinstance(result, RunResult):
        raise TypeError(f"Expected RunResult, got {type(result)}")

    funnel = result.funnel_stats or {}

    # 빈 funnel 처리
    if not funnel:
        return (
            "================================================================\n"
            "  📊 Scan Summary (funnel 미수집)\n"
            "================================================================\n"
        )

    # funnel 기본값 설정 (누락 시)
    uni_size = funnel.get("universe_size", 0)
    pre_cap_size = funnel.get("pre_cap_limit_size", uni_size)
    cap_limit = funnel.get("universe_cap_limit", 0)
    fetch_ok = funnel.get("fetch_success", 0)
    fetch_fail = funnel.get("fetch_failed", 0)
    short_bars = funnel.get("short_bars", 0)
    fetch_exceptions = funnel.get("fetch_exceptions", {})
    source_counts = funnel.get("source_counts", {})

    lines = []
    lines.append("=" * 66)
    lines.append(f"  📊 Scan Summary @ {result.target_date}  ({market})")
    lines.append("=" * 66)

    # 1. Universe 라인
    if cap_limit > 0 and pre_cap_size > cap_limit:
        universe_line = f"  Universe : {pre_cap_size} → top {cap_limit} 적용 → {uni_size} 종목"
    else:
        universe_line = f"  Universe : {uni_size} 종목"
    lines.append(universe_line)

    # 2. OHLCV 확보 라인
    total_attempted = fetch_ok + fetch_fail + short_bars
    lines.append(f"  OHLCV 확보 : {fetch_ok} 종목 ({total_attempted - fetch_ok:+d})")

    # 2-1. fetch 실패 세부
    if fetch_fail > 0 or fetch_exceptions:
        exc_str = ", ".join(
            f"{k}: {v}" for k, v in sorted(fetch_exceptions.items())
        ) if fetch_exceptions else ""
        exc_display = f"  {{{exc_str}}}" if exc_str else ""
        lines.append(f"    ├ fetch 실패 : {fetch_fail} {exc_display}")

    # 2-2. short_bars
    if short_bars > 0:
        lines.append(f"    └ 봉수 < 30 (short_bars) : {short_bars}")

    # 3. 소스별 응답 분포
    if source_counts:
        source_str = " / ".join(
            f"{k} {v}" for k, v in sorted(source_counts.items())
        )
        lines.append(f"  소스별 응답 분포 : {source_str}")

    # 4. Cache stats (RunResult.cache_stats에서)
    if result.cache_stats:
        cache_display = ", ".join(
            f"{k}={v}" for k, v in sorted(result.cache_stats.items())
        )
        lines.append(f"  Cache stats : {cache_display}")

    # 5. 전략별 결과
    lines.append("")
    lines.append("  전략별 결과")

    if result.candidates_by_strategy:
        for strat_name, candidates in sorted(result.candidates_by_strategy.items()):
            lines.append(f"    {strat_name:<30} : {len(candidates)} 후보")
    if result.errors:
        for strat_name, err_msg in sorted(result.errors.items()):
            # 에러 메시지 첫 50자만 표시
            err_short = err_msg[:50].split('\n')[0]
            lines.append(f"    {strat_name:<30} : ❌ {err_short}")
    if not result.candidates_by_strategy and not result.errors:
        lines.append("    (결과 없음)")

    lines.append("=" * 66)
    return "\n".join(lines)


def format_run_summary_json(result, market: str) -> dict:
    """JSON 임베드용 summary dict."""
    from core.runner import RunResult

    if not isinstance(result, RunResult):
        raise TypeError(f"Expected RunResult, got {type(result)}")

    funnel = result.funnel_stats or {}

    return {
        "target_date": result.target_date,
        "market": market,
        "funnel": {
            "universe_size": funnel.get("universe_size", 0),
            "pre_cap_limit_size": funnel.get("pre_cap_limit_size", 0),
            "universe_cap_limit": funnel.get("universe_cap_limit", 0),
            "fetch_success": funnel.get("fetch_success", 0),
            "fetch_failed": funnel.get("fetch_failed", 0),
            "short_bars": funnel.get("short_bars", 0),
            "fetch_exceptions": dict(funnel.get("fetch_exceptions", {})),
            "source_counts": dict(funnel.get("source_counts", {})),
        },
        "strategies": {
            strat_name: {"count": len(candidates)}
            for strat_name, candidates in result.candidates_by_strategy.items()
        },
        "errors": result.errors,
    }


FORMATTERS = {
    "table": format_table,
    "json": format_json,
    "csv": format_csv,
    "markdown": format_markdown,
}
