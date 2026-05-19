"""backtest_engine/walk_forward.py — Walk-Forward Optimization framework.

basin/라플라스의악마 비판에 대응:
  - 인접 윈도우 간 파라미터 안정성 측정 (param_stability_score)
  - OOS 성과 저하 정량화 (oos_sharpe_decay)
  - 윈도우 길이 자체에 대한 robustness 추후 검증 가능 (train/test 변경 후 재실행)

설계 원칙:
  - Strategy-agnostic: evaluator callable 추상화로 모든 전략 지원
  - 합성 데이터·실제 백테스트 둘 다 지원
  - Phase 4 (2026-05-14 변경 12개 검증) 의 인프라

판정 기준 (둘 다 충족 시 PASS):
  - param_stability_score < 0.30  (각 파라미터의 CV ≤ 30%)
  - oos_metric_decay < 0.40       (OOS 성과 저하 ≤ 40%)
"""
from __future__ import annotations

import itertools
import logging
import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---- Type aliases ------------------------------------------------------------

# evaluator(ohlcv, params, start, end) -> (metric, n_trades)
Evaluator = Callable[
    [dict[str, pd.DataFrame], dict[str, Any], pd.Timestamp, pd.Timestamp],
    tuple[float, int],
]


# ---- Configuration & data structures -----------------------------------------


@dataclass(frozen=True)
class WalkForwardConfig:
    """Walk-forward 윈도우 설정.

    윈도우 시퀀스 예 (train=90, test=30, step=30, 2024-01-01 ~ 2024-12-31):
      W1: train[01-01 ~ 03-30] → test[03-31 ~ 04-29]
      W2: train[01-31 ~ 04-29] → test[04-30 ~ 05-29]
      ...
    """

    train_days: int = 90
    test_days: int = 30
    step_days: int = 30
    start_date: str = "2024-01-01"   # inclusive
    end_date: str = "2025-12-31"     # inclusive
    metric_name: str = "sharpe"      # 정보 표기용 (evaluator 가 실제 계산)
    min_trades_for_metric: int = 5   # train 거래 < 임계값이면 해당 파라미터 셋 무시


@dataclass
class WFWindow:
    """단일 walk-forward 윈도우 결과."""

    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    best_params: dict[str, Any]
    train_metric: float
    test_metric: float
    train_trades: int
    test_trades: int


_STABILITY_THRESHOLD = 0.30   # CV (std/|mean|) 임계값
_DECAY_THRESHOLD = 0.40       # OOS metric 저하 비율 임계값


@dataclass
class WFReport:
    """모든 윈도우 수집 후 통계 + 판정."""

    strategy_name: str
    param_grid: dict[str, list[Any]]
    windows: list[WFWindow] = field(default_factory=list)
    config: WalkForwardConfig | None = None

    # ---- 핵심 안정성 지표 -------------------------------------------------

    @property
    def param_stability_score(self) -> dict[str, float]:
        """각 파라미터의 CV (=std/|mean|).

        모든 윈도우에서 동일 best_params → CV=0 (완벽 안정).
        windows 가 비어있으면 빈 dict 반환.
        숫자형이 아닌 파라미터(불리언/문자열) 는 std/mean 계산 불가 → 변동 여부만 0/1 로 표기.
        """
        if not self.windows:
            return {}

        scores: dict[str, float] = {}
        for key in self.param_grid.keys():
            values = [w.best_params.get(key) for w in self.windows if key in w.best_params]
            if not values:
                continue
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
                arr = np.array(values, dtype=float)
                mean_abs = float(np.abs(np.mean(arr)))
                std = float(np.std(arr, ddof=0))
                scores[key] = std / mean_abs if mean_abs > 1e-12 else 0.0
            else:
                # 비숫자형: 분기 횟수 / 윈도우 수
                unique_count = len(set(map(repr, values)))
                scores[key] = 0.0 if unique_count == 1 else (unique_count - 1) / max(len(values) - 1, 1)
        return scores

    @property
    def oos_metric_decay(self) -> float:
        """(mean_train - mean_test) / |mean_train|.

        train/test mean 둘 다 결측이거나 train mean이 0 근방이면 NaN.
        값이 음수면 OOS가 train 보다 좋다는 의미 (드물지만 가능).
        """
        if not self.windows:
            return float("nan")
        train_vals = np.array([w.train_metric for w in self.windows], dtype=float)
        test_vals = np.array([w.test_metric for w in self.windows], dtype=float)
        # NaN 제거
        mask = ~(np.isnan(train_vals) | np.isnan(test_vals))
        if mask.sum() == 0:
            return float("nan")
        train_mean = float(np.mean(train_vals[mask]))
        test_mean = float(np.mean(test_vals[mask]))
        if abs(train_mean) < 1e-12:
            return float("nan")
        return (train_mean - test_mean) / abs(train_mean)

    @property
    def passed_stability(self) -> bool:
        """모든 파라미터의 CV < 0.30 이면 True."""
        scores = self.param_stability_score
        if not scores:
            return False
        return all(cv < _STABILITY_THRESHOLD for cv in scores.values())

    @property
    def passed_decay(self) -> bool:
        """OOS decay < 0.40 이면 True. NaN이면 False (판정 불가는 실패)."""
        decay = self.oos_metric_decay
        return not math.isnan(decay) and decay < _DECAY_THRESHOLD

    @property
    def verdict(self) -> str:
        """단순 종합 판정 라벨."""
        if self.passed_stability and self.passed_decay:
            return "PASS"
        if not self.passed_stability and not self.passed_decay:
            return "FAIL (unstable + decayed)"
        if not self.passed_stability:
            return "FAIL (unstable params)"
        return "FAIL (OOS decay)"

    def summary(self) -> dict[str, Any]:
        """리포트 직렬화용 dict."""
        return {
            "strategy_name": self.strategy_name,
            "n_windows": len(self.windows),
            "param_stability_score": self.param_stability_score,
            "oos_metric_decay": self.oos_metric_decay,
            "passed_stability": self.passed_stability,
            "passed_decay": self.passed_decay,
            "verdict": self.verdict,
        }


# ---- Helpers -----------------------------------------------------------------


def _generate_windows(config: WalkForwardConfig) -> Iterator[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """롤링 윈도우 시퀀스 생성. 마지막 test 가 end_date 를 넘으면 중단."""
    start = pd.Timestamp(config.start_date)
    end = pd.Timestamp(config.end_date)
    cursor = start
    while True:
        train_start = cursor
        train_end = train_start + pd.Timedelta(days=config.train_days - 1)
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.Timedelta(days=config.test_days - 1)
        if test_end > end:
            break
        yield train_start, train_end, test_start, test_end
        cursor = cursor + pd.Timedelta(days=config.step_days)


def _iter_param_combinations(param_grid: dict[str, list[Any]]) -> Iterator[dict[str, Any]]:
    """그리드 서치용 파라미터 조합 itertools.product."""
    if not param_grid:
        yield {}
        return
    keys = list(param_grid.keys())
    for values in itertools.product(*(param_grid[k] for k in keys)):
        yield dict(zip(keys, values))


def compute_sharpe(equity_curve: pd.Series, periods_per_year: int = 252) -> float:
    """일별 equity_curve → 연환산 Sharpe ratio.

    equity_curve 가 비어있거나 변동성이 0이면 NaN.
    무위험금리는 0 가정 (long-only swing 단기 회전).
    """
    if len(equity_curve) < 2:
        return float("nan")
    returns = equity_curve.pct_change().dropna()
    if len(returns) == 0 or returns.std() < 1e-12:
        return float("nan")
    return float(math.sqrt(periods_per_year) * returns.mean() / returns.std())


# ---- Main entry point --------------------------------------------------------


def run_walk_forward(
    strategy_name: str,
    evaluator: Evaluator,
    param_grid: dict[str, list[Any]],
    ohlcv_data: dict[str, pd.DataFrame],
    config: WalkForwardConfig,
) -> WFReport:
    """롤링 train/test 윈도우 그리드 서치 → WFReport.

    각 윈도우에서:
      1. train 구간에 대해 모든 param 조합 evaluate
      2. min_trades_for_metric 미달 조합 제외
      3. 최고 train_metric 의 best_params 선정
      4. 해당 params 로 test 구간 evaluate (OOS)
      5. WFWindow 기록

    Args:
        strategy_name: 보고서 표기용 (예: "strategy_one_d_v2")
        evaluator: (ohlcv, params, start, end) → (metric, n_trades)
        param_grid: {param_name: [value1, value2, ...]}
        ohlcv_data: {ticker: DataFrame with DatetimeIndex}
        config: WalkForwardConfig

    Returns:
        WFReport (windows 비어있으면 모든 윈도우 skip 됨을 의미)
    """
    windows: list[WFWindow] = []
    combinations = list(_iter_param_combinations(param_grid))
    if not combinations:
        logger.warning("param_grid 가 비어있어 빈 조합으로 실행")
        combinations = [{}]

    for train_start, train_end, test_start, test_end in _generate_windows(config):
        best_params: dict[str, Any] | None = None
        best_metric = float("-inf")
        best_trades = 0

        for params in combinations:
            try:
                metric, n_trades = evaluator(ohlcv_data, params, train_start, train_end)
            except Exception as exc:  # noqa: BLE001
                logger.warning("evaluator 실패 (train, params=%s): %s", params, exc)
                continue
            if n_trades < config.min_trades_for_metric:
                continue
            if math.isnan(metric):
                continue
            if metric > best_metric:
                best_metric = metric
                best_params = params
                best_trades = n_trades

        if best_params is None:
            logger.info(
                "윈도우 skip (유효 파라미터 없음): train [%s ~ %s]",
                train_start.date(),
                train_end.date(),
            )
            continue

        try:
            test_metric, test_trades = evaluator(ohlcv_data, best_params, test_start, test_end)
        except Exception as exc:  # noqa: BLE001
            logger.warning("evaluator 실패 (test, params=%s): %s", best_params, exc)
            test_metric = float("nan")
            test_trades = 0

        windows.append(
            WFWindow(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                best_params=best_params,
                train_metric=best_metric,
                test_metric=test_metric,
                train_trades=best_trades,
                test_trades=test_trades,
            )
        )

    return WFReport(
        strategy_name=strategy_name,
        param_grid=param_grid,
        windows=windows,
        config=config,
    )
