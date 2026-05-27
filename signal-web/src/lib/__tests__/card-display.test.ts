import { describe, expect, test } from 'vitest';
import { buildCheckItem, buildReasonItem } from '@/lib/card-display';
import type { SignalComponent } from '@/lib/adapt';

describe('card-display', () => {
  test('근거는 ok 컴포넌트 앞 2개를 압축 표시', () => {
    const components: SignalComponent[] = [
      { key: 'rsi_oversold', label: 'RSI 과매도', status: 'ok', value: '28.5' },
      { key: 'double_bottom', label: '쌍바닥', status: 'ok', value: null },
      { key: 'bullish_engulfing', label: '장악형 양봉', status: 'ok', value: null },
    ];

    expect(buildReasonItem(components, 'MEAN REVERSION')).toEqual({
      label: '근거',
      value: 'RSI 과매도 · 쌍바닥',
      sub: null,
      tone: 'var(--body)',
    });
  });

  test('ok가 없으면 warn 근거를 표시', () => {
    const components: SignalComponent[] = [
      { key: 'momentum_15d', label: '15일 상대강도', status: 'warn', value: '+1.8%' },
    ];

    expect(buildReasonItem(components, 'MOMENTUM')).toEqual({
      label: '근거',
      value: '15일 상대강도',
      sub: null,
      tone: '#ffb74d',
    });
  });

  test('근거가 없으면 전략 라벨로 fallback', () => {
    expect(buildReasonItem([], 'BULL FLAG')).toEqual({
      label: '근거',
      value: 'BULL FLAG',
      sub: null,
      tone: 'var(--body)',
    });
  });

  test('체크는 현재가 기준 손절 위험과 목표 여력을 표시', () => {
    expect(buildCheckItem({
      currentPrice: 10000,
      stop: 9709,
      target1: 11710,
      isIntraday: false,
      expiryCountdown: null,
    })).toEqual({
      label: '체크',
      value: '손절 2.9%',
      sub: '목표 +17.1%',
      tone: 'var(--body)',
    });
  });

  test('손절까지 1% 미만이면 손절 임박을 강조', () => {
    expect(buildCheckItem({
      currentPrice: 10000,
      stop: 9950,
      target1: 11000,
      isIntraday: false,
      expiryCountdown: null,
    })).toEqual({
      label: '체크',
      value: '손절 임박',
      sub: '목표 +10.0%',
      tone: '#ff6b81',
    });
  });

  test('목표 통과는 체크 헤드라인으로 표시', () => {
    expect(buildCheckItem({
      currentPrice: 12000,
      stop: 9700,
      target1: 11710,
      isIntraday: false,
      expiryCountdown: null,
    }).value).toBe('목표 통과');
  });

  test('intraday는 만료 countdown을 유지하고 체크를 sub로 압축', () => {
    expect(buildCheckItem({
      currentPrice: 10000,
      stop: 9709,
      target1: 11710,
      isIntraday: true,
      expiryCountdown: '37분 남음',
    })).toEqual({
      label: '만료',
      value: '37분 남음',
      sub: '손절 2.9% · 목표 +17.1%',
      tone: 'var(--body)',
    });
  });
});
