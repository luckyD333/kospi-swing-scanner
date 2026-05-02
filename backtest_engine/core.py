"""
core.py — 타입 정의 및 기본 지표 계산

타임프레임에 무관한 인터페이스. 입력은 항상 OHLCV DataFrame (index=datetime).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

# ============================================================================
# 타입 정의
# ============================================================================

class SignalType(Enum):
    LONG_ENTRY = "long_entry"
    LONG_EXIT = "long_exit"


class ExitReason(Enum):
    TARGET_1 = "target_1"       # 1차 목표 (+3%)
    TARGET_2 = "target_2"       # 2차 목표 (+5%)
    STOP_LOSS = "stop_loss"     # 고정 손절 (-2.5%)
    GAP_DOWN = "gap_down"       # 갭다운 손절 (시초가 -3%)
    TIME_STOP = "time_stop"     # 시간 손절 (N봉 경과)


@dataclass
class TradeSignal:
    """매수 시그널"""
    timestamp: pd.Timestamp
    ticker: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    confidence: float
    conditions_met: dict[str, bool] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    atr_at_entry: float | None = None

    def __post_init__(self):
        assert 0 <= self.confidence <= 1.0, f"confidence out of range: {self.confidence}"
        assert self.stop_loss < self.entry_price, "stop_loss must be below entry"
        assert self.target_1 > self.entry_price, "target_1 must be above entry"


@dataclass
class Position:
    """보유 포지션"""
    ticker: str
    entry_time: pd.Timestamp
    entry_price: float
    shares: int
    stop_loss: float
    target_1: float
    target_2: float
    bars_held: int = 0
    atr_at_entry: float | None = None

    @property
    def cost(self) -> float:
        return self.entry_price * self.shares


@dataclass
class Trade:
    """완료된 거래 (청산까지)"""
    ticker: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    shares: int
    exit_reason: ExitReason
    bars_held: int

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def pnl_pct(self) -> float:
        return (self.exit_price / self.entry_price - 1.0) * 100

    @property
    def is_win(self) -> bool:
        return self.pnl > 0


@dataclass
class BacktestResult:
    """백테스트 결과 요약"""
    trades: list[Trade]
    initial_capital: float
    final_capital: float
    equity_curve: pd.Series

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.is_win)
        return wins / len(self.trades)

    @property
    def total_return_pct(self) -> float:
        return (self.final_capital / self.initial_capital - 1.0) * 100

    @property
    def avg_pnl_pct(self) -> float:
        if not self.trades:
            return 0.0
        return float(np.mean([t.pnl_pct for t in self.trades]))

    @property
    def avg_bars_held(self) -> float:
        if not self.trades:
            return 0.0
        return float(np.mean([t.bars_held for t in self.trades]))

    @property
    def max_drawdown_pct(self) -> float:
        if len(self.equity_curve) == 0:
            return 0.0
        running_max = self.equity_curve.cummax()
        dd = (self.equity_curve - running_max) / running_max
        return float(dd.min() * 100)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def summary(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate * 100, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "avg_pnl_pct": round(self.avg_pnl_pct, 2),
            "avg_bars_held": round(self.avg_bars_held, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "profit_factor": round(self.profit_factor, 2),
            "final_capital": round(self.final_capital, 0),
        }


# ============================================================================
# 지표 계산
# ============================================================================

def calc_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Wilder's smoothing).

    >>> import pandas as pd
    >>> p = pd.Series([44, 44.25, 44.5, 43.75, 44.5, 45.25, 46, 45.25, 46, 47])
    >>> r = calc_rsi(p, period=5)
    >>> bool(r.iloc[-1] > 50)
    True
    """
    if len(prices) < period + 1:
        return pd.Series([np.nan] * len(prices), index=prices.index)

    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Wilder's smoothing (EMA with alpha = 1/period)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # loss가 0이면 완전 상승 → RSI=100
    rsi = rsi.where(avg_loss != 0, 100)
    # gain이 0이면 완전 하락 → RSI=0
    rsi = rsi.where(avg_gain != 0, 0)
    return rsi


def calc_bollinger(prices: pd.Series, period: int = 20, std_dev: float = 2.0):
    """
    Bollinger Bands.

    Returns:
        (middle, upper, lower) 각 pd.Series
    """
    middle = prices.rolling(window=period, min_periods=period).mean()
    std = prices.rolling(window=period, min_periods=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return middle, upper, lower


def calc_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
):
    """
    MACD (Moving Average Convergence Divergence).

    Returns:
        (macd_line, signal_line, histogram) 각 pd.Series
    """
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range"""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
