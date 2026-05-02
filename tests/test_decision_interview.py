"""
test_decision_interview.py — CLI 인터뷰 워크플로우 검증.

실제 stdin/stdout 사용 안 함. input_fn / output_fn 주입으로 mock.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.decision.config import WeightConfig
from core.decision.interview import default_weights_path, interactive_interview


def _make_input_fn(answers: list[str]):
    """순서대로 답변하는 input mock. 답변 소진되면 IndexError로 의도적 실패."""
    iter_ans = iter(answers)
    return lambda prompt="": next(iter_ans)


def test_interview_basic_flow_creates_valid_config(tmp_path):
    answers = [
        # 1번 priority
        "per", "30", "lower", "저PER",
        # 2번 priority
        "roe", "40", "higher", "고ROE",
        # 3번 priority + done
        "momentum_pct", "30", "higher", "모멘텀",
        "done",
        # must_have 2개 + done
        "per<30",
        "ensemble_count>=2",
        "done",
    ]
    save_path = tmp_path / "weights.yml"
    cfg = interactive_interview(
        input_fn=_make_input_fn(answers),
        output_fn=lambda *_a, **_kw: None,
        save_path=save_path,
    )
    assert isinstance(cfg, WeightConfig)
    assert len(cfg.priorities) == 3
    assert cfg.priorities[0].key == "per"
    assert cfg.priorities[0].weight == 30.0
    assert cfg.priorities[0].direction == "lower_better"
    assert cfg.must_have == ["per<30", "ensemble_count>=2"]
    # 디스크 저장 검증
    assert save_path.exists()
    reloaded = WeightConfig.load(save_path)
    assert len(reloaded.priorities) == 3


def test_interview_reprompts_on_invalid_weight_sum(tmp_path):
    """가중치 합 != 100% 시 재입력 유도. 첫 시도 합 90 → 두 번째 100."""
    answers = [
        # 1차 입력 (합 90 — 실패)
        "per", "30", "lower", "저PER",
        "roe", "60", "higher", "고ROE",
        "done",
        # 재입력 안내 후 다시 처음부터
        "per", "40", "lower", "저PER",
        "roe", "60", "higher", "고ROE",
        "done",
        # must_have skip
        "done",
    ]
    cfg = interactive_interview(
        input_fn=_make_input_fn(answers),
        output_fn=lambda *_a, **_kw: None,
        save_path=tmp_path / "weights.yml",
    )
    assert sum(p.weight for p in cfg.priorities) == 100.0


def test_interview_direction_aliases(tmp_path):
    """direction 입력은 'lower'/'higher' 같은 짧은 별칭도 허용."""
    answers = [
        "per", "50", "lower", "저PER",
        "roe", "50", "higher", "고ROE",
        "done",
        "done",  # must_have skip
    ]
    cfg = interactive_interview(
        input_fn=_make_input_fn(answers),
        output_fn=lambda *_a, **_kw: None,
        save_path=tmp_path / "weights.yml",
    )
    assert cfg.priorities[0].direction == "lower_better"
    assert cfg.priorities[1].direction == "higher_better"


def test_interview_must_have_skip(tmp_path):
    """첫 must_have 입력에서 'done' → 빈 must_have."""
    answers = [
        "per", "100", "lower", "저PER",
        "done",
        "done",  # must_have skip 즉시
    ]
    cfg = interactive_interview(
        input_fn=_make_input_fn(answers),
        output_fn=lambda *_a, **_kw: None,
        save_path=tmp_path / "weights.yml",
    )
    assert cfg.must_have == []


def test_interview_minimum_priorities():
    """priority가 0개인 채로 'done' 즉시 입력 → ValueError."""
    answers = ["done"]
    with pytest.raises(ValueError, match="최소.*1"):
        interactive_interview(
            input_fn=_make_input_fn(answers),
            output_fn=lambda *_a, **_kw: None,
            save_path=None,
        )


def test_default_weights_path_under_home():
    """default 저장 위치는 ~/.kospi-scanner/weights.yml."""
    p = default_weights_path()
    assert isinstance(p, Path)
    assert p.name == "weights.yml"
    assert ".kospi-scanner" in p.parts


def test_interview_invalid_weight_value_reprompts(tmp_path):
    """숫자 아닌 weight 입력 → 재입력 유도."""
    answers = [
        "per",
        "abc",       # 첫 weight 입력 — invalid
        "30",        # 재입력 — valid
        "lower", "저PER",
        "roe", "70", "higher", "고ROE",
        "done",
        "done",
    ]
    cfg = interactive_interview(
        input_fn=_make_input_fn(answers),
        output_fn=lambda *_a, **_kw: None,
        save_path=tmp_path / "weights.yml",
    )
    assert cfg.priorities[0].weight == 30.0
