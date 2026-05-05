import type { Signal, DecisionFactor } from '@/types/signal';
import { formatStrategyLabel } from '@/lib/strategy';

export interface CardProps {
  ticker: string;
  name: string;
  nameEn: string | null;
  priceDisplay: string;
  changeDisplay: string;
  direction: 'up' | 'down' | 'flat';
  entry: number;
  stop: number;
  target1: number | null;
  target2: number | null;
  score: number | null;
  per: number | null;
  high52w: number | null;
  low52w: number | null;
  foreignRatioPct: number | null;
  volumeDisplay: string;
  marketCapDisplay: string | null;
  riskPerShare: number | null;
  riskPct: number | null;
  reward1Pct: number | null;
  reward2Pct: number | null;
  rrRatio: number | null;
  rrBand: string | null;
  atr14: number | null;
  changePct: number | null;
  currentPrice: number | null;
  strategyId: string;
  strategyLabel: string;
  strategyCategory: string;
  timeframe: string;
  rsi: number | null;
  rsi1d: number | null;
  rsi1h: number | null;
  rsi30m: number | null;
  naverUrl: string | null;
  generatedAtDisplay: string;
  signalDate: string | null;
  dataQuality: 'ok' | 'warn';
  decisionScore: number | null;
  decisionFactors: DecisionFactor[] | null;
  decisionMaxRegret: number | null;
  rank: number | null;
  allStrategyTags?: Array<{ label: string; timeframe: string }>;
}

export function adaptSignal(signal: Signal, generatedAtDisplay: string): CardProps {
  const lq = signal.live_quote;
  const d = lq?._display;
  const cp = lq?.current_price ?? null;
  const ch = lq?.change_pct ?? null;

  // ₩ 기호 제거 (백엔드 캐시 데이터 호환)
  const rawPrice = d?.current_price
    ?? (cp != null ? cp.toLocaleString('ko-KR') : '—');
  const priceDisplay = rawPrice.replace(/^₩\s*/, '');
  const changeDisplay = d?.change
    ?? (ch != null ? `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%` : '—');
  const direction = d?.direction ?? 'flat';

  const tp = signal.trade_plan;
  const der = tp.derived;
  const atrEntryRatio =
    tp.atr_14 != null && tp.entry > 0 ? tp.atr_14 / tp.entry : null;
  const dataQuality: 'ok' | 'warn' =
    cp == null || (atrEntryRatio != null && atrEntryRatio < 0.005)
      ? 'warn'
      : 'ok';

  return {
    ticker: signal.ticker,
    name: signal.name ?? signal.ticker,
    nameEn: signal.name_en,
    priceDisplay,
    changeDisplay,
    direction,
    entry: tp.entry,
    stop: tp.stop,
    target1: tp.target_1,
    target2: tp.target_2,
    score: signal.ranking?.score ?? null,
    per: signal.fundamentals?.per ?? null,
    high52w: signal.fundamentals?.high_52w ?? null,
    low52w: signal.fundamentals?.low_52w ?? null,
    foreignRatioPct: signal.flow?.foreign_ratio_pct ?? null,
    volumeDisplay:
      d?.volume ??
      (lq?.volume != null ? lq.volume.toLocaleString('ko-KR') : '—'),
    marketCapDisplay: d?.market_cap ?? null,
    riskPerShare: der?.risk_per_share ?? null,
    riskPct: der?.risk_pct ?? null,
    reward1Pct: der?.reward_1_pct ?? null,
    reward2Pct: der?.reward_2_pct ?? null,
    rrRatio: tp.rr_ratio ?? null,
    rrBand: tp.rr_band ?? null,
    atr14: tp.atr_14 ?? null,
    changePct: lq?.change_pct ?? null,
    currentPrice: lq?.current_price ?? null,
    rsi: tp.rsi_14 ?? null,
    rsi1d: tp.rsi_1d ?? (signal.strategy.timeframe === '1D' ? tp.rsi_14 : null),
    rsi1h: tp.rsi_1h ?? (signal.strategy.timeframe === '1h' ? tp.rsi_14 : null),
    rsi30m: tp.rsi_30m ?? (signal.strategy.timeframe === '30m' ? tp.rsi_14 : null),
    strategyId: signal.strategy.id,
    strategyLabel: formatStrategyLabel(signal.strategy.id, signal.strategy.label),
    strategyCategory: signal.strategy.category ?? '',
    timeframe: signal.strategy.timeframe ?? '',
    naverUrl: signal.external_links?.naver_finance ?? null,
    generatedAtDisplay,
    signalDate: signal.signal_date ?? null,
    dataQuality,
    decisionScore: signal.ranking?.decision?.final_score ?? null,
    decisionFactors: signal.ranking?.decision?.factors ?? null,
    decisionMaxRegret: signal.ranking?.decision?.max_regret ?? null,
    rank: signal.ranking?.rank ?? null,
  };
}
