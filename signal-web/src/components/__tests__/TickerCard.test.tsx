import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import TickerCard from '@/components/TickerCard';
import type { CardProps } from '@/lib/adapt';

function card(overrides: Partial<CardProps>): CardProps {
  return {
    ticker: '000000',
    name: '테스트',
    priceDisplay: '1,000',
    changeDisplay: '0.00%',
    direction: 'flat',
    entry: 1000,
    stop: 950,
    target1: null,
    reward1Pct: null,
    currentPrice: null,
    signalComponents: [],
    strategyId: 'strategy_one_d_v2',
    strategyLabel: 'Strategy One',
    timeframe: '1D',
    rsi: null,
    generatedAtDisplay: '',
    signalDate: null,
    decisionScore: null,
    signalStrength: null,
    decisionRegretScore: null,
    rank: null,
    signalStatus: 'VALID',
    orderTypeLabel: null,
    maxChase: null,
    productType: 'STOCK',
    pool: 'STOCK',
    confirmationLevel: null,
    perTickerRegime: null,
    atrBucket: null,
    recommendedHoldingBars: null,
    holdingConfidence: null,
    holdingStatus: null,
    ...overrides,
  };
}

function render(props: Partial<CardProps>): string {
  return renderToStaticMarkup(
    createElement(TickerCard, { card: card(props), onNavigate: () => {}, index: 0 }),
  );
}

describe('TickerCard 외부 서비스 링크', () => {
  it('종목코드 옆에 네이버·트레이딩뷰 링크를 둘 다 노출한다', () => {
    const html = render({ ticker: '005930' });
    expect(html).toContain('https://finance.naver.com/item/main.naver?code=005930');
    expect(html).toContain('symbol=KRX%3A005930');
  });

  it('ETF 종목에서도 두 링크가 그대로 동작한다', () => {
    const html = render({ ticker: '069500', productType: 'ETF', pool: 'ETN_ETF' });
    expect(html).toContain('code=069500');
    expect(html).toContain('symbol=KRX%3A069500');
  });
});
