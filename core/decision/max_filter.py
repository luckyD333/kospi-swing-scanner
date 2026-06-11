"""MAX effect 가드 — 최근 1~3일 누적 급등·극단 일간 수익률 후보 차단.

근거: 한국 시장 MAX effect (최근 극단 일간수익률 종목의 단기 반전,
개인투자자 복권 수요 주도). 기존 S3 전일 +30% 가드(PR-E)의 누적 버전.
docs/audit/trading_system_audit.md 후속 논의 참조.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MaxFilterConfig:
    surge_3d_exclude_pct: float = 25.0   # 3일 누적 ≥ → EXCLUDE
    surge_3d_penalty_pct: float = 18.0   # 3일 누적 ≥ → score ×penalty_mult
    max_daily_5d_pct: float = 20.0       # 5일 내 일간 max ≥ → EXCLUDE
    penalty_mult: float = 0.5


@dataclass(frozen=True)
class SurgeVerdict:
    action: str            # "PASS" | "PENALTY" | "EXCLUDE" | "SKIPPED"
    score_mult: float      # PENALTY 시 penalty_mult, 그 외 1.0
    surge_3d_pct: float | None
    max_daily_5d_pct: float | None


def evaluate_surge(df: pd.DataFrame | None, cfg: MaxFilterConfig) -> SurgeVerdict:
    """1D OHLCV 마지막 봉 기준 급등 판정. 봉 4개 미만이면 SKIPPED."""
    if df is None or len(df) < 4 or "close" not in df.columns:
        return SurgeVerdict("SKIPPED", 1.0, None, None)

    close = df["close"].astype(float)
    surge_3d = (close.iloc[-1] / close.iloc[-4] - 1.0) * 100.0
    daily = close.pct_change().iloc[-5:] * 100.0
    max_daily = float(daily.max()) if not daily.dropna().empty else 0.0

    if surge_3d >= cfg.surge_3d_exclude_pct or max_daily >= cfg.max_daily_5d_pct:
        return SurgeVerdict("EXCLUDE", 1.0, float(surge_3d), max_daily)
    if surge_3d >= cfg.surge_3d_penalty_pct:
        return SurgeVerdict("PENALTY", cfg.penalty_mult, float(surge_3d), max_daily)
    return SurgeVerdict("PASS", 1.0, float(surge_3d), max_daily)
