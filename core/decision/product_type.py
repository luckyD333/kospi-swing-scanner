"""
core/decision/product_type.py — 종목 상품 유형 분류 + 풀 매핑.

PR-B (P0-2): ETN/ETF/REIT/SPAC 가 STOCK 풀에서 PER/ROE 가산 받는 결함 차단.

분류 우선순위 (가장 정확한 신호 우선):
  1. 명자 키워드: '스팩' / '기업인수목적' → SPAC
  2. 명자 키워드: '리츠' → REIT
  3. ETF API 명단 hit → ETN (7xxxxx) 또는 ETF (그 외)
  4. 정형 주식 코드 (6자리, 7로 시작 안 함) → STOCK
  5. 그 외 (7xxxxx 비-ETF 등) → UNKNOWN (D2: STOCK 폴백 대신 안전 분리)

UNKNOWN 후보는 후속 tradability_filter 에서 풀 진입 차단 + 경고 로그.
"""
from __future__ import annotations

from enum import Enum


class ProductType(str, Enum):
    """종목 상품 유형."""
    STOCK = "STOCK"
    ETN = "ETN"
    ETF = "ETF"
    REIT = "REIT"
    SPAC = "SPAC"
    UNKNOWN = "UNKNOWN"  # D2: 분류 실패 시 안전 분리


class Pool(str, Enum):
    """랭킹 풀 (UI/API 소비자 grouping 용 명시 축, D3)."""
    STOCK = "STOCK"
    ETN_ETF = "ETN_ETF"
    OTHER = "OTHER"  # REIT, SPAC, UNKNOWN


_SPAC_KEYWORDS = ("스팩", "기업인수목적")
_REIT_KEYWORDS = ("리츠",)
_ETN_KEYWORDS = ("ETN",)


def classify(ticker: str, name: str, etf_list: set[str] | None = None) -> ProductType:
    """ticker + 종목명 + ETF API 명단 → ProductType.

    Args:
        ticker: 6자리 KRX 종목 코드.
        name: 종목명 (한글).
        etf_list: 네이버 etfItemList API 의 itemcode 집합 (ETF + ETN 통합).

    Returns:
        ProductType — 분류 신호가 약하면 UNKNOWN.
    """
    etf_list = etf_list or set()

    # 1) 명자 키워드 — 가장 강한 신호
    if any(kw in name for kw in _SPAC_KEYWORDS):
        return ProductType.SPAC
    if any(kw in name for kw in _REIT_KEYWORDS):
        return ProductType.REIT

    # 2) ETF API 명단 — ETF 와 ETN 통합 source
    #    ETN 은 7xxxxx, ETF 는 그 외 (1/2/3/4xxxxx 일반적)
    if ticker in etf_list:
        if ticker.startswith("7"):
            return ProductType.ETN
        return ProductType.ETF

    # 3) 정형 주식 코드 → STOCK
    if len(ticker) == 6 and ticker.isdigit():
        if ticker.startswith("7"):
            # ETN 키워드를 Step 1이 아닌 여기서 체크하는 이유:
            # ETF API 명단에 있는 5xxxxx 종목도 이름에 "ETN"이 붙을 수 있어서
            # Step 1에 올리면 API 명단 우선 원칙(Step 2)이 깨짐.
            # 7xxxxx + API 명단 미포함인 경우에만 이름 키워드로 ETN 판정.
            if any(kw in name for kw in _ETN_KEYWORDS):
                return ProductType.ETN
            return ProductType.UNKNOWN  # D2 안전 분리
        return ProductType.STOCK

    # 4) 비정형 코드 → UNKNOWN
    return ProductType.UNKNOWN


def to_pool(pt: ProductType) -> Pool:
    """ProductType → Pool 매핑.

    STOCK → STOCK 풀, ETN/ETF → ETN_ETF 풀, 그 외 → OTHER (랭킹 제외 대상).
    """
    if pt == ProductType.STOCK:
        return Pool.STOCK
    if pt in (ProductType.ETN, ProductType.ETF):
        return Pool.ETN_ETF
    return Pool.OTHER
