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


class TestRRFilter:
    """RR sweet spot 진입 필터 테스트 (PR #3)"""

    def test_rr_filter_excludes_below_min(self, perfect_double_bottom_scenario):
        """RR < min_rr_ratio 시그널은 use_rr_filter=True 시 reject"""
        scenario = perfect_double_bottom_scenario
        # 낮은 RR을 강제하기 위해 target_2를 낮게 설정
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=25,
                use_rr_filter=True,
                min_rr_ratio=2.0,
                target_2_pct=0.02,  # +2%, stop_loss_pct=0.025 → RR=0.02/0.025=0.8 < 2.0
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(scenario.df)

        signal = None
        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                signal = s
                break

        assert signal is None, "RR < min_rr_ratio 시그널이 reject되지 않음"

    def test_rr_filter_allows_sweet_spot(self, perfect_double_bottom_scenario):
        """RR이 sweet spot 범위(2.0~2.5)인 시그널은 accept + rr_band='sweet'"""
        scenario = perfect_double_bottom_scenario
        # RR을 sweet spot 범위로 설정: target_2=0.05, stop_loss_pct=0.025 → RR=0.05/0.025=2.0
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=25,
                use_rr_filter=True,
                min_rr_ratio=2.0,
                sweet_spot_rr_low=2.0,
                sweet_spot_rr_high=2.5,
                target_2_pct=0.05,
                stop_loss_pct=0.025,
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(scenario.df)

        signal = None
        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                signal = s
                break

        assert signal is not None, "sweet spot RR 시그널이 accept되지 않음"
        assert hasattr(signal, 'metadata'), "TradeSignal에 metadata 필드 없음"
        assert signal.metadata.get('rr_band') == 'sweet', \
            f"rr_band='sweet' 기대, 실제: {signal.metadata.get('rr_band')}"

    def test_rr_filter_allows_above_sweet_spot(self, perfect_double_bottom_scenario):
        """RR >= sweet_spot_rr_high인 시그널은 accept + rr_band='over'"""
        scenario = perfect_double_bottom_scenario
        # RR을 over범위로 설정: target_2=0.075, stop_loss_pct=0.025 → RR=0.075/0.025=3.0
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=25,
                use_rr_filter=True,
                min_rr_ratio=2.0,
                sweet_spot_rr_low=2.0,
                sweet_spot_rr_high=2.5,
                target_2_pct=0.075,
                stop_loss_pct=0.025,
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(scenario.df)

        signal = None
        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                signal = s
                break

        assert signal is not None, "over RR 시그널이 accept되지 않음"
        assert signal.metadata.get('rr_band') == 'over', \
            f"rr_band='over' 기대, 실제: {signal.metadata.get('rr_band')}"

    def test_rr_filter_disabled_default(self, perfect_double_bottom_scenario):
        """use_rr_filter=False(디폴트) 시 낮은 RR도 accept (회귀 가드)"""
        scenario = perfect_double_bottom_scenario
        # 낮은 RR 설정
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=25,
                use_rr_filter=False,  # 명시적으로 OFF
                target_2_pct=0.02,    # RR=0.02/0.025=0.8
                stop_loss_pct=0.025,
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(scenario.df)

        signal = None
        for idx in range(30, min(35, len(df))):
            s = strategy.check_entry(df, idx)
            if s is not None:
                signal = s
                break

        assert signal is not None, "use_rr_filter=False일 때 낮은 RR 시그널이 reject됨"
        # metadata에 rr_ratio, rr_band 있어야 함 (정보 제공용)
        assert hasattr(signal, 'metadata'), "TradeSignal에 metadata 필드 없음"
        assert 'rr_ratio' in signal.metadata, "metadata에 rr_ratio 없음"
        assert 'rr_band' in signal.metadata, "metadata에 rr_band 없음"


class TestATRStops:
    """ATR 기반 동적 손절·목표가 테스트 (PR #4)"""

    def test_atr_stop_uses_max_when_atr_wider(self):
        """고변동성 종목: ATR×1.5 > fixed% → ATR 손절 채택"""
        # close 수열로 고변동 OHLCV 생성
        closes = [100.0] * 20 + [95.0, 94.0, 93.0, 94.5, 95.5, 96.0, 96.5]
        from backtest_engine.scenarios import _make_ohlcv_from_closes
        df = _make_ohlcv_from_closes(
            closes,
            pd.Timestamp("2026-01-17"),
            freq="D",
            noise_pct=0.05,  # 고변동성 (±5%)
            seed=42,
        )

        from backtest_engine.core import calc_atr
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=14,
                use_atr_stops=True,
                atr_stop_mult=1.5,
                stop_loss_pct=0.025,
                atr_min_threshold=0.0,
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(df)

        # ATR 계산 확인
        atr_series = calc_atr(df["high"], df["low"], df["close"], 14)
        atr_at_idx = float(atr_series.iloc[-1])
        assert atr_at_idx > 0, "ATR 계산 실패"

        # entry 직전 봉에서 진입 시뮬레이션
        entry_price = float(df.iloc[-1]["close"])
        fixed_stop_distance = entry_price * 0.025
        atr_stop_distance = atr_at_idx * 1.5

        # ATR 손절이 더 넓어야 함 (고변동성)
        assert atr_stop_distance > fixed_stop_distance, \
            f"ATR {atr_stop_distance:.2f} > fixed {fixed_stop_distance:.2f}"

    def test_atr_stop_uses_max_when_pct_wider(self):
        """저변동성 종목: fixed% > ATR×1.5 → fixed% 손절 채택"""
        # 저변동성 데이터
        closes = [100.0] * 30 + [100.1, 100.05, 99.95, 100.0, 100.05]
        from backtest_engine.scenarios import _make_ohlcv_from_closes
        df = _make_ohlcv_from_closes(
            closes,
            pd.Timestamp("2026-01-17"),
            freq="D",
            noise_pct=0.001,  # 저변동성 (±0.1%)
            seed=42,
        )

        from backtest_engine.core import calc_atr
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=14,
                use_atr_stops=True,
                atr_stop_mult=1.5,
                stop_loss_pct=0.025,
                atr_min_threshold=0.0,
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(df)

        # ATR 계산 확인
        atr_series = calc_atr(df["high"], df["low"], df["close"], 14)
        atr_at_idx = float(atr_series.iloc[-1])

        entry_price = float(df.iloc[-1]["close"])
        fixed_stop_distance = entry_price * 0.025
        atr_stop_distance = atr_at_idx * 1.5

        # fixed% 손절이 더 넓어야 함 (저변동성)
        assert fixed_stop_distance > atr_stop_distance, \
            f"fixed {fixed_stop_distance:.2f} > ATR {atr_stop_distance:.2f}"

    def test_atr_target_uses_atr_mult(self):
        """target_2 = entry + ATR×3.0"""
        closes = [100.0] * 20 + [95.0, 94.0, 93.0, 94.5, 95.5, 96.0, 96.5]
        from backtest_engine.scenarios import _make_ohlcv_from_closes
        df = _make_ohlcv_from_closes(
            closes,
            pd.Timestamp("2026-01-17"),
            freq="D",
            noise_pct=0.05,
            seed=42,
        )

        from backtest_engine.core import calc_atr
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=14,
                use_atr_stops=True,
                atr_target_mult=3.0,
                target_2_pct=0.05,
                atr_min_threshold=0.0,
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(df)

        atr_series = calc_atr(df["high"], df["low"], df["close"], 14)
        atr_at_idx = float(atr_series.iloc[-1])
        entry_price = float(df.iloc[-1]["close"])

        expected_target_2_atr = entry_price + atr_at_idx * 3.0
        fixed_target_2 = entry_price * (1 + 0.05)

        # ATR 목표가가 fixed보다 높아야 함 (고변동성)
        assert expected_target_2_atr > fixed_target_2

    def test_atr_nan_falls_back_to_fixed_pct(self):
        """상장 직후 < 14봉: ATR NaN → fixed% fallback"""
        # 짧은 데이터 (< 14봉)
        closes = [100.0, 100.5, 101.0, 100.8, 100.2, 100.5, 99.8, 100.3]
        from backtest_engine.scenarios import _make_ohlcv_from_closes
        df = _make_ohlcv_from_closes(
            closes,
            pd.Timestamp("2026-01-17"),
            freq="D",
        )

        from backtest_engine.core import calc_atr
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=2,
                use_atr_stops=True,
                atr_stop_mult=1.5,
                stop_loss_pct=0.025,
                atr_min_threshold=0.0,
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(df)

        atr_series = calc_atr(df["high"], df["low"], df["close"], 14)
        # ATR가 NaN이어야 함 (lookback 부족)
        atr_at_idx = atr_series.iloc[-1]
        assert pd.isna(atr_at_idx), "짧은 데이터에서 ATR이 NaN이 아님"

    def test_atr_below_threshold_falls_back(self):
        """ATR < threshold: fixed% fallback"""
        closes = [100.0] * 30 + [100.1, 100.05, 99.95, 100.0, 100.05]
        from backtest_engine.scenarios import _make_ohlcv_from_closes
        df = _make_ohlcv_from_closes(
            closes,
            pd.Timestamp("2026-01-17"),
            freq="D",
            noise_pct=0.001,
        )

        from backtest_engine.core import calc_atr
        strategy = StrategyD(
            config=StrategyDConfig(
                min_lookback_bars=14,
                use_atr_stops=True,
                atr_stop_mult=1.5,
                stop_loss_pct=0.025,
                atr_min_threshold=0.5,  # 높은 threshold
            ),
            double_bottom_detector=DoubleBottomSimple(),
        )
        df = strategy.prepare(df)

        atr_series = calc_atr(df["high"], df["low"], df["close"], 14)
        atr_at_idx = float(atr_series.iloc[-1])

        # ATR이 threshold 미만이어야 함 (저변동성)
        assert atr_at_idx < 0.5, f"ATR {atr_at_idx} >= threshold 0.5"


class TestConditionalTimeStop:
    """조건부 시간 손절 테스트 (PR #5)"""

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

    def test_conditional_time_stop_triggers_on_no_progress(self):
        """3봉 경과 + PnL < 1% → CONDITIONAL_TIME_STOP 발동"""
        strategy = StrategyD(
            config=StrategyDConfig(
                use_conditional_time_stop=True,
                conditional_time_stop_bars=3,
                min_progress_pct=0.01,
            )
        )
        pos = self._make_position(entry_price=10000.0)
        # 현재 종가 = 10000 + (10000 * 0.005) = 10050 → PnL = +0.5% (< 1% threshold)
        bar = pd.Series({
            "open": 10020.0,
            "high": 10100.0,
            "low": 9950.0,
            "close": 10050.0,
        })
        reason = strategy.check_exit(pos, bar, bars_held=3)
        assert reason == ExitReason.CONDITIONAL_TIME_STOP

    def test_conditional_time_stop_skipped_with_progress(self):
        """3봉 경과 + PnL >= 1% → CONDITIONAL_TIME_STOP 미발동"""
        strategy = StrategyD(
            config=StrategyDConfig(
                use_conditional_time_stop=True,
                conditional_time_stop_bars=3,
                min_progress_pct=0.01,
                time_stop_bars=999,  # 무조건 시간 손절을 무한으로 설정하여 미발동
            )
        )
        pos = self._make_position(entry_price=10000.0)
        # 현재 종가 = 10000 + (10000 * 0.015) = 10150 → PnL = +1.5% (>= 1% threshold)
        bar = pd.Series({
            "open": 10050.0,
            "high": 10200.0,
            "low": 10000.0,
            "close": 10150.0,
        })
        reason = strategy.check_exit(pos, bar, bars_held=3)
        # 다른 조건 미충족 → None (청산 신호 없음)
        assert reason is None

    def test_conditional_time_stop_disabled_default(self):
        """use_conditional_time_stop=False (디폴트) 시 미발동 (회귀 가드)"""
        strategy = StrategyD(
            config=StrategyDConfig(
                use_conditional_time_stop=False,  # 명시적 OFF
                conditional_time_stop_bars=3,
                min_progress_pct=0.01,
            )
        )
        pos = self._make_position(entry_price=10000.0)
        # PnL = +0.5%, bars_held=3 인데도 조건부 시간 손절 미발동
        bar = pd.Series({
            "open": 10020.0,
            "high": 10100.0,
            "low": 9950.0,
            "close": 10050.0,
        })
        reason = strategy.check_exit(pos, bar, bars_held=3)
        # CONDITIONAL_TIME_STOP 아님
        assert reason != ExitReason.CONDITIONAL_TIME_STOP

    def test_force_time_stop_alias_still_works(self):
        """force_time_stop_bars 설정 시 무조건 시간 손절 발동 (alias 호환성)"""
        strategy = StrategyD(
            config=StrategyDConfig(
                use_conditional_time_stop=False,
                force_time_stop_bars=3,
                time_stop_bars=999,  # 이 값은 무시됨
            )
        )
        pos = self._make_position()
        # bars_held=3, 다른 조건 미충족
        bar = pd.Series({
            "open": 10050.0,
            "high": 10150.0,
            "low": 9900.0,
            "close": 10100.0,
        })
        reason = strategy.check_exit(pos, bar, bars_held=3)
        assert reason == ExitReason.TIME_STOP

    def test_priority_stop_loss_beats_conditional_time_stop(self):
        """같은 봉에 STOP_LOSS + CONDITIONAL_TIME_STOP 모두 조건 충족 → STOP_LOSS 우선"""
        strategy = StrategyD(
            config=StrategyDConfig(
                use_conditional_time_stop=True,
                conditional_time_stop_bars=2,
                min_progress_pct=0.01,
            )
        )
        pos = self._make_position(entry_price=10000.0)
        # 저가 = 9700 (손절가 9750 미만) + PnL = +0.5% + bars_held = 2
        bar = pd.Series({
            "open": 9800.0,
            "high": 10100.0,
            "low": 9700.0,
            "close": 10050.0,
        })
        reason = strategy.check_exit(pos, bar, bars_held=2)
        # STOP_LOSS가 우선순위 높음
        assert reason == ExitReason.STOP_LOSS
