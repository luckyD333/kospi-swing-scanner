export function confirmationColor(level: string): string {
  if (level === 'STRONG') return '#30d158';
  if (level === 'MEDIUM') return '#ffc107';
  return '#ff6b81';
}

export function confirmationBg(level: string): string {
  if (level === 'STRONG') return 'rgba(48,209,88,0.12)';
  if (level === 'MEDIUM') return 'rgba(255,193,7,0.12)';
  return 'rgba(255,107,129,0.12)';
}

export interface SignalStatusBadgeStyle {
  label: string;
  color: string;
  bg: string;
}

export function signalStatusBadge(
  status: string | undefined | null,
): SignalStatusBadgeStyle | null {
  switch (status) {
    case 'TARGET_REACHED':
      return { label: '목표', color: '#30d158', bg: 'rgba(48,209,88,0.12)' };
    case 'STOPPED_OUT':
      return { label: '손절', color: '#ff6b81', bg: 'rgba(255,107,129,0.12)' };
    case 'STALE':
      return { label: '만료', color: 'var(--muted)', bg: 'rgba(128,128,128,0.12)' };
    default:
      return null;
  }
}
