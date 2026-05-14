"""자산군 기반 signal_strength percentile rank 변환 테스트."""
from unittest.mock import Mock

from output.signals_builder import compute_signal_strength_percentile


class TestComputeSignalStrengthPercentile:
    """signal_strength percentile rank 계산 테스트."""

    def _make_candidate(self, ticker: str, score: float, asset_class: str | None = None) -> Mock:
        """테스트용 Candidate 모의 객체 생성."""
        c = Mock()
        c.ticker = ticker
        c.score = score
        if asset_class is not None:
            c.asset_class = asset_class
        return c

    def test_stock_pool_5_candidates_median(self):
        """STOCK 풀 5개 후보 (score 100/200/300/400/500) → score=300 인 경우 percentile=50.0."""
        candidates = [
            self._make_candidate("001", 100, "STOCK"),
            self._make_candidate("002", 200, "STOCK"),
            self._make_candidate("003", 300, "STOCK"),
            self._make_candidate("004", 400, "STOCK"),
            self._make_candidate("005", 500, "STOCK"),
        ]
        c = candidates[2]  # score=300
        result = compute_signal_strength_percentile(c, candidates)
        assert result == 50.0, f"Expected 50.0, got {result}"

    def test_single_bond_etf_returns_neutral(self):
        """BOND_ETF 풀 단독 1개 후보 → 50.0 반환."""
        c = self._make_candidate("bond_001", 150, "BOND_ETF")
        candidates = [c]
        result = compute_signal_strength_percentile(c, candidates)
        assert result == 50.0

    def test_two_bond_etf_candidates_lowest(self):
        """BOND_ETF 풀 2개 (score 50, 80) → score=50 → 0.0."""
        c_low = self._make_candidate("bond_low", 50, "BOND_ETF")
        c_high = self._make_candidate("bond_high", 80, "BOND_ETF")
        candidates = [c_low, c_high]
        result = compute_signal_strength_percentile(c_low, candidates)
        assert result == 0.0

    def test_two_bond_etf_candidates_highest(self):
        """BOND_ETF 풀 2개 (score 50, 80) → score=80 → 100.0."""
        c_low = self._make_candidate("bond_low", 50, "BOND_ETF")
        c_high = self._make_candidate("bond_high", 80, "BOND_ETF")
        candidates = [c_low, c_high]
        result = compute_signal_strength_percentile(c_high, candidates)
        assert result == 100.0

    def test_three_bond_etf_candidates_middle(self):
        """BOND_ETF 풀 3개 (score 40, 60, 80) → score=60 → 50.0."""
        c1 = self._make_candidate("bond_1", 40, "BOND_ETF")
        c2 = self._make_candidate("bond_2", 60, "BOND_ETF")
        c3 = self._make_candidate("bond_3", 80, "BOND_ETF")
        candidates = [c1, c2, c3]
        result = compute_signal_strength_percentile(c2, candidates)
        assert result == 50.0

    def test_tied_scores_same_percentile(self):
        """동일 score 동률: rank < c.score 만 카운트하므로 동일 percentile."""
        c1 = self._make_candidate("a", 100, "STOCK")
        c2 = self._make_candidate("b", 100, "STOCK")
        c3 = self._make_candidate("c", 200, "STOCK")
        candidates = [c1, c2, c3]
        result1 = compute_signal_strength_percentile(c1, candidates)
        result2 = compute_signal_strength_percentile(c2, candidates)
        assert result1 == result2, f"Tied scores should have same percentile: {result1} vs {result2}"
        # score=100 → score < 100 인 후보 0개 → rank=0, 0/(3-1)*100=0.0
        assert result1 == 0.0, f"Expected 0.0 (lowest tier), got {result1}"

    def test_no_asset_class_single_candidate_returns_neutral(self):
        """asset_class 미설정 단독 후보 → 50.0 (중립)."""
        c = Mock()
        c.ticker = "001"
        c.score = 250
        candidates = [c]
        result = compute_signal_strength_percentile(c, candidates)
        assert result == 50.0

    def test_mixed_score_pool_percentile(self):
        """풀 전체(자산군 무관) 기준 cross-sectional percentile."""
        # 전체 5개 후보 (score 100,200,300,200,300)
        stock_1 = self._make_candidate("s1", 100, "STOCK")
        stock_2 = self._make_candidate("s2", 200, "STOCK")
        stock_3 = self._make_candidate("s3", 300, "STOCK")
        bond_1 = self._make_candidate("b1", 200, "BOND_ETF")
        bond_2 = self._make_candidate("b2", 300, "BOND_ETF")
        all_candidates = [stock_1, stock_2, stock_3, bond_1, bond_2]

        # score=100 → 0개 미만 → rank=0, 0/(5-1)*100=0.0
        assert compute_signal_strength_percentile(stock_1, all_candidates) == 0.0
        # score=200 → 1개 미만(100만) → rank=1, 1/4*100=25.0
        assert compute_signal_strength_percentile(stock_2, all_candidates) == 25.0
        assert compute_signal_strength_percentile(bond_1, all_candidates) == 25.0
        # score=300 → 3개 미만(100,200,200) → rank=3, 3/4*100=75.0
        assert compute_signal_strength_percentile(stock_3, all_candidates) == 75.0

    def test_four_candidates_quartile_boundaries(self):
        """4개 후보 → 분기점: 0%, 33.3%, 66.7%, 100%."""
        c1 = self._make_candidate("a", 100, "STOCK")
        c2 = self._make_candidate("b", 200, "STOCK")
        c3 = self._make_candidate("c", 300, "STOCK")
        c4 = self._make_candidate("d", 400, "STOCK")
        candidates = [c1, c2, c3, c4]

        # c1: 0 < 100 → rank=0, pct=0/3*100=0
        result1 = compute_signal_strength_percentile(c1, candidates)
        assert result1 == 0.0

        # c2: 1 < 200 → rank=1, pct=1/3*100=33.3
        result2 = compute_signal_strength_percentile(c2, candidates)
        assert abs(result2 - 33.3) < 0.1

        # c3: 2 < 300 → rank=2, pct=2/3*100=66.7
        result3 = compute_signal_strength_percentile(c3, candidates)
        assert abs(result3 - 66.7) < 0.1

        # c4: 3 < 400 → rank=3, pct=3/3*100=100
        result4 = compute_signal_strength_percentile(c4, candidates)
        assert result4 == 100.0

    def test_large_stock_pool_single_percentile(self):
        """큰 STOCK 풀에서 일정 위치 검증."""
        # 100개 STOCK (score 1~100)
        candidates = [
            self._make_candidate(f"stock_{i}", float(i), "STOCK")
            for i in range(1, 101)
        ]
        c_median = self._make_candidate("stock_50", 50.0, "STOCK")
        candidates.append(c_median)
        candidates.sort(key=lambda x: x.score)

        # score=50 → 50개 미만 (scores 1~49) → rank=49, pct=49/100*100=49.0
        result = compute_signal_strength_percentile(c_median, candidates)
        expected = round(49.0 / 100.0 * 100, 1)  # 49.0
        assert result == expected
