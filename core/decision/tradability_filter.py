"""
core/decision/tradability_filter.py — 후보 풀 진입 단계 거래가능성 hard filter.

PR-D (P1-2): 거래량 부족·일중 변동 과대·손절 과소·상하한가 근접·NAV 괴리율 위배
종목을 ranking 이전에 차단. 좋은 점수가 나와도 실거래 불가능한 신호 제거.

Round 4 결정 (가용 데이터 대체):
  - 호가 스프레드 raw 미보유 → 일중 변동폭 (high-low)/close × 100 으로 대리
  - KRX 종목 마스터 미보유 → product_type 기반 분기
  - NAV 괴리율은 ETF API 가 NAV 필드 제공할 때만 검사

설계:
  - candidate.metadata 의 가용 키만 검사 (필요 metadata 부재 시 해당 필터 skip)
  - rejection 사유는 RejectionRecord 로 기록 → 호출자가 JSONL 로 영속화 가능
  - 필터 임계값은 FilterThresholds dataclass — yaml 로드는 PR-D Step 2 에서 추가
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from core.strategy_base import Candidate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FilterThresholds:
    """필터 임계값 — profile=standard 기본값.

    profile=strict 운영, loose 백테스트 디버그용. 외부화는 PR-D Step 2.
    """
    min_value_traded_krw_stock: float = 5e8       # 20일 평균 거래대금 (원), 일반주 5억
    min_value_traded_krw_etn_etf: float = 1e9     # ETN/ETF 별도 기준 10억 (시드 작은 ETN 회피)
    max_intraday_range_pct: float = 5.0           # 일중 (high-low)/close × 100, 호가 스프레드 대리
    atr_stop_min_ratio: float = 1.0               # 손절폭 ÷ ATR(14) 최소 비율. 미만 시 reject
    max_price_limit_proximity_pct: float = 5.0    # 상한가 95% 또는 하한가 105% 진입 차단
    max_nav_premium_abs_pct: float = 2.0          # ETN/ETF 한정 NAV 괴리율 절대값


@dataclass(frozen=True)
class RejectionRecord:
    """필터 탈락 후보 사유 기록 — JSONL 영속화 (filter_rejected.log) 용 페이로드."""
    ticker: str
    product_type: str
    reason: str          # min_value_traded / high_intraday_range / atr_stop_too_tight /
                         # price_limit_proximity / nav_premium_excess / product_type_unknown
    actual: float
    threshold: float

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "product_type": self.product_type,
            "reason": self.reason,
            "actual": self.actual,
            "threshold": self.threshold,
        }


def _check_value_traded(
    meta: dict, product_type: str, th: FilterThresholds,
) -> tuple[float, float] | None:
    """거래대금 부족 검사. (actual, threshold) 또는 None (통과)."""
    actual = meta.get("value_traded_20d_avg")
    if actual is None:
        return None
    threshold = (
        th.min_value_traded_krw_etn_etf
        if product_type in ("ETN", "ETF")
        else th.min_value_traded_krw_stock
    )
    return (float(actual), threshold) if actual < threshold else None


def _check_intraday_range(
    meta: dict, th: FilterThresholds,
) -> tuple[float, float] | None:
    """일중 변동폭 과대 검사 (호가 스프레드 대리)."""
    actual = meta.get("intraday_range_pct")
    if actual is None:
        return None
    return (float(actual), th.max_intraday_range_pct) if actual > th.max_intraday_range_pct else None


def _check_atr_stop_ratio(
    cand: Candidate, meta: dict, th: FilterThresholds,
) -> tuple[float, float] | None:
    """손절폭 ÷ ATR(14) 비율이 임계 미만 시 reject (변동성 대비 손절 과소)."""
    atr = meta.get("atr_14")
    entry = getattr(cand, "entry_price", None)
    stop = getattr(cand, "stop_loss", None)
    if atr is None or entry is None or stop is None or atr <= 0:
        return None
    stop_distance = abs(entry - stop)
    ratio = stop_distance / float(atr)
    return (ratio, th.atr_stop_min_ratio) if ratio < th.atr_stop_min_ratio else None


def _check_price_limit_proximity(
    meta: dict, th: FilterThresholds,
) -> tuple[float, float] | None:
    """상한가 95% 이상 또는 하한가 105% 이내 근접 시 reject.

    metadata key 'price_limit_proximity_pct': 0 = 정확히 상/하한가 도달, 100 = 충분히 떨어짐.
    임계 (예: 5.0) 미만이면 위험.
    """
    actual = meta.get("price_limit_proximity_pct")
    if actual is None:
        return None
    return (float(actual), th.max_price_limit_proximity_pct) if actual < th.max_price_limit_proximity_pct else None


def _check_nav_premium(
    meta: dict, product_type: str, th: FilterThresholds,
) -> tuple[float, float] | None:
    """ETN/ETF 한정 NAV 괴리율 절대값 임계 초과 시 reject."""
    if product_type not in ("ETN", "ETF"):
        return None
    actual = meta.get("nav_premium_pct")
    if actual is None:
        return None
    abs_actual = abs(float(actual))
    return (abs_actual, th.max_nav_premium_abs_pct) if abs_actual > th.max_nav_premium_abs_pct else None


_CHECKS = (
    ("min_value_traded", _check_value_traded),
    ("high_intraday_range", _check_intraday_range),
    ("atr_stop_too_tight", None),  # _check_atr_stop_ratio 는 Candidate 필요 — 별도 처리
    ("price_limit_proximity", _check_price_limit_proximity),
    ("nav_premium_excess", _check_nav_premium),
)


def apply(
    candidates: list[Candidate],
    thresholds: FilterThresholds | None = None,
) -> tuple[list[Candidate], list[RejectionRecord]]:
    """후보 리스트 → (통과, 탈락 사유). 첫 번째 위배 사유로 reject (단축 평가).

    필요 metadata 부재 시 해당 필터 skip — 관대 모드. UNKNOWN product_type 후보는
    'product_type_unknown' 사유로 reject (D2 안전 분리).
    """
    th = thresholds or FilterThresholds()
    passed: list[Candidate] = []
    rejected: list[RejectionRecord] = []
    for cand in candidates:
        meta = cand.metadata or {}
        product_type = str(meta.get("product_type", "UNKNOWN"))
        # D2: UNKNOWN 후보는 풀 진입 차단
        if product_type == "UNKNOWN":
            rejected.append(RejectionRecord(
                ticker=cand.ticker, product_type=product_type,
                reason="product_type_unknown", actual=0.0, threshold=0.0,
            ))
            continue
        # 메타 기반 검사
        value_check = _check_value_traded(meta, product_type, th)
        if value_check is not None:
            actual, thr = value_check
            rejected.append(RejectionRecord(
                cand.ticker, product_type, "min_value_traded", actual, thr,
            ))
            continue
        range_check = _check_intraday_range(meta, th)
        if range_check is not None:
            actual, thr = range_check
            rejected.append(RejectionRecord(
                cand.ticker, product_type, "high_intraday_range", actual, thr,
            ))
            continue
        atr_check = _check_atr_stop_ratio(cand, meta, th)
        if atr_check is not None:
            actual, thr = atr_check
            rejected.append(RejectionRecord(
                cand.ticker, product_type, "atr_stop_too_tight", actual, thr,
            ))
            continue
        prox_check = _check_price_limit_proximity(meta, th)
        if prox_check is not None:
            actual, thr = prox_check
            rejected.append(RejectionRecord(
                cand.ticker, product_type, "price_limit_proximity", actual, thr,
            ))
            continue
        nav_check = _check_nav_premium(meta, product_type, th)
        if nav_check is not None:
            actual, thr = nav_check
            rejected.append(RejectionRecord(
                cand.ticker, product_type, "nav_premium_excess", actual, thr,
            ))
            continue
        passed.append(cand)
    return passed, rejected


def enrich_metadata(cand: Candidate, ohlcv_1d: pd.DataFrame | None) -> None:
    """1D OHLCV 에서 거래가능성 메타 계산해 cand.metadata 에 in-place 주입.

    주입 키 (가용 컬럼이 있을 때만):
      - value_traded_20d_avg: close × volume 의 20일 평균 (원)
      - intraday_range_pct: 마지막 봉 (high-low)/close × 100 (호가 스프레드 대리)
    """
    if ohlcv_1d is None or ohlcv_1d.empty:
        return
    cols = set(ohlcv_1d.columns)
    if "close" in cols and "volume" in cols:
        try:
            tail = ohlcv_1d.tail(20)
            avg = float((tail["close"] * tail["volume"]).mean())
            if avg == avg:  # NaN 방지
                cand.metadata["value_traded_20d_avg"] = avg
        except Exception as e:
            logger.debug(f"value_traded 계산 실패 ({cand.ticker}): {e}")
    if {"high", "low", "close"}.issubset(cols):
        try:
            last = ohlcv_1d.iloc[-1]
            close = float(last["close"])
            if close > 0:
                rng = (float(last["high"]) - float(last["low"])) / close * 100.0
                cand.metadata["intraday_range_pct"] = rng
        except Exception as e:
            logger.debug(f"intraday_range 계산 실패 ({cand.ticker}): {e}")


def write_rejection_log(
    rejected: list[RejectionRecord], log_path: Path | str,
) -> None:
    """RejectionRecord 리스트 → JSONL append (filter_rejected.log).

    스키마:
      {"ticker": "...", "product_type": "...", "reason": "...",
       "actual": float, "threshold": float}
    """
    if not rejected:
        return
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for rec in rejected:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
