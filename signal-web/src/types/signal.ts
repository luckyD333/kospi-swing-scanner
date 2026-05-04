export interface SignalDisplay {
  current_price: string;
  change: string;
  direction: 'up' | 'down' | 'flat';
  volume: string;
  market_cap: string | null;
}

export interface LiveQuote {
  current_price: number | null;
  change_pct: number | null;
  volume: number | null;
  market_cap_krw: number | null;
  _display?: SignalDisplay;
}

export interface StrategyInfo {
  id: string;
  label: string;
  category: string | null;
  timeframe: string | null;
  description: string | null;
}

export interface TradePlanDerived {
  risk_per_share: number | null;
  risk_pct: number | null;
  reward_1_pct: number | null;
  reward_2_pct: number | null;
}

export interface TradePlan {
  entry: number;
  stop: number;
  target_1: number | null;
  target_2: number | null;
  rr_ratio: number | null;
  rr_band: string | null;
  atr_14: number | null;
  rsi_14: number | null;
  rsi_1d?: number | null;
  rsi_1h?: number | null;
  rsi_30m?: number | null;
  derived: TradePlanDerived | null;
}

export interface DecisionFactor {
  key: string;
  label: string;
  weight: number;
  normalized: number;
  contribution: number;
}

export interface DecisionMeta {
  final_score: number;
  factors: DecisionFactor[];
  max_regret: number | null;
}

export interface Ranking {
  score: number | null;
  rank: number | null;
  percentile: number | null;
  decision: DecisionMeta | null;
}

export interface Fundamentals {
  per: number | null;
  pbr: number | null;
  eps: number | null;
  dividend_yield_pct: number | null;
  high_52w: number | null;
  low_52w: number | null;
}

export interface Flow {
  foreign_ratio_pct: number | null;
  institutional_net_krw: number | null;
}

export interface ExternalLinks {
  naver_finance: string | null;
}

export interface Signal {
  ticker: string;
  name: string | null;
  name_en: string | null;
  strategy: StrategyInfo;
  trade_plan: TradePlan;
  ranking: Ranking | null;
  live_quote: LiveQuote | null;
  fundamentals: Fundamentals | null;
  flow: Flow | null;
  external_links: ExternalLinks | null;
  signal_date?: string | null;
}

export interface MarketIndex {
  label: string;
  value_display: string;
  change_display: string;
  direction: 'up' | 'down' | 'flat';
}

export interface Filters {
  strategies: string[];
  timeframes: string[];
  sort_options: string[];
}

export interface Stats {
  total_signals: number;
  by_strategy: Record<string, number>;
  by_rr_band: Record<string, number>;
}

export interface RegimeScore {
  score: number;
  regime: string;
}

export interface BreadthScore {
  up_ratio: number | null;
  above_ma20_ratio: number | null;
  avg_atr_pct: number | null;
  top_volume_return_avg: number | null;
}

export interface AxesScore {
  trend_score: number;
  volatility_regime: 'LOW' | 'MID' | 'HIGH';
}

export type FearGreedLabel =
  | 'Extreme Fear'
  | 'Fear'
  | 'Neutral'
  | 'Greed'
  | 'Extreme Greed';

export interface FearGreedComponents {
  momentum: number;
  breadth: number;
  volatility: number;
}

export interface FearGreedHistoryPoint {
  date: string;
  score: number;
}

export interface FearGreedSnapshot {
  score: number;
  label: FearGreedLabel;
  components: FearGreedComponents;
  history: FearGreedHistoryPoint[];
}

export interface SignalsResponse {
  schema_version: string;
  generated_at: string;
  generated_at_display: string;
  target_date?: string;
  target_date_display?: string;
  asof?: string;
  market_indices: Record<string, MarketIndex>;
  market_regime: Record<string, RegimeScore> | null;
  market_breadth?: Record<string, BreadthScore> | null;
  market_axes?: Record<string, AxesScore> | null;
  fear_greed?: FearGreedSnapshot | null;
  filters: Filters;
  signals: Signal[];
  stats: Stats;
}
