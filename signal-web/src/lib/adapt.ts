import type { Signal } from '@/types/signal';
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
  rrRatio: number | null;
  rrBand: string | null;
  atr: number | null;
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
  strategyLabel: string;
  strategyCategory: string;
  timeframe: string;
  naverUrl: string | null;
  generatedAtDisplay: string;
  dataQuality: 'ok' | 'warn';
}

export function adaptSignal(signal: Signal, generatedAtDisplay: string): CardProps {
  const lq = signal.live_quote;
  const d = lq?._display;
  const cp = lq?.current_price ?? null;
  const ch = lq?.change_pct ?? null;

  const priceDisplay = d?.current_price
    ?? (cp != null ? `₩${cp.toLocaleString('ko-KR')}` : '—');
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
    rrRatio: tp.rr_ratio,
    rrBand: tp.rr_band,
    atr: tp.atr_14,
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
    strategyLabel: formatStrategyLabel(signal.strategy.id, signal.strategy.label),
    strategyCategory: signal.strategy.category ?? '',
    timeframe: signal.strategy.timeframe ?? '',
    naverUrl: signal.external_links?.naver_finance ?? null,
    generatedAtDisplay,
    dataQuality,
  };
}
