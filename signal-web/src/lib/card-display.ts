import type { SignalComponent } from '@/lib/adapt';

export interface CardMetricItem {
  label: string;
  value: string;
  sub: string | null;
  tone: string;
}

const pct = (value: number): string => value.toFixed(1);

const targetText = (targetRoomPct: number | null): string | null => {
  if (targetRoomPct == null) return null;
  return targetRoomPct < 0 ? '목표 통과' : `목표 +${pct(targetRoomPct)}%`;
};

const stopText = (stopRoomPct: number | null): string | null => {
  if (stopRoomPct == null) return null;
  return stopRoomPct <= 0 ? '손절 통과' : `손절 ${pct(stopRoomPct)}%`;
};

export function buildReasonItem(
  signalComponents: SignalComponent[],
  strategyLabel: string,
): CardMetricItem {
  const okComponents = signalComponents.filter((c) => c.status === 'ok');
  const displayComponents = (okComponents.length > 0
    ? okComponents
    : signalComponents.filter((c) => c.status === 'warn')
  ).slice(0, 2);

  if (displayComponents.length === 0) {
    return {
      label: '근거',
      value: strategyLabel || '—',
      sub: null,
      tone: 'var(--body)',
    };
  }

  return {
    label: '근거',
    value: displayComponents.map((c) => c.label).join(' · '),
    sub: null,
    tone: okComponents.length > 0 ? 'var(--body)' : 'var(--quality-warn)',
  };
}

export function buildCheckItem(params: {
  currentPrice: number | null;
  stop: number;
  target1: number | null;
  isIntraday: boolean;
  expiryCountdown: string | null;
}): CardMetricItem {
  const { currentPrice, stop, target1, isIntraday, expiryCountdown } = params;
  const targetRoomPct = target1 != null && currentPrice != null && currentPrice > 0
    ? ((target1 - currentPrice) / currentPrice) * 100
    : null;
  const stopRoomPct = currentPrice != null && currentPrice > 0
    ? ((currentPrice - stop) / currentPrice) * 100
    : null;
  const target = targetText(targetRoomPct);
  const stopRisk = stopText(stopRoomPct);

  if (isIntraday) {
    const sub = [stopRisk, target].filter(Boolean).join(' · ') || null;
    return {
      label: '만료',
      value: expiryCountdown ?? '—',
      sub,
      tone: expiryCountdown === '만료' ? 'var(--quality-bad)' : 'var(--body)',
    };
  }

  if (targetRoomPct != null && targetRoomPct < 0) {
    return {
      label: '체크',
      value: '목표 통과',
      sub: stopRisk,
      tone: 'var(--quality-warn)',
    };
  }

  if (stopRoomPct != null && stopRoomPct <= 0) {
    return {
      label: '체크',
      value: '손절 통과',
      sub: target,
      tone: 'var(--quality-bad)',
    };
  }

  if (stopRoomPct != null && stopRoomPct < 1) {
    return {
      label: '체크',
      value: '손절 임박',
      sub: target,
      tone: 'var(--quality-bad)',
    };
  }

  return {
    label: '체크',
    value: stopRisk ?? '—',
    sub: target,
    tone: 'var(--body)',
  };
}
