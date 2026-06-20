'use client';

import React, { useState, useEffect, useRef } from 'react';
import type { CardProps } from '@/lib/adapt';
import { ts } from '@/lib/typography';
import { confirmationColor, signalStatusBadge } from '@/lib/signal-colors';
import { formatTickerState } from '@/lib/ticker-state';
import { buildCheckItem, buildReasonItem } from '@/lib/card-display';

interface Props {
  card: CardProps;
  onNavigate: (ticker: string) => void;
  index: number;
}

const fmtNum = (v: number | null): string =>
  v == null ? '—' : v.toLocaleString('ko-KR');


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
    signalStrength, decisionScore, decisionRegretScore,
    strategyLabel, timeframe, rank, allStrategyTags,
    signalStatus, signalFreshness,
    productType, confirmationLevel, strategyId,
    currentPrice, signalDate, signalComponents,
    rsi, perTickerRegime, atrBucket,
    orderTypeLabel, maxChase,
    recommendedHoldingBars, holdingConfidence, holdingStatus } = card;

  const statusBadge = signalStatusBadge(signalStatus);
  const cardOpacity = (signalStatus === 'VALID' && !signalFreshness?.plan_expired) ? 1 : 0.55;

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

  const primaryMetrics = [
    { label: '신호 강도', value: signalStrength != null ? signalStrength.toFixed(1) : '—' },
    { label: '잠재력 점수', value: decisionScore != null ? decisionScore.toFixed(1) : '—' },
    { label: '기회 점수', value: decisionRegretScore != null ? decisionRegretScore.toFixed(1) : '—' },
  ];
  const showHoldingGuide = holdingStatus === 'OK' && recommendedHoldingBars != null;
  const holdingConfidencePct = holdingConfidence != null
    ? `${Math.round(holdingConfidence * 100)}%`
    : null;
  const tickerState = formatTickerState(rsi, perTickerRegime, atrBucket);

  // 30m·1h 만료 countdown (signalDate + TF별 임계, KST 고정 파싱). 렌더 시점 계산 — 120s refresh 의존.
  const isIntraday = timeframe === '30m' || timeframe === '1h';
  const expiryCountdown = (() => {
    if (!isIntraday || !signalDate) return null;
    const sdRaw = signalDate.includes('+') || signalDate.endsWith('Z')
      ? signalDate
      : `${signalDate}+09:00`;
    const expiry = new Date(sdRaw).getTime() + (timeframe === '1h' ? 2 : 1) * 3600_000;
    if (Number.isNaN(expiry)) return null;
    const remainMin = Math.floor((expiry - Date.now()) / 60_000);
    if (remainMin <= 0) return '만료';
    if (remainMin >= 60) return `${Math.floor(remainMin / 60)}h ${remainMin % 60}m`;
    return `${remainMin}분 남음`;
  })();

  const reasonItem = buildReasonItem(signalComponents, strategyLabel);
  const checkItem = buildCheckItem({
    currentPrice,
    stop,
    target1,
    isIntraday,
    expiryCountdown,
  });

  const tradeCheckItems = [
    reasonItem,
    checkItem,
    {
      label: '종목상태',
      value: tickerState.label,
      sub: tickerState.sub,
      tone: tickerState.tone,
    },
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
          borderRadius: 'var(--radius-sm)',
          background: statusBadge.bg,
          color: statusBadge.color,
          fontSize: '10px',
          fontWeight: 600,
          letterSpacing: '0',
        }}>
          {statusBadge.label}
        </span>
      )}

      {/* 신호 만료 배지 */}
      {signalFreshness?.plan_expired && (
        <span style={{
          position: 'absolute',
          top: '16px',
          right: statusBadge ? '80px' : '16px',
          padding: '2px 8px',
          borderRadius: 'var(--radius-sm)',
          background: 'rgba(255,193,7,0.12)',
          color: 'var(--quality-warn)',
          fontSize: '10px',
          fontWeight: 600,
          letterSpacing: '0',
        }}>
          신호 만료
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
          ...ts('caption-sm', 'var(--tag)'),
          border: '1px solid rgba(76,152,185,0.4)',
          padding: '2px 8px',
          borderRadius: 'var(--radius-sm)',
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
            ['손절', stop,    'var(--quality-bad)'],
            ['목표', target1, 'var(--quality-good)'],
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
              {i === 0 && orderTypeLabel && (
                <div style={{
                  ...ts('caption-sm', maxChase != null ? 'var(--link)' : 'var(--muted-soft)'),
                  marginTop: '4px',
                  lineHeight: 1.2,
                }}>
                  {orderTypeLabel}
                  {maxChase != null ? ` ${fmtNum(maxChase)}` : ''}
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{
          borderTop: '1px solid var(--hairline)',
          paddingTop: '14px',
          paddingBottom: '14px',
        }}>
          <div style={{ display: 'flex' }}>
            {tradeCheckItems.map(({ label, value, sub, tone }, i) => (
              <div key={label} style={{
                flex: 1,
                minWidth: 0,
                paddingRight: i < 2 ? '12px' : '0',
                paddingLeft: i > 0 ? '12px' : '0',
                borderRight: i < 2 ? '1px solid var(--hairline)' : 'none',
              }}>
                <div style={labelStyle}>
                  {label}
                </div>
                <div style={{
                  fontFamily: 'var(--f-mono-stack)',
                  fontSize: '13px',
                  lineHeight: 1.25,
                  letterSpacing: 0,
                  color: tone,
                  overflowWrap: 'anywhere',
                }}>
                  {value}
                </div>
                {sub && (
                  <div style={{
                    ...ts('caption-sm', 'var(--muted-soft)'),
                    marginTop: '4px',
                    lineHeight: 1.25,
                    overflowWrap: 'anywhere',
                  }}>
                    {sub}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {showHoldingGuide && (
          <div style={{
            borderTop: '1px solid var(--hairline)',
            paddingTop: '14px',
            paddingBottom: '14px',
          }}>
            <div style={labelStyle}>보유 가이드</div>
            <div style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: '8px',
              flexWrap: 'wrap',
            }}>
              <span style={{
                fontFamily: 'var(--f-mono-stack)',
                fontSize: '15px',
                letterSpacing: 0,
                color: 'var(--body)',
              }}>
                {recommendedHoldingBars}거래일
              </span>
              <span style={ts('caption-sm', 'var(--muted-soft)')}>
                {holdingConfidencePct ? `근거 ${holdingConfidencePct} · ` : ''}
                D+{recommendedHoldingBars} 매도 검토
              </span>
            </div>
          </div>
        )}

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
                  color: 'var(--body)',
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
              ...ts('caption-sm', 'var(--tag)'),
              border: '1px solid var(--tag)',
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
