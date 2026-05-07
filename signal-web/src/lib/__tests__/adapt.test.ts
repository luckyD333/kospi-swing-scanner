import { describe, expect, test } from 'vitest';
import { adaptSignal } from '@/lib/adapt';
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
