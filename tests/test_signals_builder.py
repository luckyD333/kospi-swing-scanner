# tests/test_signals_builder.py
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
from zoneinfo import ZoneInfo

from output.signals_builder import (
    build_signals_payload, _fmt_krw, _fmt_pct, _format_target_display,
)
from output.models import SignalsPayload, MarketSnapshot, TickerSnapshot, Fundamentals, Flow

KST = ZoneInfo("Asia/Seoul")


def _make_snapshot():
    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-03T22:00:00+09:00",
        source={},
        market_indices={},
        tickers={"001390": TickerSnapshot(
            ticker="001390", name="KG케미칼",
            current_price=7120, change_pct=0.71, volume=2847000,
            market_cap_krw=475300000000,
            fundamentals=Fundamentals(per=11.2, high_52w=9120, low_52w=5050),
            flow=Flow(foreign_ratio_pct=18.5),
        )}
    )


def _make_candidate(rr_band_raw="sweet"):
    c = MagicMock()
    c.ticker = "001390"
    c.name = "KG케미칼"
    c.score = 87.0
    c.timeframe = "1D"
    c.entry_price = 7070
    c.stop_loss = 6820
    c.target_1 = 7580
    c.target_2 = 8100
    c.signal_date = None
    c.metadata = {
        "rr_ratio": 2.04,
        "rr_band": rr_band_raw,   # strategy 저장 값 (소문자)
        "atr_14": 183,
        "per": 11.2,
        "foreign_pct": 18.5,
        "naver_url": "https://finance.naver.com/item/main.naver?code=001390",
    }
    return c


def test_build_signals_payload_basic():
    snap = _make_snapshot()
    candidates = {"strategy_one_d_v2": [_make_candidate("sweet")]}
    payload = build_signals_payload(snap, candidates_by_strategy=candidates)
    assert isinstance(payload, SignalsPayload)
    assert len(payload.signals) == 1
    assert payload.signals[0].ticker == "001390"
    assert payload.stats["total_signals"] == 1


def test_rr_band_mapping():
    """strategy 소문자 → 모델 대문자 매핑 확인."""
    snap = _make_snapshot()
    for raw, expected in [("below", "UNDER"), ("sweet", "SWEET"), ("over", "OVER")]:
        payload = build_signals_payload(snap, {"strategy_one_d_v2": [_make_candidate(raw)]})
        assert payload.signals[0].trade_plan.rr_band == expected, f"raw={raw}"


def test_fmt_krw():
    assert _fmt_krw(475300000000) == "4,753억"
    assert _fmt_krw(1200000000000) == "1조 2,000억"


def test_fmt_pct():
    assert _fmt_pct(0.71, positive_prefix="+") == "+0.71%"
    assert _fmt_pct(-1.23, positive_prefix="+") == "-1.23%"


def test_signal_date_mapped_from_candidate():
    """Candidate.signal_date(pd.Timestamp) → Signal.signal_date(ISO 8601)."""
    snap = _make_snapshot()
    cand = _make_candidate("sweet")
    cand.signal_date = pd.Timestamp("2026-05-04 12:30:00", tz="Asia/Seoul")
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})
    assert payload.signals[0].signal_date == "2026-05-04T12:30:00+09:00"


def test_signal_date_none_when_candidate_lacks_it():
    """Candidate.signal_date 부재 시 None."""
    snap = _make_snapshot()
    cand = _make_candidate("sweet")
    cand.signal_date = None
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})
    assert payload.signals[0].signal_date is None


def test_target_date_passed_through():
    """target_date 인자가 SignalsPayload 에 정규화되어 전달."""
    snap = _make_snapshot()
    cand = _make_candidate("sweet")
    payload = build_signals_payload(
        snap, {"strategy_one_d_v2": [cand]}, target_date="20260504"
    )
    assert payload.target_date == "2026-05-04"
    assert payload.asof != ""


def test_format_target_display_intraday():
    now = datetime(2026, 5, 4, 12, 30, tzinfo=KST)
    assert _format_target_display("20260504", now) == "2026-05-04 (장중)"


def test_format_target_display_after_close_buffer():
    now = datetime(2026, 5, 4, 15, 45, tzinfo=KST)
    assert _format_target_display("20260504", now) == "2026-05-04 (장 마감 직후)"


def test_format_target_display_closed():
    now = datetime(2026, 5, 4, 16, 30, tzinfo=KST)
    assert _format_target_display("20260504", now) == "2026-05-04"


def test_format_target_display_past_date():
    """target_date 가 오늘이 아닌 과거면 라벨 없이 ISO 만."""
    now = datetime(2026, 5, 4, 12, 30, tzinfo=KST)
    assert _format_target_display("20260501", now) == "2026-05-01"


# ---------------------------------------------------------------------------
# 'all' 통합 entry — Phase 3 (regret 기반 ticker dedup)
# ---------------------------------------------------------------------------

def _make_cand_for(ticker, score=80.0):
    from core.strategy_base import Candidate
    return Candidate(
        ticker=ticker,
        name=f"종목{ticker}",
        strategy="dummy",
        signal_date=pd.Timestamp("2026-05-04"),
        score=score,
        entry_price=7000.0,
        stop_loss=6800.0,
        target_1=7400.0,
        target_2=7800.0,
        current_price=7100.0,
        metadata={
            "rr_ratio": 2.0, "rr_band": "sweet", "atr_14": 100,
            "naver_url": f"http://x/{ticker}",
            "product_type": "STOCK",  # PR-B: 풀 분리에서 STOCK 풀로 진입
        },
    )


def _multi_strategy_snapshot():
    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-04T22:00:00+09:00",
        source={}, market_indices={},
        tickers={
            t: TickerSnapshot(
                ticker=t, name=f"종목{t}", current_price=7100,
                change_pct=0.5, volume=1000,
                fundamentals=Fundamentals(), flow=Flow(),
            )
            for t in ("001", "002", "003")
        },
    )


def test_all_entry_dedups_tickers_when_weight_config_given():
    """멀티 전략 후보 → strategy='all' entry 추가 + ticker dedup."""
    from core.decision.config import Priority, WeightConfig
    cfg = WeightConfig(
        priorities=[Priority("score", 100.0, "higher_better", "전략점수")],
    )
    snap = _multi_strategy_snapshot()
    cands = {
        "strategy_one_d_v2": [
            _make_cand_for("001", 90.0),
            _make_cand_for("002", 80.0),
        ],
        "strategy_two_cross_sectional_momentum": [
            _make_cand_for("001", 70.0),  # 동일 ticker 등장 — dedup 대상
            _make_cand_for("003", 60.0),
        ],
    }
    payload = build_signals_payload(snap, cands, weight_config=cfg)

    all_signals = [s for s in payload.signals if s.strategy.id == "all"]
    assert len(all_signals) == 3, "001/002/003 ticker 만 1건씩"
    assert {s.ticker for s in all_signals} == {"001", "002", "003"}
    assert payload.stats["total_signals"] == len(payload.signals)
    assert payload.filters["strategies"][0] == "ALL"
    # rank 1..3 부여
    ranks = sorted(s.ranking.rank for s in all_signals)
    assert ranks == [1, 2, 3]


def test_all_entry_omitted_without_weight_config():
    """weight_config 없으면 'all' entry 생성 안 함 (regret 계산 불가)."""
    snap = _make_snapshot()
    cands = {"strategy_one_d_v2": [_make_candidate("sweet")]}
    payload = build_signals_payload(snap, cands, weight_config=None)
    assert all(s.strategy.id != "all" for s in payload.signals)
    assert payload.filters["strategies"] == ["STRATEGY ONE"]


def test_all_entry_strategy_label():
    """'all' entry 의 strategy label/category."""
    from core.decision.config import Priority, WeightConfig
    cfg = WeightConfig(
        priorities=[Priority("score", 100.0, "higher_better", "전략점수")],
    )
    snap = _multi_strategy_snapshot()
    cands = {
        "strategy_one_d_v2": [_make_cand_for("001", 90.0)],
        "strategy_two_cross_sectional_momentum": [_make_cand_for("002", 80.0)],
    }
    payload = build_signals_payload(snap, cands, weight_config=cfg)
    all_sig = next(s for s in payload.signals if s.strategy.id == "all")
    assert all_sig.strategy.label == "ALL"


def test_timeframe_filters_follow_actual_signal_timeframes():
    """실제 signal에 있는 timeframe만 filters.timeframes 로 노출."""
    from core.decision.config import Priority, WeightConfig

    cfg = WeightConfig(
        priorities=[Priority("score", 100.0, "higher_better", "전략점수")],
    )
    snap = _multi_strategy_snapshot()
    cand_1d = _make_cand_for("001", 90.0)
    cand_1w = _make_cand_for("002", 80.0)
    cand_1w.timeframe = "1W"
    cand_30m = _make_cand_for("003", 70.0)
    cand_30m.timeframe = "30m"
    cands = {
        "strategy_one_d_v2": [cand_1d],
        "strategy_one_w_v2": [cand_1w],
        "strategy_one_30m_v2": [cand_30m],
    }

    payload = build_signals_payload(snap, cands, weight_config=cfg)

    assert payload.filters["timeframes"] == ["ALL", "1D", "1W", "30m"]
    assert "4H" not in payload.filters["timeframes"]


def test_signal_strength_normalized_to_0_to_100():
    """ranking.signal_strength = c.score / 10 (0~100 정규화)."""
    snap = _make_snapshot()
    cand = _make_candidate("sweet")
    cand.score = 870.0  # 0~1000 범위
    payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})
    sig = payload.signals[0]
    assert sig.ranking.signal_strength == 87.0


def test_regret_factors_serialized_with_4_axes():
    """weight_config 있을 때 regret_factors 4행 노출 + contribution = weight × normalized."""
    from core.decision.config import Priority, WeightConfig
    cfg = WeightConfig(
        priorities=[Priority("score", 100.0, "higher_better", "전략점수")],
    )
    snap = _multi_strategy_snapshot()
    cands = {
        "strategy_one_d_v2": [_make_cand_for("001", 90.0), _make_cand_for("002", 80.0)],
        "strategy_two_cross_sectional_momentum": [_make_cand_for("003", 70.0)],
    }
    payload = build_signals_payload(snap, cands, weight_config=cfg)
    all_signals = [s for s in payload.signals if s.strategy.id == "all"]
    assert len(all_signals) >= 1

    for sig in all_signals:
        rf = sig.ranking.decision.regret_factors
        assert rf is not None and len(rf) == 4
        keys = {f.key for f in rf}
        assert keys == {"bull_reward", "ensemble", "max_drawdown", "dist_to_stop"}
        for f in rf:
            assert abs(f.contribution - f.weight * f.normalized) < 0.01


def test_regret_factors_contribution_sum_equals_regret_score():
    """sum(contribution) ≈ regret_score (max_drawdown 은 dd_norm 사용 명시)."""
    from core.decision.config import Priority, WeightConfig
    cfg = WeightConfig(
        priorities=[Priority("score", 100.0, "higher_better", "전략점수")],
    )
    snap = _multi_strategy_snapshot()
    cands = {
        "strategy_one_d_v2": [
            _make_cand_for("001", 90.0),
            _make_cand_for("002", 80.0),
            _make_cand_for("003", 70.0),
        ],
    }
    payload = build_signals_payload(snap, cands, weight_config=cfg)
    all_signals = [s for s in payload.signals if s.strategy.id == "all"]
    for sig in all_signals:
        rs = sig.ranking.decision.regret_score
        rf = sig.ranking.decision.regret_factors
        assert rs is not None and rf is not None
        total = sum(f.contribution for f in rf)
        assert abs(total - rs) < 0.05, f"sum={total}, regret_score={rs}"


def test_strategy_one_1h_fallback_variants_skip_duplicate_ticker_in_raw_signals():
    """strategy_one_1h_v2/r1/r2 순차 실행 시 동일 ticker는 첫 entry만 유지."""
    snap = _multi_strategy_snapshot()
    base = _make_cand_for("001", 90.0)
    base.strategy = "strategy_one_1h_v2"
    base.timeframe = "1h"
    r1_dup = _make_cand_for("001", 85.0)
    r1_dup.strategy = "strategy_one_1h_v2_r1"
    r1_dup.timeframe = "1h"
    r2_unique = _make_cand_for("002", 80.0)
    r2_unique.strategy = "strategy_one_1h_v2_r2"
    r2_unique.timeframe = "1h"

    payload = build_signals_payload(
        snap,
        {
            "strategy_one_1h_v2": [base],
            "strategy_one_1h_v2_r1": [r1_dup],
            "strategy_one_1h_v2_r2": [r2_unique],
        },
        weight_config=None,
    )

    raw_signals = [s for s in payload.signals if s.strategy.id != "all"]
    assert [(s.ticker, s.strategy.id) for s in raw_signals] == [
        ("001", "strategy_one_1h_v2"),
        ("002", "strategy_one_1h_v2_r2"),
    ]
