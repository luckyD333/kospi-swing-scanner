"""
strategies/__init__.py — 전략 registry (Open-Closed).

REGISTRY 값은 `Callable[[], Strategy]` (factory). 클래스 그대로(class()) 와 lambda 둘 다 가능.
StrategyOneDv2 는 timeframe 파라미터로 4 변형(1D/1W/1h/30m) 등록.

새 전략 추가 절차:
  1. strategies/strategy_<name>.py 작성 — Strategy Protocol 충족 (name 클래스 속성, scan 메서드)
  2. 생성자 인자 없이 호출 가능하면 자동 등록됨 (본 파일 수정 불필요)
  3. 생성자 인자가 필요하거나 다중 변형 등록이 필요하면 REGISTRY 에 명시 추가
"""
from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from pathlib import Path

from core.strategy_base import Strategy

from .strategy_four_pullback_ma import StrategyFourPullbackMa
from .strategy_five_bull_flag import StrategyFiveBullFlag
from .strategy_one_d_v2 import StrategyOneDv2, StrategyOneDv2Config
from .strategy_three_trend_following import StrategyThreeTrendFollowing
from .strategy_two_cross_sectional_momentum import StrategyTwoCrossSectionalMomentum

# 등록된 전략. 키 = CLI 에서 노출되는 이름. 값 = 인자 없이 호출하면 Strategy 인스턴스 반환하는 factory.
REGISTRY: dict[str, Callable[[], Strategy]] = {
    "strategy_one_d_v2": lambda: StrategyOneDv2(timeframe="1D"),
    "strategy_one_w_v2": lambda: StrategyOneDv2(timeframe="1W"),
    "strategy_one_1h_v2": lambda: StrategyOneDv2(timeframe="1h"),
    "strategy_one_30m_v2": lambda: StrategyOneDv2(timeframe="30m"),
    "strategy_one_d_v2_r1": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(engulf_strict=False),
        timeframe="1D",
        name_suffix="_r1",
    ),
    "strategy_one_d_v2_r2": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(
            engulf_strict=False,
            db_freshness=4,
            db_price_tolerance=0.05,
        ),
        timeframe="1D",
        name_suffix="_r2",
    ),
    # 1W 완화 변형
    "strategy_one_w_v2_r1": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(engulf_strict=False),
        timeframe="1W",
        name_suffix="_r1",
    ),
    "strategy_one_w_v2_r2": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(
            engulf_strict=False,
            db_freshness=4,
            db_price_tolerance=0.05,
        ),
        timeframe="1W",
        name_suffix="_r2",
    ),
    # 1h 완화 변형
    "strategy_one_1h_v2_r1": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(engulf_strict=False),
        timeframe="1h",
        name_suffix="_r1",
    ),
    "strategy_one_1h_v2_r2": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(
            engulf_strict=False,
            db_freshness=4,
            db_price_tolerance=0.05,
        ),
        timeframe="1h",
        name_suffix="_r2",
    ),
    # 30m 완화 변형
    "strategy_one_30m_v2_r1": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(engulf_strict=False),
        timeframe="30m",
        name_suffix="_r1",
    ),
    "strategy_one_30m_v2_r2": lambda: StrategyOneDv2(
        config=StrategyOneDv2Config(
            engulf_strict=False,
            db_freshness=4,
            db_price_tolerance=0.05,
        ),
        timeframe="30m",
        name_suffix="_r2",
    ),
    "strategy_two_cross_sectional_momentum": lambda: StrategyTwoCrossSectionalMomentum(timeframe="1D"),
    "strategy_two_1h": lambda: StrategyTwoCrossSectionalMomentum(timeframe="1h"),
    "strategy_two_30m": lambda: StrategyTwoCrossSectionalMomentum(timeframe="30m"),
    "strategy_three_trend_following": lambda: StrategyThreeTrendFollowing(timeframe="1D"),
    "strategy_three_1h": lambda: StrategyThreeTrendFollowing(timeframe="1h"),
    "strategy_three_30m": lambda: StrategyThreeTrendFollowing(timeframe="30m"),
    "strategy_four_pullback_ma":     lambda: StrategyFourPullbackMa(timeframe="1D"),
    "strategy_four_pullback_ma_1h":  lambda: StrategyFourPullbackMa(timeframe="1h"),
    "strategy_four_pullback_ma_30m": lambda: StrategyFourPullbackMa(timeframe="30m"),
    "strategy_five_bull_flag":       lambda: StrategyFiveBullFlag(timeframe="1D"),
    "strategy_five_bull_flag_1h":    lambda: StrategyFiveBullFlag(timeframe="1h"),
    "strategy_five_bull_flag_30m":   lambda: StrategyFiveBullFlag(timeframe="30m"),
}


def _autodiscover() -> None:
    """strategies/strategy_*.py 를 스캔해서 미등록 전략 클래스를 REGISTRY 에 자동 추가.

    조건:
    - 해당 파일에서 직접 정의된 클래스 (다른 모듈에서 import된 클래스 제외)
    - name 클래스 속성(str) + scan 메서드 보유
    - REGISTRY 에 아직 없는 이름
    """
    pkg = Path(__file__).parent
    for path in sorted(pkg.glob("strategy_*.py")):
        module_name = f"strategies.{path.stem}"
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module_name:
                continue
            strategy_name = getattr(cls, "name", None)
            if not isinstance(strategy_name, str) or not hasattr(cls, "scan"):
                continue
            if strategy_name not in REGISTRY:
                REGISTRY[strategy_name] = cls


_autodiscover()

# strict → [r1, r2] 순서 fallback 체인. strict가 0개일 때 r1 먼저 시도, 여전히 0개면 r2.
FALLBACKS: dict[str, list[str]] = {
    "strategy_one_d_v2": ["strategy_one_d_v2_r1", "strategy_one_d_v2_r2"],
    "strategy_one_w_v2": ["strategy_one_w_v2_r1", "strategy_one_w_v2_r2"],
    "strategy_one_1h_v2": ["strategy_one_1h_v2_r1", "strategy_one_1h_v2_r2"],
    "strategy_one_30m_v2": ["strategy_one_30m_v2_r1", "strategy_one_30m_v2_r2"],
}


def register(factory: Callable[[], Strategy], name: str | None = None) -> Callable[[], Strategy]:
    """런타임 등록 헬퍼 — 테스트의 dummy 전략 주입에 사용.

    factory 가 클래스면 .name 속성 사용 (legacy). lambda/factory 함수면 name 인자 필수.
    이미 같은 이름이 있으면 덮어쓰기 (테스트 재실행 안전).
    """
    if name is None:
        name = getattr(factory, "name", None)
    if not name:
        raise ValueError(f"strategy factory missing name (pass name= kwarg): {factory}")
    if not callable(factory):
        raise ValueError(f"strategy factory must be callable: {factory}")
    # 클래스 직접 등록 시 scan 메서드 필수 검증
    if isinstance(factory, type) and not hasattr(factory, "scan"):
        raise ValueError(f"strategy class missing scan method: {factory}")
    REGISTRY[name] = factory
    return factory


def unregister(name: str) -> None:
    """REGISTRY 에서 전략 제거 (테스트 정리용)."""
    REGISTRY.pop(name, None)


def available() -> list[str]:
    """등록된 전략 이름 리스트 (정렬)."""
    return sorted(REGISTRY.keys())
