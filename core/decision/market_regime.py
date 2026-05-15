"""
core/decision/market_regime.py — 시장 국면 분석 (HMM 기반).

KOSPI 시장 전체 동향을 나타내는 마켓 프록시를 구축하고,
Gaussian HMM으로 BEAR/BULL 국면을 추정하여 거래 가중치 조정.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn import hmm

from core.cache.ohlcv_disk import OhlcvDiskCache
from core.decision.config import Priority, WeightConfig

logger = logging.getLogger(__name__)

_HMM_SCORE_WEIGHT = 0.45
_MARKET_HEALTH_SCORE_WEIGHT = 0.55


def _market_cap_for_sort(meta: dict) -> float:
    """manifest meta 의 market_cap_bil 을 정렬 가능한 숫자로 정규화."""
    value = meta.get("market_cap_bil", 0) if isinstance(meta, dict) else 0
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


@dataclass
class RegimePoint:
    """단일 시점의 국면 분석."""
    date: str
    # 1~100 calibrated regime strength. HMM posterior 단독은 0.99대 포화가 잦아
    # market_health_score 를 함께 반영한다.
    score: float
    log_return: float
    volatility: float
    prob_bull: float
    hmm_score: float | None = None
    market_health_score: float | None = None
    trend_score: float | None = None
    impulse_score: float | None = None
    volatility_score: float | None = None


@dataclass
class RegimeAnalysis:
    """시장 국면 분석 결과."""
    current_score: float            # 1~100 calibrated regime strength
    history: list[RegimePoint]
    bull_state_mean_return: float
    bear_state_mean_return: float
    n_tickers: int
    n_days: int
    timeframe_scores: dict = field(default_factory=dict)
    # 디버그용 — UI 비노출
    model_log_likelihood: float = 0.0
    state_means: list = field(default_factory=list)
    state_covars: list = field(default_factory=list)


def build_market_proxy(cache_root: Path, max_tickers: int = 100) -> pd.DataFrame:
    """시장 전체 동향을 나타내는 마켓 프록시 DataFrame 구축.

    반환:
        (날짜 × 2-feature) DataFrame:
        - mean_return: 등가중 일별 log_return 평균
        - rolling_std: 20일 rolling std

    종목 선택:
        1. manifest.json 읽기 → tickers_meta 시가총액 내림차순
        2. 상위 max_tickers개 선택
        3. 각 ticker의 1D OHLCV 캐시 읽기 (실패 시 skip)
        4. log_return 계산 → 날짜별 평균

    종목 수 < 10 또는 날짜 수 < 30이면 빈 DataFrame 반환 (학습 불충분).
    """
    root = Path(cache_root)
    manifest_path = root / "manifest.json"

    if not manifest_path.exists():
        logger.warning(f"manifest.json 없음: {manifest_path}")
        return pd.DataFrame()

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tickers_meta = manifest.get("tickers_meta", {})
    except Exception as e:
        logger.warning(f"manifest.json 읽기 실패: {e}")
        return pd.DataFrame()

    if not tickers_meta:
        logger.warning("tickers_meta 비어있음")
        return pd.DataFrame()

    # 시가총액 내림차순 정렬 → 상위 max_tickers개
    sorted_tickers = sorted(
        tickers_meta.items(),
        key=lambda x: _market_cap_for_sort(x[1]),
        reverse=True,
    )
    selected = sorted_tickers[:max_tickers]

    # 각 ticker의 log_return 수집
    disk = OhlcvDiskCache(root)
    returns_list = []

    for ticker, meta in selected:
        try:
            df = disk.read(ticker, "1D")
            if df.empty or "close" not in df.columns:
                continue
            # log_return 계산
            log_ret = np.log(df["close"] / df["close"].shift(1)).dropna()
            if not log_ret.empty:
                returns_list.append(log_ret)
        except Exception as e:
            logger.debug(f"ticker {ticker} 읽기 실패: {e}")
            continue

    if len(returns_list) < 10:
        logger.warning(f"충분한 종목 데이터 없음: {len(returns_list)} < 10")
        return pd.DataFrame()

    # 모든 log_return을 DataFrame으로 concat → 날짜별 평균
    all_returns = pd.concat(returns_list, axis=1)
    mean_return = all_returns.mean(axis=1)

    if len(mean_return) < 30:
        logger.warning(f"충분한 날짜 데이터 없음: {len(mean_return)} < 30")
        return pd.DataFrame()

    # rolling std
    rolling_std = mean_return.rolling(20).std()

    # 두 feature를 DataFrame으로 반환 (NaN 제거)
    proxy = pd.DataFrame({
        "mean_return": mean_return,
        "rolling_std": rolling_std,
    }).dropna()

    if proxy.empty:
        return pd.DataFrame()

    return proxy


def _expanding_percentile_score(
    series: pd.Series,
    *,
    min_periods: int,
    default: float = 50.0,
) -> pd.Series:
    """각 시점 값을 그 시점까지의 과거 분포 percentile(0~100)로 변환.

    미래 데이터를 쓰지 않는 expanding 방식이라 realtime 계산과 backfill 계산이 일치한다.
    """
    out: list[float] = []
    values: list[float] = []
    for value in series:
        if pd.isna(value):
            out.append(default)
            continue
        x = float(value)
        values.append(x)
        if len(values) < min_periods:
            out.append(default)
            continue
        arr = np.asarray(values, dtype=float)
        out.append(float((arr <= x).sum()) / len(arr) * 100.0)
    return pd.Series(out, index=series.index)


def _compute_market_health_scores(proxy: pd.DataFrame) -> pd.DataFrame:
    """HMM posterior 포화를 보완하는 연속형 market health score 계산.

    구성:
      - trend_score: 20봉 누적 시장 log-return 의 expanding percentile
      - impulse_score: 5봉 누적 시장 log-return 의 expanding percentile
      - volatility_score: 현재 변동성 percentile 의 역방향 점수 (낮은 변동성 = 높은 점수)

    이 값은 시장 상태의 확률이 아니라, 현재 시장 체력의 상대 위치다.
    """
    returns = proxy["mean_return"]
    volatility = proxy["rolling_std"]

    impulse_return = returns.rolling(5, min_periods=3).sum()
    trend_return = returns.rolling(20, min_periods=10).sum()

    trend_score = _expanding_percentile_score(trend_return, min_periods=10)
    impulse_score = _expanding_percentile_score(impulse_return, min_periods=10)
    volatility_score = 100.0 - _expanding_percentile_score(
        volatility, min_periods=20,
    )

    market_health = (
        trend_score * 0.55
        + impulse_score * 0.25
        + volatility_score * 0.20
    ).clip(1.0, 100.0)

    return pd.DataFrame({
        "market_health_score": market_health.round(1),
        "trend_score": trend_score.round(1),
        "impulse_score": impulse_score.round(1),
        "volatility_score": volatility_score.round(1),
    }, index=proxy.index)


def _fit_hmm_score(proxy: pd.DataFrame) -> tuple[float, float, float, list[dict], float, list, list]:
    """GaussianHMM 학습 (multi-init best-likelihood) → calibrated score + 디버그 메타.

    NOTE:
      prob_bull 은 상태 분류 posterior 라서 강한 한쪽 상태에서는 0.99대 포화가 정상적이다.
      따라서 표시/가중치용 score 는 HMM score 와 market health score 를 혼합해 산출한다.
    """
    X = proxy.values
    best_model, best_ll = None, float("-inf")
    for seed in (42, 7, 13, 21, 99):
        m = hmm.GaussianHMM(
            n_components=2, covariance_type="diag",
            n_iter=200, random_state=seed,
        )
        # hmmlearn 이 일부 seed 에서 최종 likelihood 미세 감소를 WARNING 으로 직접 출력한다.
        # multi-init 중 더 좋은 모델을 고르는 구조라 해당 seed 경고는 운영 로그 노이즈다.
        hmm_logger = logging.getLogger("hmmlearn.base")
        prev_level = hmm_logger.level
        hmm_logger.setLevel(logging.ERROR)
        try:
            m.fit(X)
        finally:
            hmm_logger.setLevel(prev_level)
        ll = m.score(X)
        if ll > best_ll:
            best_ll, best_model = ll, m
    model = best_model
    mean_returns = model.means_[:, 0]
    bull_idx = int(np.argmax(mean_returns))
    bear_idx = 1 - bull_idx
    prob_bull = model.predict_proba(X)[:, bull_idx]
    hmm_scores = np.clip(np.round(prob_bull * 100, 1), 1.0, 100.0)
    health = _compute_market_health_scores(proxy)
    health_scores = health["market_health_score"].to_numpy(dtype=float)
    scores = np.clip(
        np.round(
            hmm_scores * _HMM_SCORE_WEIGHT
            + health_scores * _MARKET_HEALTH_SCORE_WEIGHT,
            1,
        ),
        1.0,
        100.0,
    )
    history = []
    for i, (date_idx, row) in enumerate(proxy.iterrows()):
        date_str = str(date_idx.date()) if hasattr(date_idx, "date") else str(date_idx)
        health_row = health.iloc[i]
        history.append({
            "date": date_str,
            "score": float(scores[i]),
            "log_return": float(row["mean_return"]),
            "volatility": float(row["rolling_std"]),
            "prob_bull": float(prob_bull[i]),
            "hmm_score": float(hmm_scores[i]),
            "market_health_score": float(health_row["market_health_score"]),
            "trend_score": float(health_row["trend_score"]),
            "impulse_score": float(health_row["impulse_score"]),
            "volatility_score": float(health_row["volatility_score"]),
        })
    return (
        float(scores[-1]),
        float(model.means_[bull_idx, 0]),
        float(model.means_[bear_idx, 0]),
        history,
        float(best_ll),
        model.means_.tolist(),
        [c.tolist() for c in model.covars_],
    )


def _build_proxy_1h(cache_root: Path, max_tickers: int = 30) -> pd.DataFrame:
    """1m 캐시에서 1h 리샘플링 → 마켓 프록시. 데이터 부족 시 빈 DataFrame."""
    root = Path(cache_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return pd.DataFrame()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tickers_meta = manifest.get("tickers_meta", {})
    except Exception:
        return pd.DataFrame()

    sorted_tickers = sorted(
        tickers_meta.items(),
        key=lambda x: _market_cap_for_sort(x[1]),
        reverse=True,
    )
    selected = sorted_tickers[:max_tickers]

    disk = OhlcvDiskCache(root)
    returns_list = []
    for ticker, _ in selected:
        try:
            df_1m = disk.read(ticker, "1m")
            if df_1m.empty or "close" not in df_1m.columns:
                continue
            df_1h = df_1m.resample("1h").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna(subset=["close"])
            if df_1h.empty:
                continue
            log_ret = np.log(df_1h["close"] / df_1h["close"].shift(1)).dropna()
            if not log_ret.empty:
                returns_list.append(log_ret)
        except Exception as e:
            logger.debug(f"1h proxy {ticker} 실패: {e}")
            continue

    if len(returns_list) < 10:
        logger.debug(f"1h proxy 종목 부족: {len(returns_list)} < 10")
        return pd.DataFrame()

    all_returns = pd.concat(returns_list, axis=1)
    mean_return = all_returns.mean(axis=1)

    if len(mean_return) < 30:  # ~5거래일 × 7거래시간 — HMM 최소 학습 분량
        logger.debug(f"1h proxy 봉 부족: {len(mean_return)} < 30")
        return pd.DataFrame()

    # 적응형 window: 데이터 부족 시 NaN 방지 (최소 5봉, 최대 20봉)
    _win = min(20, max(5, len(mean_return) // 3))
    rolling_std = mean_return.rolling(_win).std()
    proxy = pd.DataFrame({
        "mean_return": mean_return,
        "rolling_std": rolling_std,
    }).dropna()
    return proxy


def analyze_regime(cache_root: Path) -> RegimeAnalysis:
    """GaussianHMM(2-state)으로 BEAR/BULL 국면 추정.

    인자:
        cache_root: 캐시 루트 경로

    반환:
        RegimeAnalysis: current_score, history, bull/bear 평균 수익률 등

    예외:
        ValueError: 캐시 부족 또는 HMM 학습 실패 시
    """
    proxy_1d = build_market_proxy(cache_root)
    if proxy_1d.empty:
        raise ValueError("캐시 부족: HMM 학습 불가")

    try:
        score_1d, bull_mean, bear_mean, history_dicts, best_ll, s_means, s_covars = _fit_hmm_score(proxy_1d)
    except Exception as e:
        raise ValueError(f"HMM 수렴 실패: {e}") from e

    timeframe_scores: dict = {"1d": score_1d}
    try:
        proxy_1h = _build_proxy_1h(cache_root)
        if not proxy_1h.empty:
            score_1h, _, _, _, _, _, _ = _fit_hmm_score(proxy_1h)
            timeframe_scores["1h"] = score_1h
    except Exception as e:
        logger.debug(f"1h regime 계산 실패 (skip): {e}")

    history = [
        RegimePoint(
            date=h["date"], score=h["score"], log_return=h["log_return"],
            volatility=h["volatility"], prob_bull=h["prob_bull"],
            hmm_score=h.get("hmm_score"),
            market_health_score=h.get("market_health_score"),
            trend_score=h.get("trend_score"),
            impulse_score=h.get("impulse_score"),
            volatility_score=h.get("volatility_score"),
        )
        for h in history_dicts
    ]

    return RegimeAnalysis(
        current_score=score_1d,
        history=history,
        bull_state_mean_return=bull_mean,
        bear_state_mean_return=bear_mean,
        n_tickers=len(json.loads(
            (Path(cache_root) / "manifest.json").read_text(encoding="utf-8")
        ).get("tickers_meta", {})),
        n_days=len(proxy_1d),
        timeframe_scores=timeframe_scores,
        model_log_likelihood=best_ll,
        state_means=s_means,
        state_covars=s_covars,
    )


def apply_regime_overlay(
    base_config: WeightConfig,
    regime_score: float,
) -> WeightConfig:
    """국면 점수 기반 priority weight 조정.

    인자:
        base_config: 기본 WeightConfig
        regime_score: 1~100 (높을수록 BULL)

    반환:
        조정된 WeightConfig (원본 불변, 새 객체 반환)

    조정 규칙:
        - BULL (score >= 70): momentum_pct weight 1.3배
        - BEAR (score < 30): per/roe weight 1.2배, momentum_pct 0.7배
        - NEUTRAL (30-69): 조정 없음

    최종: 모든 weight을 합=100으로 정규화
    """
    # 기본 weight 사본
    new_weights = {p.key: p.weight for p in base_config.priorities}

    if regime_score >= 70:
        # BULL: momentum 강화
        if "momentum_pct" in new_weights:
            new_weights["momentum_pct"] *= 1.3
    elif regime_score < 30:
        # BEAR: quality(per, roe) 강화, momentum 약화
        for k in ("per", "roe"):
            if k in new_weights:
                new_weights[k] *= 1.2
        if "momentum_pct" in new_weights:
            new_weights["momentum_pct"] *= 0.7
    # NEUTRAL(30-69): 조정 없음

    # 합=100 정규화 (필수)
    total = sum(new_weights.values())
    priorities = [
        Priority(
            key=p.key,
            weight=round(new_weights[p.key] / total * 100, 4),
            direction=p.direction,
            label=p.label,
        )
        for p in base_config.priorities
    ]

    return WeightConfig(
        priorities=priorities,
        must_have=base_config.must_have,
        strategy_weights=base_config.strategy_weights,
    )


def get_regime_label(score: float) -> str:
    """score(1~100) → BULL / NEUTRAL / BEAR 라벨."""
    if score >= 70:
        return "BULL"
    if score < 30:
        return "BEAR"
    return "NEUTRAL"


def _window_avg(history: list[dict], n: int) -> dict:
    """history 마지막 n개의 평균 score → {score, regime, n_days}."""
    recent = history[-n:] if len(history) >= n else history
    avg = round(sum(float(p["score"]) for p in recent) / len(recent), 1) if recent else 50.0
    return {"score": avg, "regime": get_regime_label(avg), "n_days": len(recent)}


def save_regime_analysis(cache_root: Path) -> None:
    """HMM regime 계산 → {cache_root}/regime_analysis.json 저장."""
    analysis = analyze_regime(cache_root)
    history = [
        {
            "date": p.date,
            "score": p.score,
            "log_return": p.log_return,
            "volatility": p.volatility,
            "prob_bull": p.prob_bull,
            "hmm_score": p.hmm_score,
            "market_health_score": p.market_health_score,
            "trend_score": p.trend_score,
            "impulse_score": p.impulse_score,
            "volatility_score": p.volatility_score,
        }
        for p in analysis.history
    ]
    data = {
        "computed_at": datetime.now().isoformat(),
        "current_score": analysis.current_score,
        "current_regime": get_regime_label(analysis.current_score),
        "timeframe_scores": {
            tf: {"score": s, "regime": get_regime_label(s)}
            for tf, s in analysis.timeframe_scores.items()
        },
        "windows": {
            "3d": _window_avg(history, 3),
            "7d": _window_avg(history, 7),
            "30d": _window_avg(history, 30),
            "90d": _window_avg(history, 90),
        },
        "history": history,
        "bull_state_mean_return": analysis.bull_state_mean_return,
        "bear_state_mean_return": analysis.bear_state_mean_return,
        "n_tickers": analysis.n_tickers,
        "n_days": analysis.n_days,
    }
    regime_path = Path(cache_root) / "regime_analysis.json"
    regime_path.parent.mkdir(parents=True, exist_ok=True)
    regime_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(f"regime_analysis 저장: {regime_path} (score={analysis.current_score})")


def load_regime_analysis(cache_root: Path) -> dict | None:
    """저장된 regime_analysis.json 로드. 없거나 파싱 실패 시 None."""
    regime_path = Path(cache_root) / "regime_analysis.json"
    if not regime_path.exists():
        return None
    try:
        return json.loads(regime_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"regime_analysis.json 로드 실패: {e}")
        return None
