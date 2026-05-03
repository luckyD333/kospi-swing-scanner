'use client';

import { useState } from 'react';
import type { MarketIndex } from '@/types/signal';
import { ts } from '@/lib/typography';

interface Props {
  marketIndices: Record<string, MarketIndex>;
  generatedAtDisplay: string;
  onHome?: () => void;
}

function NavLink({ label }: { label: string }) {
  const [hov, setHov] = useState(false);
  return (
    <span
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        ...ts('nav-link', hov ? 'var(--ink)' : 'var(--muted)'),
        cursor: 'pointer',
        transition: 'color 150ms',
      }}
    >
      {label}
    </span>
  );
}

export default function TopNav({ marketIndices, generatedAtDisplay, onHome }: Props) {
  const entries = Object.entries(marketIndices);
  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.95)',
      backdropFilter: 'blur(8px)',
      borderBottom: '1px solid var(--hairline)',
    }}>
      {/* 시장 현황 로우 */}
      <div className="scroll-x-hidden" style={{
        height: '36px',
        display: 'flex', alignItems: 'center',
        padding: '0 40px',
        borderBottom: '1px solid var(--hairline)',
      }}>
        {entries.map(([key, item], i) => (
          <div key={key} style={{
            display: 'flex', alignItems: 'center', gap: '7px',
            flexShrink: 0,
            paddingRight: '20px',
            marginRight: '20px',
            borderRight: i < entries.length - 1 ? '1px solid var(--hairline)' : 'none',
          }}>
            <span style={ts('caption-sm', 'var(--muted)')}>
              {item.label}
            </span>
            <span style={{
              ...ts('caption', 'var(--body-strong)'),
              letterSpacing: '0.5px',  // 가격은 caption 2px tracking 대신 좁게
            }}>
              {item.value_display}
            </span>
            <span style={ts(
              'caption-sm',
              item.direction === 'up' ? 'var(--gain)' : item.direction === 'down' ? 'var(--loss)' : 'var(--muted)',
            )}>
              {item.change_display}
            </span>
          </div>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ ...ts('caption-sm', 'var(--muted-soft)'), flexShrink: 0 }}>
          {generatedAtDisplay}
        </span>
      </div>

      {/* 워드마크 + ABOUT 로우 */}
      <div style={{
        height: '48px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 40px',
      }}>
        <button
          onClick={onHome}
          style={{
            ...ts('wordmark'),
            background: 'none', border: 'none',
            cursor: 'pointer',
          }}
        >
          SIGNAL
        </button>
        <NavLink label="ABOUT" />
      </div>
    </nav>
  );
}
