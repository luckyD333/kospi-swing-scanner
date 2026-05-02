"""strategy.py 테스트: Strategy D v2 진입/청산 로직"""
import pandas as pd
import pytest

from backtest_engine.core import ExitReason, Position
from backtest_engine.detectors import (
    DoubleBottomFractal,
    DoubleBottomProminence,
    DoubleBottomSimple,
)
from backtest_engine.strategy import StrategyD, StrategyDConfig


class TestStrategyDEntry:
    """진입 조건 테스트"""

    def test_entry_on_perfect_scenario(self, perfect_double_bottom_scenario):
        """완벽한 쌍바닥 시나리오에서 진입 시그널 발생"""
        scenario = perfect_double_bottom_scenario
        strategy = StrategyD(
            config=StrategyDConfig(min_lookback_bars=25),  # warmup 20봉 + 여유
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(scenario.df)

        signal = None
        found_idx = None
        # 진입 예상 지점(32) ±2 범위에서 탐색
        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                signal = s
                found_idx = idx
                break

        assert signal is not None, "완벽 시나리오인데 진입 시그널 없음"
        assert found_idx is not None
        # 예상 진입 지점(32) ±2 이내
        assert abs(found_idx - scenario.expected_entry_idx) <= 2

    def test_no_entry_in_uptrend(self, uptrend_scenario):
        """상승 추세에서는 진입 시그널 없음"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        df = strategy.prepare(uptrend_scenario.df)

        signals = [strategy.check_entry(df, idx) for idx in range(25, len(df))]
        valid_signals = [s for s in signals if s is not None]
        assert len(valid_signals) == 0, f"상승장인데 시그널 {len(valid_signals)}개 감지됨"

    def test_no_entry_in_choppy(self, choppy_scenario):
        """횡보장에서는 진입 시그널 거의 없음"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        df = strategy.prepare(choppy_scenario.df)

        signals = [strategy.check_entry(df, idx) for idx in range(25, len(df))]
        valid_signals = [s for s in signals if s is not None]
        # 횡보장에서는 우연 시그널 0~1개 수준이어야 함
        assert len(valid_signals) <= 2


class TestStrategyDExit:
    """청산 조건 테스트"""

    def _make_position(self, entry_price: float = 10000.0) -> Position:
        """테스트용 포지션"""
        return Position(
            ticker="TEST",
            entry_time=pd.Timestamp("2026-01-17"),
            entry_price=entry_price,
            shares=100,
            stop_loss=entry_price * 0.975,  # -2.5%
            target_1=entry_price * 1.03,     # +3%
            target_2=entry_price * 1.05,     # +5%
        )

    def test_target_1_hit(self):
        """+3% 도달 시 TARGET_1 청산"""
        strategy = StrategyD()
        pos = self._make_position(entry_price=10000.0)
        bar = pd.Series({"open": 10000.0, "high": 10350.0, "low": 9950.0, "close": 10300.0})
        reason = strategy.check_exit(pos, bar, bars_held=0)
        assert reason == ExitReason.TARGET_1

    def test_stop_loss_hit(self):
        """-2.5% 도달 시 STOP_LOSS 청산"""
        strategy = StrategyD()
        pos = self._make_position()
        bar = pd.Series({"open": 9900.0, "high": 9950.0, "low": 9700.0, "close": 9800.0})
        reason = strategy.check_exit(pos, bar, bars_held=0)
        assert reason == ExitReason.STOP_LOSS

    def test_gap_down_detection(self):
        """-3% 이상 갭다운 시 GAP_DOWN 청산 (보유 1봉 이상)"""
        strategy = StrategyD()
        pos = self._make_position()
        # 시초가 -4% 갭다운
        bar = pd.Series({"open": 9600.0, "high": 9650.0, "low": 9500.0, "close": 9550.0})
        reason = strategy.check_exit(pos, bar, bars_held=1)
        assert reason == ExitReason.GAP_DOWN

    def test_gap_down_not_triggered_on_entry_bar(self):
        """진입 봉(bars_held=0)에서는 갭다운 손절 작동 안 함"""
        strategy = StrategyD()
        pos = self._make_position()
        # 시초가가 -4% 아래지만, 해당 bar가 진입 봉 자체이므로 갭다운으로 보지 않음
        # 대신 STOP_LOSS로 걸릴 것 (저가가 -3% 이하)
        bar = pd.Series({"open": 9600.0, "high": 9650.0, "low": 9500.0, "close": 9550.0})
        reason = strategy.check_exit(pos, bar, bars_held=0)
        assert reason == ExitReason.STOP_LOSS  # gap_down이 아니라 stop_loss

    def test_time_stop_triggered(self):
        """3봉 경과 시 TIME_STOP 청산"""
        strategy = StrategyD(config=StrategyDConfig(time_stop_bars=3))
        pos = self._make_position()
        # 시간 손절 조건만 충족 (다른 조건 해당 없음)
        bar = pd.Series({"open": 10050.0, "high": 10100.0, "low": 9950.0, "close": 10020.0})
        reason = strategy.check_exit(pos, bar, bars_held=3)
        assert reason == ExitReason.TIME_STOP

    def test_no_exit_when_all_clear(self):
        """아무 조건도 해당 안 되면 청산 없음"""
        strategy = StrategyD()
        pos = self._make_position()
        bar = pd.Series({"open": 10050.0, "high": 10150.0, "low": 9900.0, "close": 10100.0})
        reason = strategy.check_exit(pos, bar, bars_held=1)
        assert reason is None

    def test_exit_priority_stop_before_target(self):
        """같은 봉에 손절+익절 모두 도달 시 손절 우선 (보수적)"""
        strategy = StrategyD()
        pos = self._make_position(entry_price=10000.0)
        # 저가 -3%(손절), 고가 +4%(익절) 둘 다 터치
        bar = pd.Series({"open": 10000.0, "high": 10400.0, "low": 9700.0, "close": 10100.0})
        reason = strategy.check_exit(pos, bar, bars_held=0)
        # 갭다운 제외, 손절이 먼저 체크됨
        assert reason == ExitReason.STOP_LOSS


class TestExitPriceExecution:
    """execute_exit 가격 계산 테스트"""

    def _make_position(self, entry_price: float = 10000.0) -> Position:
        return Position(
            ticker="TEST",
            entry_time=pd.Timestamp("2026-01-17"),
            entry_price=entry_price,
            shares=100,
            stop_loss=entry_price * 0.975,
            target_1=entry_price * 1.03,
            target_2=entry_price * 1.05,
        )

    def test_gap_down_uses_open(self):
        strategy = StrategyD()
        pos = self._make_position()
        bar = pd.Series({"open": 9500.0, "high": 9600.0, "low": 9400.0, "close": 9550.0})
        price = strategy.execute_exit(pos, bar, ExitReason.GAP_DOWN)
        assert price == 9500.0

    def test_target_1_uses_target_price(self):
        strategy = StrategyD()
        pos = self._make_position()
        bar = pd.Series({"open": 10100.0, "high": 10500.0, "low": 10050.0, "close": 10300.0})
        price = strategy.execute_exit(pos, bar, ExitReason.TARGET_1)
        assert price == pos.target_1

    def test_stop_loss_conservative(self):
        """손절가는 open과 stop_loss 중 낮은 값 (불리한 쪽)"""
        strategy = StrategyD()
        pos = self._make_position(entry_price=10000.0)
        # 시초가가 이미 손절가 아래로 갭다운
        bar = pd.Series({"open": 9600.0, "high": 9650.0, "low": 9500.0, "close": 9550.0})
        price = strategy.execute_exit(pos, bar, ExitReason.STOP_LOSS)
        assert price == 9600.0  # open이 더 낮으므로 open으로 체결 가정


class TestConfidenceScoring:
    """신뢰도 점수 계산 테스트 (스펙 §3.2)"""

    def test_base_confidence_on_perfect_scenario(self, perfect_double_bottom_scenario):
        """완벽 시나리오의 신뢰도는 기본값(0.55) 이상"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        df = strategy.prepare(perfect_double_bottom_scenario.df)

        signal = None
        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                signal = s
                break

        assert signal is not None
        assert signal.confidence >= 0.55, f"기본 신뢰도 0.55 미만: {signal.confidence}"

    def test_confidence_capped_at_1(self, perfect_double_bottom_scenario):
        """신뢰도는 1.0 초과 불가"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        df = strategy.prepare(perfect_double_bottom_scenario.df)

        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                assert s.confidence <= 1.0
                break

    def test_confidence_increases_with_bb_breach(self, perfect_double_bottom_scenario):
        """2차 바닥이 BB 내부일 때 신뢰도 부스트 (+0.10)"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        df = strategy.prepare(perfect_double_bottom_scenario.df)

        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                # 완벽 시나리오는 BB breach 조건 충족 → 0.65 이상
                if s.conditions_met.get("second_bottom_inside_bb"):
                    assert s.confidence >= 0.65
                break

    def test_confidence_is_float_rounded(self, perfect_double_bottom_scenario):
        """신뢰도 값은 소수 4자리로 반올림된 float"""
        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
        df = strategy.prepare(perfect_double_bottom_scenario.df)

        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                assert isinstance(s.confidence, float)
                assert s.confidence == round(s.confidence, 4)
                break


class TestStrategyDAllDetectors:
    """3가지 detector 구현 모두로 진입 로직 동작 검증"""

    @pytest.mark.parametrize("detector_cls", [
        DoubleBottomSimple,
        DoubleBottomFractal,
        DoubleBottomProminence,
    ])
    def test_each_detector_finds_entry_in_perfect_scenario(
        self, detector_cls, perfect_double_bottom_scenario
    ):
        """각 detector별로 완벽 시나리오에서 진입 확인"""
        strategy = StrategyD(
            config=StrategyDConfig(min_lookback_bars=25),
            double_bottom_detector=detector_cls(),
        )
        df = strategy.prepare(perfect_double_bottom_scenario.df)

        signal_found = False
        for idx in range(30, min(35, len(df))):
            if strategy.check_entry(df, idx) is not None:
                signal_found = True
                break

        assert signal_found, f"{detector_cls.__name__}으로 완벽 시나리오 진입 실패"
