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

  // 시장 지표 아이템 — borderless=true 이면 구분선·패딩 없이 gap만 사용 (서브열용)
  function MarketItems({ borderless }: { borderless?: boolean }) {
    const itemStyle = (showBorder: boolean): React.CSSProperties => borderless ? {} : {
      paddingRight: '20px',
      marginRight: '20px',
      borderRight: showBorder ? '1px solid var(--hairline)' : 'none',
    };

    return (
      <>
        {entries.map(([key, item], i) => {
          const isLastIndex = i === entries.length - 1;
          const showBorder = !isLastIndex || hasRegime;
          return (
            <div key={key} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              flexShrink: 0,
              ...itemStyle(showBorder),
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
                flexShrink: 0,
                ...itemStyle(!isLast),
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
      </>
    );
  }

  return (
    <nav className="topnav" style={{
      position: 'sticky', top: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.95)',
      backdropFilter: 'blur(8px)',
      borderBottom: '1px solid var(--hairline)',
    }}>
      {/* 워드마크 + 시장현황(데스크탑) + generated_at — 44px 행 */}
      <div
        className="topnav-main-row"
        style={{
          height: '44px',
          display: 'flex', alignItems: 'center',
          gap: '0',
          overflow: 'hidden',
        }}
      >
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
          SIG-BORA
        </button>

        {/* 시장 현황 — 데스크탑에서만 인라인 노출 */}
        <div className="topnav-market-inline">
          <MarketItems />
        </div>

        {/* 업데이트 시각 */}
        <span style={{
          ...ts('caption-sm', '#ff9f0a'),
          flexShrink: 0,
          whiteSpace: 'nowrap',
          paddingLeft: '12px',
          borderLeft: '1px solid var(--hairline)',
        }}>
          갱신 {generatedAtDisplay}
        </span>
      </div>

      {/* 모바일 서브열 — 639px 이하에서만 노출 */}
      <div className="topnav-market-sub">
        <MarketItems borderless />
      </div>
    </nav>
  );
}
