"""test_tradability_filter.py — 거래가능성 필터 (PR-D Step 1).

각 필터 항목 (거래대금·일중변동·ATR·상하한가·NAV) 별 invariant 검증.
metadata 부재 시 skip(관대) + UNKNOWN product_type reject(D2).
"""
from __future__ import annotations

import pandas as pd

from core.decision.tradability_filter import (
    FilterThresholds,
    RejectionRecord,
    apply,
)
from core.strategy_base import Candidate


def _cand(ticker: str, **meta) -> Candidate:
    return Candidate(
        ticker=ticker, name=f"name_{ticker}", strategy="dummy",
        signal_date=pd.Timestamp("2026-05-07"), score=80.0,
        entry_price=10000.0, stop_loss=9800.0, target_1=10400.0, target_2=10800.0,
        metadata=dict(meta),
    )


# ---------------------------------------------------------------------------
# 거래대금 필터
# ---------------------------------------------------------------------------

def test_low_value_traded_stock_excluded():
    """일반주 20일 평균 거래대금 < 5억 → reject."""
    cands = [_cand("A", product_type="STOCK", value_traded_20d_avg=3e8)]
    passed, rejected = apply(cands)
    assert passed == []
    assert len(rejected) == 1
    assert rejected[0].reason == "min_value_traded"
    assert rejected[0].actual == 3e8
    assert rejected[0].threshold == 5e8


def test_low_value_traded_etn_uses_etn_threshold():
    """ETN 은 별도 임계값 (10억) 적용."""
    cands = [_cand("X", product_type="ETN", value_traded_20d_avg=8e8)]
    passed, rejected = apply(cands)
    assert passed == []
    assert rejected[0].reason == "min_value_traded"
    assert rejected[0].threshold == 1e9


def test_value_traded_skipped_when_metadata_missing():
    """value_traded_20d_avg 메타 없으면 해당 필터 skip (관대 모드)."""
    cands = [_cand("A", product_type="STOCK", atr_14=200)]
    passed, _ = apply(cands)
    assert len(passed) == 1


# ---------------------------------------------------------------------------
# 일중 변동폭 (호가 스프레드 대리)
# ---------------------------------------------------------------------------

def test_high_intraday_range_excluded():
    """일중 (high-low)/close × 100 > 5% → reject."""
    cands = [_cand("A", product_type="STOCK",
                   value_traded_20d_avg=1e10, intraday_range_pct=8.0)]
    passed, rejected = apply(cands)
    assert passed == []
    assert rejected[0].reason == "high_intraday_range"


def test_intraday_range_within_threshold_passes():
    """일중 변동폭 5% 이하 → 통과."""
    cands = [_cand("A", product_type="STOCK",
                   value_traded_20d_avg=1e10, intraday_range_pct=3.5)]
    passed, _ = apply(cands)
    assert len(passed) == 1


# ---------------------------------------------------------------------------
# ATR 손절 비율
# ---------------------------------------------------------------------------

def test_stop_too_tight_relative_to_atr():
    """손절폭 ÷ ATR(14) < 1.0 → reject (변동성 대비 손절 과소)."""
    cand = Candidate(
        ticker="A", name="A", strategy="d", signal_date=pd.Timestamp("2026-05-07"),
        score=80.0, entry_price=10000, stop_loss=9950,  # 손절폭 50
        target_1=10400, target_2=10800,
        metadata={"product_type": "STOCK", "atr_14": 100,
                  "value_traded_20d_avg": 1e10},  # ATR 100, 손절 50 < 100
    )
    passed, rejected = apply([cand])
    assert passed == []
    assert rejected[0].reason == "atr_stop_too_tight"


def test_stop_above_atr_passes():
    """손절폭 ≥ ATR → 통과."""
    cand = Candidate(
        ticker="A", name="A", strategy="d", signal_date=pd.Timestamp("2026-05-07"),
        score=80.0, entry_price=10000, stop_loss=9800,  # 손절폭 200
        target_1=10400, target_2=10800,
        metadata={"product_type": "STOCK", "atr_14": 150,
                  "value_traded_20d_avg": 1e10},  # 200 > 150
    )
    passed, _ = apply([cand])
    assert len(passed) == 1


# ---------------------------------------------------------------------------
# 상하한가 근접
# ---------------------------------------------------------------------------

def test_price_limit_proximity_excluded():
    """상한가 95% 이상 (proximity_pct < 5.0) → reject."""
    cands = [_cand("A", product_type="STOCK",
                   value_traded_20d_avg=1e10, price_limit_proximity_pct=2.0)]
    passed, rejected = apply(cands)
    assert passed == []
    assert rejected[0].reason == "price_limit_proximity"


# ---------------------------------------------------------------------------
# NAV 괴리율 (ETN/ETF 한정)
# ---------------------------------------------------------------------------

def test_nav_premium_excess_excluded_for_etn():
    """ETN 의 |NAV 괴리율| > 2% → reject."""
    cands = [_cand("X", product_type="ETN",
                   value_traded_20d_avg=1e10, nav_premium_pct=3.5)]
    passed, rejected = apply(cands)
    assert passed == []
    assert rejected[0].reason == "nav_premium_excess"
    assert rejected[0].actual == 3.5


def test_nav_premium_negative_also_excluded():
    """음수 NAV 괴리율도 절대값 기준으로 검사."""
    cands = [_cand("X", product_type="ETN",
                   value_traded_20d_avg=1e10, nav_premium_pct=-2.5)]
    passed, rejected = apply(cands)
    assert passed == []
    assert rejected[0].reason == "nav_premium_excess"
    assert rejected[0].actual == 2.5  # 절대값


def test_nav_premium_not_checked_for_stock():
    """STOCK 은 NAV 괴리율 검사 미적용."""
    cands = [_cand("A", product_type="STOCK",
                   value_traded_20d_avg=1e10, nav_premium_pct=10.0)]
    passed, _ = apply(cands)
    assert len(passed) == 1


# ---------------------------------------------------------------------------
# UNKNOWN product_type 차단 (D2)
# ---------------------------------------------------------------------------

def test_unknown_product_type_excluded():
    """UNKNOWN 후보는 다른 메타 통과해도 reject (D2 안전 분리)."""
    cands = [_cand("A", value_traded_20d_avg=1e10)]  # product_type 없음 → UNKNOWN
    passed, rejected = apply(cands)
    assert passed == []
    assert rejected[0].reason == "product_type_unknown"


def test_explicit_unknown_excluded():
    """명시적 product_type=UNKNOWN 도 동일 처리."""
    cands = [_cand("A", product_type="UNKNOWN", value_traded_20d_avg=1e10)]
    passed, rejected = apply(cands)
    assert passed == []
    assert rejected[0].reason == "product_type_unknown"


# ---------------------------------------------------------------------------
# 통합 / 임계값 커스터마이즈
# ---------------------------------------------------------------------------

def test_passes_when_all_metadata_clean():
    """모든 메타 정상 + 임계값 내 → 통과."""
    cand = Candidate(
        ticker="A", name="A", strategy="d", signal_date=pd.Timestamp("2026-05-07"),
        score=80.0, entry_price=10000, stop_loss=9800,
        target_1=10400, target_2=10800,
        metadata={
            "product_type": "STOCK",
            "value_traded_20d_avg": 1e10,
            "intraday_range_pct": 2.0,
            "atr_14": 150,
            "price_limit_proximity_pct": 50.0,
        },
    )
    passed, rejected = apply([cand])
    assert len(passed) == 1
    assert rejected == []


def test_rejection_record_to_dict():
    """RejectionRecord JSONL 직렬화 호환."""
    cands = [_cand("A", product_type="STOCK", value_traded_20d_avg=1e8)]
    _, rejected = apply(cands)
    record = rejected[0].to_dict()
    assert record["ticker"] == "A"
    assert record["product_type"] == "STOCK"
    assert record["reason"] == "min_value_traded"
    assert record["actual"] == 1e8


def test_custom_thresholds_applied():
    """FilterThresholds 커스텀 — 더 보수적 거래대금 임계."""
    cands = [_cand("A", product_type="STOCK", value_traded_20d_avg=8e8)]
    # 기본 5억 → 통과
    passed, _ = apply(cands)
    assert len(passed) == 1
    # 임계 10억으로 올리면 reject
    th = FilterThresholds(min_value_traded_krw_stock=1e9)
    passed, rejected = apply(cands, th)
    assert passed == []
    assert rejected[0].reason == "min_value_traded"


# ---------------------------------------------------------------------------
# enrich_metadata helper
# ---------------------------------------------------------------------------

def test_enrich_metadata_computes_value_traded():
    """1D OHLCV → value_traded_20d_avg = (close × volume) 평균."""
    from core.decision.tradability_filter import enrich_metadata
    df = pd.DataFrame({
        "close": [100.0] * 20,
        "high": [101.0] * 20,
        "low": [99.0] * 20,
        "volume": [1000] * 20,
    })
    cand = _cand("A", product_type="STOCK")
    enrich_metadata(cand, df)
    # 100 × 1000 × 20개 평균 = 100000
    assert cand.metadata["value_traded_20d_avg"] == 100000.0
    # intraday range = (101-99)/100 × 100 = 2.0
    assert cand.metadata["intraday_range_pct"] == 2.0


def test_enrich_metadata_handles_empty_ohlcv():
    """빈 DataFrame → 메타 주입 안 함, 예외 없음."""
    from core.decision.tradability_filter import enrich_metadata
    cand = _cand("A", product_type="STOCK")
    enrich_metadata(cand, pd.DataFrame())
    enrich_metadata(cand, None)
    assert "value_traded_20d_avg" not in cand.metadata
    assert "intraday_range_pct" not in cand.metadata


# ---------------------------------------------------------------------------
# write_rejection_log
# ---------------------------------------------------------------------------

def test_write_rejection_log_creates_jsonl(tmp_path):
    """RejectionRecord 리스트 → JSONL append (한 줄당 한 객체)."""
    from core.decision.tradability_filter import write_rejection_log
    log = tmp_path / "filter_rejected.log"
    records = [
        RejectionRecord("A", "STOCK", "min_value_traded", 1e8, 5e8),
        RejectionRecord("B", "ETN", "nav_premium_excess", 3.5, 2.0),
    ]
    write_rejection_log(records, log)
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    import json as _json
    rec0 = _json.loads(lines[0])
    assert rec0["ticker"] == "A"
    assert rec0["reason"] == "min_value_traded"
    rec1 = _json.loads(lines[1])
    assert rec1["product_type"] == "ETN"


def test_write_rejection_log_appends_existing(tmp_path):
    """이미 존재하는 로그에 append (overwrite 아님)."""
    from core.decision.tradability_filter import write_rejection_log
    log = tmp_path / "filter_rejected.log"
    write_rejection_log([RejectionRecord("A", "STOCK", "x", 0, 0)], log)
    write_rejection_log([RejectionRecord("B", "STOCK", "y", 0, 0)], log)
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


def test_write_empty_list_noop(tmp_path):
    """빈 list → 파일 미생성."""
    from core.decision.tradability_filter import write_rejection_log
    log = tmp_path / "filter_rejected.log"
    write_rejection_log([], log)
    assert not log.exists()
