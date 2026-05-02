"""
core/decision/config.py — 가중치 + 필수 조건 데이터 모델.

Phase 2 의사결정 프레임워크의 사용자 설정. weights.yml 로드/저장 + must_have DSL.

DSL 형식:
  "<key><op><value>"  e.g. "per<30", "ensemble_count>=2", "roe>=5"
연산자: <, <=, >, >=, ==, !=
"""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

VALID_DIRECTIONS = ("lower_better", "higher_better")
_DSL_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?)\s*$")
_OPS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}


@dataclass
class Priority:
    """단일 우선순위 항목 (가중치 + 정규화 방향)."""
    key: str           # 메트릭 키 (per, roe, momentum_pct, score, ensemble_count, ...)
    weight: float      # 0~100 (전체 합이 100이어야 함)
    direction: str     # "lower_better" | "higher_better"
    label: str         # 사용자 표기

    def __post_init__(self):
        if self.direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be one of {VALID_DIRECTIONS}, got {self.direction!r}"
            )


@dataclass
class MustHaveOp:
    """파싱된 필수 조건 (key OP value).

    optional=True면 메트릭이 후보에 없을 때 *조건 자체를 skip*해서 통과로 간주.
    DSL: '?per<30' (key 앞 '?' prefix)는 optional. 'per<30' 는 필수.
    """
    key: str
    op: str
    value: float
    optional: bool = False


@dataclass
class WeightConfig:
    """가중치 + 필수 조건 묶음. yaml 로드/저장 지원."""
    priorities: list[Priority]
    must_have: list[str] = field(default_factory=list)

    def __post_init__(self):
        # 합 100% 검증 (부동소수점 허용)
        total = sum(p.weight for p in self.priorities)
        if abs(total - 100.0) > 0.01:
            raise ValueError(
                f"priorities 가중치 합이 100이 아니에요: {total} "
                f"({[p.key + ':' + str(p.weight) for p in self.priorities]})"
            )
        # 키 중복 검증
        keys = [p.key for p in self.priorities]
        if len(keys) != len(set(keys)):
            dups = [k for k in keys if keys.count(k) > 1]
            raise ValueError(f"priority key 중복: {sorted(set(dups))}")

    # -- yaml -------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str) -> "WeightConfig":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"weights 설정 파일 없음: {p}")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        priorities = [
            Priority(
                key=item["key"],
                weight=float(item["weight"]),
                direction=item["direction"],
                label=item.get("label", item["key"]),
            )
            for item in data.get("priorities", [])
        ]
        must_have = list(data.get("must_have", []))
        return cls(priorities=priorities, must_have=must_have)

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "priorities": [
                {"key": x.key, "weight": x.weight,
                 "direction": x.direction, "label": x.label}
                for x in self.priorities
            ],
            "must_have": list(self.must_have),
        }
        p.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# must_have DSL
# ---------------------------------------------------------------------------

def parse_must_have(expr: str) -> MustHaveOp:
    """'per<30' → MustHaveOp(...). '?per<30' → optional=True (결측 시 통과)."""
    raw = expr.strip()
    optional = False
    if raw.startswith("?"):
        optional = True
        raw = raw[1:]
    m = _DSL_RE.match(raw)
    if not m:
        raise ValueError(
            f"must_have 표현식 파싱 실패: {expr!r}. "
            "형식: '[?]<key><op><value>' (op: <, <=, >, >=, ==, !=). "
            "'?' prefix는 메트릭 결측 시 조건 skip."
        )
    key, op, value = m.group(1), m.group(2), float(m.group(3))
    return MustHaveOp(key=key, op=op, value=value, optional=optional)


def eval_must_have(exprs: list[str], metrics: dict) -> bool:
    """모든 필수 조건이 통과하면 True.

    결측/None 메트릭 처리:
      - 필수 조건('per<30'): 결측 → False (보수적, 평가 불가 = 탈락)
      - 옵션 조건('?per<30'): 결측 → 조건 skip (통과로 간주)
    """
    for expr in exprs:
        op = parse_must_have(expr)
        actual = metrics.get(op.key)
        if actual is None:
            if op.optional:
                continue  # optional 조건은 결측 시 skip
            return False
        try:
            if not _OPS[op.op](float(actual), op.value):
                return False
        except (TypeError, ValueError):
            return False
    return True
