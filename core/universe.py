"""
core/universe.py — 종목 유니버스 필터 (Naver 단일 소스).

Strategy D v2 §3.4 (시총·유동성·상장경과·관리종목 등) 구현.
시가총액은 네이버 시총 페이지 크롤링 raw 값을 사용.

거래정지/관리종목 제외는 데이터 소스가 메타데이터를 제공하지 않으면 스킵.

PR-B: ProductType 분류 (STOCK/ETN/ETF/REIT/SPAC/UNKNOWN) 부여 — 풀 분리 동력.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .data_fetch import DataClient
from .decision.product_type import ProductType, classify

logger = logging.getLogger(__name__)


@dataclass
class UniverseFilter:
    """시총 + 유동성 필터 파라미터 (모두 inclusive 범위)."""
    min_market_cap_bil: float = 2000.0      # 최소 시총 (억)
    max_market_cap_bil: float = 30000.0     # 최대 시총 (억)
    min_daily_volume: int = 100_000          # 일 최소 거래량
    market: str = "KOSPI"
    max_universe_size: int | None = None  # 시총 상위 N (None = 무제한)


@dataclass
class UniverseResult:
    """필터 통과 ticker + 시총 lookup + ProductType 분류 (PR-B)."""
    tickers: list[str]
    cap_lookup: dict[str, float]   # ticker → 원 단위 시총 (네이버 raw)
    name_lookup: dict[str, str]    # ticker → 종목명
    pre_cap_limit_size: int = 0    # cap range 통과했지만 top-N 컷 전
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
      2) 시총 범위 [min, max]억 필터
      3) max_universe_size 지정 시 시총 상위 N 컷오프

    실패 모드:
      - 시총 조회 실패 → 필터 없이 전종목 통과 (warning)
    """
    all_tickers = client.get_tickers(filt.market, target_date)

    cap_lookup: dict[str, float] = {}
    name_lookup: dict[str, str] = {}

    # 1) 네이버에서 추정 시총 + 종목명 확보
    cap_df = client.get_market_cap(filt.market, target_date)
    if not cap_df.empty and "시가총액" in cap_df.columns:
        cap_lookup = cap_df["시가총액"].to_dict()
        if "종목명" in cap_df.columns:
            name_lookup = cap_df["종목명"].to_dict()

    # 2) 시총 lookup 자체가 없으면 필터 우회
    if not cap_lookup:
        logger.warning("  시가총액 조회 실패. 필터 없이 전종목 진행.")
        return UniverseResult(
            tickers=list(all_tickers),
            cap_lookup={},
            name_lookup=name_lookup,
            pre_cap_limit_size=0,
        )

    # 3) 시총 범위 필터 (억 단위)
    filtered = [
        t for t in all_tickers
        if filt.min_market_cap_bil
        <= cap_lookup.get(t, 0) / 100_000_000
        <= filt.max_market_cap_bil
    ]

    # 4) 시총 상위 N 컷오프 (top-N cap limit)
    pre_limit = len(filtered)
    if filt.max_universe_size and pre_limit > filt.max_universe_size:
        filtered_ranked = sorted(
            filtered, key=lambda t: cap_lookup.get(t, 0), reverse=True
        )
        filtered_final = filtered_ranked[: filt.max_universe_size]
        logger.info(
            f"  유니버스 cap 적용: {pre_limit} → {filt.max_universe_size}"
        )
    else:
        filtered_final = filtered

    # 5) ProductType 분류 (PR-B) — ETF 명단 1회 fetch 후 ticker 별 매핑.
    try:
        etf_list = client.get_etf_list(target_date)
    except Exception as e:
        logger.warning(f"ETF 명단 fetch 실패, 키워드/prefix 만으로 분류: {e}")
        etf_list = set()
    product_type_lookup: dict[str, ProductType] = {
        t: classify(t, name_lookup.get(t, ""), etf_list)
        for t in filtered_final
    }
    unknown_count = sum(
        1 for pt in product_type_lookup.values() if pt == ProductType.UNKNOWN
    )
    if unknown_count:
        logger.info(f"  ProductType UNKNOWN 분류: {unknown_count}건 (D2 안전 분리)")

    return UniverseResult(
        tickers=filtered_final,
        cap_lookup=cap_lookup,
        name_lookup=name_lookup,
        pre_cap_limit_size=pre_limit,
        product_type_lookup=product_type_lookup,
    )
