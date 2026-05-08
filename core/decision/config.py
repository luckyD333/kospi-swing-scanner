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

import json
import logging
import operator
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

logger = logging.getLogger(__name__)

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


_DEFAULT_POOLS: tuple[str, ...] = ("STOCK", "ETN_ETF", "OTHER")


@dataclass
class Priority:
    """단일 우선순위 항목 (가중치 + 정규화 방향).

    PR-B (P0-2): applies_to_pools 로 Pool 별 적용 여부 표시.
      - default: 모든 풀 적용 (("STOCK", "ETN_ETF", "OTHER"))
      - 펀더멘털 항목 (per/roe): ("STOCK",) — ETN/ETF 풀에서 자동 NOT_APPLICABLE
        처리되며 가중치 동적 정규화 (aggregator).
    """
    key: str           # 메트릭 키 (per, roe, momentum_pct, score, ensemble_count, ...)
    weight: float      # 0~100 (전체 합이 100이어야 함)
    direction: str     # "lower_better" | "higher_better"
    label: str         # 사용자 표기
    applies_to_pools: tuple[str, ...] = _DEFAULT_POOLS

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
    strategy_weights: dict[str, float] = field(default_factory=dict)

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

        # Task 6: 구형식 weights 감지 → 자동 migration
        priorities_raw = data.get("priorities", [])
        if _is_legacy_weights(priorities_raw):
            # 구형식 감지됨 → backup + migration
            backup_legacy_weights(p)
            data = migrate_legacy_weights(data)

        priorities = [
            Priority(
                key=item["key"],
                weight=float(item["weight"]),
                direction=item["direction"],
                label=item.get("label", item["key"]),
                applies_to_pools=tuple(
                    item.get("applies_to_pools", _DEFAULT_POOLS),
                ),
            )
            for item in data.get("priorities", [])
        ]
        must_have = list(data.get("must_have", []))
        strategy_weights = {
            str(k): float(v)
            for k, v in data.get("strategy_weights", {}).items()
        }
        return cls(priorities=priorities, must_have=must_have, strategy_weights=strategy_weights)

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        priority_payload: list[dict] = []
        for x in self.priorities:
            entry: dict = {
                "key": x.key, "weight": x.weight,
                "direction": x.direction, "label": x.label,
            }
            # default 풀 집합과 다를 때만 yaml 에 명시 (간결성)
            if tuple(x.applies_to_pools) != _DEFAULT_POOLS:
                entry["applies_to_pools"] = list(x.applies_to_pools)
            priority_payload.append(entry)
        payload = {
            "priorities": priority_payload,
            "must_have": list(self.must_have),
        }
        if self.strategy_weights:
            payload["strategy_weights"] = dict(self.strategy_weights)
        p.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    @classmethod
    def load_dynamic(cls, path: Path | str) -> "WeightConfig":
        """dynamic_weights.json → WeightConfig.

        JSON 스키마:
        {
          "weight_config": {
            "priorities": [{"key": "per", "weight": 28.5, "direction": "lower_better", "label": "저PER"}],
            "must_have": ["per<30"],
            "strategy_weights": {"strategy_one_d_v2": 2.0}
          }
        }
        파일 없거나 파싱 실패 시 FileNotFoundError / ValueError raise.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"dynamic_weights 파일 없음: {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"dynamic_weights 파싱 실패: {e}") from e
        wc = data.get("weight_config", {})
        priorities = [
            Priority(
                key=item["key"],
                weight=float(item["weight"]),
                direction=item["direction"],
                label=item.get("label", item["key"]),
                applies_to_pools=tuple(
                    item.get("applies_to_pools", _DEFAULT_POOLS),
                ),
            )
            for item in wc.get("priorities", [])
        ]
        must_have = list(wc.get("must_have", []))
        strategy_weights = {
            str(k): float(v)
            for k, v in wc.get("strategy_weights", {}).items()
        }
        return cls(priorities=priorities, must_have=must_have, strategy_weights=strategy_weights)


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


# ---------------------------------------------------------------------------
# Task 6: Legacy weights.yml migration
# ---------------------------------------------------------------------------

LEGACY_KEY_MAP: dict[str, str | None] = {
    "ensemble_score": None,      # 잠재력에서 완전 제거 (대응 factor 없음, drop)
    "momentum_pct": "momentum_3m",  # 단기 → 중기 모멘텀으로 의미 변경
    "rr_ratio": None,             # 잠재력에서 제거, 기회 점수 R:R 그룹으로 재배치
    "ensemble": None,             # 기회 점수에서도 제거 (정보 중복)
}


def backup_legacy_weights(path: Path) -> Path | None:
    """구형식 weights.yml 을 weights.legacy.yml.bak 으로 백업.

    이미 백업이 존재하면 덮어쓰지 않음 (기존 백업 보존).
    백업 실패 시 None 반환, migration 은 진행.
    """
    backup = path.with_suffix(".legacy.yml.bak")
    if backup.exists():
        return backup  # 기존 백업 보존
    try:
        shutil.copy2(path, backup)
        logger.info(f"구형식 weights.yml 백업 생성: {backup}")
        return backup
    except OSError as e:
        logger.warning(f"weights.yml 백업 실패: {e}. 계속 진행합니다.")
        return None


def _is_legacy_weights(priorities_list: list[dict]) -> bool:
    """weights yaml 이 구형식인지 판정.

    구형식 key 가 하나라도 있으면 legacy 로 간주.
    """
    legacy_keys = set(LEGACY_KEY_MAP.keys())
    present_keys = {item.get("key") for item in priorities_list}
    return bool(present_keys & legacy_keys)


def migrate_legacy_weights(yaml_dict: dict) -> dict:
    """구형식 priority key 를 신규 key 로 변환.

    동작:
      1. priorities 리스트 순회
      2. key 가 LEGACY_KEY_MAP 에 있으면 매핑 확인
         - value 가 None → drop + 경고 (logger.warning)
         - value 가 str → key 만 신규 이름으로 갱신, weight 유지
      3. drop 된 항목의 가중치를 남은 항목에 정규화 분배
      4. 각 pool 별 weight 합 100% 로 정규화
      5. 결과 dict 반환

    이미 신규 형식이면 그대로 통과.
    """
    priorities = yaml_dict.get("priorities", [])

    if not _is_legacy_weights(priorities):
        # 신규 형식이거나 legacy key 가 없으면 그대로 반환
        return yaml_dict

    new_priorities = []
    dropped_weight = 0.0

    for item in priorities:
        key = item.get("key")

        if key in LEGACY_KEY_MAP:
            new_key = LEGACY_KEY_MAP[key]
            if new_key is None:
                # drop 케이스
                dropped_weight += item.get("weight", 0.0)
                logger.warning(
                    f"잠재력 점수에서 제거됨 (대응 factor 없음): {key!r}. "
                    f"기회 점수 또는 신규 factor 로 재배치되었습니다."
                )
                continue
            else:
                # 매핑 케이스: key 만 변경, 나머지는 유지
                item = dict(item)  # shallow copy
                logger.warning(
                    f"priority key 변환: {key!r} → {new_key!r}. "
                    f"의미 변경 확인 (단기→중기 모멘텀 등): {item.get('label')}"
                )
                item["key"] = new_key

        new_priorities.append(item)

    # drop 된 가중치를 남은 항목에 proportionally 분배 (정규화)
    if new_priorities and dropped_weight > 0.01:
        total_weight = sum(p.get("weight", 0.0) for p in new_priorities)
        if total_weight > 0.01:
            scale_factor = 100.0 / total_weight
            for item in new_priorities:
                item["weight"] = item.get("weight", 0.0) * scale_factor
            logger.info(
                f"drop 된 가중치({dropped_weight:.1f}) 를 남은 항목에 정규화 분배. "
                f"정규화 인수: {scale_factor:.3f}"
            )

    # 새 priorities 로 dict 업데이트
    result = dict(yaml_dict)
    result["priorities"] = new_priorities

    # Pool 별 weight 합 검증
    _validate_pool_weights(result)

    return result


def _validate_pool_weights(yaml_dict: dict) -> None:
    """Pool 별 가중치 합 검증 및 경고.

    각 pool (STOCK, ETN_ETF, BOND_ETF, OTHER) 별로
    적용 가능한 priority 의 weight 합이 100% 인지 확인.
    미달 또는 초과 시 logger.warning 으로 안내.
    """
    priorities = yaml_dict.get("priorities", [])

    # pool 명 수집
    all_pools = set()
    for item in priorities:
        applies_to = item.get("applies_to_pools", _DEFAULT_POOLS)
        all_pools.update(applies_to)

    # pool 별 weight 합 검증
    for pool in all_pools:
        pool_weight = sum(
            item.get("weight", 0.0)
            for item in priorities
            if pool in item.get("applies_to_pools", _DEFAULT_POOLS)
        )
        if abs(pool_weight - 100.0) > 0.01:
            logger.warning(
                f"Pool '{pool}' 의 priority weight 합이 100이 아닙니다: {pool_weight:.2f}. "
                f"aggregator 에서 동적 정규화되거나, 설정을 검토하세요."
            )
