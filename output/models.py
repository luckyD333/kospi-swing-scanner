# output/models.py
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class Fundamentals(BaseModel):
    per: Optional[float] = None
    per_negative: bool = False  # PR-A: 적자 sentinel ('—'/'-'/<0). DATA_MISSING 과 구분
    high_52w: Optional[int] = None
    low_52w: Optional[int] = None


class Flow(BaseModel):
    foreign_ratio_pct: Optional[float] = None


class TickerSnapshot(BaseModel):
    ticker: str
    name: str
    name_en: Optional[str] = None
    current_price: int
    change_pct: float
    volume: int
    market_cap_krw: Optional[int] = None
    fundamentals: Fundamentals
    flow: Flow
    price_history_atr14: Optional[int] = None
    external_links: dict[str, str] = {}
    # timeframe 별 RSI(14). strategy 후보 여부와 무관하게 ticker 의 indicator.
    rsi_by_tf: Optional[dict[str, Optional[float]]] = None


class MarketIndexRaw(BaseModel):
    value: float
    change_pct: float


class MarketSnapshot(BaseModel):
    schema_version: str = "1.0"
    generated_at: str
    source: dict[str, str]
    market_indices: dict[str, MarketIndexRaw]
    tickers: dict[str, TickerSnapshot]
    # strategy 후보 여부와 무관한 시장 국면 (timeframe_scores: {"1d": {...}, "1h": {...}})
    market_regime: Optional[dict] = None
    # 다축 시황 — timeframe → breadth/axes 지표
    market_breadth: Optional[dict] = None
    market_axes: Optional[dict] = None
    # Fear & Greed 컴포지트 (Momentum + Breadth + Volatility) + 30일 sparkline.
    # 형식: {"score": 0-100, "label": "Extreme Fear|...|Extreme Greed",
    #         "components": {"momentum": .., "breadth": .., "volatility": ..},
    #         "history": [{"date": "YYYY-MM-DD", "score": ..}, ...]}
    fear_greed: Optional[dict] = None


class TradePlanDerived(BaseModel):
    risk_per_share: int
    risk_pct: float
    reward_1_pct: float
    reward_2_pct: Optional[float] = None


class TradePlan(BaseModel):
    entry: int                              # EOD 종가 기반 진입가 (백테스트 참조)
    stop: int                               # 원래 기술적 손절
    target_1: int
    target_2: Optional[int] = None
    rr_ratio: float
    rr_band: Literal["SWEET", "UNDER", "OVER"]
    atr_14: Optional[int] = None
    rsi_14: Optional[float] = None
    derived: Optional[TradePlanDerived] = Field(default=None)

    # 30m 지지선 기반 권장 지정가 진입 (UI 주 표시값)
    limit_entry: Optional[int] = None
    limit_stop: Optional[int] = None
    rr_ratio_limit: Optional[float] = None
    rr_band_limit: Optional[Literal["SWEET", "UNDER", "OVER"]] = None

    @model_validator(mode="after")
    def compute_derived(self) -> TradePlan:
        risk = self.entry - self.stop
        reward1 = self.target_1 - self.entry
        reward2 = (self.target_2 - self.entry) if self.target_2 else None
        self.derived = TradePlanDerived(
            risk_per_share=abs(risk),
            risk_pct=round(abs(risk) / self.entry * 100, 2),
            reward_1_pct=round(reward1 / self.entry * 100, 2),
            reward_2_pct=round(reward2 / self.entry * 100, 2) if reward2 else None,
        )
        # limit_entry/limit_stop 있으면 R/R 자동 계산
        if self.limit_entry and self.limit_stop:
            risk_l = self.limit_entry - self.limit_stop
            reward_l = self.target_1 - self.limit_entry
            if risk_l > 0:
                self.rr_ratio_limit = round(reward_l / risk_l, 2)
                self.rr_band_limit = (
                    "UNDER" if self.rr_ratio_limit < 2.0
                    else "SWEET" if self.rr_ratio_limit < 2.5
                    else "OVER"
                )
        return self


class DecisionFactor(BaseModel):
    key: str
    label: str
    weight: float
    normalized: float
    contribution: float


class DecisionMeta(BaseModel):
    final_score: float
    factors: list[DecisionFactor]
    max_regret: Optional[float] = None


class Ranking(BaseModel):
    score: float
    rank: int
    percentile: float
    decision: Optional[DecisionMeta] = None


class LiveQuoteDisplay(BaseModel):
    current_price: str
    change: str
    direction: Literal["up", "down", "flat"]
    volume: str
    market_cap: Optional[str] = None


class LiveQuote(BaseModel):
    current_price: int
    change_pct: float
    volume: int
    market_cap_krw: Optional[int] = None
    display: Optional[LiveQuoteDisplay] = Field(alias="_display", default=None)

    model_config = {"populate_by_name": True}


class MarketIndexDisplay(BaseModel):
    label: str
    value_display: str
    change_display: str
    direction: Literal["up", "down", "flat"]


class StrategyContext(BaseModel):
    id: str
    label: str
    category: str
    timeframe: str
    description: Optional[str] = None


SignalStatus = Literal["VALID", "TARGET_REACHED", "STOPPED_OUT", "STALE"]


class Signal(BaseModel):
    ticker: str
    name: str
    name_en: Optional[str] = None
    strategy: StrategyContext
    trade_plan: TradePlan
    ranking: Ranking
    live_quote: LiveQuote
    fundamentals: Fundamentals
    flow: Flow
    external_links: dict[str, str] = {}
    signal_date: Optional[str] = None  # 마지막 bar timestamp (ISO 8601)
    signal_status: SignalStatus = "VALID"  # API 응답 시점 동적 계산
    # PR-B (P0-2): 상품 유형 + 랭킹 풀 — UI/API 소비자 grouping/필터 명시 축
    product_type: Optional[str] = None  # ProductType.value: STOCK/ETN/ETF/REIT/SPAC/UNKNOWN
    pool: Optional[str] = None          # Pool.value: STOCK/ETN_ETF/OTHER


class SignalsPayload(BaseModel):
    schema_version: str = "1.0"
    generated_at: str
    generated_at_display: str
    target_date: str = ""  # 스캔 기준 영업일 (YYYY-MM-DD)
    target_date_display: str = ""  # 예: "2026-05-04 (장중)"
    asof: str = ""  # 신호 생성 시각 (ISO 8601)
    market_indices: dict[str, MarketIndexDisplay]
    market_regime: Optional[dict] = None
    filters: dict
    signals: list[Signal]
    stats: dict
