"""
tests/test_decide_legacy_weights.py — Phase 2 --decide 모드에서
구형식 weights.yml 호환성 검증.

신규 이후에도 기존 weights.yml 로 --decide 를 실행하면
자동으로 migration 되어 정상 동작하는지 확인.
"""

from core.decision.config import WeightConfig


class TestDecideLegacyWeightsCompat:
    """Phase 2 --decide 모드에서 구형식 weights 호환성."""

    def test_decide_accepts_legacy_weights_yml(self, tmp_path):
        """--decide 호출이 구형식 weights.yml 로도 정상 로드."""
        weights_file = tmp_path / "weights.yml"

        # 기존 weights.yml 형식 (Task 6 이전)
        weights_file.write_text("""
priorities:
  - key: ensemble_score
    weight: 25.0
    direction: higher_better
    label: 다중 전략 합의도
  - key: momentum_pct
    weight: 25.0
    direction: higher_better
    label: 가격 모멘텀
  - key: rr_ratio
    weight: 15.0
    direction: higher_better
    label: 손익비
  - key: roe
    weight: 15.0
    direction: higher_better
    label: ROE (수익성)
    applies_to_pools: [STOCK]
  - key: per
    weight: 10.0
    direction: lower_better
    label: PER (저평가)
    applies_to_pools: [STOCK]
  - key: regime_score
    weight: 10.0
    direction: higher_better
    label: 시장 국면
must_have:
  - "ensemble_count>=1"
strategy_weights:
  strategy_one_d_v2: 1.3
  strategy_one_w_v2: 1.3
  strategy_three_trend_following: 1.0
""", encoding="utf-8")

        # WeightConfig.load() 호출
        config = WeightConfig.load(weights_file)

        # 기본 검증: config 객체 생성 성공
        assert config is not None
        assert len(config.priorities) > 0

        # migration 검증: momentum_3m 이 있고 momentum_pct 는 없어야 함
        keys = {p.key for p in config.priorities}
        assert "momentum_3m" in keys
        assert "momentum_pct" not in keys
        assert "ensemble_score" not in keys
        assert "rr_ratio" not in keys

    def test_decide_new_weights_yml_unchanged(self, tmp_path):
        """신규 weights.yml 은 그대로 로드."""
        weights_file = tmp_path / "weights.yml"

        weights_file.write_text("""
priorities:
  - key: momentum_3m
    label: 가격 모멘텀 (3개월)
    weight: 35.0
    direction: higher_better
    applies_to_pools: [STOCK, ETN_ETF]
  - key: regime_score
    label: 시장 국면
    weight: 15.0
    direction: higher_better
    applies_to_pools: [STOCK, ETN_ETF]
  - key: roe
    label: ROE (수익성)
    weight: 15.0
    direction: higher_better
    applies_to_pools: [STOCK]
  - key: per
    label: PER (저평가)
    weight: 10.0
    direction: lower_better
    applies_to_pools: [STOCK]
  - key: liquidity
    label: 유동성
    weight: 25.0
    direction: higher_better
    applies_to_pools: [STOCK, ETN_ETF]
must_have: []
strategy_weights:
  strategy_one_d_v2: 1.3
""", encoding="utf-8")

        config = WeightConfig.load(weights_file)

        # 신규 스키마 검증
        assert len(config.priorities) == 5
        keys = {p.key for p in config.priorities}
        assert keys == {"momentum_3m", "regime_score", "roe", "per", "liquidity"}

        # 가중치 합 검증 (STOCK pool)
        stock_weight = sum(
            p.weight for p in config.priorities
            if "STOCK" in p.applies_to_pools
        )
        assert abs(stock_weight - 100.0) < 0.01

    def test_legacy_backup_file_creation(self, tmp_path):
        """구형식 로드 시 backup 자동 생성."""
        from core.decision.config import backup_legacy_weights

        weights_file = tmp_path / "weights.yml"
        weights_file.write_text("priorities: []")

        backup = backup_legacy_weights(weights_file)

        assert backup is not None
        assert backup.name == "weights.legacy.yml.bak"
        assert backup.exists()

    def test_legacy_backup_not_overwritten(self, tmp_path):
        """기존 backup 은 보존."""
        from core.decision.config import backup_legacy_weights

        weights_file = tmp_path / "weights.yml"
        backup_file = tmp_path / "weights.legacy.yml.bak"

        weights_file.write_text("new")
        backup_file.write_text("old")

        result = backup_legacy_weights(weights_file)

        # 기존 backup 유지
        assert backup_file.read_text() == "old"
        assert result == backup_file
