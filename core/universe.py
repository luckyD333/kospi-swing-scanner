"""
core/universe.py — 종목 유니버스 필터 (Naver 단일 소스).

Strategy D v2 §3.4 (시총·유동성·상장경과·관리종목 등) 구현.
시가총액은 네이버 시총 페이지 크롤링 raw 값을 사용.

거래정지는 시총 목록의 당일 거래량으로 제외. 관리종목 제외는 소스가
메타데이터를 제공하지 않으면 스킵.

PR-B: ProductType 분류 (STOCK/ETN/ETF/REIT/SPAC/UNKNOWN) 부여 — 풀 분리 동력.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .data_fetch import DataClient
from .decision.product_type import (
    ProductType,
    classify,
    is_swing_ineligible_product_name,
)

logger = logging.getLogger(__name__)


@dataclass
class UniverseFilter:
    """시총 + 유동성 필터 파라미터 (모두 inclusive 범위)."""
    min_market_cap_bil: float = 5000.0      # 최소 시총 (억) — 2026-05-19 상향: 베타 추정 안정성 + 슬리피지 감소
    max_market_cap_bil: float = 30000.0     # 최대 시총 (억)
    min_daily_volume: int = 100_000          # 일 최소 거래량
    market: str = "KOSPI"
    max_universe_size: int | None = 100  # 일반 주식 거래량 상위 N (None = 무제한)
    max_etf_size: int = 30               # ETF 거래량 상위 N (0 = 제외)


@dataclass
class UniverseResult:
    """필터 통과 ticker + 시총 lookup + ProductType 분류 (PR-B)."""
    tickers: list[str]
    cap_lookup: dict[str, float]   # ticker → 원 단위 시총 (네이버 raw)
    name_lookup: dict[str, str]    # ticker → 종목명
    pre_cap_limit_size: int = 0    # 거래량 top-N 컷 전 주식 + ETF 수
    product_type_lookup: dict[str, ProductType] = field(default_factory=dict)
    """ticker → ProductType. ETF API 명단 + 종목명 키워드 + 코드 prefix 분류 (PR-B)."""


def build_universe(
    client: DataClient,
    target_date: str,
    filt: UniverseFilter,
) -> UniverseResult:
    """
    Phase 1 유니버스 필터링 (Naver 단일 소스).

    절차:
      1) 네이버 전종목 + 추정 시총 (sise_market_sum 크롤링 1회)
      2) 일반 주식: 시총 범위 [min, max]억 + 당일 거래량 필터
      3) ETF: 당일 거래량 필터 (주식 시총 범위 미적용)
      4) 부적합 상품 제외 후 주식/ETF 각각 거래량 상위 N개 선택

    실패 모드:
      - 시총 조회 실패 → 필터 없이 전종목 통과 (warning)
    """
    all_tickers = client.get_tickers(filt.market, target_date)

    cap_lookup: dict[str, float] = {}
    name_lookup: dict[str, str] = {}
    volume_lookup: dict[str, float] | None = None

    # 1) 네이버에서 추정 시총 + 종목명 확보
    cap_df = client.get_market_cap(filt.market, target_date)
    if not cap_df.empty and "시가총액" in cap_df.columns:
        cap_lookup = cap_df["시가총액"].to_dict()
        if "종목명" in cap_df.columns:
            name_lookup = cap_df["종목명"].to_dict()
        if "거래량" in cap_df.columns:
            volume_lookup = cap_df["거래량"].astype(float).fillna(0).to_dict()

    # 2) 시총 lookup 자체가 없으면 필터 우회
    if not cap_lookup:
        logger.warning("  시가총액 조회 실패. 필터 없이 전종목 진행.")
        return UniverseResult(
            tickers=list(all_tickers),
            cap_lookup={},
            name_lookup=name_lookup,
            pre_cap_limit_size=0,
        )

    # 3) ProductType 분류 (PR-B) — ETF 명단 1회 fetch 후 ticker 별 매핑.
    try:
        etf_list = client.get_etf_list(target_date)
    except Exception as e:
        logger.warning(f"ETF 명단 fetch 실패, 키워드/prefix 만으로 분류: {e}")
        etf_list = set()
    product_type_lookup: dict[str, ProductType] = {
        t: classify(t, name_lookup.get(t, ""), etf_list)
        for t in all_tickers
    }
    unknown_count = sum(
        1 for pt in product_type_lookup.values() if pt == ProductType.UNKNOWN
    )
    if unknown_count:
        logger.info(f"  ProductType UNKNOWN 분류: {unknown_count}건 (D2 안전 분리)")

    def volume_ok(ticker: str) -> bool:
        return (
            volume_lookup is None
            or volume_lookup.get(ticker, 0) >= filt.min_daily_volume
        )

    stocks = [
        ticker for ticker in all_tickers
        if product_type_lookup[ticker] not in (ProductType.ETF, ProductType.ETN)
        and filt.min_market_cap_bil
        <= cap_lookup.get(ticker, 0) / 100_000_000
        <= filt.max_market_cap_bil
        and volume_ok(ticker)
    ]
    etfs = [
        ticker for ticker in all_tickers
        if product_type_lookup[ticker] == ProductType.ETF and volume_ok(ticker)
    ]

    before_name_filter = stocks + etfs
    stocks = [
        ticker for ticker in stocks
        if not is_swing_ineligible_product_name(name_lookup.get(ticker, ""))
    ]
    etfs = [
        ticker for ticker in etfs
        if not is_swing_ineligible_product_name(name_lookup.get(ticker, ""))
    ]
    eligible = stocks + etfs
    if len(eligible) < len(before_name_filter):
        eligible_set = set(eligible)
        excluded = [t for t in before_name_filter if t not in eligible_set]
        sample = ", ".join(
            f"{t}({name_lookup.get(t, t)})"
            for t in excluded[:5]
        )
        suffix = "..." if len(excluded) > 5 else ""
        logger.info(
            f"  스윙 부적합 상품명 제외: {len(excluded)}건 (예: {sample}{suffix})"
        )

    rank_lookup = volume_lookup or cap_lookup
    stocks.sort(key=lambda ticker: rank_lookup.get(ticker, 0), reverse=True)
    etfs.sort(key=lambda ticker: rank_lookup.get(ticker, 0), reverse=True)
    pre_limit = len(stocks) + len(etfs)
    if filt.max_universe_size is not None:
        stocks = stocks[:filt.max_universe_size]
    etfs = etfs[:filt.max_etf_size] if filt.max_etf_size > 0 else []
    logger.info(
        f"  거래량 상위 유니버스: 주식 {len(stocks)}개 + ETF {len(etfs)}개"
    )

    return UniverseResult(
        tickers=stocks + etfs,
        cap_lookup=cap_lookup,
        name_lookup=name_lookup,
        pre_cap_limit_size=pre_limit,
        product_type_lookup=product_type_lookup,
    )
