'use client';

import type { MarketIndex, RegimeScore, BreadthScore, AxesScore, FearGreedSnapshot } from '@/types/signal';
import { ts } from '@/lib/typography';
import FearGreedGauge from './FearGreedGauge';

interface Props {
  marketIndices: Record<string, MarketIndex>;
  generatedAtDisplay: string;
  targetDateDisplay?: string;
  marketRegime?: Record<string, RegimeScore> | null;
  marketBreadth?: Record<string, BreadthScore> | null;
  marketAxes?: Record<string, AxesScore> | null;
  fearGreed?: FearGreedSnapshot | null;
  onHome?: () => void;
}

const REGIME_ORDER = ['1d', '1h'] as const;

const regimeColor = (regime: string): string =>
  regime === 'BULL' ? 'var(--gain)'
  : regime === 'BEAR' ? 'var(--loss)'
  : 'var(--flat)';

export default function TopNav({ marketIndices, generatedAtDisplay, targetDateDisplay, marketRegime, marketBreadth, marketAxes, fearGreed, onHome }: Props) {
  const entries = Object.entries(marketIndices);
  const sortedRegimes = marketRegime
    ? REGIME_ORDER.filter((tf) => marketRegime[tf]).map((tf) => [tf, marketRegime[tf]] as const)
    : [];
  const hasFearGreed = fearGreed != null;
  const hasRegime = hasFearGreed || sortedRegimes.length > 0;
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

        {/* 시장 현황 + 마켓 레짐 — 단일 인라인 컨테이너, 구분선만 */}
        <div style={{
          display: 'flex',
          flex: 1,
          alignItems: 'center',
          gap: '0',
          overflow: 'hidden',
          height: '100%',
        }}>
          {entries.map(([key, item], i) => {
            const isLastIndex = i === entries.length - 1;
            const showBorder = !isLastIndex || hasRegime;
            return (
              <div key={key} style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                paddingRight: '20px',
                marginRight: '20px',
                borderRight: showBorder ? '1px solid var(--hairline)' : 'none',
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
            );
          })}

          {/* Fear & Greed 게이지 — 1D/1H regime chip 자리에 단일 컴포지트 표시.
              fearGreed 부재 시 (initial deploy 등) 기존 1D/1H regime chip 으로 graceful fallback. */}
          {hasFearGreed ? (
            <FearGreedGauge data={fearGreed!} />
          ) : (
            sortedRegimes.map(([tf, r], i) => {
              const isLast = i === sortedRegimes.length - 1;
              return (
                <div key={tf} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  paddingRight: '20px',
                  marginRight: '20px',
                  borderRight: !isLast ? '1px solid var(--hairline)' : 'none',
                  flexShrink: 0,
                }}>
                  <span style={ts('caption-sm', 'var(--muted)')}>
                    {tf.toUpperCase()}
                  </span>
                  <span style={{
                    ...ts('caption', regimeColor(r.regime)),
                    letterSpacing: '0.5px',
                  }}>
                    {r.regime}
                  </span>
                  <span style={ts('caption-sm', 'var(--muted-soft)')}>
                    {r.score}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* 기준일 + 업데이트 시각 */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: '2px',
          flexShrink: 0,
        }}>
          {targetDateDisplay ? (
            <span style={{
              fontFamily: 'var(--f-mono-stack)',
              fontSize: '10px',
              color: 'var(--body-strong)',
              letterSpacing: '0.5px',
              whiteSpace: 'nowrap',
            }}>
              기준 {targetDateDisplay}
            </span>
          ) : null}
          <span style={{
            fontFamily: 'var(--f-mono-stack)',
            fontSize: '9px',
            color: 'var(--muted-soft)',
            letterSpacing: '1px',
            whiteSpace: 'nowrap',
          }}>
            갱신 {generatedAtDisplay}
          </span>
        </div>
      </div>
    </nav>
  );
}
