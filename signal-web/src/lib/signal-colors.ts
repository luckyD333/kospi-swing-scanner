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
