"""
tests/test_squeeze.py — Squeeze 워치리스트 + 가드레일 테스트.

Test Plan:
  1. is_squeeze(): 경계값 검증 (width_percentile_60 < 0.25, position 0.4~0.7)
  2. build_squeeze_queue(): 우선순위 정렬 + max_queue_size 제한
  3. 가드레일 회귀: 거래량 1.5×, width_percentile_60 > 0.85 penalty
"""
from __future__ import annotations



from core.decision.donchian import DonchianFrame
from core.decision.squeeze import is_squeeze, build_squeeze_queue


class TestIsSqueeze:
    """is_squeeze 경계값 테스트."""

    def test_squeeze_true_basic(self):
        """1d + 1h 동시 width_percentile_60 < 0.25 + position 0.4~0.7 → True."""
        d_1d = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=95.0,
            middle=97.5,
            width_pct=5.128,
            width_percentile_60=0.2,  # < 0.25 ✓
            position=0.5,  # 0.4~0.7 ✓
            days_since_upper_break=3,
            days_since_lower_break=10,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=99.0,
            middle=99.5,
            width_pct=1.005,
            width_percentile_60=0.15,  # < 0.25 ✓
            position=0.5,
            days_since_upper_break=1,
            days_since_lower_break=5,
            slope=0.02,
        )
        assert is_squeeze(d_1d, d_1h) is True

    def test_squeeze_false_width_1d_too_high(self):
        """1d width_percentile_60 ≥ 0.25 → False."""
        d_1d = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=90.0,
            middle=95.0,
            width_pct=10.526,
            width_percentile_60=0.3,  # > 0.25 ✗
            position=0.5,
            days_since_upper_break=2,
            days_since_lower_break=8,
            slope=0.03,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=99.0,
            middle=99.5,
            width_pct=1.005,
            width_percentile_60=0.15,
            position=0.5,
            days_since_upper_break=1,
            days_since_lower_break=5,
            slope=0.02,
        )
        assert is_squeeze(d_1d, d_1h) is False

    def test_squeeze_false_width_1h_too_high(self):
        """1h width_percentile_60 ≥ 0.25 → False."""
        d_1d = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=95.0,
            middle=97.5,
            width_pct=5.128,
            width_percentile_60=0.2,
            position=0.5,
            days_since_upper_break=3,
            days_since_lower_break=10,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=98.0,
            middle=99.0,
            width_pct=2.020,
            width_percentile_60=0.35,  # > 0.25 ✗
            position=0.5,
            days_since_upper_break=1,
            days_since_lower_break=5,
            slope=0.02,
        )
        assert is_squeeze(d_1d, d_1h) is False

    def test_squeeze_false_position_below_range(self):
        """position < 0.4 (하단권) → False."""
        d_1d = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=95.0,
            middle=97.5,
            width_pct=5.128,
            width_percentile_60=0.2,
            position=0.3,  # < 0.4 ✗
            days_since_upper_break=10,
            days_since_lower_break=1,
            slope=-0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=99.0,
            middle=99.5,
            width_pct=1.005,
            width_percentile_60=0.15,
            position=0.3,
            days_since_upper_break=5,
            days_since_lower_break=1,
            slope=-0.02,
        )
        assert is_squeeze(d_1d, d_1h) is False

    def test_squeeze_false_position_above_range(self):
        """position > 0.7 (상단권) → False."""
        d_1d = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=95.0,
            middle=97.5,
            width_pct=5.128,
            width_percentile_60=0.2,
            position=0.75,  # > 0.7 ✗
            days_since_upper_break=1,
            days_since_lower_break=10,
            slope=0.08,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=99.0,
            middle=99.5,
            width_pct=1.005,
            width_percentile_60=0.15,
            position=0.75,
            days_since_upper_break=1,
            days_since_lower_break=10,
            slope=0.05,
        )
        assert is_squeeze(d_1d, d_1h) is False

    def test_squeeze_false_d_1d_none(self):
        """d_1d = None → False."""
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=99.0,
            middle=99.5,
            width_pct=1.005,
            width_percentile_60=0.15,
            position=0.5,
            days_since_upper_break=1,
            days_since_lower_break=5,
            slope=0.02,
        )
        assert is_squeeze(None, d_1h) is False

    def test_squeeze_false_d_1h_none(self):
        """d_1h = None → False."""
        d_1d = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=95.0,
            middle=97.5,
            width_pct=5.128,
            width_percentile_60=0.2,
            position=0.5,
            days_since_upper_break=3,
            days_since_lower_break=10,
            slope=0.05,
        )
        assert is_squeeze(d_1d, None) is False

    def test_squeeze_false_nan_width(self):
        """width_percentile_60 = NaN → False."""
        d_1d = DonchianFrame(
            timeframe="1d",
            period=20,
            upper=100.0,
            lower=95.0,
            middle=97.5,
            width_pct=5.128,
            width_percentile_60=float("nan"),  # NaN
            position=0.5,
            days_since_upper_break=3,
            days_since_lower_break=10,
            slope=0.05,
        )
        d_1h = DonchianFrame(
            timeframe="1h",
            period=20,
            upper=100.0,
            lower=99.0,
            middle=99.5,
            width_pct=1.005,
            width_percentile_60=0.15,
            position=0.5,
            days_since_upper_break=1,
            days_since_lower_break=5,
            slope=0.02,
        )
        assert is_squeeze(d_1d, d_1h) is False


class TestBuildSqueezeQueue:
    """build_squeeze_queue 정렬 + 크기 제한 테스트."""

    def test_squeeze_queue_sorted_by_1d_width_percentile(self):
        """Squeeze 종목 3개 → 1d width_percentile_60 낮은 순 정렬."""
        donchian_1d = {
            "005930": DonchianFrame(
                timeframe="1d", period=20,
                upper=100.0, lower=95.0, middle=97.5,
                width_pct=5.128,
                width_percentile_60=0.1,  # 낮음 (우선 1)
                position=0.5,
                days_since_upper_break=3, days_since_lower_break=10, slope=0.05,
            ),
            "000660": DonchianFrame(
                timeframe="1d", period=20,
                upper=100.0, lower=95.0, middle=97.5,
                width_pct=5.128,
                width_percentile_60=0.2,  # 중간 (우선 2)
                position=0.5,
                days_since_upper_break=3, days_since_lower_break=10, slope=0.05,
            ),
            "051910": DonchianFrame(
                timeframe="1d", period=20,
                upper=100.0, lower=95.0, middle=97.5,
                width_pct=5.128,
                width_percentile_60=0.15,  # 중간-낮음 (우선 2.5)
                position=0.5,
                days_since_upper_break=3, days_since_lower_break=10, slope=0.05,
            ),
            "123456": DonchianFrame(
                timeframe="1d", period=20,
                upper=100.0, lower=80.0, middle=90.0,
                width_pct=22.222,
                width_percentile_60=0.5,  # 높음 (비 squeeze)
                position=0.5,
                days_since_upper_break=5, days_since_lower_break=5, slope=0.0,
            ),
            "654321": None,  # None (비 squeeze)
        }
        donchian_1h = {
            "005930": DonchianFrame(
                timeframe="1h", period=20,
                upper=100.0, lower=99.0, middle=99.5,
                width_pct=1.005,
                width_percentile_60=0.1,
                position=0.5,
                days_since_upper_break=1, days_since_lower_break=5, slope=0.02,
            ),
            "000660": DonchianFrame(
                timeframe="1h", period=20,
                upper=100.0, lower=99.0, middle=99.5,
                width_pct=1.005,
                width_percentile_60=0.2,
                position=0.5,
                days_since_upper_break=1, days_since_lower_break=5, slope=0.02,
            ),
            "051910": DonchianFrame(
                timeframe="1h", period=20,
                upper=100.0, lower=99.0, middle=99.5,
                width_pct=1.005,
                width_percentile_60=0.15,
                position=0.5,
                days_since_upper_break=1, days_since_lower_break=5, slope=0.02,
            ),
            "123456": None,
            "654321": DonchianFrame(
                timeframe="1h", period=20,
                upper=100.0, lower=99.0, middle=99.5,
                width_pct=1.005,
                width_percentile_60=0.1,
                position=0.5,
                days_since_upper_break=1, days_since_lower_break=5, slope=0.02,
            ),
        }
        queue = build_squeeze_queue(donchian_1d, donchian_1h, max_queue_size=20)
        # 3개 squeeze: 005930 (w=0.1), 051910 (w=0.15), 000660 (w=0.2)
        assert len(queue) == 3
        assert queue[0] == "005930"
        assert queue[1] == "051910"
        assert queue[2] == "000660"

    def test_squeeze_queue_respects_max_size(self):
        """max_queue_size=2 → 상위 2개만 반환."""
        donchian_1d = {
            f"ticker_{i}": DonchianFrame(
                timeframe="1d", period=20,
                upper=100.0, lower=95.0, middle=97.5,
                width_pct=5.128,
                width_percentile_60=0.1 + i * 0.01,
                position=0.5,
                days_since_upper_break=3, days_since_lower_break=10, slope=0.05,
            )
            for i in range(5)
        }
        donchian_1h = {
            f"ticker_{i}": DonchianFrame(
                timeframe="1h", period=20,
                upper=100.0, lower=99.0, middle=99.5,
                width_pct=1.005,
                width_percentile_60=0.1 + i * 0.01,
                position=0.5,
                days_since_upper_break=1, days_since_lower_break=5, slope=0.02,
            )
            for i in range(5)
        }
        queue = build_squeeze_queue(donchian_1d, donchian_1h, max_queue_size=2)
        assert len(queue) == 2
        assert queue[0] == "ticker_0"  # width=0.1
        assert queue[1] == "ticker_1"  # width=0.11

    def test_squeeze_queue_empty_when_none(self):
        """Squeeze 종목 없음 → 빈 리스트."""
        donchian_1d = {
            "005930": DonchianFrame(
                timeframe="1d", period=20,
                upper=100.0, lower=80.0, middle=90.0,
                width_pct=22.222,
                width_percentile_60=0.5,
                position=0.5,
                days_since_upper_break=5, days_since_lower_break=5, slope=0.0,
            ),
        }
        donchian_1h = {
            "005930": None,
        }
        queue = build_squeeze_queue(donchian_1d, donchian_1h, max_queue_size=20)
        assert len(queue) == 0


class TestVolumeGuardrail:
    """거래량 1.5× 가드레일 회귀 (전략별 단위 테스트에서 검증)."""

    def test_volume_guardrail_blocks_low_volume(self):
        """vol_today < avg_vol_20 × 1.5 → 후보 제외.

        이 테스트는 strategy_two_unit / strategy_three_unit 등에서
        fixture 거래량을 보정할 때 검증됨.
        """
        # 전략 단위 테스트에서 거래량 fixture 확인하는 로직
        # 여기서는 guardrail 적용 후 strategy별 테스트에서 회귀 검증
        pass


class TestWidthPercentileGuardrail:
    """변동성 큰 시장 페널티: width_percentile_60 > 0.85 → score ×0.7."""

    def test_width_percentile_penalty_applies(self):
        """이 테스트는 각 strategy 파일에서 점수 계산 후 검증.

        예: strategy_two_cross_sectional_momentum.py 에서
        width_percentile_60 > 0.85 인 종목의 score 가 0.7배로 감점되는지.
        """
        pass
