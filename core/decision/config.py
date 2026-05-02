"""
core/decision/config.py — 가중치 + 필수 조건 데이터 모델.

Phase 2 의사결정 프레임워크의 사용자 설정. weights.yml 로드/저장 + must_have DSL.

DSL 형식:
  "<key><op><value>"  e.g.
    "per<30"                                    (numeric)
    "ensemble_count>=2"                         (numeric)
    "source_strategy==gap_up_momentum_top"      (string, ==/!= 만)
    "is_high_quality==True"                     (boolean)
연산자: <, <=, >, >=, ==, !=
부등호(<, <=, >, >=)는 numeric 전용. string/boolean 에는 ==/!= 만.
"""
from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

VALID_DIRECTIONS = ("lower_better", "higher_better")
# value 는 numeric/string/boolean 모두 허용 — 임의 word 매칭 후 parse 단계에서 type 분기.
_DSL_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z_0-9]*)\s*(<=|>=|==|!=|<|>)\s*(.+?)\s*$"
)
_OPS: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
}
_NUMERIC_ONLY_OPS = ("<", "<=", ">", ">=")


def _coerce_value(raw: str) -> float | str | bool:
    """DSL value 를 type-aware 로 변환.

    'True'/'False' → boolean, 숫자 문자열 → float, 그 외 → string.
    """
    s = raw.strip()
    if s == "True":
        return True
    if s == "False":
        return False
    try:
        return float(s)
    except ValueError:
        return s


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

    value 타입:
      - numeric (float): 모든 연산자 사용 가능
      - string: ==/!= 만 (부등호는 numeric only)
      - boolean (True/False): ==/!= 만
    """
    key: str
    op: str
    value: float | str | bool
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
    """'per<30' → MustHaveOp(...). '?per<30' → optional=True (결측 시 통과).

    string/boolean value 도 지원: 'source_strategy==gap_up_momentum_top',
    'is_high_quality==True'. 부등호(<, >, <=, >=)는 numeric 전용이므로
    string/boolean value 와 함께 쓰면 eval 단계에서 평가 실패해 탈락 처리.
    """
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
    key, op, value = m.group(1), m.group(2), _coerce_value(m.group(3))
    return MustHaveOp(key=key, op=op, value=value, optional=optional)


def eval_must_have(exprs: list[str], metrics: dict) -> bool:
    """모든 필수 조건이 통과하면 True.

    결측/None 메트릭 처리:
      - 필수 조건('per<30'): 결측 → False (보수적, 평가 불가 = 탈락)
      - 옵션 조건('?per<30'): 결측 → 조건 skip (통과로 간주)

    Type 처리:
      - 부등호(<, <=, >, >=): numeric 전용. value 가 string/boolean 이거나
        actual 이 float 변환 불가 시 False (탈락).
      - ==/!=: type-aware 직접 비교 (numeric/string/boolean 모두 가능).
    """
    for expr in exprs:
        op = parse_must_have(expr)
        actual = metrics.get(op.key)
        if actual is None:
            if op.optional:
                continue  # optional 조건은 결측 시 skip
            return False
        if op.op in _NUMERIC_ONLY_OPS:
            # 부등호는 numeric 전용. value 가 string/boolean 이면 평가 불가 → 탈락
            if isinstance(op.value, str) or isinstance(op.value, bool):
                return False
            try:
                if not _OPS[op.op](float(actual), float(op.value)):
                    return False
            except (TypeError, ValueError):
                return False
        else:
            # ==/!= : type-aware 직접 비교
            try:
                if not _OPS[op.op](actual, op.value):
                    return False
            except TypeError:
                return False
    return True
