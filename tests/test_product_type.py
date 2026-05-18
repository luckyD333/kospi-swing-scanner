"""test_product_type.py — ProductType 분류기 + Pool 매핑 검증 (PR-B Step 1).

D2 결정: 분류 실패 시 STOCK 폴백 대신 UNKNOWN 으로 안전 분리.
"""
from __future__ import annotations

import pytest

from core.decision.product_type import Pool, ProductType, classify, to_pool


# ---------------------------------------------------------------------------
# 명자 키워드 분류 (가장 강한 신호)
# ---------------------------------------------------------------------------

def test_classify_spac_by_name_keyword():
    """명자에 '스팩' → SPAC."""
    assert classify("123456", "신한제10호스팩") == ProductType.SPAC


def test_classify_spac_by_kibeop_keyword():
    """명자에 '기업인수목적' → SPAC."""
    assert classify("234567", "삼성기업인수목적10호") == ProductType.SPAC


def test_classify_reit_by_name_keyword():
    """명자에 '리츠' → REIT."""
    assert classify("330590", "롯데리츠") == ProductType.REIT


def test_spac_keyword_overrides_etf_list():
    """명자 키워드가 ETF API hit 보다 우선 (잘못 등록된 케이스 방지)."""
    assert classify("123456", "이상한스팩", etf_list={"123456"}) == ProductType.SPAC


# ---------------------------------------------------------------------------
# ETF API 명단 분류
# ---------------------------------------------------------------------------

def test_classify_etf_by_api_list():
    """ETF API 명단 hit + 7로 시작 안 함 → ETF."""
    assert classify("069500", "KODEX 200", etf_list={"069500"}) == ProductType.ETF


def test_classify_etn_by_7_prefix_in_etf_list():
    """ETF API 명단 hit + 7xxxxx → ETN."""
    assert classify("760013", "키움레버리지반도체TOP10ETN", etf_list={"760013"}) == ProductType.ETN


def test_classify_etn_5_prefix_in_etf_list():
    """ETF API 명단 hit + 5xxxxx → 이름에 'ETN' 있으면 ETN, 없으면 ETF."""
    assert classify("530031", "어떤 ETN", etf_list={"530031"}) == ProductType.ETN
    assert classify("530031", "KODEX 200", etf_list={"530031"}) == ProductType.ETF


def test_classify_etn_5_prefix_not_in_etf_list():
    """etfItemList 미등록 5xxxxx ETN → 이름 키워드로 ETN 판정 (550082 실사례)."""
    assert classify("550082", "N2 KIS CD금리투자 ETN") == ProductType.ETN
    assert classify("530031", "KODEX 200") == ProductType.STOCK


# ---------------------------------------------------------------------------
# 정형 주식 코드 → STOCK
# ---------------------------------------------------------------------------

def test_classify_stock_kospi_6digit():
    """6자리 정형 코드 + ETF 미등록 → STOCK."""
    assert classify("005930", "삼성전자") == ProductType.STOCK


def test_classify_stock_kosdaq_6digit():
    """KOSDAQ 6자리 코드 → STOCK."""
    assert classify("086520", "에코프로") == ProductType.STOCK


def test_classify_stock_2_prefix():
    """2xxxxx 도 일반 주식 가능 (예: 코스닥)."""
    assert classify("293490", "카카오게임즈") == ProductType.STOCK


# ---------------------------------------------------------------------------
# 신형 우선주 (5자리 숫자 + 1 알파벳) → STOCK
# ---------------------------------------------------------------------------

def test_classify_stock_new_preferred_share_alphanumeric():
    """신형 우선주 코드 (5자리 숫자 + 1 대문자, 예: 02826K) → STOCK."""
    assert classify("02826K", "삼성물산우B") == ProductType.STOCK


def test_classify_stock_new_preferred_share_other_suffix():
    """다른 알파벳 suffix 도 STOCK."""
    assert classify("00088L", "예시우C") == ProductType.STOCK


def test_alphanumeric_preferred_etf_list_overrides():
    """ETF API 명단 hit 이 우선 (alphanumeric 코드라도 ETF 로 분류)."""
    assert classify("02826K", "이상한 ETF", etf_list={"02826K"}) == ProductType.ETF


def test_alphanumeric_etn_etf_serial_code_unaffected():
    """ETN/ETF 직렬 코드 (\\d{4}[A-Z]\\d) 는 step 5 패턴 미해당 → ETF API 명단 의존."""
    # 명단 미포함 → UNKNOWN (정상 운영에선 collect.py 가 명단 채워서 도달 X)
    assert classify("0025N0", "어떤 ETN") == ProductType.UNKNOWN
    # 명단 포함 + 이름에 ETN → ETN
    assert classify("0025N0", "KODEX 채권 ETN", etf_list={"0025N0"}) == ProductType.ETN


# ---------------------------------------------------------------------------
# UNKNOWN 폴백 (D2)
# ---------------------------------------------------------------------------

def test_classify_unknown_for_7_prefix_not_in_etf_list():
    """7xxxxx 인데 ETF API 에 없고 이름에 ETN 없음 → UNKNOWN (STOCK 폴백 X — D2)."""
    assert classify("700000", "이상한 종목") == ProductType.UNKNOWN


def test_etn_name_keyword_api_miss():
    """7xxxxx + ETF API 명단 없음 + 이름에 ETN → ETN (700028 케이스)."""
    assert classify("700028", "하나 레버리지 반도체 ETN", etf_list=set()) == ProductType.ETN


def test_etn_name_keyword_api_hit():
    """7xxxxx + ETF API 명단 hit → ETN (API 명단이 우선, 결과 동일)."""
    assert classify("700028", "하나 레버리지 반도체 ETN", etf_list={"700028"}) == ProductType.ETN


def test_classify_unknown_for_non_6digit():
    """비정형 종목 코드 → UNKNOWN."""
    assert classify("ABCDEF", "이름") == ProductType.UNKNOWN
    assert classify("12345", "5자리") == ProductType.UNKNOWN
    assert classify("1234567", "7자리") == ProductType.UNKNOWN


def test_classify_with_empty_etf_list():
    """ETF 명단이 비어도 분류 동작 (None 또는 빈 set)."""
    assert classify("005930", "삼성전자") == ProductType.STOCK
    assert classify("005930", "삼성전자", etf_list=None) == ProductType.STOCK
    assert classify("005930", "삼성전자", etf_list=set()) == ProductType.STOCK


# ---------------------------------------------------------------------------
# Pool 매핑
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pt,expected", [
    (ProductType.STOCK, Pool.STOCK),
    (ProductType.ETF, Pool.ETN_ETF),
    (ProductType.ETN, Pool.ETN_ETF),
    (ProductType.REIT, Pool.OTHER),
    (ProductType.SPAC, Pool.OTHER),
    (ProductType.UNKNOWN, Pool.OTHER),
])
def test_to_pool_mapping(pt: ProductType, expected: Pool):
    """ProductType → Pool 매핑 검증."""
    assert to_pool(pt) == expected


def test_pool_grouping_independence():
    """STOCK 풀과 ETN_ETF 풀은 서로 독립 (이름 일치 여부 검증)."""
    assert Pool.STOCK != Pool.ETN_ETF
    assert Pool.STOCK != Pool.OTHER
    assert Pool.ETN_ETF != Pool.OTHER
