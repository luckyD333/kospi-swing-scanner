"""
engine.py — 백테스트 엔진

여러 종목을 동시 시뮬레이션. 자금 부족 처리는 2가지 방식 제공:
  - CashAllocationConservative: confidence 순서대로 진입, 자금 부족 시 skip
  - CashAllocationAggressive: 기존 보유 포지션의 저 confidence 종목 청산 후 교체
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from .core import (
    BacktestResult,
    ExitReason,
    Position,
    Trade,
    TradeSignal,
)
from .strategy import StrategyD


@dataclass
class BacktestConfig:
    """백테스트 실행 설정"""
    initial_capital: float = 10_000_000.0      # 1천만원
    position_size_pct: float = 0.20             # 종목당 20%
    max_positions: int = 5                      # 동시 보유 최대 5개
    min_cash_pct: float = 0.10                  # 최소 현금 비율 10%
    commission_pct: float = 0.0025              # 왕복 0.25% (거래세 + 슬리피지)
    allocation_mode: str = "conservative"       # "conservative" or "aggressive"


class AllocationStrategy(ABC):
    """자금 배분 전략 추상 클래스"""

    @abstractmethod
    def should_enter(
        self,
        signal: TradeSignal,
        positions: dict[str, Position],
        cash: float,
        total_capital: float,
        config: BacktestConfig,
    ) -> tuple[bool, str | None]:
        """
        진입 여부 결정.

        Returns:
            (enter?, replace_ticker?) — replace_ticker는 교체할 기존 보유 종목
        """
        ...


class CashAllocationConservative(AllocationStrategy):
    """보수적: 자금 부족 시 skip, 기존 포지션 교체 안 함"""

    def should_enter(self, signal, positions, cash, total_capital, config):
        if len(positions) >= config.max_positions:
            return False, None
        if signal.ticker in positions:
            return False, None

        required_cash = total_capital * config.position_size_pct
        min_cash_reserve = total_capital * config.min_cash_pct

        if cash - required_cash < min_cash_reserve:
            return False, None
        return True, None


class CashAllocationAggressive(AllocationStrategy):
    """공격적: 슬롯 가득 찼을 때 기존 최저 confidence 종목 교체"""

    def __init__(self, replace_threshold: float = 0.1):
        # 신규 시그널 confidence가 기존 보유 confidence보다 X 이상 높을 때만 교체
        self.replace_threshold = replace_threshold

    def should_enter(self, signal, positions, cash, total_capital, config):
        if signal.ticker in positions:
            return False, None

        required_cash = total_capital * config.position_size_pct
        min_cash_reserve = total_capital * config.min_cash_pct

        # 슬롯 여유 있고 현금 충분하면 바로 진입
        if len(positions) < config.max_positions:
            if cash - required_cash >= min_cash_reserve:
                return True, None

        # 슬롯 부족 시 교체 로직 미구현 — conservative와 동일하게 skip
        # Position에 confidence가 없어 교체 기준 결정 불가. 향후 개선 필요.
        return False, None


# ============================================================================
# 백테스트 엔진
# ============================================================================

class BacktestEngine:
    """단일 종목 또는 여러 종목 백테스트"""

    def __init__(
        self,
        strategy: StrategyD,
        config: BacktestConfig | None = None,
    ):
        self.strategy = strategy
        self.config = config or BacktestConfig()

        if self.config.allocation_mode == "conservative":
            self.allocator: AllocationStrategy = CashAllocationConservative()
        elif self.config.allocation_mode == "aggressive":
            self.allocator = CashAllocationAggressive()
        else:
            raise ValueError(f"unknown allocation_mode: {self.config.allocation_mode}")

    def run_single(
        self,
        df: pd.DataFrame,
        ticker: str = "TEST",
    ) -> BacktestResult:
        """단일 종목 백테스트"""
        return self.run_multi({ticker: df})

    def run_multi(
        self,
        data: dict[str, pd.DataFrame],
    ) -> BacktestResult:
        """여러 종목 동시 백테스트. 시간순으로 진행."""

        # 1) 각 종목에 지표 미리 계산
        prepared: dict[str, pd.DataFrame] = {
            ticker: self.strategy.prepare(df) for ticker, df in data.items()
        }

        # 2) 전체 타임라인: 모든 종목의 index 합집합
        all_times = sorted(set().union(*[df.index for df in prepared.values()]))
        if not all_times:
            return BacktestResult(
                trades=[],
                initial_capital=self.config.initial_capital,
                final_capital=self.config.initial_capital,
                equity_curve=pd.Series(dtype=float),
            )

        # 3) 상태 초기화
        cash = self.config.initial_capital
        positions: dict[str, Position] = {}
        trades: list[Trade] = []
        equity_points: list[tuple[pd.Timestamp, float]] = []

        # 4) 각 시간대별 순회
        for t in all_times:
            # 4-1) 기존 포지션 청산 체크
            for ticker in list(positions.keys()):
                df = prepared[ticker]
                if t not in df.index:
                    continue
                idx = df.index.get_loc(t)
                if isinstance(idx, slice):
                    idx = idx.start
                bar = df.iloc[idx]
                position = positions[ticker]
                position.bars_held += 1

                reason = self.strategy.check_exit(position, bar, position.bars_held)
                if reason is not None:
                    exit_price = self.strategy.execute_exit(position, bar, reason)
                    # 거래 비용 차감
                    gross_proceeds = exit_price * position.shares
                    net_proceeds = gross_proceeds * (1 - self.config.commission_pct / 2)
                    cash += net_proceeds

                    trade = Trade(
                        ticker=ticker,
                        entry_time=position.entry_time,
                        exit_time=t,
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        shares=position.shares,
                        exit_reason=reason,
                        bars_held=position.bars_held,
                    )
                    trades.append(trade)
                    del positions[ticker]

            # 4-2) 새 진입 시그널 수집
            signals_this_bar: list[TradeSignal] = []
            for ticker, df in prepared.items():
                if t not in df.index:
                    continue
                if ticker in positions:
                    continue
                idx = df.index.get_loc(t)
                if isinstance(idx, slice):
                    idx = idx.start
                signal = self.strategy.check_entry(df, idx, ticker=ticker)
                if signal is not None:
                    signals_this_bar.append(signal)

            # 4-3) confidence 내림차순 정렬 후 진입 처리
            signals_this_bar.sort(key=lambda s: s.confidence, reverse=True)

            # 현재 총자본 계산 (현금 + 보유 포지션 시가)
            holdings_value = sum(
                pos.shares * self._current_price(prepared, tk, t, fallback=pos.entry_price)
                for tk, pos in positions.items()
            )
            total_capital = cash + holdings_value

            for signal in signals_this_bar:
                can_enter, _ = self.allocator.should_enter(
                    signal, positions, cash, total_capital, self.config
                )
                if not can_enter:
                    continue

                # 진입 실행
                position_value = total_capital * self.config.position_size_pct
                shares = int(position_value / signal.entry_price)
                if shares <= 0:
                    continue

                gross_cost = shares * signal.entry_price
                net_cost = gross_cost * (1 + self.config.commission_pct / 2)

                if cash - net_cost < total_capital * self.config.min_cash_pct:
                    continue

                cash -= net_cost
                positions[signal.ticker] = Position(
                    ticker=signal.ticker,
                    entry_time=t,
                    entry_price=signal.entry_price,
                    shares=shares,
                    stop_loss=signal.stop_loss,
                    target_1=signal.target_1,
                    target_2=signal.target_2,
                )

            # 4-4) equity curve 기록
            holdings_value = sum(
                pos.shares * self._current_price(prepared, tk, t, fallback=pos.entry_price)
                for tk, pos in positions.items()
            )
            equity_points.append((t, cash + holdings_value))

        # 5) 남은 포지션 강제 청산 (마지막 가격)
        for ticker, position in list(positions.items()):
            df = prepared[ticker]
            last_bar = df.iloc[-1]
            exit_price = float(last_bar["close"])
            gross_proceeds = exit_price * position.shares
            net_proceeds = gross_proceeds * (1 - self.config.commission_pct / 2)
            cash += net_proceeds

            trade = Trade(
                ticker=ticker,
                entry_time=position.entry_time,
                exit_time=df.index[-1],
                entry_price=position.entry_price,
                exit_price=exit_price,
                shares=position.shares,
                exit_reason=ExitReason.TIME_STOP,
                bars_held=position.bars_held,
            )
            trades.append(trade)

        # 6) 결과
        equity_series = pd.Series(
            {t: v for t, v in equity_points},
            dtype=float,
        )

        return BacktestResult(
            trades=trades,
            initial_capital=self.config.initial_capital,
            final_capital=cash,
            equity_curve=equity_series,
        )

    def _current_price(
        self,
        prepared: dict[str, pd.DataFrame],
        ticker: str,
        t: pd.Timestamp,
        fallback: float = 0.0,
    ) -> float:
        """특정 시간대의 종가 조회 (해당 시점 데이터 없으면 마지막 값)"""
        df = prepared[ticker]
        if t in df.index:
            return float(df.loc[t]["close"])
        # 이전 시점의 가장 최근 가격
        mask = df.index <= t
        if mask.any():
            return float(df.loc[mask].iloc[-1]["close"])
        return fallback
