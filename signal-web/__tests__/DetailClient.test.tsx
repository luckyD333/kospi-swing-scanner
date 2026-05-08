import { describe, expect, test } from 'vitest';
import { adaptDetailSignal } from '@/lib/adapt';
import type { DetailProps, MarketIndex, RegimeScore } from '@/types/signal';

describe('DetailClient - 다중 매칭 렌더링 데이터 구조', () => {
  test('matches 1개일 때: DetailProps 구조 검증', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      name: '삼성전자',
      generated_at_display: '2026-05-08 15:30',
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
      fundamentals: { per: 12, high_52w: 80000, low_52w: 60000 },
      live_quote: { current_price: 70000, change_pct: 1.5, volume: 1000000, market_cap_krw: null },
      external_links: { naver_finance: 'https://finance.naver.com' },
      confirmation_level: 'STRONG',
      active_regime: 'BULL',
      tradability_score: 85,
    };

    const detail = adaptDetailSignal(raw);

    // matches 1개 확인
    expect(detail.matches).toHaveLength(1);
    expect(detail.matches[0].strategy.label).toBe('STRATEGY ONE');
    expect(detail.matches[0].strategy.timeframe).toBe('1D');
    expect(detail.matches[0].signalStrength).toBe(82);
    expect(detail.matches[0].opportunityScore).toBe(68);

    // 잠재력 점수 확인
    expect(detail.potentialScore).toBe(75);
    expect(detail.potentialFactors).toHaveLength(1);
    expect(detail.potentialFactors[0].label).toBe('가격 모멘텀 (3개월)');
  });

  test('matches 2개일 때: 모든 매칭 전략 보존', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '466920',
      name: 'SOL 조선TOP3플러스',
      generated_at_display: '2026-05-08 15:30',
      potential_score: 75,
      potential_factors: [],
      matches: [
        {
          strategy: { id: 'strategy_two_1h', label: 'STRATEGY TWO', timeframe: '1h' },
          signal_strength: 82,
          opportunity_score: 68,
          opportunity_factors: [],
          trade_plan: { entry: 41950, stop: 41000, target_1: 43200, target_2: 44500, rr_ratio: 1.32, rr_band: 'SWEET' },
        },
        {
          strategy: { id: 'strategy_four_30m', label: 'STRATEGY FOUR', timeframe: '30m' },
          signal_strength: 67,
          opportunity_score: 55,
          opportunity_factors: [],
          trade_plan: { entry: 41100, stop: 40750, target_1: 41800, target_2: 42500, rr_ratio: 6.0, rr_band: 'OVER' },
        },
      ],
    };

    const detail = adaptDetailSignal(raw);

    // matches 2개 확인
    expect(detail.matches).toHaveLength(2);
    expect(detail.matches[0].strategy.label).toBe('STRATEGY TWO');
    expect(detail.matches[1].strategy.label).toBe('STRATEGY FOUR');
    expect(detail.matches[0].signalStrength).toBe(82);
    expect(detail.matches[1].signalStrength).toBe(67);
    expect(detail.matches[0].opportunityScore).toBe(68);
    expect(detail.matches[1].opportunityScore).toBe(55);
  });

  test('잠재력 점수: factor 라벨 자동 매핑', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      generated_at_display: '2026-05-08 15:30',
      potential_score: 75.5,
      potential_factors: [
        { key: 'momentum_3m', weight: 35, normalized: 0.8, contribution: 28 },
        { key: 'liquidity', weight: 25, normalized: 0.9, contribution: 22.5 },
      ],
      matches: [],
    };

    const detail = adaptDetailSignal(raw);

    expect(detail.potentialFactors).toHaveLength(2);
    expect(detail.potentialFactors[0].label).toBe('가격 모멘텀 (3개월)');
    expect(detail.potentialFactors[1].label).toBe('유동성');
  });

  test('기회 점수 Factor: 4개 factor 라벨 매핑', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      generated_at_display: '2026-05-08 15:30',
      potential_score: 75,
      potential_factors: [],
      matches: [
        {
          strategy: { id: 'strategy_one_1d_v2', label: 'STRATEGY ONE', timeframe: '1D' },
          signal_strength: 82,
          opportunity_score: 68,
          opportunity_factors: [
            { key: 'bull_reward', weight: 40, normalized: 0.6, contribution: 24 },
            { key: 'max_drawdown', weight: 20, normalized: 0.55, contribution: 11 },
            { key: 'dist_to_stop', weight: 15, normalized: 0.5, contribution: 7.5 },
            { key: 'signal_freshness', weight: 25, normalized: 0.8, contribution: 20 },
          ],
          trade_plan: { entry: 70000, stop: 68000, target_1: 72000, target_2: 75000 },
        },
      ],
    };

    const detail = adaptDetailSignal(raw);

    expect(detail.matches[0].opportunityFactors).toHaveLength(4);
    expect(detail.matches[0].opportunityFactors[0].label).toBe('목표 수익');
    expect(detail.matches[0].opportunityFactors[1].label).toBe('손절 위험 (역)');
    expect(detail.matches[0].opportunityFactors[2].label).toBe('손절까지 여유');
    expect(detail.matches[0].opportunityFactors[3].label).toBe('신호 신선도');
  });

  test('매매 파라미터: 각 match마다 독립적 구조', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      generated_at_display: '2026-05-08 15:30',
      potential_score: 75,
      potential_factors: [],
      matches: [
        {
          strategy: { id: 'strategy_one_1d_v2', label: 'STRATEGY ONE', timeframe: '1D' },
          signal_strength: 82,
          opportunity_score: 68,
          opportunity_factors: [],
          trade_plan: { entry: 70000, stop: 68000, target_1: 72000, target_2: 75000, rr_ratio: 2.0, rr_band: 'SWEET' },
        },
      ],
    };

    const detail = adaptDetailSignal(raw);
    const m = detail.matches[0];

    expect(m.entry).toBe(70000);
    expect(m.stop).toBe(68000);
    expect(m.target1).toBe(72000);
    expect(m.target2).toBe(75000);
    expect(m.rrRatio).toBe(2.0);
    expect(m.rrBand).toBe('SWEET');
  });

  test('opportunityFactors가 null이면 null로 유지', () => {
    const raw = {
      schema_version: '2.0',
      ticker: '005930',
      generated_at_display: '2026-05-08 15:30',
      potential_score: 75,
      potential_factors: [],
      matches: [
        {
          strategy: { id: 'strategy_one_1d_v2', label: 'STRATEGY ONE', timeframe: '1D' },
          signal_strength: 82,
          opportunity_score: 68,
          opportunity_factors: null,
          trade_plan: { entry: 70000, stop: 68000, target_1: 72000, target_2: 75000 },
        },
      ],
    };

    const detail = adaptDetailSignal(raw);
    expect(detail.matches[0].opportunityFactors).toBeNull();
  });
});
