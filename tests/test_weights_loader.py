"""
tests/test_weights_loader.py — 가중치 로더 + 신규 schema 검증.

신규 weights.yml 스키마:
  - 잠재력 점수: momentum_3m / regime_score / roe / per / liquidity (합계 100%)
  - 기회 점수: weights.yml 에 없음 (regret_scorer 에서 직접 가중치 적용)
"""
import shutil

from core.decision.config import WeightConfig


class TestNewWeightsSchema:
    """신규 weights.yml 스키마 검증."""

    def test_new_weights_yml_schema(self, tmp_path):
        """신규 5-factor 잠재력 점수 weights.yml 로드."""
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
""", encoding="utf-8")

        config = WeightConfig.load(weights_file)

        # 5개 factor 확인
        assert len(config.priorities) == 5
        keys = {p.key for p in config.priorities}
        assert keys == {"momentum_3m", "regime_score", "roe", "per", "liquidity"}

        # STOCK pool 가중치 합 100%
        stock_weight = sum(
            p.weight for p in config.priorities
            if "STOCK" in p.applies_to_pools
        )
        assert abs(stock_weight - 100.0) < 0.01, f"STOCK weight sum: {stock_weight}"

        # ETN_ETF pool 가중치 합 (roe, per 제외 → aggregator 에서 동적 정규화)
        # momentum_3m(35) + regime_score(15) + liquidity(25) = 75
        # aggregator 가 ETN_ETF pool 에서 NOT_APPLICABLE 항목을 제거하고 정규화
        etf_weight = sum(
            p.weight for p in config.priorities
            if "ETN_ETF" in p.applies_to_pools
        )
        assert abs(etf_weight - 75.0) < 0.01, f"ETN_ETF weight sum (raw, pre-normalization): {etf_weight}"

    def test_new_weights_yml_alternative_pool_names(self, tmp_path):
        """Plan 에서 제시한 pool 이름 변형 (EQUITY_ETF, BOND_ETF) 지원."""
        weights_file = tmp_path / "weights.yml"
        # pool 이름을 "EQUITY_ETF", "BOND_ETF" 로 사용하는 경우도 지원
        weights_file.write_text("""
priorities:
  - key: momentum_3m
    label: 가격 모멘텀 (3개월)
    weight: 35.0
    direction: higher_better
    applies_to_pools: [STOCK, EQUITY_ETF, BOND_ETF]

  - key: regime_score
    label: 시장 국면
    weight: 15.0
    direction: higher_better
    applies_to_pools: [STOCK, EQUITY_ETF, BOND_ETF]

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
    applies_to_pools: [STOCK, EQUITY_ETF, BOND_ETF]
""", encoding="utf-8")

        config = WeightConfig.load(weights_file)
        assert len(config.priorities) == 5


class TestLegacyKeyMap:
    """구형식 weights.yml migration 검증."""

    def test_legacy_key_momentum_pct_to_momentum_3m(self, tmp_path):
        """구형식 momentum_pct → 신규 momentum_3m 으로 변환 + 정규화."""
        from core.decision.config import migrate_legacy_weights

        old_yaml = {
            "priorities": [
                {"key": "momentum_pct", "weight": 25.0, "direction": "higher_better", "label": "가격 모멘텀"},
                {"key": "rr_ratio", "weight": 15.0, "direction": "higher_better", "label": "손익비"},
                {"key": "roe", "weight": 15.0, "direction": "higher_better", "label": "ROE (수익성)", "applies_to_pools": ["STOCK"]},
                {"key": "per", "weight": 10.0, "direction": "lower_better", "label": "PER (저평가)", "applies_to_pools": ["STOCK"]},
                {"key": "regime_score", "weight": 10.0, "direction": "higher_better", "label": "시장 국면"},
                {"key": "ensemble_score", "weight": 25.0, "direction": "higher_better", "label": "다중 전략 합의도"},
            ]
        }

        result = migrate_legacy_weights(old_yaml)

        # momentum_pct → momentum_3m 변환 확인
        keys = {p["key"] for p in result["priorities"]}
        assert "momentum_3m" in keys
        assert "momentum_pct" not in keys

        # ensemble_score, rr_ratio 는 drop 되어야 함
        assert "ensemble_score" not in keys
        assert "rr_ratio" not in keys

        # drop 된 weight (15+25=40) 를 남은 weight (25+15+10+10=60) 에 정규화
        # scale = 100 / 60 = 1.667
        # momentum_3m weight = 25 * 1.667 ≈ 41.7
        momentum_3m = next(p for p in result["priorities"] if p["key"] == "momentum_3m")
        assert abs(momentum_3m["weight"] - 41.67) < 0.1  # 정규화된 값

        # 전체 weight 합 100% 확인
        total = sum(p["weight"] for p in result["priorities"])
        assert abs(total - 100.0) < 0.01

    def test_legacy_ensemble_score_dropped(self, tmp_path):
        """구형식 ensemble_score → drop + 경고."""
        from core.decision.config import migrate_legacy_weights

        old_yaml = {
            "priorities": [
                {"key": "ensemble_score", "weight": 25.0, "direction": "higher_better", "label": "다중 전략 합의도"},
                {"key": "momentum_pct", "weight": 25.0, "direction": "higher_better", "label": "가격 모멘텀"},
                {"key": "regime_score", "weight": 15.0, "direction": "higher_better", "label": "시장 국면"},
                {"key": "roe", "weight": 15.0, "direction": "higher_better", "label": "ROE (수익성)", "applies_to_pools": ["STOCK"]},
                {"key": "per", "weight": 10.0, "direction": "lower_better", "label": "PER (저평가)", "applies_to_pools": ["STOCK"]},
                {"key": "rr_ratio", "weight": 10.0, "direction": "higher_better", "label": "손익비"},
            ]
        }

        result = migrate_legacy_weights(old_yaml)

        keys = {p["key"] for p in result["priorities"]}
        assert "ensemble_score" not in keys
        assert "rr_ratio" not in keys

        # drop 된 가중치(25+10=35) 정규화 후 전체 합 100%
        total = sum(p["weight"] for p in result["priorities"])
        assert abs(total - 100.0) < 0.01

    def test_legacy_rr_ratio_dropped(self, tmp_path):
        """구형식 rr_ratio → drop + 경고 (기회 점수로 재배치)."""
        from core.decision.config import migrate_legacy_weights

        old_yaml = {
            "priorities": [
                {"key": "rr_ratio", "weight": 15.0, "direction": "higher_better", "label": "손익비"},
                {"key": "roe", "weight": 15.0, "direction": "higher_better", "label": "ROE (수익성)", "applies_to_pools": ["STOCK"]},
            ]
        }

        result = migrate_legacy_weights(old_yaml)

        keys = {p["key"] for p in result["priorities"]}
        assert "rr_ratio" not in keys

    def test_legacy_mixed_old_and_new_schema(self, tmp_path):
        """구형식과 신규 혼재 → 구형식만 변환, 신규는 그대로."""
        from core.decision.config import migrate_legacy_weights

        mixed_yaml = {
            "priorities": [
                {"key": "momentum_pct", "weight": 25.0, "direction": "higher_better", "label": "가격 모멘텀"},  # 구형식
                {"key": "momentum_3m", "weight": 35.0, "direction": "higher_better", "label": "가격 모멘텀 (3개월)"},  # 신규 (이미 있음)
                {"key": "roe", "weight": 15.0, "direction": "higher_better", "label": "ROE (수익성)", "applies_to_pools": ["STOCK"]},
                {"key": "per", "weight": 10.0, "direction": "lower_better", "label": "PER (저평가)", "applies_to_pools": ["STOCK"]},
                {"key": "regime_score", "weight": 10.0, "direction": "higher_better", "label": "시장 국면"},
                {"key": "liquidity", "weight": 5.0, "direction": "higher_better", "label": "유동성"},
            ]
        }

        result = migrate_legacy_weights(mixed_yaml)

        # momentum_pct 는 제거, momentum_3m 은 유지
        keys = {p["key"] for p in result["priorities"]}
        assert "momentum_pct" not in keys
        assert "momentum_3m" in keys

    def test_legacy_weight_sum_validation_after_migration(self, tmp_path, caplog):
        """Migration 후 가중치 합 정규화."""
        import logging
        from core.decision.config import migrate_legacy_weights

        old_yaml = {
            "priorities": [
                {"key": "momentum_pct", "weight": 25.0, "direction": "higher_better", "label": "가격 모멘텀"},
                {"key": "regime_score", "weight": 15.0, "direction": "higher_better", "label": "시장 국면"},
                {"key": "roe", "weight": 15.0, "direction": "higher_better", "label": "ROE (수익성)", "applies_to_pools": ["STOCK"]},
                {"key": "per", "weight": 10.0, "direction": "lower_better", "label": "PER (저평가)", "applies_to_pools": ["STOCK"]},
                {"key": "rr_ratio", "weight": 35.0, "direction": "higher_better", "label": "손익비"},  # drop 예정
            ]
        }

        caplog.set_level(logging.WARNING)
        result = migrate_legacy_weights(old_yaml)

        # rr_ratio 제거 → 가중치 정규화 후 합계 100%
        total = sum(p["weight"] for p in result["priorities"])
        assert abs(total - 100.0) < 0.01

        # drop 및 정규화 로그 확인
        assert any("제거됨" in record.message for record in caplog.records)
        assert any("정규화" in record.message for record in caplog.records)

    def test_backup_legacy_weights_creates_file_if_not_exists(self, tmp_path):
        """기존 weights.yml backup 생성 (이미 backup 존재 시 덮어쓰지 않음)."""
        from core.decision.config import backup_legacy_weights

        weights_file = tmp_path / "weights.yml"
        weights_file.write_text("priorities: []")

        backup_path = backup_legacy_weights(weights_file)

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.name == "weights.legacy.yml.bak"
        assert backup_path.read_text() == "priorities: []"

    def test_backup_legacy_weights_preserves_existing(self, tmp_path):
        """기존 backup 파일이 있으면 덮어쓰지 않음."""
        from core.decision.config import backup_legacy_weights

        weights_file = tmp_path / "weights.yml"
        weights_file.write_text("priorities: [new]")

        backup_path = tmp_path / "weights.legacy.yml.bak"
        backup_path.write_text("priorities: [old]")  # 기존 backup

        result = backup_legacy_weights(weights_file)

        # 기존 backup 유지
        assert result == backup_path
        assert backup_path.read_text() == "priorities: [old]"  # 변경 없음

    def test_backup_legacy_weights_handles_oserror(self, tmp_path, monkeypatch):
        """backup 실패 시 None 반환."""
        from core.decision.config import backup_legacy_weights

        weights_file = tmp_path / "weights.yml"
        weights_file.write_text("priorities: []")

        # shutil.copy2 를 실패하도록 monkeypatch
        def failing_copy(*args, **kwargs):
            raise OSError("Permission denied")

        monkeypatch.setattr(shutil, "copy2", failing_copy)

        result = backup_legacy_weights(weights_file)
        assert result is None


class TestWeightConfigLoaderIntegration:
    """WeightConfig.load() 에서 migration 통합."""

    def test_load_with_legacy_weights_auto_migrates(self, tmp_path, caplog):
        """legacy weights.yml 로드 시 자동 migration + 경고 로그."""
        from core.decision.config import WeightConfig

        weights_file = tmp_path / "weights.yml"
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
""", encoding="utf-8")

        config = WeightConfig.load(weights_file)

        # migration 후 신규 스키마 확인
        keys = {p.key for p in config.priorities}
        assert "momentum_3m" in keys
        assert "ensemble_score" not in keys
        assert "rr_ratio" not in keys

    def test_load_with_new_weights_no_migration(self, tmp_path):
        """신규 weights.yml 로드 시 migration 스킵."""
        from core.decision.config import WeightConfig

        weights_file = tmp_path / "weights.yml"
        weights_file.write_text("""
priorities:
  - key: momentum_3m
    weight: 35.0
    direction: higher_better
    label: 가격 모멘텀 (3개월)
    applies_to_pools: [STOCK, ETN_ETF]
  - key: regime_score
    weight: 15.0
    direction: higher_better
    label: 시장 국면
    applies_to_pools: [STOCK, ETN_ETF]
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
  - key: liquidity
    weight: 25.0
    direction: higher_better
    label: 유동성
    applies_to_pools: [STOCK, ETN_ETF]
""", encoding="utf-8")

        config = WeightConfig.load(weights_file)

        assert len(config.priorities) == 5
        keys = {p.key for p in config.priorities}
        assert keys == {"momentum_3m", "regime_score", "roe", "per", "liquidity"}
