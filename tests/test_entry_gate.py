"""
tests/test_entry_gate.py — 전략별 entry gate 정책 매트릭스 단위 테스트.

TDD: Red → Green → Verify
"""
from core.decision.entry_gate import (
    ENTRY_GATE_POLICY,
    STRONG_SETUP_THRESHOLD,
    is_strategy_allowed,
)


class TestEntryGatePolicy:
    """Entry gate 정책 매트릭스 검증."""

    def test_policy_coverage(self):
        """모든 전략이 정책 매트릭스에 포함됨."""
        expected_strategies = [
            "strategy_one",
            "strategy_two",
            "strategy_three",
            "strategy_four",
            "strategy_five",
        ]
        assert all(s in ENTRY_GATE_POLICY for s in expected_strategies)

    def test_all_regimes_covered(self):
        """각 전략별로 모든 7개 regime이 정의됨."""
        regimes = [
            "UPTREND_STRONG",
            "UPTREND_WEAK",
            "RANGE_TIGHT",
            "RANGE",
            "DOWNTREND_WEAK",
            "DOWNTREND_STRONG",
            "MIXED",
        ]
        for strategy in ENTRY_GATE_POLICY:
            policy = ENTRY_GATE_POLICY[strategy]
            assert len(policy) == 7, f"{strategy}에 regime 누락"
            for regime in regimes:
                assert regime in policy, f"{strategy}에서 {regime} 누락"

    def test_downtrend_strong_always_block(self):
        """DOWNTREND_STRONG → 모든 전략 차단."""
        for strategy in ENTRY_GATE_POLICY:
            policy = ENTRY_GATE_POLICY[strategy]
            assert policy["DOWNTREND_STRONG"] == "block"


class TestIsStrategyAllowed:
    """is_strategy_allowed() 함수 단위 테스트."""

    def test_allow_action(self):
        """action=allow → 항상 True."""
        # strategy_one이 UPTREND_WEAK에서 allow
        assert is_strategy_allowed("strategy_one_d_v2", "UPTREND_WEAK") is True

    def test_block_action(self):
        """action=block → 항상 False."""
        # 모든 전략이 DOWNTREND_STRONG에서 block
        assert is_strategy_allowed("strategy_one_d_v2", "DOWNTREND_STRONG") is False
        assert is_strategy_allowed("strategy_two_1h", "DOWNTREND_STRONG") is False

    def test_allow_strong_only_with_high_setup(self):
        """action=allow_strong_only + setup_score ≥ 60 → True."""
        # strategy_one이 RANGE_TIGHT에서 allow_strong_only
        assert (
            is_strategy_allowed(
                "strategy_one_d_v2", "RANGE_TIGHT", setup_score=70
            )
            is True
        )

    def test_allow_strong_only_with_low_setup(self):
        """action=allow_strong_only + setup_score < 60 → False."""
        assert (
            is_strategy_allowed(
                "strategy_one_d_v2", "RANGE_TIGHT", setup_score=50
            )
            is False
        )

    def test_allow_strong_only_no_setup_score(self):
        """action=allow_strong_only + setup_score=None → False."""
        assert (
            is_strategy_allowed("strategy_one_d_v2", "RANGE_TIGHT", setup_score=None)
            is False
        )

    def test_downtrend_weak_strategy_one(self):
        """strategy_one + DOWNTREND_WEAK → allow_strong_only."""
        # setup_score 70 미만 시 차단
        assert (
            is_strategy_allowed(
                "strategy_one_30m_v2", "DOWNTREND_WEAK", setup_score=50
            )
            is False
        )
        # setup_score 70 이상 시 통과
        assert (
            is_strategy_allowed(
                "strategy_one_30m_v2", "DOWNTREND_WEAK", setup_score=70
            )
            is True
        )

    def test_range_tight_strategy_three(self):
        """strategy_three + RANGE_TIGHT → allow."""
        # 추세 추종 전략은 에너지 응축 상태에서도 진입 허용
        assert is_strategy_allowed("strategy_three_1h", "RANGE_TIGHT") is True

    def test_range_tight_strategy_four(self):
        """strategy_four + RANGE_TIGHT → allow_strong_only."""
        assert is_strategy_allowed("strategy_four_30m", "RANGE_TIGHT") is False
        assert (
            is_strategy_allowed("strategy_four_30m", "RANGE_TIGHT", setup_score=70)
            is True
        )

    def test_normalize_family_variant_one(self):
        """strategy_one_d_v2 → strategy_one."""
        # UPTREND_STRONG은 allow_strong_only이므로 setup_score 필요
        assert is_strategy_allowed("strategy_one_d_v2", "UPTREND_STRONG", setup_score=70) is True
        assert is_strategy_allowed("strategy_one_d_v2", "UPTREND_STRONG") is False

    def test_normalize_family_variant_two(self):
        """strategy_two_1h → strategy_two."""
        assert is_strategy_allowed("strategy_two_1h", "UPTREND_STRONG") is True

    def test_normalize_family_variant_three(self):
        """strategy_three_30m_v2 → strategy_three."""
        assert is_strategy_allowed("strategy_three_30m_v2", "UPTREND_STRONG") is True

    def test_normalize_family_variant_four(self):
        """strategy_four_pullback_ma_1h → strategy_four."""
        assert is_strategy_allowed("strategy_four_pullback_ma_1h", "UPTREND_STRONG") is True

    def test_normalize_family_variant_five(self):
        """strategy_five_bull_flag_30m → strategy_five."""
        assert is_strategy_allowed("strategy_five_bull_flag_30m", "UPTREND_STRONG") is True

    def test_unknown_strategy_defaults_block(self):
        """미정의 전략 family → block."""
        # unknown family는 정책 매트릭스에 없으므로 get() 기본값 'block'
        assert is_strategy_allowed("strategy_unknown", "UPTREND_STRONG") is False

    def test_strong_setup_threshold_constant(self):
        """STRONG_SETUP_THRESHOLD 상수 정의 확인."""
        assert STRONG_SETUP_THRESHOLD == 60

    def test_boundary_setup_score_59(self):
        """setup_score = 59 (경계값 - 1) → 미통과."""
        assert (
            is_strategy_allowed(
                "strategy_one_d_v2", "DOWNTREND_WEAK", setup_score=59
            )
            is False
        )

    def test_boundary_setup_score_60(self):
        """setup_score = 60 (경계값) → 통과."""
        assert (
            is_strategy_allowed(
                "strategy_one_d_v2", "DOWNTREND_WEAK", setup_score=60
            )
            is True
        )


class TestStrategyPolicies:
    """전략별 정책 상세 검증."""

    def test_strategy_one_uptrend_strong(self):
        """Strategy 1 (평균 회귀): UPTREND_STRONG → allow_strong_only (풀백만)."""
        policy_action = ENTRY_GATE_POLICY["strategy_one"]["UPTREND_STRONG"]
        assert policy_action == "allow_strong_only"

    def test_strategy_one_range_tight(self):
        """Strategy 1: RANGE_TIGHT → allow_strong_only."""
        policy_action = ENTRY_GATE_POLICY["strategy_one"]["RANGE_TIGHT"]
        assert policy_action == "allow_strong_only"

    def test_strategy_two_uptrend_strong(self):
        """Strategy 2 (모멘텀): UPTREND_STRONG → allow."""
        policy_action = ENTRY_GATE_POLICY["strategy_two"]["UPTREND_STRONG"]
        assert policy_action == "allow"

    def test_strategy_two_range(self):
        """Strategy 2: RANGE → block."""
        policy_action = ENTRY_GATE_POLICY["strategy_two"]["RANGE"]
        assert policy_action == "block"

    def test_strategy_three_range_tight(self):
        """Strategy 3 (Donchian 추세): RANGE_TIGHT → allow (돌파 대기)."""
        policy_action = ENTRY_GATE_POLICY["strategy_three"]["RANGE_TIGHT"]
        assert policy_action == "allow"

    def test_strategy_three_range(self):
        """Strategy 3: RANGE → block."""
        policy_action = ENTRY_GATE_POLICY["strategy_three"]["RANGE"]
        assert policy_action == "block"

    def test_strategy_four_range_tight(self):
        """Strategy 4 (Pullback MA): RANGE_TIGHT → allow_strong_only."""
        policy_action = ENTRY_GATE_POLICY["strategy_four"]["RANGE_TIGHT"]
        assert policy_action == "allow_strong_only"

    def test_strategy_five_range_tight(self):
        """Strategy 5 (Bull Flag): RANGE_TIGHT → allow."""
        policy_action = ENTRY_GATE_POLICY["strategy_five"]["RANGE_TIGHT"]
        assert policy_action == "allow"
