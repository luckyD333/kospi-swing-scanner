"""
core/strategy_base.py — 멀티 전략 공통 인터페이스.

모든 전략은 Strategy Protocol 을 만족해야 하며, 동일한 ScanContext 입력으로
Candidate 리스트를 반환한다. 백테스트 어댑터는 Candidate → TradeSignal 변환만.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import pandas as pd


@dataclass
class ScanContext:
    """단일 fetch 결과를 모든 전략이 공유하는 read-only 컨테이너.

    attribute:
      - target_date: YYYYMMDD 기준일
      - universe: 시총·유동성 필터 통과 ticker 튜플 (frozen 호환)
      - ohlcv: ticker → OHLCV DataFrame (legacy alias = ohlcv_by_tf["1D"])
      - names: ticker → 종목명
      - market_caps: ticker → 시가총액(억원)
      - market: KOSPI | KOSDAQ | KRX
      - ohlcv_by_tf: timeframe → ticker → OHLCV (multi-tf scan 용)
      - fundamentals: ticker → {per, roe, foreign_pct, naver_url, ...} (Phase 1)
        전략은 직접 읽지 않음 (전략 무수정 원칙). runner가 후보 metadata에 사후 주입.
      - regime: dict | None — regime_analysis.json 로드 결과 (없으면 None)
      - per_ticker_regime: ticker → "UPTREND_STRONG"|"RANGE"|... (Task 5a, default={})
      - donchian_1h_by_ticker: ticker → DonchianFrame | None (1h setup quality, Task 5a, default={})
      - donchian_1d_by_ticker: ticker → DonchianFrame | None (1d 가드레일용, default={})

    legacy 호환: `ohlcv` 또는 `ohlcv_by_tf` 중 하나만 채워서 생성하면 다른 쪽이
    `__post_init__` 에서 자동 동기화된다.
    """
    target_date: str
    universe: tuple[str, ...]
    ohlcv: dict[str, pd.DataFrame]
    names: dict[str, str]
    market_caps: dict[str, float]
    market: str
    ohlcv_by_tf: dict[str, dict[str, pd.DataFrame]] = field(default_factory=dict)
    fundamentals: dict[str, dict] = field(default_factory=dict)
    regime: dict | None = None  # regime_analysis.json 로드 결과 (없으면 None)
    per_ticker_regime: dict[str, str] = field(default_factory=dict)  # Task 5a
    donchian_1h_by_ticker: dict = field(default_factory=dict)  # Task 5a
    donchian_1d_by_ticker: dict = field(default_factory=dict)  # 1d 가드레일용

    def __post_init__(self):
        if not self.ohlcv_by_tf and self.ohlcv:
            self.ohlcv_by_tf = {"1D": self.ohlcv}
        elif "1D" in self.ohlcv_by_tf and not self.ohlcv:
            self.ohlcv = self.ohlcv_by_tf["1D"]


@dataclass
class Candidate:
    """전략 출력 단위. 백테스트 어댑터는 이 객체를 TradeSignal 로 변환한다."""
    ticker: str
    name: str
    strategy: str           # registry key (예: "strategy_one_d_v2")
    signal_date: pd.Timestamp
    score: float            # 0.0 ~ 1000.0
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    current_price: float = 0.0   # 반올림 전 원시 현재가 (마지막 봉 종가)
    market_cap_bil: float = 0.0
    volume_20d_avg: float = 0.0
    conditions_met: dict[str, bool] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    limit_entry: int | None = None   # 30m 지지선 기반 권장 지정가 (None = 권장 없음)
    limit_stop: int | None = None    # limit_entry 기준 ATR 재계산 손절

    def __post_init__(self):
        if not (0.0 <= self.score <= 1000.0):
            raise ValueError(f"score out of range: {self.score}")
        if not (self.stop_loss < self.entry_price < self.target_1 <= self.target_2):
            raise ValueError(
                f"price order invalid: sl={self.stop_loss} entry={self.entry_price} "
                f"t1={self.target_1} t2={self.target_2}"
            )
        if self.limit_entry is not None:
            if self.limit_stop is None:
                raise ValueError("limit_stop required when limit_entry is set")
            if not (0 < self.limit_stop < self.limit_entry < self.target_1):
                raise ValueError(
                    f"limit price order invalid: ls={self.limit_stop} "
                    f"le={self.limit_entry} t1={self.target_1}"
                )
            if self.limit_entry >= self.entry_price:
                raise ValueError(
                    f"limit_entry must be below entry_price: "
                    f"le={self.limit_entry} entry={self.entry_price}"
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

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        """ScanContext 받아 score 내림차순 정렬된 top_n Candidate 반환."""
        ...
