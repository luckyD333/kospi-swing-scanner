import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import FearGreedGauge from '@/components/FearGreedGauge';
import TopNav from '@/components/TopNav';
import VKospiIndicator from '@/components/VKospiIndicator';
import type { FearGreedSnapshot, VKospiSnapshot } from '@/types/signal';

describe('정보용 시장 심리 지표', () => {
  it('F&G가 매수 판단에 반영되지 않는 정보용 지표임을 표시한다', () => {
    const data: FearGreedSnapshot = {
      score: 42,
      label: 'Fear',
      components: { momentum: 40, breadth: 35, volatility: 51 },
      history: [],
      status: 'informational',
    };

    const html = renderToStaticMarkup(createElement(FearGreedGauge, { data }));

    expect(html).toContain('정보용');
    expect(html).toContain('매수 판단 미반영');
  });

  it('V-KOSPI를 F&G와 분리하고 방향성 지표가 아님을 표시한다', () => {
    const data: VKospiSnapshot = {
      value: 35.2,
      change_pct: 2.1,
      asof: '2026-07-15',
      percentile_90d: 88.9,
      status: 'informational',
    };

    const html = renderToStaticMarkup(createElement(VKospiIndicator, { data }));

    expect(html).toContain('V-KOSPI');
    expect(html).toContain('35.20');
    expect(html).toContain('+2.10%');
    expect(html).toContain('90일 88.9%');
    expect(html).toContain('방향성 지표가 아님');
    expect(html).toContain('매수 판단 미반영');
  });

  it('F&G 미니 차트와 1D/1H 시장 국면을 항상 함께 표시한다', () => {
    const fearGreed: FearGreedSnapshot = {
      score: 42,
      label: 'Fear',
      components: { momentum: 40, breadth: 35, volatility: 51 },
      history: [
        { date: '2026-07-14', score: 45 },
        { date: '2026-07-15', score: 42 },
      ],
      status: 'informational',
    };

    const html = renderToStaticMarkup(createElement(TopNav, {
      marketIndices: {},
      fearGreed,
      marketRegime: {
        '1d': { score: 67, regime: 'NEUTRAL' },
        '1h': { score: 26.6, regime: 'BEAR' },
      },
    }));

    expect(html).toContain('<svg');
    expect(html).toContain('1D');
    expect(html).toContain('NEUTRAL');
    expect(html).toContain('67');
    expect(html).toContain('1H');
    expect(html).toContain('BEAR');
    expect(html).toContain('26.6');
  });
});
