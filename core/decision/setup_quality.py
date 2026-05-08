"""core/decision/setup_quality.py — 1h 셋업 품질 점수 계산.

추세 추종 (Trend Following) 및 평균 회귀 (Mean Reversion) 셋업의 1h 시간대 품질 평가.
점수는 메타 정보로만 사용 (entry gate/threshold 차단용), 점수 가산에는 미사용.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.decision.donchian import DonchianFrame


# 기본 임계값 (config 에서 override 가능)
SETUP_SCORE_THRESHOLD_DEFAULT = 20  # Section 3-B-4 (Task 10 완화: 40 → 20, prod 카탈로그 풀 보장)
SETUP_SCORE_STRONG = 60  # entry_gate 의 allow_strong_only 임계값과 일치


@dataclass(frozen=True)
class SetupQuality:
    """1h 셋업 품질 점수 + 근거."""

    score: int  # 0~100
    reasons: tuple[str, ...]  # ['1h_aligned_up', '1h_squeeze', ...]


def trend_setup_quality(d_1h: DonchianFrame) -> SetupQuality:
    """추세 추종 셋업 (1d UPTREND_*/RANGE_TIGHT 통과 후) 의 1h 품질 점수.

    가산 정책:
      - 1h position >= 0.6 → +30 '1h_aligned_up'
      - 1h width_percentile_60 < 0.3 (squeeze) → +25 '1h_squeeze'
      - 0 <= days_since_upper_break <= 3 (fresh) → +20 '1h_fresh_breakout'
      - days_since_upper_break > 10 (late chase) → -15 '1h_late_chase'
      - 1h slope > 0 → +15 '1h_slope_up'

    score 음수면 0 으로 clip.
    """
    score = 0
    reasons = []

    # 추세 상승 정렬
    if d_1h.position >= 0.6:
        score += 30
        reasons.append("1h_aligned_up")

    # 변동성 압축
    if d_1h.width_percentile_60 < 0.3:
        score += 25
        reasons.append("1h_squeeze")

    # 상단 돌파 신선도
    if 0 <= d_1h.days_since_upper_break <= 3:
        score += 20
        reasons.append("1h_fresh_breakout")
    elif d_1h.days_since_upper_break > 10:
        score -= 15
        reasons.append("1h_late_chase")

    # 추세 방향
    if d_1h.slope > 0:
        score += 15
        reasons.append("1h_slope_up")

    score = max(0, score)

    return SetupQuality(score=score, reasons=tuple(reasons))


def mean_rev_setup_quality(
    d_1h: DonchianFrame, slope_flat_threshold: float = 0.001
) -> SetupQuality:
    """평균 회귀 셋업 (1d RANGE/UPTREND_WEAK) 의 1h 품질 점수.

    가산 정책:
      - 1h position <= 0.20 → +35 '1h_at_lower'
      - 0.4 <= width_percentile_60 <= 0.8 (정상 변동) → +20 '1h_normal_volatility'
      - abs(1h slope) < threshold (수평) → +15 '1h_flat'

    score 음수면 0 으로 clip.
    """
    score = 0
    reasons = []

    # 하단권 위치
    if d_1h.position <= 0.20:
        score += 35
        reasons.append("1h_at_lower")

    # 정상 변동성 범위
    if 0.4 <= d_1h.width_percentile_60 <= 0.8:
        score += 20
        reasons.append("1h_normal_volatility")

    # 수평 추세 (변동성 수축)
    if abs(d_1h.slope) < slope_flat_threshold:
        score += 15
        reasons.append("1h_flat")

    score = max(0, score)

    return SetupQuality(score=score, reasons=tuple(reasons))


def passes_setup_threshold(
    quality: SetupQuality, threshold: int = SETUP_SCORE_THRESHOLD_DEFAULT
) -> bool:
    """셋업 품질이 임계값을 통과하는지 검증."""
    return quality.score >= threshold
