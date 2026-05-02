"""
core/decision/interview.py — CLI 인터뷰 워크플로우.

사용자에게 우선순위·가중치·필수 조건을 묻고 WeightConfig 를 생성한다.
input_fn / output_fn 주입 가능 → 단위 테스트에서 stdin/stdout 없이 검증.

워크플로우 (의사결정 프레임워크 SKILL.md Step 1):
  1. priority 항목 N개 입력 (key/weight/direction/label)
  2. 가중치 합 100% 검증, 실패 시 처음부터 재입력
  3. must_have 조건 N개 입력 (DSL: 'per<30' 등)
  4. ~/.kospi-scanner/weights.yml 저장
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import Priority, WeightConfig

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]

_DIRECTION_ALIASES = {
    "lower": "lower_better", "lower_better": "lower_better",
    "low": "lower_better", "<": "lower_better",
    "higher": "higher_better", "higher_better": "higher_better",
    "high": "higher_better", ">": "higher_better",
}


def default_weights_path() -> Path:
    """기본 저장 경로: ~/.kospi-scanner/weights.yml"""
    return Path.home() / ".kospi-scanner" / "weights.yml"


def interactive_interview(
    input_fn: InputFn | None = None,
    output_fn: OutputFn | None = None,
    save_path: Path | None = None,
) -> WeightConfig:
    """
    인터뷰 → WeightConfig 생성. save_path 주어지면 yaml 저장도 수행.

    input_fn / output_fn 기본값은 None — 호출 시점에 builtins.input/print 로
    lazy resolve. 테스트가 `patch("builtins.input")` 하면 자동 반영.
    """
    if input_fn is None:
        input_fn = input
    if output_fn is None:
        output_fn = print
    output_fn(_intro_text())

    # 1) priority 입력 — 합 100% 될 때까지 반복. 0개 입력 시 인터뷰 중단.
    priorities: list[Priority] = []
    while True:
        priorities = _collect_priorities(input_fn, output_fn)
        if not priorities:
            # 사용자가 즉시 'done' → 인터뷰 중단
            break
        total = sum(p.weight for p in priorities)
        if abs(total - 100.0) <= 0.01:
            break
        output_fn(
            f"⚠️  가중치 합이 {total}% 에요. 100%가 되어야 해요. 처음부터 다시 입력해주세요.\n"
        )

    if not priorities:
        raise ValueError("priority 최소 1개 필요해요.")

    # 2) must_have 입력
    must_have = _collect_must_have(input_fn, output_fn)

    cfg = WeightConfig(priorities=priorities, must_have=must_have)

    # 3) 저장
    if save_path is not None:
        cfg.save(save_path)
        output_fn(f"\n✅ 저장 완료: {save_path}\n")

    return cfg


def _collect_priorities(input_fn: InputFn, output_fn: OutputFn) -> list[Priority]:
    """priority 항목들 입력. 'done' 입력 시 종료."""
    priorities: list[Priority] = []
    output_fn(
        "\n─── 우선순위 항목 입력 ───\n"
        "각 항목의 key, 가중치(%), 방향(lower/higher), 라벨을 입력해요.\n"
        "key 자리에 'done' 입력 시 종료.\n"
    )
    while True:
        idx = len(priorities) + 1
        key = input_fn(f"[{idx}] key (또는 'done'): ").strip()
        if key.lower() == "done":
            break
        if not key:
            continue
        weight = _ask_float(input_fn, output_fn, f"[{idx}] 가중치(%): ")
        direction = _ask_direction(input_fn, output_fn, f"[{idx}] 방향: ")
        label = input_fn(f"[{idx}] 라벨: ").strip() or key
        try:
            priorities.append(Priority(key=key, weight=weight,
                                       direction=direction, label=label))
        except ValueError as e:
            output_fn(f"  ⚠️ {e}. 항목 입력 무시.\n")
            continue
    return priorities


def _collect_must_have(input_fn: InputFn, output_fn: OutputFn) -> list[str]:
    """필수 조건 입력. 'done' 시 종료."""
    output_fn(
        "\n─── 필수 조건 (must_have) ───\n"
        "DSL 형식: '<key><op><value>' 예: 'per<30', 'ensemble_count>=2'\n"
        "조건 미충족 후보는 자동 탈락. 'done' 입력 시 종료.\n"
        "\n"
        "⚠ 메트릭 결측 처리:\n"
        "  - 일반 조건 ('per<30'): 메트릭 결측 시 *탈락*\n"
        "  - 옵션 조건 ('?per<30', '?' prefix): 메트릭 결측 시 *조건 skip*\n"
        "  → 전략별로 안 만드는 메트릭(예: momentum_pct는 strategy_two만 생성)은\n"
        "    '?' prefix 권장. 그래야 다른 전략 후보가 부당 탈락 안 해요.\n"
    )
    must_have: list[str] = []
    while True:
        expr = input_fn(f"[{len(must_have) + 1}] 조건 (또는 'done'): ").strip()
        if expr.lower() == "done":
            break
        if expr:
            must_have.append(expr)
    return must_have


def _ask_float(input_fn: InputFn, output_fn: OutputFn, prompt: str) -> float:
    while True:
        raw = input_fn(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            output_fn(f"  ⚠️ 숫자가 아니에요: {raw!r}. 다시 입력해주세요.\n")


def _ask_direction(input_fn: InputFn, output_fn: OutputFn, prompt: str) -> str:
    while True:
        raw = input_fn(prompt).strip().lower()
        if raw in _DIRECTION_ALIASES:
            return _DIRECTION_ALIASES[raw]
        output_fn(
            f"  ⚠️ 알 수 없는 방향: {raw!r}. 'lower' 또는 'higher' 입력해주세요.\n"
        )


def _intro_text() -> str:
    return (
        "\n========================================================\n"
        " 의사결정 프레임워크 — 가중치 인터뷰\n"
        "========================================================\n"
        "Step 0 (분류): 결정의 가역성과 검토 상한을 미리 정해주세요.\n"
        "  - Type 1 (one-way door): 큰 영향, 풀 프로세스 권장\n"
        "  - Type 2 (two-way door): 가전·메뉴 등, 경량 프로세스\n"
        "  - 검토 상한: 영향 100만원 이하 ≤ 6회 / 1000만원 이하 ≤ 10회 / 그 이상 풀 프로세스\n"
        "\n"
        "Step 1 (본 인터뷰): 후보 평가 우선순위와 가중치를 정의해요.\n"
        "  ‼  후보를 *보기 전에* 가중치를 정해야 motivated reasoning 회피.\n"
        "  ‼  항목은 5~9개 권장 (Miller's Law).\n"
        "========================================================\n"
    )
