'use client';

import { useState, useEffect } from 'react';
import type { CardProps } from '@/lib/adapt';
import { ts } from '@/lib/typography';

interface Props {
  card: CardProps;
  onClick: () => void;
  index: number;
}

const fmtNum = (v: number | null): string =>
  v == null ? '—' : v.toLocaleString('ko-KR');

export default function TickerCard({ card, onClick, index }: Props) {
  const [hov, setHov] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), index * 60);
    return () => clearTimeout(timer);
  }, [index]);

  const { name, ticker, priceDisplay, changeDisplay, direction,
    entry, stop, target1, score, per,
    rsi, strategyLabel, timeframe, dataQuality } = card;

  // 한국 주식 관례: 상승=빨강 / 하락=파랑 / 보합=화이트
  const dirGlyph = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '─';
  const priceColor =
    direction === 'up' ? 'var(--gain)' :
    direction === 'down' ? 'var(--loss)' :
    'var(--flat)';

  const nameLen = name.length;
  const nameFontSize = nameLen > 12
    ? `${Math.max(24, Math.round(42 * 12 / nameLen))}px`
    : '42px';
  const tickerFontSize = nameLen > 12 ? '17px' : '21px';

  const primaryMetrics = [
    { label: 'RSI', value: rsi != null ? rsi.toFixed(1) : '—' },
    { label: 'PER', value: per != null ? `${per}x` : '—' },
    { label: '신뢰도', value: score != null ? `${(score / 10).toFixed(0)}%` : '—' },
  ];

  // 라벨은 muted-soft로 한 톤 낮춰 데이터가 자연스럽게 떠오르게 함
  const labelStyle = { ...ts('caption-sm', 'var(--muted-soft)'), marginBottom: '5px' };

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        background: 'var(--canvas)',
        outline: hov ? '1px solid var(--hairline-strong)' : '1px solid transparent',
        outlineOffset: '-1px',
        // design.md known-gap — data-quality flag 시 좌측 4px warning 막대
        borderLeft: `4px solid ${dataQuality === 'warn' ? 'var(--warning)' : 'transparent'}`,
        padding: '52px 32px 52px 28px',  // 좌측 4px 막대 보정 (32px - 4px)
        cursor: 'pointer',
        transition: 'outline-color 200ms ease-out, opacity 400ms ease-out, transform 400ms ease-out',
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(16px)',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        height: '100%',
      }}
    >
      {/* 종목명 — 시선 앵커 1: 100% ink */}
      <div style={{
        fontFamily: 'var(--f-display-stack)',
        fontSize: nameFontSize,
        fontWeight: 400,
        lineHeight: 1.1,
        letterSpacing: '1px',
        color: 'var(--ink)',
        wordBreak: 'keep-all',
      }}>
        {name}
      </div>

      {/* 종목 코드 — muted-soft로 한 톤 낮춤 */}
      <div style={{
        fontFamily: 'var(--f-mono-stack)',
        fontSize: tickerFontSize,
        fontWeight: 400,
        lineHeight: 1,
        letterSpacing: '1px',
        color: 'var(--muted-soft)',
      }}>
        {ticker}
      </div>

      {/* 현재가 + 등락 — 한국 관례 색 분기 */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', marginTop: '4px' }}>
        <span style={{
          fontFamily: 'var(--f-mono-stack)', fontSize: '20px', fontWeight: 400,
          lineHeight: 1.2, letterSpacing: '0',
          color: priceColor,
        }}>
          {priceDisplay}
        </span>
        <span style={{
          ...ts('caption', priceColor),
          fontSize: '12px',
        }}>
          {dirGlyph} {changeDisplay}
        </span>
      </div>

      {/* 하단 고정 영역 */}
      <div style={{ marginTop: 'auto' }}>

        {/* 진입 / 손절 / 목표 — body-strong (매매 트리거 정보, 한 톤 올림) */}
        <div style={{
          display: 'flex',
          paddingTop: '14px',
          paddingBottom: '14px',
          borderTop: '1px solid var(--hairline)',
        }}>
          {([['진입', entry], ['손절', stop], ['목표', target1]] as [string, number | null][]).map(([label, val], i) => (
            <div key={label} style={{
              flex: 1,
              paddingRight: i < 2 ? '12px' : '0',
              paddingLeft: i > 0 ? '12px' : '0',
              borderRight: i < 2 ? '1px solid var(--hairline)' : 'none',
            }}>
              <div style={labelStyle}>
                {label}
              </div>
              <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '15px', color: 'var(--body-strong)' }}>
                {fmtNum(val)}
              </div>
            </div>
          ))}
        </div>

        {/* 핵심 지표 1행: RR | SCR | ATR — body 톤. RR band 색 분기 제거 */}
        <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: '14px', paddingBottom: '14px' }}>
          <div style={{ display: 'flex' }}>
            {primaryMetrics.map(({ label, value }, i) => (
              <div key={label} style={{
                flex: 1,
                paddingRight: i < 2 ? '12px' : '0',
                paddingLeft: i > 0 ? '12px' : '0',
                borderRight: i < 2 ? '1px solid var(--hairline)' : 'none',
              }}>
                <div style={labelStyle}>
                  {label}
                </div>
                <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '14px', color: 'var(--body)', letterSpacing: 0 }}>
                  {value}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 전략 태그 */}
        <div style={{ display: 'flex', gap: '6px', paddingTop: '4px', paddingBottom: '4px', flexWrap: 'wrap' }}>
          {[strategyLabel, timeframe].map(tag => (
            <span key={tag} style={{
              ...ts('caption-sm', 'var(--muted)'),
              letterSpacing: '1.5px',
              border: '1px solid var(--hairline)',
              padding: '4px 10px',
            }}>
              {tag}
            </span>
          ))}
        </div>

      </div>
    </div>
  );
}
