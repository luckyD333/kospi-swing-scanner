'use client';

import type { FearGreedSnapshot } from '@/types/signal';
import { ts } from '@/lib/typography';

interface Props {
  data: FearGreedSnapshot;
  showBorder?: boolean;
}

const labelColor = (label: string): string => {
  switch (label) {
    case 'Extreme Fear':
      return 'var(--loss)';
    case 'Fear':
      return 'var(--loss-soft, var(--loss))';
    case 'Greed':
      return 'var(--gain-soft, var(--gain))';
    case 'Extreme Greed':
      return 'var(--gain)';
    case 'Neutral':
    default:
      return 'var(--flat)';
  }
};

function Sparkline({ points, color }: { points: number[]; color: string }) {
  if (points.length === 0) return null;
  const W = 80;
  const H = 18;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = Math.max(1, max - min);
  const path = points
    .map((v, i) => {
      const x = (i / Math.max(1, points.length - 1)) * W;
      const y = H - ((v - min) / range) * H;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ display: 'block' }}
      aria-hidden="true"
    >
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={1.2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function FearGreedGauge({ data, showBorder = false }: Props) {
  const color = labelColor(data.label);
  const points = data.history.map((h) => h.score);
  const tooltip =
    `Momentum ${data.components.momentum.toFixed(1)} · ` +
    `Breadth ${data.components.breadth.toFixed(1)} · ` +
    `Volatility ${data.components.volatility.toFixed(1)}`;
  return (
    <div
      title={tooltip}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        paddingRight: '20px',
        marginRight: '20px',
        borderRight: showBorder ? '1px solid var(--hairline)' : 'none',
        flexShrink: 0,
      }}
    >
      <span style={ts('caption-sm', 'var(--muted)')}>F&amp;G</span>
      <span style={{ ...ts('caption', color), letterSpacing: '0.5px' }}>
        {data.label}
      </span>
      <span style={{ ...ts('caption', 'var(--body-strong)'), letterSpacing: '0.5px' }}>
        {Math.round(data.score)}
      </span>
      <Sparkline points={points} color={color} />
    </div>
  );
}
