export interface TickerStateDisplay {
  label: string;
  sub: string | null;
  tone: string;
}

const atrLabelKo: Record<string, string> = {
  LOW: '변동 낮음',
  MID: '변동 보통',
  HIGH: '변동 높음',
};

const isFiniteNumber = (value: number | null): value is number =>
  typeof value === 'number' && Number.isFinite(value);

function tickerStateByRsi(rsi: number | null): TickerStateDisplay {
  if (!isFiniteNumber(rsi)) {
    return { label: '확인중', sub: null, tone: 'var(--muted)' };
  }
  if (rsi <= 30) return { label: '과매도', sub: null, tone: 'var(--quality-warn)' };
  if (rsi <= 35) return { label: '반등대기', sub: null, tone: 'var(--quality-warn)' };
  if (rsi >= 75) return { label: '과열심화', sub: null, tone: 'var(--gain)' };
  if (rsi >= 70) return { label: '과열주의', sub: null, tone: 'var(--quality-warn)' };
  return { label: '중립권', sub: null, tone: 'var(--body)' };
}

export function formatTickerState(
  rsi: number | null,
  perTickerRegime: string | null,
  atrBucket: string | null = null,
): TickerStateDisplay {
  const regime = perTickerRegime ?? 'MIXED';
  const rsiState = tickerStateByRsi(rsi);
  let display: TickerStateDisplay;

  switch (regime) {
    case 'UPTREND_STRONG':
      display = isFiniteNumber(rsi) && rsi >= 70
        ? { label: '과열강세', sub: null, tone: 'var(--gain)' }
        : { label: '강세추세', sub: null, tone: 'var(--gain)' };
      break;
    case 'UPTREND_WEAK':
      display = isFiniteNumber(rsi) && rsi <= 45
        ? { label: '눌림회복', sub: null, tone: 'var(--gain)' }
        : { label: '상승시도', sub: null, tone: 'var(--gain)' };
      break;
    case 'RANGE_TIGHT':
      display = isFiniteNumber(rsi) && rsi <= 35
        ? { label: '압축반등', sub: null, tone: 'var(--quality-warn)' }
        : { label: '압축대기', sub: null, tone: 'var(--body)' };
      break;
    case 'RANGE':
      display = rsiState.label === '과열심화'
        ? { label: '과열주의', sub: null, tone: 'var(--quality-warn)' }
        : rsiState;
      break;
    case 'DOWNTREND_WEAK':
      display = { label: '약세주의', sub: null, tone: 'var(--quality-warn)' };
      break;
    case 'DOWNTREND_STRONG':
      display = { label: '하락위험', sub: null, tone: 'var(--loss)' };
      break;
    default:
      display = rsiState;
      break;
  }

  const subParts = [
    isFiniteNumber(rsi) ? `RSI ${rsi.toFixed(0)}` : null,
    atrBucket ? (atrLabelKo[atrBucket] ?? `ATR ${atrBucket}`) : null,
  ].filter(Boolean);

  return {
    ...display,
    sub: subParts.length > 0 ? subParts.join(' · ') : null,
  };
}
