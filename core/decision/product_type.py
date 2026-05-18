"""
core/decision/product_type.py — 종목 상품 유형 분류 + 풀 매핑.

PR-B (P0-2): ETN/ETF/REIT/SPAC 가 STOCK 풀에서 PER/ROE 가산 받는 결함 차단.

분류 우선순위 (가장 정확한 신호 우선):
  1. 명자 키워드: '스팩' / '기업인수목적' → SPAC
  2. 명자 키워드: '리츠' → REIT
  3. ETF API 명단 hit → ETN (7xxxxx) 또는 ETF (그 외)
  4. 정형 주식 코드 (6자리, 7로 시작 안 함) → STOCK
  5. 신형 우선주 코드 (5자리 숫자 + 1 알파벳, 예: 02826K) → STOCK
  6. 그 외 (7xxxxx 비-ETF 등) → UNKNOWN (D2: STOCK 폴백 대신 안전 분리)

UNKNOWN 후보는 후속 tradability_filter 에서 풀 진입 차단 + 경고 로그.

Task 1 (Plan 2026-05-08): 3-tier 자산군 분류.
  - AssetClass enum: STOCK / EQUITY_ETF / BOND_ETF / OTHER
  - classify_asset_class(product_type, name) → AssetClass
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


class AssetClass(str, Enum):
    """자산군 3-tier 분류 (Task 1)."""
    STOCK = "STOCK"
    EQUITY_ETF = "EQUITY_ETF"
    BOND_ETF = "BOND_ETF"
    OTHER = "OTHER"


class Pool(str, Enum):
    """랭킹 풀 (UI/API 소비자 grouping 용 명시 축, D3)."""
    STOCK = "STOCK"
    ETN_ETF = "ETN_ETF"
    OTHER = "OTHER"  # REIT, SPAC, UNKNOWN


_SPAC_KEYWORDS = ("스팩", "기업인수목적")
_REIT_KEYWORDS = ("리츠",)
_ETN_KEYWORDS = ("ETN",)

# Task 1: 채권 ETF 감지 키워드 (정확히 이 7개만)
BOND_KEYWORDS = {"채권", "초단기채", "회사채", "국고", "금리", "단기자금", "MMF"}


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
    #    ETN 은 7xxxxx 또는 종목명 'ETN' 포함 (55xxxx 등 비-7 코드 ETN도 존재)
    if ticker in etf_list:
        if ticker.startswith("7") or any(kw in name for kw in _ETN_KEYWORDS):
            return ProductType.ETN
        return ProductType.ETF

    # 3) 정형 주식 코드 → STOCK
    if len(ticker) == 6 and ticker.isdigit():
        if ticker.startswith("7"):
            if any(kw in name for kw in _ETN_KEYWORDS):
                return ProductType.ETN
            return ProductType.UNKNOWN  # D2 안전 분리
        # 5xxxxx 등 비-7 코드 ETN: etfItemList 미등록이어도 이름으로 판정
        if any(kw in name for kw in _ETN_KEYWORDS):
            return ProductType.ETN
        return ProductType.STOCK

    # 4) 신형 우선주 코드 (5자리 숫자 + 1 알파벳, 예: 02826K = 삼성물산우B) → STOCK
    #    KRX 가 우B/우C 등 신형 우선주에 부여하는 alphanumeric 코드. 본주와 동일 발행사라
    #    fundamentals/regime 신호 유효. ETF API 명단(step 2)과 ETN/ETF 직렬코드(\d{4}[A-Z]\d)는
    #    여기 도달하기 전에 분류되므로 상호배타적.
    if len(ticker) == 6 and ticker[:5].isdigit() and ticker[5:].isalpha() and ticker[5:].isupper():
        return ProductType.STOCK

    # 5) 비정형 코드 → UNKNOWN
    return ProductType.UNKNOWN


def classify_asset_class(product_type: ProductType, name: str) -> AssetClass:
    """ProductType + 종목명 → AssetClass (3-tier 자산군 분류).

    주식(STOCK) / 주식형ETF(EQUITY_ETF) / 채권형ETF(BOND_ETF) / 기타(OTHER) 로 분류.
    종목명의 채권 키워드 매칭으로 채권 ETF 감지.

    Args:
        product_type: ProductType enum (STOCK/ETF/ETN/REIT/SPAC/UNKNOWN).
        name: 종목명 (한글).

    Returns:
        AssetClass — STOCK | EQUITY_ETF | BOND_ETF | OTHER.
    """
    if product_type == ProductType.STOCK:
        return AssetClass.STOCK

    if product_type in (ProductType.ETF, ProductType.ETN):
        if any(kw in name for kw in BOND_KEYWORDS):
            return AssetClass.BOND_ETF
        return AssetClass.EQUITY_ETF

    return AssetClass.OTHER


def to_pool(pt: ProductType) -> Pool:
    """ProductType → Pool 매핑.

    STOCK → STOCK 풀, ETN/ETF → ETN_ETF 풀, 그 외 → OTHER (랭킹 제외 대상).
    """
    if pt == ProductType.STOCK:
        return Pool.STOCK
    if pt in (ProductType.ETN, ProductType.ETF):
        return Pool.ETN_ETF
    return Pool.OTHER
