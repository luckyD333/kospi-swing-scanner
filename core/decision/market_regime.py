"""
core/decision/market_regime.py — 시장 국면 분석 (HMM 기반).

KOSPI 시장 전체 동향을 나타내는 마켓 프록시를 구축하고,
Gaussian HMM으로 BEAR/BULL 국면을 추정하여 거래 가중치 조정.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from hmmlearn import hmm

from core.cache.ohlcv_disk import OhlcvDiskCache
from core.decision.config import Priority, WeightConfig

logger = logging.getLogger(__name__)


@dataclass
class RegimePoint:
    """단일 시점의 국면 분석."""
    date: str
    score: int              # 1~100 (P(BULL) × 100)
    log_return: float
    volatility: float
    prob_bull: float


@dataclass
class RegimeAnalysis:
    """시장 국면 분석 결과."""
    current_score: int              # 1~100
    history: list[RegimePoint]
    bull_state_mean_return: float
    bear_state_mean_return: float
    n_tickers: int
    n_days: int


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
        key=lambda x: x[1].get("market_cap_bil", 0),
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


def analyze_regime(cache_root: Path) -> RegimeAnalysis:
    """GaussianHMM(2-state)으로 BEAR/BULL 국면 추정.

    인자:
        cache_root: 캐시 루트 경로

    반환:
        RegimeAnalysis: current_score, history, bull/bear 평균 수익률 등

    예외:
        ValueError: 캐시 부족 또는 HMM 학습 실패 시
    """
    proxy = build_market_proxy(cache_root)

    if proxy.empty:
        raise ValueError("캐시 부족: HMM 학습 불가")

    # 2-state GaussianHMM 학습
    X = proxy.values  # (n_days, 2)
    try:
        model = hmm.GaussianHMM(n_components=2, covariance_type="full", n_iter=100)
        model.fit(X)
    except Exception as e:
        raise ValueError(f"HMM 수렴 실패: {e}") from e

    # BULL state 판별 (mean_return이 큰 쪽이 BULL)
    mean_returns = model.means_[:, 0]  # 각 state의 첫 번째 feature(mean_return)
    bull_state_idx = np.argmax(mean_returns)
    bear_state_idx = 1 - bull_state_idx

    # 상태별 평균 수익률
    bull_mean_return = float(model.means_[bull_state_idx, 0])
    bear_mean_return = float(model.means_[bear_state_idx, 0])

    # 각 시점의 BULL 확률
    prob_bull = model.predict_proba(X)[:, bull_state_idx]

    # score = 1~100
    scores = np.clip(np.round(prob_bull * 100), 1, 100).astype(int)

    # history 구성
    history = []
    for i, (date_idx, row) in enumerate(proxy.iterrows()):
        date_str = str(date_idx.date()) if hasattr(date_idx, "date") else str(date_idx)
        point = RegimePoint(
            date=date_str,
            score=int(scores[i]),
            log_return=float(row["mean_return"]),
            volatility=float(row["rolling_std"]),
            prob_bull=float(prob_bull[i]),
        )
        history.append(point)

    return RegimeAnalysis(
        current_score=int(scores[-1]),
        history=history,
        bull_state_mean_return=bull_mean_return,
        bear_state_mean_return=bear_mean_return,
        n_tickers=len(json.loads(
            (Path(cache_root) / "manifest.json").read_text(encoding="utf-8")
        ).get("tickers_meta", {})),  # manifest 전체 종목 수 (실제 HMM 학습에 쓰인 수의 상한)
        n_days=len(proxy),
    )


def apply_regime_overlay(
    base_config: WeightConfig,
    regime_score: int,
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
