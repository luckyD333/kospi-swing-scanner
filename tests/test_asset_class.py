"""
테스트: AssetClass enum + classify_asset_class() 함수.

Plan Task 1 TDD — Red 단계.
"""
from __future__ import annotations

from core.decision.product_type import AssetClass, ProductType, classify_asset_class


class TestAssetClassEnum:
    """AssetClass enum 존재 검증."""

    def test_asset_class_members(self):
        """AssetClass enum 이 4개 멤버를 가져야 함."""
        assert hasattr(AssetClass, "STOCK")
        assert hasattr(AssetClass, "EQUITY_ETF")
        assert hasattr(AssetClass, "BOND_ETF")
        assert hasattr(AssetClass, "OTHER")

    def test_asset_class_values(self):
        """AssetClass 멤버 값."""
        assert AssetClass.STOCK.value == "STOCK"
        assert AssetClass.EQUITY_ETF.value == "EQUITY_ETF"
        assert AssetClass.BOND_ETF.value == "BOND_ETF"
        assert AssetClass.OTHER.value == "OTHER"


class TestClassifyAssetClass:
    """classify_asset_class() 함수 테스트."""

    def test_stock_classification(self):
        """일반 주식 → STOCK."""
        result = classify_asset_class(ProductType.STOCK, "삼성전자")
        assert result == AssetClass.STOCK

        result = classify_asset_class(ProductType.STOCK, "SK하이닉스")
        assert result == AssetClass.STOCK

    def test_stock_empty_name(self):
        """주식 + 빈 name → STOCK."""
        result = classify_asset_class(ProductType.STOCK, "")
        assert result == AssetClass.STOCK

    def test_equity_etf_no_bond_keyword(self):
        """주식형 ETF (채권 키워드 없음) → EQUITY_ETF."""
        result = classify_asset_class(ProductType.ETF, "SOL 조선TOP3플러스")
        assert result == AssetClass.EQUITY_ETF

        result = classify_asset_class(ProductType.ETF, "TIGER 200")
        assert result == AssetClass.EQUITY_ETF

    def test_bond_etf_with_bond_keyword(self):
        """ETF + 채권 키워드 → BOND_ETF."""
        # 채권
        result = classify_asset_class(ProductType.ETF, "SOL 초단기채권액티브")
        assert result == AssetClass.BOND_ETF

        # 국고채
        result = classify_asset_class(ProductType.ETF, "KODEX 국고채10년")
        assert result == AssetClass.BOND_ETF

        # 초단기채
        result = classify_asset_class(ProductType.ETF, "KOSEF 초단기채")
        assert result == AssetClass.BOND_ETF

    def test_bond_etf_with_multiple_keywords(self):
        """채권 키워드 여러 개도 감지."""
        # 회사채
        result = classify_asset_class(ProductType.ETF, "ARIRANG 회사채")
        assert result == AssetClass.BOND_ETF

        # 금리
        result = classify_asset_class(ProductType.ETF, "금리 연계 ETF")
        assert result == AssetClass.BOND_ETF

        # 단기자금
        result = classify_asset_class(ProductType.ETF, "단기자금 커버드")
        assert result == AssetClass.BOND_ETF

        # MMF
        result = classify_asset_class(ProductType.ETF, "MMF 유사 상품")
        assert result == AssetClass.BOND_ETF

    def test_etn_no_bond_keyword(self):
        """ETN + 채권 키워드 없음 → EQUITY_ETF."""
        result = classify_asset_class(ProductType.ETN, "TIGER 레버리지")
        assert result == AssetClass.EQUITY_ETF

    def test_etn_with_bond_keyword(self):
        """ETN + 채권 키워드 → BOND_ETF."""
        result = classify_asset_class(ProductType.ETN, "골드 초단기채ETN")
        assert result == AssetClass.BOND_ETF

    def test_reit_classification(self):
        """REIT → OTHER."""
        result = classify_asset_class(ProductType.REIT, "롯데리츠")
        assert result == AssetClass.OTHER

    def test_spac_classification(self):
        """SPAC → OTHER."""
        result = classify_asset_class(ProductType.SPAC, "기업인수목적 특수목적회사")
        assert result == AssetClass.OTHER

    def test_unknown_classification(self):
        """UNKNOWN → OTHER."""
        result = classify_asset_class(ProductType.UNKNOWN, "분류불명")
        assert result == AssetClass.OTHER


class TestBondKeywords:
    """BOND_KEYWORDS 상수 검증."""

    def test_bond_keywords_defined(self):
        """BOND_KEYWORDS 가 정의되어 있어야 함."""
        from core.decision.product_type import BOND_KEYWORDS

        assert isinstance(BOND_KEYWORDS, (set, frozenset, tuple))
        assert "채권" in BOND_KEYWORDS
        assert "초단기채" in BOND_KEYWORDS
        assert "회사채" in BOND_KEYWORDS
        assert "국고" in BOND_KEYWORDS
        assert "금리" in BOND_KEYWORDS
        assert "단기자금" in BOND_KEYWORDS
        assert "MMF" in BOND_KEYWORDS
