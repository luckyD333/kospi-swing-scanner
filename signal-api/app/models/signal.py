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
    # 30m 지지선 기반 권장 지정가 진입
    limit_entry: float | None = None
    limit_stop: float | None = None
    rr_ratio_limit: float | None = None
    rr_band_limit: str | None = None
    # PR-C (P1-1): 주문 타입 의도 분류
    order_type_intent: str | None = None    # BREAKOUT / PULLBACK / IMMEDIATE
    order_type_label_ko: str | None = None  # 역지정가 / 지정가 / 시장가


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
    signal_date: str | None = None
    signal_status: str = "VALID"  # VALID | TARGET_REACHED | STOPPED_OUT | STALE
    # PR-B (P0-2): 상품 유형 + 랭킹 풀
    product_type: str | None = None  # STOCK/ETN/ETF/REIT/SPAC/UNKNOWN
    pool: str | None = None          # STOCK/ETN_ETF/OTHER
    # PR-K (P3-1): 거래 용이성 점수
    tradability_score: float | None = None
    # PR-H/PR-J (P2-3, P3-2): confirmation 등급 + 시장 국면
    confirmation_level: str | None = None  # STRONG/MEDIUM/WEAK
    active_regime: str | None = None       # BULL/NEUTRAL/BEAR


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
