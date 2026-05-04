'use client';

import type { MarketIndex, RegimeScore } from '@/types/signal';
import { ts } from '@/lib/typography';

interface Props {
  marketIndices: Record<string, MarketIndex>;
  generatedAtDisplay: string;
  marketRegime?: Record<string, RegimeScore> | null;
  onHome?: () => void;
}

export default function TopNav({ marketIndices, generatedAtDisplay, marketRegime, onHome }: Props) {
  const entries = Object.entries(marketIndices);
  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.95)',
      backdropFilter: 'blur(8px)',
      borderBottom: '1px solid var(--hairline)',
    }}>
      {/* 워드마크 + 시장현황 + generated_at — 단일 44px 로우 */}
      <div style={{
        height: '44px',
        display: 'flex', alignItems: 'center',
        padding: '0 40px',
        gap: '0',
        overflow: 'hidden',
      }}>
        {/* SIGNAL 워드마크 */}
        <button
          onClick={onHome}
          style={{
            ...ts('wordmark'),
            background: 'none', border: 'none',
            cursor: 'pointer',
            flexShrink: 0,
            paddingRight: '24px',
            marginRight: '24px',
            borderRight: '1px solid var(--hairline)',
            height: '100%',
            display: 'flex', alignItems: 'center',
          }}
        >
          SIGNAL
        </button>

        {/* 시장 현황 — 인라인, 구분선만 */}
        <div style={{
          display: 'flex',
          flex: 1,
          alignItems: 'center',
          gap: '0',
          overflow: 'hidden',
          height: '100%',
        }}>
          {entries.map(([key, item], i) => (
            <div key={key} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              paddingRight: '20px',
              marginRight: '20px',
              borderRight: i < entries.length - 1 ? '1px solid var(--hairline)' : 'none',
              flexShrink: 0,
            }}>
              <span style={ts('caption-sm', 'var(--muted)')}>
                {item.label}
              </span>
              <span style={{
                ...ts('caption', 'var(--body-strong)'),
                letterSpacing: '0.5px',
              }}>
                {item.value_display}
              </span>
              <span style={ts(
                'caption-sm',
                item.direction === 'up' ? 'var(--gain)' : item.direction === 'down' ? 'var(--loss)' : 'var(--flat)',
              )}>
                {item.change_display}
              </span>
            </div>
          ))}
        </div>

        {/* market regime — generated_at 좌측에 압축 */}
        {marketRegime && Object.entries(marketRegime).map(([tf, r]) => (
          <span key={tf} style={{
            fontFamily: 'var(--f-mono-stack)',
            fontSize: '10px',
            letterSpacing: '2px',
            marginRight: '16px',
            textTransform: 'uppercase' as const,
            flexShrink: 0,
            color: r.regime === 'BULL' ? 'var(--gain)' : r.regime === 'BEAR' ? 'var(--loss)' : 'var(--muted)',
          }}>
            {tf.toUpperCase()} {r.regime}·{r.score}
          </span>
        ))}

        {/* 업데이트 시각 */}
        <span style={{
          fontFamily: 'var(--f-mono-stack)',
          fontSize: '9px',
          color: 'var(--muted-soft)',
          letterSpacing: '1px',
          whiteSpace: 'nowrap',
          flexShrink: 0,
        }}>
          {generatedAtDisplay}
        </span>
      </div>
    </nav>
  );
}
