"""strategy_two: RSI/percentile 극단치는 over-extension 가드로 차단된다."""
import numpy as np
import pandas as pd

from core.strategy_base import ScanContext
from strategies.strategy_two_cross_sectional_momentum import (
    StrategyTwoConfig,
    StrategyTwoCrossSectionalMomentum,
)


def _monotonic_uptrend_df(start: float, end: float, n: int = 60) -> pd.DataFrame:
    closes = np.linspace(start, end, n)
    return pd.DataFrame(
        {"open": closes, "high": closes * 1.01, "low": closes * 0.99,
         "close": closes, "volume": [1_000_000] * n},
        index=pd.date_range("2026-03-01", periods=n, freq="D"),
    )


def _ctx_single_ticker(df: pd.DataFrame, ticker: str = "OVERHEATED") -> ScanContext:
    return ScanContext(
        target_date="20260508",
        universe=(ticker,),
        ohlcv={ticker: df},
        names={ticker: "test"},
        market_caps={ticker: 5_000_000_000_000},
        market="KOSPI",
        ohlcv_by_tf={"1D": {ticker: df}},
        per_ticker_regime={ticker: "UPTREND_STRONG"},
    )


def test_blocks_rsi_above_threshold():
    """RSI 100 단조 상승은 rsi_max=80 가드로 차단."""
    df = _monotonic_uptrend_df(10000, 30000)
    ctx = _ctx_single_ticker(df)
    cfg = StrategyTwoConfig(rsi_max=80.0)  # percentile_max None → percentile 가드 비활성
    strat = StrategyTwoCrossSectionalMomentum(config=cfg)
    assert strat.scan(ctx, top_n=10) == []


def test_blocks_percentile_above_threshold():
    """단일 ticker (rank=1.0) 는 percentile_max=0.95 가드로 차단."""
    df = _monotonic_uptrend_df(10000, 30000)
    ctx = _ctx_single_ticker(df)
    cfg = StrategyTwoConfig(percentile_max=0.95)  # rsi_max None → RSI 가드 비활성
    strat = StrategyTwoCrossSectionalMomentum(config=cfg)
    assert strat.scan(ctx, top_n=10) == []


def test_default_cfg_keeps_legacy_behavior():
    """default cfg 는 가드 비활성 (legacy 호환). 단조 상승 후보 1 개 산출."""
    df = _monotonic_uptrend_df(10000, 30000)
    ctx = _ctx_single_ticker(df)
    strat = StrategyTwoCrossSectionalMomentum()
    candidates = strat.scan(ctx, top_n=10)
    assert len(candidates) == 1


def test_registry_strategy_two_has_overextension_guards_active():
    """운영 registry 의 strategy_two 는 가드 활성 (rsi_max=80, percentile_max=0.95)."""
    from strategies import REGISTRY
    factory = REGISTRY["strategy_two_cross_sectional_momentum"]
    strat = factory()
    assert strat.config.rsi_max == 80.0
    assert strat.config.percentile_max == 0.95
