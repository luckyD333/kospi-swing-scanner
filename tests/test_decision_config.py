"""
test_decision_config.py — WeightConfig + must_have DSL 검증.

Phase 2 의사결정 프레임워크의 가중치/필수 조건 데이터 모델.
"""
from __future__ import annotations


import pytest

from core.decision.config import (
    Priority,
    WeightConfig,
    eval_must_have,
    parse_must_have,
)


# ---------------------------------------------------------------------------
# Priority / WeightConfig dataclass
# ---------------------------------------------------------------------------

def test_priority_basic():
    p = Priority(key="per", weight=20.0, direction="lower_better", label="저PER")
    assert p.key == "per"
    assert p.weight == 20.0
    assert p.direction == "lower_better"


def test_priority_direction_validation():
    """direction은 'lower_better' 또는 'higher_better' 만."""
    with pytest.raises(ValueError, match="direction"):
        Priority(key="per", weight=20.0, direction="invalid", label="x")


def test_weight_config_sum_must_be_100():
    """priorities 가중치 합 != 100% → ValueError."""
    bad = [
        Priority(key="per", weight=30.0, direction="lower_better", label="x"),
        Priority(key="roe", weight=50.0, direction="higher_better", label="y"),
    ]
    with pytest.raises(ValueError, match="100"):
        WeightConfig(priorities=bad, must_have=[])


def test_weight_config_no_duplicate_keys():
    """동일 key 중복 → ValueError."""
    bad = [
        Priority(key="per", weight=50.0, direction="lower_better", label="x"),
        Priority(key="per", weight=50.0, direction="higher_better", label="y"),
    ]
    with pytest.raises(ValueError, match="중복"):
        WeightConfig(priorities=bad, must_have=[])


def test_weight_config_valid_construction():
    cfg = WeightConfig(
        priorities=[
            Priority(key="per", weight=30.0, direction="lower_better", label="저PER"),
            Priority(key="roe", weight=40.0, direction="higher_better", label="고ROE"),
            Priority(key="momentum_pct", weight=30.0, direction="higher_better",
                     label="모멘텀"),
        ],
        must_have=["per<30", "ensemble_count>=2"],
    )
    assert len(cfg.priorities) == 3
    assert cfg.must_have == ["per<30", "ensemble_count>=2"]


# ---------------------------------------------------------------------------
# YAML 로드
# ---------------------------------------------------------------------------

def test_load_from_yaml(tmp_path):
    yaml_content = """
priorities:
  - key: per
    weight: 30
    direction: lower_better
    label: 저PER
  - key: roe
    weight: 40
    direction: higher_better
    label: 고ROE
  - key: momentum_pct
    weight: 30
    direction: higher_better
    label: 모멘텀
must_have:
  - per<30
  - ensemble_count>=2
"""
    p = tmp_path / "weights.yml"
    p.write_text(yaml_content)
    cfg = WeightConfig.load(p)
    assert len(cfg.priorities) == 3
    assert cfg.priorities[0].key == "per"
    assert cfg.must_have == ["per<30", "ensemble_count>=2"]


def test_save_to_yaml_roundtrip(tmp_path):
    cfg = WeightConfig(
        priorities=[
            Priority(key="per", weight=50.0, direction="lower_better", label="저PER"),
            Priority(key="roe", weight=50.0, direction="higher_better", label="고ROE"),
        ],
        must_have=["per<30"],
    )
    p = tmp_path / "weights.yml"
    cfg.save(p)
    loaded = WeightConfig.load(p)
    assert loaded.priorities[0].key == "per"
    assert loaded.priorities[0].weight == 50.0
    assert loaded.must_have == ["per<30"]


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        WeightConfig.load(tmp_path / "missing.yml")


# ---------------------------------------------------------------------------
# must_have DSL 파싱
# ---------------------------------------------------------------------------

def test_parse_must_have_lt():
    op = parse_must_have("per<30")
    assert op.key == "per"
    assert op.op == "<"
    assert op.value == 30.0


def test_parse_must_have_gte():
    op = parse_must_have("ensemble_count>=2")
    assert op.key == "ensemble_count"
    assert op.op == ">="
    assert op.value == 2.0


def test_parse_must_have_all_ops():
    """6 비교 연산자 모두 지원."""
    for expr, expected_op in [
        ("a<1", "<"), ("b<=2", "<="),
        ("c>3", ">"), ("d>=4", ">="),
        ("e==5", "=="), ("f!=6", "!="),
    ]:
        op = parse_must_have(expr)
        assert op.op == expected_op


def test_parse_must_have_invalid():
    with pytest.raises(ValueError, match="must_have"):
        parse_must_have("invalid expression")


# ---------------------------------------------------------------------------
# must_have evaluator
# ---------------------------------------------------------------------------

def test_eval_must_have_passes():
    metrics = {"per": 25.0, "ensemble_count": 2}
    assert eval_must_have(["per<30", "ensemble_count>=2"], metrics) is True


def test_eval_must_have_fails_one():
    metrics = {"per": 35.0, "ensemble_count": 2}
    assert eval_must_have(["per<30", "ensemble_count>=2"], metrics) is False


def test_eval_must_have_handles_missing_metric():
    """metric 미존재 또는 None → 자동 탈락."""
    metrics = {"per": 25.0}  # ensemble_count 없음
    assert eval_must_have(["per<30", "ensemble_count>=2"], metrics) is False


def test_eval_must_have_handles_none_value():
    """metric 값이 None → 자동 탈락 (결측 종목은 필수 조건 못 검증)."""
    metrics = {"per": None, "ensemble_count": 2}
    assert eval_must_have(["per<30", "ensemble_count>=2"], metrics) is False


def test_eval_must_have_empty_passes():
    """빈 must_have 리스트 → 항상 통과."""
    assert eval_must_have([], {"per": 100}) is True


def test_parse_must_have_optional_prefix():
    """'?key<value' → optional=True."""
    op = parse_must_have("?momentum_pct>10")
    assert op.optional is True
    assert op.key == "momentum_pct"
    assert op.op == ">"
    assert op.value == 10.0


def test_parse_must_have_no_prefix_required():
    """prefix 없으면 optional=False."""
    op = parse_must_have("per<30")
    assert op.optional is False


def test_eval_must_have_optional_skips_on_missing():
    """optional 조건 + 메트릭 결측 → 조건 skip (통과로 간주)."""
    metrics = {"per": 25.0}  # momentum_pct 없음
    assert eval_must_have(["per<30", "?momentum_pct>10"], metrics) is True


def test_eval_must_have_optional_still_evaluated_when_present():
    """optional 조건이라도 메트릭이 있으면 정상 평가."""
    # momentum_pct=5 → 조건 미달 → 탈락
    metrics = {"per": 25.0, "momentum_pct": 5.0}
    assert eval_must_have(["?momentum_pct>10"], metrics) is False
    # momentum_pct=20 → 통과
    metrics2 = {"per": 25.0, "momentum_pct": 20.0}
    assert eval_must_have(["?momentum_pct>10"], metrics2) is True


def test_eval_must_have_required_still_fails_on_missing():
    """일반 (non-optional) 조건은 결측 시 여전히 탈락 (기존 동작 유지)."""
    metrics = {"per": 25.0}
    assert eval_must_have(["momentum_pct>10"], metrics) is False
