"""tests/test_param_sensitivity.py — 파라미터 민감도 자동화 (Phase 5).

목적:
  핵심 파라미터를 ±10/20% perturbation 후 결과가 너무 흔들리지 않는지
  자동 검증. fragile 파라미터 발견 시 회귀 알람.

판정:
  Sharpe 변동의 CV (std/|mean|) < _MAX_CV (기본 0.60) 이면 PASS.
  baseline 절대값 비교 X — 환경 변화에 robust 한 상대적 안정성 판정.

실행:
  .venv/bin/python -m pytest tests/test_param_sensitivity.py -m sensitivity -v
  # 기본 collection 에는 skip (-m sensitivity 명시 필요)

데이터:
  .cache_wf/1D/*.parquet (scripts/collect_wf_history.py 로 사전 수집).
  데이터 부재 시 자동 skip.

스코프 (Phase 5 step A):
  Strategy 1 (StrategyD) 핵심 4개 파라미터.
  S2~S5 sensitivity 는 후속 PR.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest_engine.engine import BacktestConfig, BacktestEngine
from backtest_engine.strategy import StrategyD, StrategyDConfig
from backtest_engine.walk_forward import compute_sharpe


_CACHE_WF = Path(__file__).resolve().parent.parent / ".cache_wf" / "1D"
_PERIOD_START = pd.Timestamp("2025-08-01")
_PERIOD_END = pd.Timestamp("2026-05-15")
_MAX_CV = 0.60   # ±20% perturbation 시 Sharpe CV 임계값


pytestmark = pytest.mark.sensitivity


# -----------------------------------------------------------------------------
# 데이터 로드 (모듈 단위 캐싱)
# -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wf_ohlcv() -> dict[str, pd.DataFrame]:
    """Phase 4 캐시 데이터 로드. 없으면 skip."""
    if not _CACHE_WF.exists():
        pytest.skip(
            f"WF 캐시 부재: {_CACHE_WF}. "
            "사전 수집: python scripts/collect_wf_history.py"
        )
    files = list(_CACHE_WF.glob("*.parquet"))
    if len(files) < 10:
        pytest.skip(f"WF 캐시 ticker 수 부족: {len(files)} (>= 10 필요)")
    data: dict[str, pd.DataFrame] = {}
    for f in files:
        df = pd.read_parquet(f)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        data[f.stem] = df
    return data


# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------


def _run_strategy_one(
    config: StrategyDConfig,
    ohlcv: dict[str, pd.DataFrame],
) -> tuple[float, int]:
    """단일 StrategyD config 로 백테스트 → (sharpe, n_trades)."""
    sliced = {
        ticker: df[(df.index >= _PERIOD_START) & (df.index <= _PERIOD_END)]
        for ticker, df in ohlcv.items()
    }
    sliced = {t: df for t, df in sliced.items() if len(df) >= 30}
    if not sliced:
        return float("nan"), 0
    strategy = StrategyD(config=config)
    engine = BacktestEngine(strategy=strategy, config=BacktestConfig())
    result = engine.run_multi(sliced)
    return compute_sharpe(result.equity_curve), result.total_trades


def _measure_cv(sharpes: list[float]) -> float:
    """CV = std / |mean|. mean ≈ 0 또는 모두 NaN 이면 inf."""
    arr = np.array([s for s in sharpes if not np.isnan(s)], dtype=float)
    if len(arr) < 2:
        return float("inf")
    m = float(np.abs(np.mean(arr)))
    if m < 1e-6:
        return float("inf")
    return float(np.std(arr, ddof=0) / m)


# -----------------------------------------------------------------------------
# Strategy 1 — 핵심 파라미터 sensitivity
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "param_name,base_value,delta_pcts",
    [
        ("rsi_oversold", 30.0, [-0.20, -0.10, 0.0, 0.10, 0.20]),
        ("stop_loss_pct", 0.025, [-0.20, -0.10, 0.0, 0.10, 0.20]),
        ("target_1_pct", 0.03, [-0.20, -0.10, 0.0, 0.10, 0.20]),
        ("atr_target_mult", 3.0, [-0.20, -0.10, 0.0, 0.10, 0.20]),
    ],
    ids=["rsi_oversold", "stop_loss_pct", "target_1_pct", "atr_target_mult"],
)
def test_strategy_one_param_robust(
    wf_ohlcv: dict[str, pd.DataFrame],
    param_name: str,
    base_value: float,
    delta_pcts: list[float],
):
    """±20% perturbation 시 Sharpe CV < 0.60 검증.

    fragile 한 파라미터는 단일 그리드 서치로 추출된 best 가 OOS 에서
    무력화될 가능성이 높음 → CV 임계값으로 자동 alarm.
    """
    sharpes: list[float] = []
    trades: list[int] = []
    for delta in delta_pcts:
        value = base_value * (1 + delta)
        # rsi_oversold 는 0~100 범위 유지
        if param_name == "rsi_oversold":
            value = max(5.0, min(95.0, value))
        cfg = StrategyDConfig(**{param_name: value})
        sharpe, n = _run_strategy_one(cfg, wf_ohlcv)
        sharpes.append(sharpe)
        trades.append(n)

    cv = _measure_cv(sharpes)
    msg = (
        f"{param_name} CV={cv:.3f} (base={base_value}, "
        f"sharpes={[round(s, 3) if not np.isnan(s) else None for s in sharpes]}, "
        f"trades={trades})"
    )
    # 진단 정보를 항상 노출 (verbose 모드 가독성)
    print(f"\n[sensitivity] {msg}")
    assert cv < _MAX_CV, f"FRAGILE: {msg}"
