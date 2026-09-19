import { describe, expect, test } from 'vitest';
import type { CardProps } from '@/lib/adapt';
import {
  ASSET_GROUPS,
  DEFAULT_ASSET_GROUP,
  filterCardsByAssetGroup,
  isEtfCard,
} from '@/lib/asset-filter';

function card(overrides: Partial<CardProps>): CardProps {
  return {
    ticker: '000000',
    name: '테스트',
    nameEn: null,
    priceDisplay: '1,000',
    changeDisplay: '0.00%',
    direction: 'flat',
    entry: 1000,
    stop: 950,
    target1: null,
    target2: null,
    score: null,
    per: null,
    high52w: null,
    low52w: null,
    foreignRatioPct: null,
    volumeDisplay: '0',
    marketCapDisplay: null,
    riskPerShare: null,
    riskPct: null,
    reward1Pct: null,
    reward2Pct: null,
    rrRatio: null,
    rrBand: null,
    atr14: null,
    changePct: null,
    currentPrice: null,
    signalComponents: [],
    strategyId: 'strategy_one_d_v2',
    strategyLabel: 'Strategy One',
    strategyCategory: '',
    timeframe: '1D',
    rsi: null,
    rsi1d: null,
    rsi1h: null,
    naverUrl: null,
    generatedAtDisplay: '',
    signalDate: null,
    dataQuality: 'ok',
    decisionScore: null,
    decisionFactors: null,
    decisionMaxRegret: null,
    signalStrength: null,
    decisionRegretScore: null,
    decisionRegretFactors: null,
    rank: null,
    signalStatus: 'VALID',
    orderTypeIntent: null,
    orderTypeLabel: null,
    productType: 'STOCK',
    pool: 'STOCK',
    tradabilityScore: null,
    confirmationLevel: null,
    activeRegime: null,
    perTickerRegime: null,
    atrBucket: null,
    ensembleScore: null,
    regimeLabel: null,
    fngLabel: null,
    recommendedHoldingBars: null,
    holdingConfidence: null,
    holdingStatus: null,
    ...overrides,
  };
}

describe('asset-filter', () => {
  const stock = card({ ticker: '005930', productType: 'STOCK', pool: 'STOCK' });
  const etf = card({ ticker: '069500', productType: 'ETF', pool: 'ETN_ETF' });
  const etn = card({ ticker: '700000', productType: 'ETN', pool: 'ETN_ETF' });

  test('ALL 이 첫 옵션이자 기본값이다', () => {
    expect(DEFAULT_ASSET_GROUP).toBe('ALL');
    expect(ASSET_GROUPS).toEqual(['ALL', '주식', 'ETF']);
  });

  test('ALL 은 주식과 ETF/ETN 카드를 모두 유지한다', () => {
    expect(filterCardsByAssetGroup([stock, etf, etn], 'ALL').map((c) => c.ticker))
      .toEqual(['005930', '069500', '700000']);
  });

  test('주식과 ETF 필터는 기존 분류 기준을 유지한다', () => {
    expect(filterCardsByAssetGroup([stock, etf, etn], '주식').map((c) => c.ticker))
      .toEqual(['005930']);
    expect(filterCardsByAssetGroup([stock, etf, etn], 'ETF').map((c) => c.ticker))
      .toEqual(['069500', '700000']);
    expect(isEtfCard(etf)).toBe(true);
  });
});
