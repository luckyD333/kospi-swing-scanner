"""
output/decision_journal.py — Decision Journal markdown 생성.

Phase 2: SKILL.md "Decision Journal 메모" 템플릿을 RankedCandidate + WeightConfig
로 자동 채움. 사용자 입력 영역 (감정, 확신)은 빈 칸 + 안내.

두 가지 출력:
  - format_decision_journal: 단일 후보 결정 메모 (사용자가 N개 선택했을 때 각 후보별)
  - format_ranking_report: Top N 후보 ranking 표 + 가중치 정보 + 의사결정 가이드
"""
from __future__ import annotations

from datetime import datetime

from core.decision.aggregator import RankedCandidate
from core.decision.config import WeightConfig


def _fmt_num(v, fmt: str = "{:.2f}") -> str:
    if v is None:
        return "N/A"
    try:
        return fmt.format(float(v))
    except (TypeError, ValueError):
        return "N/A"


def _break_even_winrate(rr: float) -> float:
    """R:R 비율 → 손익분기 승률 (%). rr<=0 (손실 시나리오)이면 None 반환 (호출 측 경고 표기)."""
    if rr <= 0:
        return float("nan")
    return 100.0 / (1.0 + rr)


def format_decision_journal(
    ranked: RankedCandidate,
    weight_config: WeightConfig,
    notes: str | None = None,
) -> str:
    """단일 후보 Decision Journal markdown."""
    cand = ranked.candidate
    meta = cand.metadata or {}
    naver_url = meta.get("naver_url", "")

    rr_t1 = cand.reward_pct_t1 / cand.risk_pct if cand.risk_pct > 0 else 0
    rr_t2 = cand.reward_pct_t2 / cand.risk_pct if cand.risk_pct > 0 else 0
    be_t1 = _break_even_winrate(rr_t1)
    be_t2 = _break_even_winrate(rr_t2)

    lines: list[str] = []
    lines.append(f"# Decision Journal — [{cand.ticker}] {cand.name}")
    lines.append("")
    lines.append(f"- **결정 일시**: {datetime.now().isoformat(timespec='minutes')}")
    lines.append("- **분류**: Type 1 / Type 2  *(사용자 직접 입력)*")
    lines.append(f"- **종목 링크**: [{cand.ticker} 네이버 종목 상세]({naver_url})" if naver_url
                 else f"- **종목 코드**: {cand.ticker}")
    lines.append(f"- **전략**: `{cand.strategy}`  ·  **시그널 일자**: {str(cand.signal_date)[:10]}")
    lines.append("")

    # 1) 그때 가진 정보 — 펀더멘털
    lines.append("## 1. 그때 가진 정보")
    lines.append("")
    lines.append("### 1.1 펀더멘털")
    lines.append(f"- **PER**: {_fmt_num(meta.get('per'))}")
    lines.append(f"- **ROE**: {_fmt_num(meta.get('roe'))}")
    lines.append(f"- **외국인비율**: {_fmt_num(meta.get('foreign_pct'))}%")
    lines.append(f"- **시총**: {_fmt_num(cand.market_cap_bil, '{:,.0f}')} 억원")
    lines.append(f"- **20일 평균 거래량**: {_fmt_num(cand.volume_20d_avg, '{:,.0f}')} 주")
    lines.append("")

    # 1.2 전략 시그널
    lines.append("### 1.2 전략 시그널")
    lines.append(f"- **Score**: {cand.score:.1f} (전략 내부 점수)")
    if "momentum_pct" in meta:
        lines.append(f"- **모멘텀**: {_fmt_num(meta.get('momentum_pct'))}")
    if "percentile_rank" in meta:
        lines.append(f"- **percentile rank**: {_fmt_num(meta.get('percentile_rank'), '{:.3f}')}")
    if "breakout_pct" in meta:
        lines.append(f"- **돌파율**: {_fmt_num(meta.get('breakout_pct'))}")
    if "ensemble_count" in meta:
        lines.append(f"- **다중 전략 등장 수**: {meta['ensemble_count']}")
    conds = [k for k, v in (cand.conditions_met or {}).items() if v]
    if conds:
        lines.append(f"- **충족 조건**: {', '.join(conds)}")
    lines.append("")

    # 2) 적용한 프로세스
    lines.append("## 2. 적용한 프로세스")
    lines.append("")
    lines.append(f"- **최종 점수 (final_score)**: **{ranked.final_score}**")
    lines.append("")
    lines.append("### 가중치 + 기여도")
    lines.append("")
    lines.append("| 항목 | 가중치(%) | 정규화 점수 | 기여도 |")
    lines.append("|---|---:|---:|---:|")
    for prio in weight_config.priorities:
        norm = ranked.normalized_metrics.get(prio.key)
        contrib = ranked.contributions.get(prio.key)
        lines.append(
            f"| {prio.label} (`{prio.key}`) | {prio.weight} | "
            f"{_fmt_num(norm, '{:.3f}')} | {_fmt_num(contrib, '{:.2f}')} |"
        )
    lines.append("")
    if "max_regret" in ranked.normalized_metrics:
        lines.append(f"- **Minimax 최대 후회**: {ranked.normalized_metrics['max_regret']}")
        lines.append("")

    # 3) 예상 시나리오 (R:R + break-even)
    def _be_str(be: float) -> str:
        # NaN (손실 시나리오: target <= entry) → 명시 경고
        return "❌ N/A (손실 시나리오)" if be != be else f"~{be:.1f}%"

    lines.append("## 3. 예상 시나리오")
    lines.append("")
    lines.append(f"- **진입가**: {cand.entry_price:,.0f}")
    lines.append(f"- **손절가**: {cand.stop_loss:,.0f} ({-cand.risk_pct:+.2f}%)")
    lines.append(f"- **1차 목표**: {cand.target_1:,.0f} (+{cand.reward_pct_t1:.2f}%)  "
                 f"R:R 1:{rr_t1:.2f}, break-even win rate {_be_str(be_t1)}")
    lines.append(f"- **2차 목표**: {cand.target_2:,.0f} (+{cand.reward_pct_t2:.2f}%)  "
                 f"R:R 1:{rr_t2:.2f}, break-even win rate {_be_str(be_t2)}")
    lines.append("")
    lines.append(
        "> ⚠ break-even win rate 는 R:R 비율 기반 *이론값*이에요. "
        "실제 도달 확률은 변동성·시장 상황에 따라 달라요."
    )
    lines.append("")

    # 4) 사용자 후속 입력
    lines.append("## 4. 당시 감정 상태  *(사용자 직접 입력)*")
    lines.append("")
    lines.append("- [ ] 균형  [ ] 확신  [ ] 불안  [ ] 압박  [ ] 흥분  [ ] 피곤")
    lines.append("- 감정이 결정에 영향?  *(Yes/No 와 어떻게)*: ")
    lines.append("")
    lines.append("## 5. 확신 수준  *(사용자 직접 입력)*")
    lines.append("")
    lines.append("- 전체 확신: __ % / 100%")
    lines.append("- 근거:")
    lines.append("  - [ ] 정량 점수 우위")
    lines.append("  - [ ] Pre-mortem 통과 (회피 불가능 시나리오 수용)")
    lines.append("  - [ ] 검토 충분성 임계값 도달")
    lines.append("  - [ ] 시간적 거리 (10/10/10) 통과")
    lines.append("")

    # 6) 노트
    lines.append("## 6. 메모")
    lines.append("")
    if notes:
        lines.append(notes)
    else:
        lines.append("*(사용자 자유 메모)*")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "*본 메모는 hindsight bias 방어 장치예요. "
        "결과가 어떻든 이 메모를 먼저 읽고 평가해요.*"
    )
    lines.append("")
    return "\n".join(lines)


def format_ranking_report(
    ranked: list[RankedCandidate],
    target_date: str,
    top_n: int,
    weight_config: WeightConfig,
) -> str:
    """Top N 후보 ranking markdown."""
    if not ranked:
        return f"# {target_date} 의사결정 후보 — 후보 없음\n"

    top = ranked[:top_n]
    lines: list[str] = []
    lines.append(f"# {target_date} 의사결정 — Top {top_n}")
    lines.append("")
    lines.append(f"가중치 기준 final_score 내림차순. 후보 풀: {len(ranked)}개 → 상위 {len(top)}개.")
    lines.append("")

    # 가중치 요약
    lines.append("## 적용 가중치")
    lines.append("")
    lines.append("| 항목 | 가중치(%) | 방향 |")
    lines.append("|---|---:|:--|")
    for prio in weight_config.priorities:
        dir_label = "낮을수록 좋음" if prio.direction == "lower_better" else "높을수록 좋음"
        lines.append(f"| {prio.label} (`{prio.key}`) | {prio.weight} | {dir_label} |")
    if weight_config.must_have:
        lines.append("")
        lines.append(f"**필수 조건**: {', '.join(weight_config.must_have)}")
    lines.append("")

    # 후보 표
    lines.append("## 후보 ranking")
    lines.append("")
    lines.append(
        "| 순위 | 종목 | 이름 | final_score | PER | ROE | 외인% | "
        "score | 다중전략 | 진입 | 손절% | 목표2% | 네이버 |"
    )
    lines.append("|---:|:---|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:--|")
    for i, rc in enumerate(top, 1):
        c = rc.candidate
        m = c.metadata or {}
        lines.append(
            f"| {i} | {c.ticker} | {c.name} | {rc.final_score} | "
            f"{_fmt_num(m.get('per'))} | {_fmt_num(m.get('roe'))} | "
            f"{_fmt_num(m.get('foreign_pct'))} | {c.score:.0f} | "
            f"{m.get('ensemble_count', '-')} | "
            f"{c.entry_price:,.0f} | {-c.risk_pct:.2f} | {c.reward_pct_t2:.2f} | "
            f"[link]({m.get('naver_url', '')}) |"
        )
    lines.append("")

    # 기여도 breakdown
    lines.append("## 기여도 breakdown")
    lines.append("")
    lines.append("각 항목의 정규화 점수(0~1) × 가중치 = 기여도. 합산이 final_score.")
    lines.append("")
    prio_headers = " | ".join(
        f"{p.label} ({p.weight}%)" for p in weight_config.priorities
    )
    prio_sep = " | ".join("---:" for _ in weight_config.priorities)
    has_regret = any(
        "max_regret" in rc.normalized_metrics for rc in top
    )
    regret_header = " | max_regret |" if has_regret else " |"
    regret_sep = " ---: |" if has_regret else " |"
    lines.append(f"| 순위 | 종목 | final_score | {prio_headers}{regret_header}")
    lines.append(f"|---:|:---|---:| {prio_sep}{regret_sep}")
    for i, rc in enumerate(top, 1):
        c = rc.candidate
        contribs = " | ".join(
            _fmt_num(rc.contributions.get(p.key), "{:.2f}")
            for p in weight_config.priorities
        )
        regret_cell = (
            f" | {_fmt_num(rc.normalized_metrics.get('max_regret'), '{:.4f}')} |"
            if has_regret else " |"
        )
        lines.append(f"| {i} | {c.ticker} | {rc.final_score} | {contribs}{regret_cell}")
    lines.append("")

    lines.append("> 다음: `python cli.py --decide --select 005930,000660 --notes \"...\"` "
                 "로 선택 후보별 Decision Journal 생성.")
    lines.append("")
    return "\n".join(lines)
