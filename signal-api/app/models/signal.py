from typing import Any
from pydantic import BaseModel


class StrategyInfo(BaseModel):
    id: str
    label: str
    category: str | None = None
    timeframe: str | None = None
    description: str | None = None


class TradePlanDerived(BaseModel):
    risk_per_share: float | None = None
    risk_pct: float | None = None
    reward_1_pct: float | None = None
    reward_2_pct: float | None = None


class TradePlan(BaseModel):
    entry: float
    stop: float
    target_1: float | None = None
    target_2: float | None = None
    rr_ratio: float | None = None
    rr_band: str | None = None
    atr_14: float | None = None
    derived: TradePlanDerived | None = None


class Ranking(BaseModel):
    score: float | None = None
    rank: int | None = None
    percentile: float | None = None


class LiveQuote(BaseModel):
    current_price: float | None = None
    change_pct: float | None = None
    volume: int | None = None
    market_cap_krw: float | None = None

    model_config = {"extra": "allow"}  # _display 서브오브젝트 허용


class Fundamentals(BaseModel):
    per: float | None = None
    pbr: float | None = None
    eps: float | None = None
    dividend_yield_pct: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None


class Flow(BaseModel):
    foreign_ratio_pct: float | None = None
    institutional_net_krw: float | None = None


class ExternalLinks(BaseModel):
    naver_finance: str | None = None


class Signal(BaseModel):
    ticker: str
    name: str | None = None
    name_en: str | None = None
    strategy: StrategyInfo
    trade_plan: TradePlan
    ranking: Ranking | None = None
    live_quote: LiveQuote | None = None
    fundamentals: Fundamentals | None = None
    flow: Flow | None = None
    external_links: ExternalLinks | None = None


class SignalMarketEntry(BaseModel):
    label: str | None = None
    value_display: str | None = None
    change_display: str | None = None
    direction: str | None = None


class Filters(BaseModel):
    strategies: list[str] = []
    timeframes: list[str] = []
    sort_options: list[str] = []


class SignalsResponse(BaseModel):
    schema_version: str
    generated_at: str
    generated_at_display: str | None = None
    market_indices: dict[str, SignalMarketEntry] = {}
    filters: Filters | None = None
    signals: list[Signal] = []
    stats: dict[str, Any] | None = None

    model_config = {"extra": "allow"}
