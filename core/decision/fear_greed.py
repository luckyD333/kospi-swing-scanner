"""Fear & Greed Index 컴포지트.

3 components (Momentum + Breadth + Volatility) 동일가중 평균으로 0-100 단일 score
를 산출한다. 각 component 는 90 일 시계열의 percentile rank 로 정규화 (Volatility 는
역방향: 변동성 상승 = fear). 단계 라벨 (Extreme Fear / Fear / Neutral / Greed /
Extreme Greed) 은 CNN F&G 와 동일한 구간을 사용.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_MIN_CONSTITUENTS = 10


def percentile_rank(history: Iterable[float], target: float | None) -> float:
    """target 이 history 분포에서 차지하는 백분위 (0-100, ≤ 비율).

    history 가 비어있거나 target 이 None/NaN 이면 50 (중립).
    """
    if target is None or (isinstance(target, float) and np.isnan(target)):
        return 50.0
    arr = np.asarray(
        [v for v in history if v is not None and not (isinstance(v, float) and np.isnan(v))],
        dtype=float,
    )
    if arr.size == 0:
        return 50.0
    rank = float((arr <= target).sum()) / arr.size * 100.0
    return min(100.0, max(0.0, rank))


def score_to_label(score: float) -> str:
    """0-100 score → 5단계 라벨.

    경계: 0–24 Extreme Fear / 25–44 Fear / 45–55 Neutral / 56–74 Greed / 75–100 Extreme Greed.
    """
    if score < 25:
        return "Extreme Fear"
    if score < 45:
        return "Fear"
    if score <= 55:
        return "Neutral"
    if score < 75:
        return "Greed"
    return "Extreme Greed"


@dataclass
class FearGreedSnapshot:
    """단일 시점 fear/greed 결과."""

    score: float
    label: str
    components: dict[str, float]
    history: list[dict[str, float | str]]


def _last_and_history(s: pd.Series, lookback: int) -> tuple[float, np.ndarray]:
    """series 의 마지막 값과 그 직전 lookback 일 history 분리."""
    if len(s) == 0:
        return float("nan"), np.empty(0)
    target = float(s.iloc[-1])
    start = max(0, len(s) - lookback - 1)
    history = s.iloc[start:-1].to_numpy(dtype=float)
    return target, history


def compute_components(
    momentum_series: pd.Series,
    breadth_series: pd.Series,
    volatility_series: pd.Series,
    *,
    lookback: int = 90,
) -> dict[str, float]:
    """각 series 의 last 값을 90 일 percentile rank 로 변환한 component score.

    - momentum_series: HMM regime score (0-100)
    - breadth_series: (up_ratio + above_ma20_ratio) / 2 (0-1 또는 0-100)
    - volatility_series: 시장 실현변동성

    Volatility 는 invert (`100 − rank`) — 변동성↑ = fear.
    """
    mom_t, mom_hist = _last_and_history(momentum_series, lookback)
    brd_t, brd_hist = _last_and_history(breadth_series, lookback)
    vol_t, vol_hist = _last_and_history(volatility_series, lookback)

    momentum = percentile_rank(mom_hist, mom_t)
    breadth = percentile_rank(brd_hist, brd_t)
    volatility = 100.0 - percentile_rank(vol_hist, vol_t)

    return {
        "momentum": round(momentum, 1),
        "breadth": round(breadth, 1),
        "volatility": round(volatility, 1),
    }


def composite(components: dict[str, float]) -> float:
    """3 component 동일가중 평균 (33.3 % × 3)."""
    return float(np.mean([components["momentum"], components["breadth"], components["volatility"]]))


def compute_with_history(
    momentum_series: pd.Series,
    breadth_series: pd.Series,
    volatility_series: pd.Series,
    *,
    lookback: int = 90,
    history_window: int = 30,
) -> FearGreedSnapshot:
    """현재 score + 직전 history_window 일 sparkline.

    각 시점의 score 는 그 시점까지의 시계열 슬라이스로 동일 알고리즘 재계산
    (backfill = realtime 알고리즘).
    """
    common = momentum_series.index
    common = common.intersection(breadth_series.index)
    common = common.intersection(volatility_series.index)
    common = common.sort_values()

    if len(common) == 0:
        return FearGreedSnapshot(
            score=50.0,
            label="Neutral",
            components={"momentum": 50.0, "breadth": 50.0, "volatility": 50.0},
            history=[],
        )

    target_dates = common[-history_window:]
    history: list[dict[str, float | str]] = []
    last_components: dict[str, float] = {}

    for d in target_dates:
        comps = compute_components(
            momentum_series.loc[:d],
            breadth_series.loc[:d],
            volatility_series.loc[:d],
            lookback=lookback,
        )
        score_d = composite(comps)
        history.append({"date": pd.Timestamp(d).strftime("%Y-%m-%d"), "score": round(score_d, 1)})
        last_components = comps

    current_score = float(history[-1]["score"])
    return FearGreedSnapshot(
        score=current_score,
        label=score_to_label(current_score),
        components=last_components,
        history=history,
    )


def _normalize_dates(idx: pd.Index) -> pd.DatetimeIndex:
    """timezone-aware/naive 무관 일자 단위 DatetimeIndex 로 정규화 (intersection 안전)."""
    dt = pd.to_datetime(idx)
    if getattr(dt, "tz", None) is not None:
        dt = dt.tz_localize(None)
    return dt.normalize()


def _load_momentum_history(cache_root: Path) -> pd.Series:
    """regime_analysis.json 의 history 에서 momentum (regime score) 시계열."""
    path = cache_root / "regime_analysis.json"
    if not path.exists():
        return pd.Series(dtype=float)
    try:
        data = json.loads(path.read_text())
        history = data.get("history") or []
        if not history:
            return pd.Series(dtype=float)
        dates = _normalize_dates(pd.Index([h["date"] for h in history]))
        scores = [float(h["score"]) for h in history]
        return pd.Series(scores, index=dates).sort_index()
    except Exception as e:
        logger.warning(f"momentum history 로드 실패: {e}")
        return pd.Series(dtype=float)


def _load_universe_closes(
    cache_root: Path, tickers: list[str], top_n: int = 200
) -> pd.DataFrame:
    """universe top-N ticker 의 1D close 시계열을 로드한다."""
    closes: dict[str, pd.Series] = {}
    for ticker in tickers[:top_n]:
        path = cache_root / "1D" / f"{ticker}.parquet"
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
            if df.empty or "close" not in df.columns:
                continue
            s = df["close"].copy()
            s.index = _normalize_dates(s.index)
            closes[ticker] = s
        except Exception:
            continue

    if not closes:
        return pd.DataFrame()

    return pd.DataFrame(closes).sort_index()


def _compute_breadth_from_closes(close_df: pd.DataFrame) -> pd.Series:
    """1D close 로 daily breadth 시계열을 계산한다."""
    if close_df.empty:
        return pd.Series(dtype=float)

    returns = close_df.pct_change(fill_method=None)
    up_ratio = returns.gt(0).where(returns.notna()).mean(axis=1)
    ma20 = close_df.rolling(window=20, min_periods=20).mean()
    valid_ma20 = close_df.notna() & ma20.notna()
    above_ma20 = close_df.gt(ma20).where(valid_ma20).mean(axis=1)
    coverage_ok = (
        returns.notna().mean(axis=1).ge(0.80)
        & valid_ma20.mean(axis=1).ge(0.80)
    )
    return ((up_ratio + above_ma20) / 2.0).loc[coverage_ok].dropna()


def build_fear_greed_payload(
    cache_root: Path,
    tickers: list[str],
    *,
    volatility_series: pd.Series,
    lookback: int = 90,
    history_window: int = 30,
) -> dict | None:
    """주식 universe와 공유 시장 변동성으로 F&G snapshot을 생성한다.

    regime_analysis.json, 1D close, volatility_series 중 하나라도 부족하거나
    세 시계열의 공통 이력이 lookback+1 미만이면 None을 반환한다.
    """
    cache_root = Path(cache_root)
    momentum = _load_momentum_history(cache_root)
    close_df = _load_universe_closes(cache_root, tickers)
    if close_df.shape[1] < _MIN_CONSTITUENTS:
        logger.info(
            f"[fear_greed] 구성 종목 부족: {close_df.shape[1]} < {_MIN_CONSTITUENTS}"
        )
        return None
    breadth = _compute_breadth_from_closes(close_df)
    volatility = volatility_series

    if momentum.empty or breadth.empty or volatility.empty:
        logger.info(
            f"[fear_greed] 입력 부족: momentum={len(momentum)} "
            f"breadth={len(breadth)} volatility={len(volatility)}"
        )
        return None

    common = momentum.dropna().index.intersection(breadth.dropna().index)
    common = common.intersection(volatility.dropna().index)
    if len(common) < lookback + 1:
        logger.info(
            f"[fear_greed] 공통 이력 부족: {len(common)} < {lookback + 1}"
        )
        return None

    snap = compute_with_history(
        momentum, breadth, volatility,
        lookback=lookback, history_window=history_window,
    )
    return {
        "score": snap.score,
        "label": snap.label,
        "components": snap.components,
        "history": snap.history,
        "status": "informational",
    }
