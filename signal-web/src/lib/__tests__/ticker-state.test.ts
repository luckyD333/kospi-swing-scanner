import { describe, expect, test } from 'vitest';
import { formatTickerState } from '@/lib/ticker-state';

describe('formatTickerState', () => {
  test('강한 상승 국면과 높은 RSI는 과열강세로 표시', () => {
    const state = formatTickerState(72.3, 'UPTREND_STRONG', 'HIGH');
    expect(state.label).toBe('과열강세');
    expect(state.tone).toBe('var(--gain)');
    expect(state.sub).toBe('RSI 72 · 변동 높음');
  });

  test('박스권에서 낮은 RSI는 반등대기로 표시', () => {
    const state = formatTickerState(34.8, 'RANGE', 'MID');
    expect(state.label).toBe('반등대기');
    expect(state.sub).toBe('RSI 35 · 변동 보통');
  });

  test('강한 하락 국면은 RSI와 무관하게 하락위험으로 표시', () => {
    const state = formatTickerState(45.1, 'DOWNTREND_STRONG', 'LOW');
    expect(state.label).toBe('하락위험');
    expect(state.tone).toBe('var(--loss)');
    expect(state.sub).toBe('RSI 45 · 변동 낮음');
  });

  test('종목 국면이 없으면 RSI 기반 상태로 fallback', () => {
    const state = formatTickerState(29.9, null, null);
    expect(state.label).toBe('과매도');
    expect(state.sub).toBe('RSI 30');
  });
});
