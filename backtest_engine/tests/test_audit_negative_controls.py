"""감사 음성 대조(negative control) 테스트 — 거짓 edge 검출.

docs/audit/trading_system_audit.md §8 참조. 쌍바닥+RSI 과매도 전략(StrategyD)이
패턴이 존재할 수 없는 가격 경로(단조 상승, 완전 평탄)에서 거래를 만들어내면
신호 정의 또는 엔진에 거짓 발화 경로가 있다는 뜻이다. 결정론적·무네트워크.
"""
from __future__ import annotations

import pandas as pd

from backtest_engine.engine import BacktestEngine
from backtest_engine.strategy import StrategyD


def _df_from_close(closes: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.001 for c in closes],
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=dates,
    )


def test_monotonic_uptrend_generates_zero_trades():
    """순수 상승 추세에는 쌍바닥·RSI 과매도가 없다 → 거래 0건이어야 함."""
    closes = [10_000 * (1.002 ** i) for i in range(200)]
    result = BacktestEngine(StrategyD()).run_single(_df_from_close(closes))

    assert len(result.trades) == 0, (
        f"단조 상승 경로에서 {len(result.trades)}건 거래 발생 — "
        "mean reversion 신호의 거짓 발화"
    )
    assert result.final_capital == result.initial_capital


def test_flat_market_generates_zero_trades():
    """무변동 가격(상승/하락 없음)에서는 어떤 신호도 없어야 함."""
    closes = [10_000.0] * 200
    result = BacktestEngine(StrategyD()).run_single(_df_from_close(closes))

    assert len(result.trades) == 0, (
        f"평탄 가격에서 {len(result.trades)}건 거래 발생 — 노이즈 거래"
    )
    assert result.final_capital == result.initial_capital
