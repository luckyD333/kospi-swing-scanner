"""
strategies/__init__.py — 전략 registry (Open-Closed: 신규 추가 시 한 줄만 수정).

새 전략 추가 절차:
  1. strategies/<name>.py 작성 — Strategy Protocol 충족 (name, scan)
  2. 본 파일 import 한 줄 + REGISTRY 한 줄 추가
  3. 전략 단위 테스트 + tests/test_ocp.py 통과 확인
"""
from __future__ import annotations

from typing import Dict, Type

from core.strategy_base import Strategy

from .strategy_one_d_v2 import StrategyOneDv2

# 등록된 전략. 키 = CLI 에서 노출되는 이름.
REGISTRY: Dict[str, Type[Strategy]] = {
    StrategyOneDv2.name: StrategyOneDv2,
}


def register(strategy_cls: Type[Strategy]) -> Type[Strategy]:
    """런타임 등록 헬퍼 — 테스트의 dummy 전략 주입에 사용.

    Strategy Protocol 충족 (.name 속성 + .scan 메소드) 확인 후 REGISTRY 갱신.
    이미 같은 이름이 있으면 덮어쓰기 (테스트 재실행 안전).
    """
    name = getattr(strategy_cls, "name", None)
    if not name:
        raise ValueError(f"strategy class missing .name attribute: {strategy_cls}")
    if not callable(getattr(strategy_cls, "scan", None)):
        raise ValueError(f"strategy class missing .scan() method: {strategy_cls}")
    REGISTRY[name] = strategy_cls
    return strategy_cls


def unregister(name: str) -> None:
    """REGISTRY 에서 전략 제거 (테스트 정리용)."""
    REGISTRY.pop(name, None)


def available() -> list[str]:
    """등록된 전략 이름 리스트 (정렬)."""
    return sorted(REGISTRY.keys())
