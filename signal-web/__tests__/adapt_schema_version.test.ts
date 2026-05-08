import { describe, expect, test } from 'vitest';
import { adaptDetailSignal, adaptDetailV2, adaptDetailLegacy, getFactorLabel } from '@/lib/adapt';

describe('getFactorLabel', () => {
  test('신규 factor key를 한국어로 매핑', () => {
    expect(getFactorLabel('momentum_3m')).toBe('가격 모멘텀 (3개월)');
    expect(getFactorLabel('regime_score')).toBe('시장 국면');
    expect(getFactorLabel('roe')).toBe('ROE (수익성)');
    expect(getFactorLabel('per')).toBe('PER (저평가)');
    expect(getFactorLabel('liquidity')).toBe('유동성');
    expect(getFactorLabel('bull_reward')).toBe('목표 수익');
    expect(getFactorLabel('max_drawdown')).toBe('손절 위험 (역)');
    expect(getFactorLabel('dist_to_stop')).toBe('손절까지 여유');
    expect(getFactorLabel('signal_freshness')).toBe('신호 신선도');
  });

  test('기존 deprecated key도 호환성 유지', () => {
    expect(getFactorLabel('momentum_pct')).toBe('가격 모멘텀');
    expect(getFactorLabel('rr_ratio')).toBe('손익비');
    expect(getFactorLabel('ensemble_score')).toBe('다전략 합의도');
    expect(getFactorLabel('breakout_strength')).toBe('돌파 강도');
  });

  test('알려지지 않은 key는 그대로 반환', () => {
    expect(getFactorLabel('unknown_factor')).toBe('unknown_factor');
  });
});

describe('adaptDetailSignal - dual parser', () => {
  test('schema_version 2.0 응답은 adaptDetailV2 사용', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      name: '삼성전자',
      potential_score: 75,
      potential_factors: [
        { key: 'momentum_3m', label: 'momentum_3m', weight: 35, normalized: 0.8, contribution: 28 },
      ],
      matches: [
        {
          strategy: { id: 'strategy_one_1d_v2', label: 'STRATEGY ONE', timeframe: '1D' },
          signal_strength: 82,
          opportunity_score: 68,
          opportunity_factors: [
            { key: 'bull_reward', label: 'bull_reward', weight: 40, normalized: 0.6, contribution: 24 },
          ],
          trade_plan: { entry: 70000, stop: 68000, target_1: 72000, target_2: 75000, rr_ratio: 2.0, rr_band: 'SWEET' },
        },
      ],
      fundamentals: { per: 12 },
      live_quote: { current_price: 70000, change_pct: 1.5, volume: 1000000, market_cap_krw: null },
      external_links: { naver_finance: 'https://finance.naver.com' },
      generated_at_display: '2026-05-08',
    };

    const detail = adaptDetailSignal(raw);
    expect(detail.potentialScore).toBe(75);
    expect(detail.matches.length).toBe(1);
    expect(detail.matches[0].strategy.label).toBe('STRATEGY ONE');
    expect(detail.matches[0].signalStrength).toBe(82);
    expect(detail.matches[0].opportunityScore).toBe(68);
  });

  test('schema_version 없거나 1.x 응답은 adaptDetailLegacy 사용', () => {
    const raw = {
      ticker: '000000',
      name: 'Test Stock',
      name_en: 'Test',
      strategy: {
        id: 'strategy_one_1d_v2',
        label: 'STRATEGY ONE',
        category: 'Mean Reversion',
        timeframe: '1D',
        description: null,
      },
      trade_plan: {
        entry: 10000,
        stop: 9800,
        target_1: 10500,
        target_2: 11000,
        rr_ratio: 2.5,
        rr_band: 'SWEET',
        atr_14: 150,
        rsi_14: 45,
        derived: null,
      },
      ranking: {
        score: 82,
        rank: 5,
        percentile: 95,
        signal_strength: 82,
        decision: {
          final_score: 75,
          factors: [
            { key: 'momentum_pct', label: 'momentum_pct', weight: 25, normalized: 0.8, contribution: 20 },
          ],
          max_regret: 68,
          regret_score: 68,
          regret_factors: [
            { key: 'bull_reward', label: 'bull_reward', weight: 40, normalized: 0.6, contribution: 24 },
          ],
        },
      },
      live_quote: {
        current_price: 10000,
        change_pct: 1.2,
        volume: 500000,
        market_cap_krw: 5000000000,
      },
      fundamentals: { per: 10 },
      external_links: { naver_finance: 'https://finance.naver.com' },
      flow: { foreign_ratio_pct: 5.2, institutional_net_krw: 100000000 },
    };

    const detail = adaptDetailSignal(raw);
    expect(detail.ticker).toBe('000000');
    expect(detail.potentialScore).toBe(75);
    expect(detail.matches.length).toBe(1);
    // formatStrategyLabel은 "전략 1" 형식으로 변환됨
    expect(detail.matches[0].strategy.label).toBe('전략 1');
  });

  test('matches 배열이 없으면 빈 배열로 처리', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      name: 'Test',
      potential_score: null,
      potential_factors: [],
      matches: [],
    };

    const detail = adaptDetailSignal(raw);
    expect(detail.matches.length).toBe(0);
  });

  test('factor 라벨이 자동으로 매핑됨', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      potential_score: 75,
      potential_factors: [
        { key: 'momentum_3m', weight: 35, normalized: 0.8, contribution: 28 },
        { key: 'liquidity', weight: 25, normalized: 0.9, contribution: 22.5 },
      ],
      matches: [],
    };

    const detail = adaptDetailSignal(raw);
    expect(detail.potentialFactors[0].label).toBe('가격 모멘텀 (3개월)');
    expect(detail.potentialFactors[1].label).toBe('유동성');
  });

  test('matches의 opportunityFactors도 라벨 매핑', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      potential_score: 75,
      potential_factors: [],
      matches: [
        {
          strategy: { id: 'strategy_one_1d_v2', label: 'STRATEGY ONE', timeframe: '1D' },
          signal_strength: 82,
          opportunity_score: 68,
          opportunity_factors: [
            { key: 'bull_reward', weight: 40, normalized: 0.6, contribution: 24 },
            { key: 'signal_freshness', weight: 25, normalized: 0.5, contribution: 12.5 },
          ],
          trade_plan: { entry: 10000, stop: 9800, target_1: 10500, target_2: 11000 },
        },
      ],
    };

    const detail = adaptDetailSignal(raw);
    expect(detail.matches[0].opportunityFactors[0].label).toBe('목표 수익');
    expect(detail.matches[0].opportunityFactors[1].label).toBe('신호 신선도');
  });
});
