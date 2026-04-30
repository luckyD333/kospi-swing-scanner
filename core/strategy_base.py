"""
core/strategy_base.py — 멀티 전략 공통 인터페이스.

모든 전략은 Strategy Protocol 을 만족해야 하며, 동일한 ScanContext 입력으로
Candidate 리스트를 반환한다. 백테스트 어댑터는 Candidate → TradeSignal 변환만.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Protocol, Tuple, runtime_checkable

import pandas as pd


@dataclass
class ScanContext:
    """단일 fetch 결과를 모든 전략이 공유하는 read-only 컨테이너.

    attribute:
      - target_date: YYYYMMDD 기준일
      - universe: 시총·유동성 필터 통과 ticker 튜플 (frozen 호환)
      - ohlcv: ticker → OHLCV DataFrame (지표 미계산 raw)
      - names: ticker → 종목명
      - market_caps: ticker → 시가총액(억원)
      - market: KOSPI | KOSDAQ | KRX
    """
    target_date: str
    universe: Tuple[str, ...]
    ohlcv: Dict[str, pd.DataFrame]
    names: Dict[str, str]
    market_caps: Dict[str, float]
    market: str


@dataclass
class Candidate:
    """전략 출력 단위. 백테스트 어댑터는 이 객체를 TradeSignal 로 변환한다."""
    ticker: str
    name: str
    strategy: str           # registry key (예: "strategy_one_d_v2")
    signal_date: pd.Timestamp
    score: float            # 0.0 ~ 1.0
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    market_cap_bil: float = 0.0
    volume_20d_avg: float = 0.0
    conditions_met: Dict[str, bool] = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score out of range: {self.score}")
        if not (self.stop_loss < self.entry_price < self.target_1 <= self.target_2):
            raise ValueError(
                f"price order invalid: sl={self.stop_loss} entry={self.entry_price} "
                f"t1={self.target_1} t2={self.target_2}"
            )

    @property
    def risk_pct(self) -> float:
        return (self.entry_price - self.stop_loss) / self.entry_price * 100

    @property
    def reward_pct_t1(self) -> float:
        return (self.target_1 - self.entry_price) / self.entry_price * 100

    @property
    def reward_pct_t2(self) -> float:
        return (self.target_2 - self.entry_price) / self.entry_price * 100


@runtime_checkable
class Strategy(Protocol):
    """모든 전략 구현이 만족해야 하는 인터페이스."""
    name: str

    def scan(self, ctx: ScanContext, top_n: int) -> List[Candidate]:
        """ScanContext 받아 score 내림차순 정렬된 top_n Candidate 반환."""
        ...
