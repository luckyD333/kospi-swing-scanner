"""test_signals_builder_setup_meta.py — Signal 객체에 setup_score/reasons 메타 필드 노출."""

import pytest

from core.decision.donchian import DonchianFrame
from core.decision.setup_quality import trend_setup_quality
from output.models import Signal


@pytest.fixture
def sample_signal_dict() -> dict:
    """Signal 객체 생성을 위한 기본 dict."""
    return {
        "ticker": "005930",
        "name": "삼성전자",
        "name_en": "Samsung Electronics",
        "strategy": {
            "id": "strategy_three_trend_following",
            "label": "STRATEGY THREE",
            "category": "TREND_FOLLOWING",
            "timeframe": "1D",
        },
        "trade_plan": {
            "entry": 70000,
            "stop": 65000,
            "target_1": 75000,
            "target_2": 80000,
            "rr_ratio": 1.5,
            "rr_band": "SWEET",
            "atr_14": 1000,
            "rsi_14": 65.5,
        },
        "ranking": {
            "score": 50.0,
            "rank": 1,
            "percentile": 95.0,
            "signal_strength": 50.0,
            "decision": {
                "final_score": 50.0,
                "factors": [
                    {
                        "key": "momentum_3m",
                        "label": "3개월 추세",
                        "weight": 35.0,
                        "normalized": 50.0,
                        "contribution": 17.5,
                    }
                ],
                "max_regret": 40.0,
                "regret_score": 40.0,
            },
        },
        "live_quote": {
            "current_price": 72000,
            "change_pct": 2.5,
            "volume": 1000000,
            "market_cap_krw": 500000000000,
        },
        "fundamentals": {
            "per": 15.0,
            "per_negative": False,
            "high_52w": 80000,
            "low_52w": 60000,
        },
        "flow": {
            "foreign_ratio_pct": 45.2,
        },
        "external_links": {},
        "signal_date": "2026-05-08T16:00:00+09:00",
        "signal_status": "VALID",
        "product_type": "STOCK",
        "pool": "STOCK",
        "asset_class": "STOCK",
    }


def test_signal_with_setup_score_and_reasons(sample_signal_dict):
    """Signal 객체에 setup_score/setup_reasons 필드가 포함되는지 검증."""
    sample_signal_dict["setup_score"] = 75
    sample_signal_dict["setup_reasons"] = ["1h_aligned_up", "1h_squeeze", "1h_fresh_breakout", "1h_slope_up"]

    signal = Signal(**sample_signal_dict)

    assert signal.setup_score == 75
    assert signal.setup_reasons == ["1h_aligned_up", "1h_squeeze", "1h_fresh_breakout", "1h_slope_up"]


def test_signal_without_setup_score_defaults_to_none(sample_signal_dict):
    """setup_score/setup_reasons 가 없을 때 None 으로 기본값 설정."""
    # setup_score/reasons 미포함

    signal = Signal(**sample_signal_dict)

    assert signal.setup_score is None
    assert signal.setup_reasons is None


def test_signal_with_zero_setup_score(sample_signal_dict):
    """setup_score 0 (임계값 미달) 는 정상 처리."""
    sample_signal_dict["setup_score"] = 0
    sample_signal_dict["setup_reasons"] = ["1h_late_chase"]

    signal = Signal(**sample_signal_dict)

    assert signal.setup_score == 0
    assert signal.setup_reasons == ["1h_late_chase"]


def test_signal_json_serialization_with_setup_meta(sample_signal_dict):
    """Signal 을 JSON 으로 직렬화할 때 setup_score/reasons 포함."""
    sample_signal_dict["setup_score"] = 65
    sample_signal_dict["setup_reasons"] = ["1h_aligned_up", "1h_normal_volatility", "1h_flat"]

    signal = Signal(**sample_signal_dict)
    signal_json = signal.model_dump(mode="json", exclude_none=False)

    assert "setup_score" in signal_json
    assert signal_json["setup_score"] == 65
    assert "setup_reasons" in signal_json
    assert signal_json["setup_reasons"] == ["1h_aligned_up", "1h_normal_volatility", "1h_flat"]


def test_setup_quality_to_signal_integration():
    """DonchianFrame → SetupQuality → Signal 흐름 검증."""
    d_1h = DonchianFrame(
        timeframe="1h",
        period=20,
        upper=100.0,
        lower=70.0,
        middle=85.0,
        width_pct=35.3,
        width_percentile_60=0.2,
        position=0.7,
        days_since_upper_break=1,
        days_since_lower_break=10,
        slope=0.01,
    )

    # SetupQuality 계산
    quality = trend_setup_quality(d_1h)
    assert quality.score == 90
    assert len(quality.reasons) == 4

    # Signal 에 메타 필드 채우기
    signal_dict = {
        "ticker": "005930",
        "name": "삼성전자",
        "name_en": None,
        "strategy": {
            "id": "strategy_three_trend_following",
            "label": "STRATEGY THREE",
            "category": "TREND_FOLLOWING",
            "timeframe": "1D",
        },
        "trade_plan": {
            "entry": 70000,
            "stop": 65000,
            "target_1": 75000,
            "rr_ratio": 1.5,
            "rr_band": "SWEET",
        },
        "ranking": {
            "score": 50.0,
            "rank": 1,
            "percentile": 95.0,
            "signal_strength": 50.0,
            "decision": {
                "final_score": 50.0,
                "factors": [],
                "regret_score": 40.0,
            },
        },
        "live_quote": {
            "current_price": 72000,
            "change_pct": 2.5,
            "volume": 1000000,
            "market_cap_krw": 500000000000,
        },
        "fundamentals": {
            "per": 15.0,
            "per_negative": False,
        },
        "flow": {
            "foreign_ratio_pct": 45.2,
        },
        "external_links": {},
        "signal_date": "2026-05-08T16:00:00+09:00",
        "signal_status": "VALID",
        "product_type": "STOCK",
        "pool": "STOCK",
        "asset_class": "STOCK",
        "setup_score": quality.score,
        "setup_reasons": list(quality.reasons),
    }

    signal = Signal(**signal_dict)

    assert signal.setup_score == 90
    assert signal.setup_reasons == ["1h_aligned_up", "1h_squeeze", "1h_fresh_breakout", "1h_slope_up"]
