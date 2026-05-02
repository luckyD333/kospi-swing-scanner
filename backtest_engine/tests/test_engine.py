"""engine.py 테스트: 시나리오 기반 end-to-end 백테스트"""
import pandas as pd

from backtest_engine.core import ExitReason
from backtest_engine.engine import (
    BacktestConfig,
    BacktestEngine,
    CashAllocationConservative,
)
from backtest_engine.strategy import StrategyD, StrategyDConfig


class TestEngineSingleScenario:
    """단일 시나리오에서 엔진 동작 검증"""

    def _make_engine(self):
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        config = BacktestConfig(
            initial_capital=10_000_000.0,
            position_size_pct=0.20,
            max_positions=5,
            commission_pct=0.0025,
        )
        return BacktestEngine(strategy, config)

    def test_perfect_scenario_produces_winning_trade(
        self, perfect_double_bottom_scenario
    ):
        """완벽 시나리오: 진입 후 익절 도달"""
        engine = self._make_engine()
        result = engine.run_single(perfect_double_bottom_scenario.df, ticker="PERFECT")

        assert result.total_trades == 1, f"거래 수 1개여야 함, 실제: {result.total_trades}"
        trade = result.trades[0]
        assert trade.is_win, f"win 기대, 실제 pnl_pct={trade.pnl_pct:.2f}%"
        assert trade.exit_reason in (ExitReason.TARGET_1, ExitReason.TARGET_2)

    def test_fake_double_bottom_triggers_stop_loss(
        self, fake_double_bottom_scenario
    ):
        """가짜 쌍바닥: 손절 청산"""
        engine = self._make_engine()
        result = engine.run_single(fake_double_bottom_scenario.df, ticker="FAKE")

        assert result.total_trades == 1
        trade = result.trades[0]
        assert not trade.is_win
        assert trade.exit_reason in (ExitReason.STOP_LOSS, ExitReason.GAP_DOWN)
        # 손실폭이 대략 손절 수준(-2.5%) 근처여야 함
        assert trade.pnl_pct <= -2.0

    def test_gap_down_triggers_gap_exit(self, gap_down_scenario):
        """갭다운 시나리오: GAP_DOWN 청산 규칙 작동"""
        engine = self._make_engine()
        result = engine.run_single(gap_down_scenario.df, ticker="GAP")

        assert result.total_trades == 1
        trade = result.trades[0]
        assert not trade.is_win
        assert trade.exit_reason == ExitReason.GAP_DOWN
        # 갭다운은 ~-4% 수준
        assert trade.pnl_pct <= -3.0

    def test_time_stop_triggers_after_3_bars(self, time_stop_scenario):
        """횡보 시나리오: 3봉 경과 시간 손절"""
        engine = self._make_engine()
        result = engine.run_single(time_stop_scenario.df, ticker="TIME")

        assert result.total_trades == 1
        trade = result.trades[0]
        assert trade.exit_reason == ExitReason.TIME_STOP
        assert trade.bars_held <= 4  # 3봉 또는 강제청산

    def test_uptrend_produces_no_trades(self, uptrend_scenario):
        """상승 추세: 진입 시그널 없으므로 거래 0"""
        engine = self._make_engine()
        result = engine.run_single(uptrend_scenario.df, ticker="UP")
        assert result.total_trades == 0

    def test_choppy_produces_no_trades(self, choppy_scenario):
        """횡보 장: 진입 거의 없음"""
        engine = self._make_engine()
        result = engine.run_single(choppy_scenario.df, ticker="CHOP")
        assert result.total_trades <= 1


class TestEngineMultiTicker:
    """여러 종목 동시 백테스트"""

    def test_max_positions_respected(
        self,
        perfect_double_bottom_scenario,
    ):
        """max_positions=2 설정 시 동시 보유 2개 초과 안 함"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        config = BacktestConfig(
            initial_capital=10_000_000.0,
            position_size_pct=0.30,
            max_positions=2,
        )
        engine = BacktestEngine(strategy, config)

        # 같은 시나리오를 여러 "종목"으로 복제
        data = {
            f"STOCK_{i}": perfect_double_bottom_scenario.df.copy()
            for i in range(5)
        }
        result = engine.run_multi(data)

        # 최대 2개까지만 진입 → 거래 수 ≤ 2
        assert result.total_trades <= 2, (
            f"max_positions=2 위반. 거래 {result.total_trades}건"
        )

    def test_capital_preservation_on_losses(self, fake_double_bottom_scenario):
        """연속 손실 시나리오에서 자본 보존 (손절 규칙 작동)"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        config = BacktestConfig(
            initial_capital=10_000_000.0,
            position_size_pct=0.20,
            max_positions=3,
        )
        engine = BacktestEngine(strategy, config)

        data = {
            f"LOSER_{i}": fake_double_bottom_scenario.df.copy()
            for i in range(3)
        }
        result = engine.run_multi(data)

        # 3종목 × 20% × -2.5%(손절) = 총 -1.5% 정도
        # 손실이 있더라도 총 자본의 10% 이상 유지되어야 함 (손절이 작동한다면)
        assert result.final_capital >= result.initial_capital * 0.90, (
            f"자본 손실 과다: {result.summary()}"
        )


class TestAllocationStrategies:
    """자금 배분 전략 비교"""

    def test_conservative_skips_when_slots_full(self):
        alloc = CashAllocationConservative()
        config = BacktestConfig(max_positions=2)
        # 기존 포지션 2개 (가득 참)
        positions = {"A": None, "B": None}  # Position 객체 내용은 테스트에 불필요
        signal = None  # not used here

        from backtest_engine.core import Position, TradeSignal
        dummy_pos = Position(
            ticker="A",
            entry_time=pd.Timestamp("2026-01-01"),
            entry_price=10000.0,
            shares=10,
            stop_loss=9750.0,
            target_1=10300.0,
            target_2=10500.0,
        )
        positions = {"A": dummy_pos, "B": dummy_pos}
        signal = TradeSignal(
            timestamp=pd.Timestamp("2026-01-02"),
            ticker="C",
            entry_price=10000.0,
            stop_loss=9750.0,
            target_1=10300.0,
            target_2=10500.0,
            confidence=0.85,
        )

        can_enter, _ = alloc.should_enter(
            signal, positions, cash=10_000_000, total_capital=10_000_000, config=config
        )
        assert can_enter is False

    def test_conservative_enters_when_slots_available(self):
        alloc = CashAllocationConservative()
        config = BacktestConfig(max_positions=5, position_size_pct=0.20, min_cash_pct=0.10)

        from backtest_engine.core import TradeSignal
        signal = TradeSignal(
            timestamp=pd.Timestamp("2026-01-02"),
            ticker="NEW",
            entry_price=10000.0,
            stop_loss=9750.0,
            target_1=10300.0,
            target_2=10500.0,
            confidence=0.85,
        )
        can_enter, _ = alloc.should_enter(
            signal, positions={}, cash=10_000_000, total_capital=10_000_000, config=config
        )
        assert can_enter is True


class TestEdgeCases:
    """경계값 및 에지 케이스"""

    def test_zero_shares_skipped(self, perfect_double_bottom_scenario):
        """position_size가 너무 작아 0주가 되면 진입 skip → 거래 0건"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        config = BacktestConfig(
            initial_capital=1.0,         # 1원 — 어떤 종목도 1주 살 수 없음
            position_size_pct=0.20,
        )
        engine = BacktestEngine(strategy, config)
        result = engine.run_single(perfect_double_bottom_scenario.df, ticker="TINY")
        assert result.total_trades == 0, "0주 케이스에서 거래가 발생하면 안 됨"

    def test_current_price_fallback_uses_entry_price(self, perfect_double_bottom_scenario):
        """_current_price가 데이터 없을 때 entry_price fallback 사용"""
        from backtest_engine.engine import BacktestEngine
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        engine = BacktestEngine(strategy)

        import pandas as pd
        df = perfect_double_bottom_scenario.df
        prepared = {"TEST": strategy.prepare(df)}

        # 데이터 범위 이전 타임스탬프 → fallback 사용
        past_ts = df.index[0] - pd.Timedelta(days=365)
        price = engine._current_price(prepared, "TEST", past_ts, fallback=12345.0)
        assert price == 12345.0

    def test_aggressive_allocator_does_not_crash(self):
        """CashAllocationAggressive가 예외 없이 동작"""
        from backtest_engine.core import Position, TradeSignal
        from backtest_engine.engine import BacktestConfig, CashAllocationAggressive
        alloc = CashAllocationAggressive()
        config = BacktestConfig(max_positions=2)
        pos = Position(
            ticker="A",
            entry_time=pd.Timestamp("2026-01-01"),
            entry_price=10000.0,
            shares=10,
            stop_loss=9750.0,
            target_1=10300.0,
            target_2=10500.0,
        )
        signal = TradeSignal(
            timestamp=pd.Timestamp("2026-01-02"),
            ticker="NEW",
            entry_price=10000.0,
            stop_loss=9750.0,
            target_1=10300.0,
            target_2=10500.0,
            confidence=0.9,
        )
        # 슬롯 가득 찬 경우: False 반환 (교체 미구현)
        can_enter, _ = alloc.should_enter(
            signal, {"A": pos, "B": pos}, cash=10_000_000, total_capital=10_000_000, config=config
        )
        assert can_enter is False

        # 슬롯 여유 있는 경우: True 반환
        can_enter2, _ = alloc.should_enter(
            signal, {}, cash=10_000_000, total_capital=10_000_000, config=config
        )
        assert can_enter2 is True


class TestBacktestResultMetrics:
    """BacktestResult 메트릭 계산"""

    def test_win_rate_calculation(self, perfect_double_bottom_scenario, fake_double_bottom_scenario):
        """승패 비율 계산 검증"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        config = BacktestConfig()
        engine = BacktestEngine(strategy, config)

        # 승 1개 + 패 1개 → win_rate 50%
        data = {
            "WIN": perfect_double_bottom_scenario.df,
            "LOSE": fake_double_bottom_scenario.df,
        }
        result = engine.run_multi(data)
        assert result.total_trades == 2
        assert result.win_rate == 0.5

    def test_equity_curve_starts_at_initial(self, perfect_double_bottom_scenario):
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        config = BacktestConfig(initial_capital=5_000_000.0)
        engine = BacktestEngine(strategy, config)

        result = engine.run_single(perfect_double_bottom_scenario.df)
        # equity curve 첫 값은 대략 initial_capital 근처
        first_eq = result.equity_curve.iloc[0]
        assert abs(first_eq - 5_000_000.0) / 5_000_000.0 < 0.05

    def test_summary_contains_all_metrics(self, perfect_double_bottom_scenario):
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        engine = BacktestEngine(strategy)
        result = engine.run_single(perfect_double_bottom_scenario.df)
        summary = result.summary()
        expected_keys = {
            "total_trades", "win_rate", "total_return_pct",
            "avg_pnl_pct", "avg_bars_held", "max_drawdown_pct",
            "profit_factor", "final_capital",
        }
        assert set(summary.keys()) == expected_keys
