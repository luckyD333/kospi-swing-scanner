import { describe, expect, test } from 'vitest';
import { adaptSignal, adaptDetailV2, adaptDetailLegacy } from '@/lib/adapt';
import type { Signal } from '@/types/signal';

const minimal: Signal = {
  ticker: '000000',
  name: null,
  name_en: null,
  strategy: {
    id: 's',
    label: 'S',
    category: 'X',
    timeframe: '1D',
    description: null,
  },
  trade_plan: {
    entry: 1000,
    stop: 950,
    target_1: null,
    target_2: null,
    rr_ratio: null,
    rr_band: null,
    atr_14: null,
    rsi_14: null,
    derived: null,
  },
  ranking: null,
  live_quote: null,
  fundamentals: null,
  flow: null,
  external_links: null,
};

describe('adaptSignal', () => {
  test('live_quote가 null이어도 throw 안 함', () => {
    const c = adaptSignal(minimal, '2026-05-03');
    expect(c.priceDisplay).toBe('—');
    expect(c.changeDisplay).toBe('—');
    expect(c.direction).toBe('flat');
    expect(c.target1).toBeNull();
    expect(c.score).toBeNull();
    expect(c.signalStrength).toBeNull();
    expect(c.decisionRegretScore).toBeNull();
    expect(c.naverUrl).toBeNull();
  });

  test('name이 null이면 ticker로 fallback', () => {
    const c = adaptSignal(minimal, '2026-05-03');
    expect(c.name).toBe('000000');
  });

  test('current_price가 null이면 dataQuality=warn', () => {
    const flagged: Signal = {
      ...minimal,
      live_quote: {
        current_price: null,
        change_pct: null,
        volume: null,
        market_cap_krw: null,
      },
    };
    const c = adaptSignal(flagged, '2026-05-03');
    expect(c.dataQuality).toBe('warn');
  });

  test('정상 시그널은 dataQuality=ok', () => {
    const ok: Signal = {
      ...minimal,
      live_quote: {
        current_price: 15050,
        change_pct: 0.5,
        volume: 100000,
        market_cap_krw: 47530_0000_0000,
      },
      trade_plan: { ...minimal.trade_plan, atr_14: 1173 },
    };
    const c = adaptSignal(ok, '2026-05-03');
    expect(c.dataQuality).toBe('ok');
    expect(c.priceDisplay).toBe('15,050');
    expect(c.changeDisplay).toBe('+0.50%');
  });

  test('atr/entry < 0.5%면 dataQuality=warn', () => {
    const tight: Signal = {
      ...minimal,
      live_quote: {
        current_price: 100000,
        change_pct: 0,
        volume: 1,
        market_cap_krw: null,
      },
      trade_plan: { ...minimal.trade_plan, entry: 100000, atr_14: 100 }, // 0.1%
    };
    const c = adaptSignal(tight, '2026-05-03');
    expect(c.dataQuality).toBe('warn');
  });

  test('_display.current_price가 있으면 그것을 우선', () => {
    const formatted: Signal = {
      ...minimal,
      live_quote: {
        current_price: 15050,
        change_pct: 0.5,
        volume: 0,
        market_cap_krw: null,
        _display: {
          current_price: '₩15 050',
          change: '+0.50%',
          direction: 'up',
          volume: '0',
          market_cap: null,
        },
      },
    };
    const c = adaptSignal(formatted, '2026-05-03');
    // ₩ 기호는 adapt에서 strip
    expect(c.priceDisplay).toBe('15 050');
    expect(c.direction).toBe('up');
  });
});


describe('adaptDetailV2 — signal_components', () => {
  const baseRaw = {
    schema_version: '2.0',
    ticker: '005930',
    name: '삼성전자',
    fundamentals: {},
    flow: {},
    live_quote: {},
    external_links: {},
    potential_score: 75,
    potential_factors: [],
  };

  test('매칭별 signal_components 매핑', () => {
    const raw = {
      ...baseRaw,
      matches: [
        {
          strategy: { id: 'strategy_one_d_v2', label: 'STRATEGY ONE', timeframe: '1D' },
          signal_strength: 80,
          opportunity_score: 70,
          opportunity_factors: [],
          trade_plan: { entry: 71000, stop: 69000, target_1: 73500 },
          signal_components: [
            { key: 'rsi_oversold', label: 'RSI 과매도', status: 'ok', value: '28.5' },
            { key: 'double_bottom', label: '쌍바닥', status: 'ok', value: null },
          ],
        },
      ],
    };
    const detail = adaptDetailV2(raw);
    expect(detail.matches).toHaveLength(1);
    expect(detail.matches[0].signalComponents).toEqual([
      { key: 'rsi_oversold', label: 'RSI 과매도', status: 'ok', value: '28.5' },
      { key: 'double_bottom', label: '쌍바닥', status: 'ok', value: null },
    ]);
  });

  test('signal_components 누락 시 빈 배열', () => {
    const raw = {
      ...baseRaw,
      matches: [
        {
          strategy: { id: 'strategy_two', label: 'TWO', timeframe: '1D' },
          signal_strength: 50,
          opportunity_score: 40,
          opportunity_factors: [],
          trade_plan: { entry: 50000, stop: 48000 },
        },
      ],
    };
    const detail = adaptDetailV2(raw);
    expect(detail.matches[0].signalComponents).toEqual([]);
  });

  test('잘못된 status 값은 ok 로 fallback', () => {
    const raw = {
      ...baseRaw,
      matches: [
        {
          strategy: { id: 'strategy_one_d_v2', label: 'ONE', timeframe: '1D' },
          signal_strength: 80,
          opportunity_score: 70,
          trade_plan: { entry: 1, stop: 1 },
          signal_components: [
            { key: 'rsi_oversold', label: 'RSI', status: 'unknown', value: null },
            { key: 'no_key', status: 'warn', value: null },
            null,
          ],
        },
      ],
    };
    const detail = adaptDetailV2(raw);
    const components = detail.matches[0].signalComponents;
    // 잘못된 status 'unknown' → ok 로 fallback, key 가 없는/null 항목은 필터링
    expect(components).toHaveLength(2);
    expect(components[0].status).toBe('ok');
    expect(components[1].status).toBe('warn');
  });
});


describe('adaptDetailLegacy — signal_components', () => {
  test('legacy 단일 entry 의 signal_components 도 매핑', () => {
    const raw = {
      ticker: '005930',
      name: '삼성전자',
      strategy: { id: 'strategy_three_trend_following', label: 'THREE', category: 'TREND', timeframe: '1D' },
      trade_plan: { entry: 71000, stop: 69000, target_1: 73500, target_2: 75000 },
      ranking: { score: 65, signal_strength: 60 },
      live_quote: { current_price: 71000, change_pct: 0.5, volume: 100, market_cap_krw: null },
      fundamentals: {},
      flow: {},
      external_links: {},
      generated_at_display: '2026-05-08',
      signal_components: [
        { key: 'donchian_breakout', label: 'Donchian 돌파', status: 'ok', value: '+2.40%' },
      ],
    };
    const detail = adaptDetailLegacy(raw);
    expect(detail.matches).toHaveLength(1);
    expect(detail.matches[0].signalComponents).toEqual([
      { key: 'donchian_breakout', label: 'Donchian 돌파', status: 'ok', value: '+2.40%' },
    ]);
  });
});
