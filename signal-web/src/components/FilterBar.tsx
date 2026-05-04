'use client';

import { useState } from 'react';
import { ts } from '@/lib/typography';

interface FilterTabProps {
  label: string;
  active: boolean;
  onClick: () => void;
  small?: boolean;
}

function FilterTab({ label, active, onClick, small }: FilterTabProps) {
  const [hov, setHov] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        ...ts('caption', active ? 'var(--ink)' : (hov ? 'var(--body)' : 'var(--muted)')),
        background: 'none',
        border: 'none',
        borderBottom: active ? '1px solid var(--ink)' : '1px solid transparent',
        cursor: 'pointer',
        padding: small ? '14px 12px' : '16px 16px',
        transition: 'color 150ms, border-color 150ms',
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </button>
  );
}

interface Props {
  strategies: string[];
  timeframes: string[];
  activeStrategy: string;
  activeTimeframe: string;
  sortBy: string;
  onStrategy: (s: string) => void;
  onTimeframe: (t: string) => void;
  onSort: (s: string) => void;
}

const SORT_OPTIONS: [string, string][] = [
  ['랭킹', 'rank'],
  ['RSI', 'rsi'],
  ['PER', 'per'],
  ['가격', 'price'],
];

export default function FilterBar({
  strategies, timeframes,
  activeStrategy, activeTimeframe, sortBy,
  onStrategy, onTimeframe, onSort,
}: Props) {
  return (
    <div className="scroll-x-hidden" style={{
      borderTop: '1px solid var(--hairline)',
      borderBottom: '1px solid var(--hairline)',
      padding: '0 40px',
      display: 'flex',
      alignItems: 'center',
      flexWrap: 'nowrap',
    }}>
      <div style={{ display: 'flex', flexShrink: 0 }}>
        {strategies.map(s => (
          <FilterTab key={s} label={s} active={activeStrategy === s} onClick={() => onStrategy(s)} />
        ))}
      </div>
      <div style={{ width: '1px', height: '24px', background: 'var(--hairline)', margin: '0 16px', flexShrink: 0 }} />
      <div style={{ display: 'flex', flexShrink: 0 }}>
        {timeframes.map(t => (
          <FilterTab key={t} label={t} active={activeTimeframe === t} onClick={() => onTimeframe(t)} />
        ))}
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ display: 'flex', flexShrink: 0 }}>
        {SORT_OPTIONS.map(([label, val]) => (
          <FilterTab key={val} label={label} active={sortBy === val} onClick={() => onSort(val)} small />
        ))}
      </div>
    </div>
  );
}
