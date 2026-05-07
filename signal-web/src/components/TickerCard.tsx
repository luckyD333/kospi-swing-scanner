'use client';

import React, { useState, useEffect, useRef } from 'react';
import type { CardProps } from '@/lib/adapt';
import { ts } from '@/lib/typography';
import { confirmationColor } from '@/lib/signal-colors';

interface Props {
  card: CardProps;
  onNavigate: (ticker: string) => void;
  index: number;
}

const fmtNum = (v: number | null): string =>
  v == null ? '—' : v.toLocaleString('ko-KR');

function rsiTone(v: number | null): string {
  if (v == null) return 'var(--body)';
  if (v < 30) return '#30d158';   // 그린: 과매도 매수 기회
  if (v > 70) return '#ff6b81';   // 핑크: 과매수 위험
  return 'var(--body)';
}

export default React.memo(function TickerCard({ card, onNavigate, index }: Props) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const mountedAt = Date.now();
    const obs = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      // 페이지 로드 직후(1초 이내) → stagger 유지, 이후 스크롤 진입 → 즉시
      const delay = Date.now() - mountedAt < 1000 ? Math.min(index * 50, 400) : 0;
      setTimeout(() => setVisible(true), delay);
      obs.disconnect();
    }, { threshold: 0.05 });
    obs.observe(el);
    return () => obs.disconnect();
  }, [index]);

  const { name, ticker, priceDisplay, changeDisplay, direction,
    entry, stop, target1,
    rsi, strategyLabel, timeframe, rank, allStrategyTags,
    signalStatus, decisionMaxRegret,
    productType, confirmationLevel, strategyId } = card;

  const statusBadge = (() => {
    switch (signalStatus) {
      case 'TARGET_REACHED':
        return { label: '목표', color: '#30d158', bg: 'rgba(48,209,88,0.12)' };
      case 'STOPPED_OUT':
        return { label: '손절', color: '#ff6b81', bg: 'rgba(255,107,129,0.12)' };
      case 'STALE':
        return { label: '만료', color: 'var(--muted)', bg: 'rgba(128,128,128,0.12)' };
      default:
        return null;
    }
  })();
  const cardOpacity = signalStatus === 'VALID' ? 1 : 0.55;

  // 한국 주식 관례: 상승=빨강 / 하락=파랑 / 보합=화이트
  const dirGlyph = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '─';
  const priceColor =
    direction === 'up' ? 'var(--gain)' :
    direction === 'down' ? 'var(--loss)' :
    'var(--flat)';

  const nameLen = name.length;
  const nameFontSize = nameLen > 12
    ? `${Math.max(18, Math.round(27 * 12 / nameLen))}px`
    : '27px';
  const tickerFontSize = nameLen > 12 ? '14px' : '16px';

  const rankDisplay = rank != null ? `#${rank}` : '—';

  const primaryMetrics = [
    { label: 'RSI', value: rsi != null ? rsi.toFixed(1) : '—' },
    { label: '랭킹', value: rankDisplay },
    { label: '후회값', value: decisionMaxRegret != null ? decisionMaxRegret.toFixed(2) : '—' },
  ];

  // 라벨은 muted-soft로 한 톤 낮춰 데이터가 자연스럽게 떠오르게 함
  const labelStyle = { ...ts('caption-sm', 'var(--muted-soft)'), marginBottom: '5px' };

  return (
    <div
      ref={ref}
      className="ticker-card"
      onClick={() => onNavigate(ticker)}
      style={{
        background: 'var(--canvas)',
        padding: '52px 32px',
        cursor: 'pointer',
        opacity: visible ? cardOpacity : 0,
        transform: visible ? 'translateY(0)' : 'translateY(16px)',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        height: '100%',
        position: 'relative',
      }}
    >
      {/* 신호 상태 배지 (VALID 외) */}
      {statusBadge && (
        <span style={{
          position: 'absolute',
          top: '16px',
          right: '16px',
          padding: '2px 8px',
          borderRadius: '4px',
          background: statusBadge.bg,
          color: statusBadge.color,
          fontSize: '10px',
          fontWeight: 600,
          letterSpacing: '0',
        }}>
          {statusBadge.label}
        </span>
      )}


      {/* 종목명 — 시선 앵커 1: 100% ink */}
      <div style={{
        fontFamily: 'var(--f-display-stack)',
        fontSize: nameFontSize,
        fontWeight: 600,
        lineHeight: 1.1,
        letterSpacing: '-0.01em',
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

      {/* 상품 유형 배지 (STOCK·UNKNOWN 이외만 표시) */}
      {productType && !['STOCK', 'UNKNOWN'].includes(productType) && (
        <span style={{
          ...ts('caption-sm', '#4c98b9'),
          border: '1px solid rgba(76,152,185,0.4)',
          padding: '2px 8px',
          borderRadius: '3px',
          alignSelf: 'flex-start',
        }}>
          {productType}
        </span>
      )}

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
          {([
            ['진입', entry,   'var(--link)'],
            ['손절', stop,    '#ff6b81'],
            ['목표', target1, '#30d158'],
          ] as [string, number | null, string][]).map(([label, val, color], i) => (
            <div key={label} style={{
              flex: 1,
              paddingRight: i < 2 ? '12px' : '0',
              paddingLeft: i > 0 ? '12px' : '0',
              borderRight: i < 2 ? '1px solid var(--hairline)' : 'none',
            }}>
              <div style={labelStyle}>
                {label}
              </div>
              <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '15px', color }}>
                {fmtNum(val)}
              </div>
            </div>
          ))}
        </div>

        {/* 핵심 지표 1행: RSI | PER | 랭킹 */}
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
                <div style={{
                  fontFamily: 'var(--f-mono-stack)', fontSize: '14px', letterSpacing: 0,
                  color: label === 'RSI' ? rsiTone(rsi) : 'var(--body)',
                }}>
                  {value}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 신호 강도 row — 항상 렌더링, null 시 visibility:hidden으로 높이 일관성 유지 */}
        <div style={{
          borderTop: (confirmationLevel && strategyId.startsWith('strategy_one_')) ? '1px solid var(--hairline)' : 'none',
          paddingTop: '14px', paddingBottom: '14px',
          visibility: (confirmationLevel && strategyId.startsWith('strategy_one_')) ? 'visible' : 'hidden',
        }}>
          <div style={labelStyle}>신호 강도</div>
          <div style={{
            fontFamily: 'var(--f-mono-stack)', fontSize: '13px', letterSpacing: 0,
            color: confirmationLevel ? confirmationColor(confirmationLevel) : 'transparent',
          }}>
            {confirmationLevel ?? '—'}
          </div>
        </div>

        {/* 전략 태그 */}
        <div style={{ display: 'flex', gap: '6px', paddingTop: '4px', paddingBottom: '4px', flexWrap: 'wrap' }}>
          {(() => {
            if (allStrategyTags && allStrategyTags.length > 1) {
              const labels = [...new Set(allStrategyTags.map(t => t.label))];
              const tfs = [...new Set(allStrategyTags.map(t => t.timeframe))];
              return [...labels, ...tfs];
            }
            return [strategyLabel, timeframe];
          })().map(tag => (
            <span key={tag} style={{
              ...ts('caption-sm', '#4c98b9'),
              border: '1px solid #4c98b9',
              padding: '4px 10px',
            }}>
              {tag}
            </span>
          ))}
        </div>

      </div>
    </div>
  );
});
