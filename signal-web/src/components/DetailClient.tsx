'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { CardProps } from '@/lib/adapt';
import type { MarketIndex, RegimeScore } from '@/types/signal';
import { ts } from '@/lib/typography';
import TopNav from './TopNav';
import PriceScramble from './PriceScramble';
import Footer from './Footer';
import DisclaimerBar from './DisclaimerBar';

interface Props {
  card: CardProps;
  marketIndices: Record<string, MarketIndex>;
  marketRegime?: Record<string, RegimeScore> | null;
}

function NaverLink({ href }: { href: string }) {
  const [hov, setHov] = useState(false);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        ...ts('button'),
        border: '1px solid var(--ink)',
        borderRadius: '9999px',
        padding: '14px 32px',
        height: '44px',
        cursor: 'pointer',
        textDecoration: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        background: hov ? 'rgba(255,255,255,0.07)' : 'transparent',
        transition: 'background 150ms ease-out',
      }}
    >
      네이버 금융에서 보기
    </a>
  );
}

function fmt(n: number | null): string {
  if (n == null) return '—';
  return n.toLocaleString('ko-KR');
}

function fmtNull(n: number | null, suffix = ''): string {
  if (n == null) return '—';
  return `${n}${suffix}`;
}

const LABEL = ts('caption', 'var(--muted)');
const SUBLABEL = { ...ts('caption', 'var(--muted-soft)'), marginTop: '8px' };
const SECTION_HEAD = { ...LABEL, marginBottom: '28px' };

export default function DetailClient({ card, marketIndices, marketRegime }: Props) {
  const router = useRouter();
  const {
    name, nameEn, ticker,
    priceDisplay, changeDisplay, direction,
    entry, stop, target1, target2,
    score, rsi,
    rsi1d, rsi1h, rsi30m,
    per, high52w, low52w,
    foreignRatioPct, volumeDisplay, marketCapDisplay,
    riskPerShare, riskPct, reward1Pct, reward2Pct,
    strategyLabel, strategyCategory, timeframe,
    naverUrl, generatedAtDisplay,
    decisionScore, decisionFactors, decisionMaxRegret,
  } = card;

  return (
    <div style={{ background: 'var(--canvas)', minHeight: '100vh' }}>
      <TopNav
        marketIndices={marketIndices}
        generatedAtDisplay={generatedAtDisplay}
        marketRegime={marketRegime}
        onHome={() => router.push('/')}
      />

      {/* 뒤로가기 */}
      <div style={{ padding: '24px 40px 0' }}>
        <button
          onClick={() => router.back()}
          style={{
            ...ts('caption', 'var(--muted)'),
            background: 'none', border: 'none',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px',
          }}
        >
          ← BACK TO CATALOG
        </button>
      </div>

      {/* Hero 밴드 */}
      <div style={{
        padding: '60px 40px 80px',
        maxWidth: '1280px',
        margin: '0 auto',
        borderBottom: '1px solid var(--hairline)',
      }}>
        <div style={{ ...LABEL, marginBottom: '32px' }}>
          {strategyLabel} · {strategyCategory} · {timeframe} · {generatedAtDisplay}
        </div>

        {/* 종목명 + 코드 — 동적 clamp size */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', flexWrap: 'wrap', marginBottom: '20px' }}>
          <div style={{
            fontFamily: 'var(--f-display-stack)',
            fontSize: 'clamp(40px, 7vw, 72px)',
            fontWeight: 400, lineHeight: 1.0,
            letterSpacing: '2px', textTransform: 'uppercase',
            color: 'var(--ink)',
          }}>
            {name}
          </div>
          <div style={{
            fontFamily: 'var(--f-mono-stack)',
            fontSize: 'clamp(20px, 3.5vw, 36px)',
            fontWeight: 400, lineHeight: 1.0,
            letterSpacing: '0px', color: 'var(--muted-soft)',
            paddingBottom: '2px',
          }}>
            {ticker}
          </div>
        </div>

        {/* 현재가 scramble — direction 기반 색 (한국 관례) */}
        <PriceScramble
          priceDisplay={priceDisplay}
          changeDisplay={changeDisplay}
          direction={direction}
          fontSize="clamp(20px, 3.5vw, 36px)"
        />

        {nameEn && (
          <div style={{ ...LABEL, marginTop: '16px' }}>
            {nameEn}
          </div>
        )}

        {naverUrl && (
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap', marginTop: '32px' }}>
            <NaverLink href={naverUrl} />
          </div>
        )}
      </div>

      {/* 매매 파라미터 */}
      <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '56px 40px 0' }}>
        <div style={SECTION_HEAD}>
          매매 파라미터
        </div>

        {/* 진입 / 손절 / 목표1 / 목표2 */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0',
          borderBottom: '1px solid var(--hairline)',
        }}>
          {[
            { label: '진입가', val: entry,   sub: '지정가', color: 'var(--link)' },
            { label: '손절가', val: stop,    sub: riskPerShare != null && riskPct != null ? `리스크 ${riskPerShare.toLocaleString('ko-KR')} (${riskPct.toFixed(1)}%)` : '', color: 'var(--loss)' },
            { label: '목표 1', val: target1, sub: target1 != null && reward1Pct != null ? `+${reward1Pct.toFixed(1)}%` : '', color: 'var(--gain)' },
            { label: '목표 2', val: target2, sub: target2 != null && reward2Pct != null ? `+${reward2Pct.toFixed(1)}%` : '', color: 'var(--gain)' },
          ].map(({ label, val, sub, color }, i) => (
            <div key={label} style={{
              padding: '24px 0',
              borderRight: i < 3 ? '1px solid var(--hairline)' : 'none',
              paddingRight: i < 3 ? '32px' : '0',
              paddingLeft: i > 0 ? '32px' : '0',
            }}>
              <div style={{ ...LABEL, marginBottom: '12px' }}>
                {label}
              </div>
              {val != null ? (
                <PriceScramble
                  priceDisplay={val.toLocaleString('ko-KR')}
                  fontSize="24px"
                  color={color}
                />
              ) : (
                <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '28px', color: 'var(--muted-soft)' }}>—</div>
              )}
              {sub && (
                <div style={SUBLABEL}>
                  {sub}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 신뢰도 / RSI */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0',
          borderBottom: '1px solid var(--hairline)',
        }}>
          {[
            { label: '신뢰도', value: score != null ? `${(score / 10).toFixed(0)}%` : '—', sub: '전략 신뢰도' },
            { label: 'RSI(14)', value: rsi != null ? rsi.toFixed(1) : '—', sub: rsi != null ? (rsi < 30 ? '과매도' : rsi > 70 ? '과매수' : '중립') : '' },
          ].map(({ label, value, sub }, i) => (
            <div key={label} style={{
              padding: '24px 0',
              borderRight: i < 1 ? '1px solid var(--hairline)' : 'none',
              paddingRight: i < 1 ? '32px' : '0',
              paddingLeft: i > 0 ? '32px' : '0',
            }}>
              <div style={{ ...LABEL, marginBottom: '12px' }}>
                {label}
              </div>
              <div style={{ ...ts('numeric-lg', 'var(--ink)') }}>
                {value}
              </div>
              {sub && (
                <div style={SUBLABEL}>
                  {sub}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 주가 참고 지표 */}
      <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 40px 0' }}>
        <div style={{ ...LABEL, margin: '48px 0 24px' }}>
          주가 참고 지표
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0',
          borderTop: '1px solid var(--hairline)',
          borderBottom: '1px solid var(--hairline)',
        }}>
          {[
            { label: 'PER',     value: fmtNull(per, 'x'), sub: '주가수익비율' },
            { label: '52주 고가', value: fmt(high52w),      sub: '' },
            { label: '52주 저가', value: fmt(low52w),       sub: '' },
          ].map(({ label, value, sub }, i) => (
            <div key={label} style={{
              padding: '20px 0',
              borderRight: i < 2 ? '1px solid var(--hairline)' : 'none',
              paddingRight: i < 2 ? '24px' : '0',
              paddingLeft: i > 0 ? '24px' : '0',
            }}>
              <div style={{ ...ts('caption-sm', 'var(--muted)'), marginBottom: '10px' }}>
                {label}
              </div>
              <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '20px', color: 'var(--ink)', letterSpacing: 0 }}>
                {value}
              </div>
              {sub && (
                <div style={{
                  ...ts('caption-sm', 'var(--muted-soft)'),
                  fontSize: '9px',
                  marginTop: '6px',
                }}>
                  {sub}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* RSI 멀티 타임프레임 */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0',
          borderBottom: '1px solid var(--hairline)',
        }}>
          {[
            { label: 'RSI(1D)',  value: rsi1d },
            { label: 'RSI(1h)',  value: rsi1h },
            { label: 'RSI(30m)', value: rsi30m },
          ].map(({ label, value }, i) => (
            <div key={label} style={{
              padding: '20px 0',
              borderRight: i < 2 ? '1px solid var(--hairline)' : 'none',
              paddingRight: i < 2 ? '32px' : '0',
              paddingLeft: i > 0 ? '32px' : '0',
            }}>
              <div style={{ ...LABEL, marginBottom: '10px' }}>
                {label}
              </div>
              <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '20px', color: 'var(--ink)' }}>
                {value != null ? value.toFixed(1) : '—'}
              </div>
              {value != null && (
                <div style={{ ...LABEL, color: 'var(--muted-soft)', marginTop: '6px' }}>
                  {value < 30 ? '과매도' : value > 70 ? '과매수' : '중립'}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* 거래량 / 외국인 비율 / 기관 순매수 */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0',
          borderBottom: '1px solid var(--hairline)',
        }}>
          {[
            { label: '시가총액',   value: marketCapDisplay ?? '—', sub: '' },
            { label: '거래량',    value: volumeDisplay,            sub: '당일 기준' },
            { label: '외국인 비율', value: foreignRatioPct != null ? `${foreignRatioPct.toFixed(1)}%` : '—', sub: '최근 공시' },
          ].map(({ label, value, sub }, i) => (
            <div key={label} style={{
              padding: '20px 0',
              borderRight: i < 2 ? '1px solid var(--hairline)' : 'none',
              paddingRight: i < 2 ? '32px' : '0',
              paddingLeft: i > 0 ? '32px' : '0',
            }}>
              <div style={{ ...LABEL, marginBottom: '10px' }}>
                {label}
              </div>
              <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '20px', color: 'var(--ink)' }}>
                {value}
              </div>
              {sub && (
                <div style={{ ...LABEL, color: 'var(--muted-soft)', marginTop: '6px' }}>
                  {sub}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 의사결정 스코어 */}
      {decisionScore != null && decisionFactors != null && (
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '56px 40px 0' }}>
          <div style={SECTION_HEAD}>
            의사결정 스코어
          </div>

          {/* 최종 스코어 */}
          <div style={{
            display: 'flex', alignItems: 'baseline', gap: '12px',
            paddingBottom: '32px',
            borderBottom: '1px solid var(--hairline)',
          }}>
            <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '48px', color: 'var(--ink)', letterSpacing: '-1px' }}>
              {decisionScore.toFixed(1)}
            </div>
            <div style={{ ...ts('caption', 'var(--muted)') }}>
              / 100
            </div>
          </div>

          {/* Factor Breakdown */}
          <div style={{ paddingTop: '24px' }}>
            {decisionFactors.map((f) => {
              const fillPct = f.weight > 0 ? Math.min(100, (f.contribution / f.weight) * 100) : 0;
              return (
                <div key={f.key} style={{
                  display: 'grid',
                  gridTemplateColumns: '160px 56px 1fr 56px',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '14px 0',
                  borderBottom: '1px solid var(--hairline)',
                }}>
                  <div style={{ ...ts('caption', 'var(--ink)') }}>{f.label}</div>
                  <div style={{ ...ts('caption', 'var(--muted)'), textAlign: 'right' }}>
                    {f.weight.toFixed(0)}%
                  </div>
                  <div style={{ background: 'var(--hairline)', borderRadius: '2px', height: '4px', overflow: 'hidden' }}>
                    <div style={{
                      width: `${fillPct.toFixed(1)}%`,
                      height: '100%',
                      background: 'var(--ink)',
                      borderRadius: '2px',
                    }} />
                  </div>
                  <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '13px', color: 'var(--ink)', textAlign: 'right' }}>
                    {f.contribution.toFixed(1)}
                  </div>
                </div>
              );
            })}
          </div>

          {decisionMaxRegret != null && (
            <div style={{ ...ts('caption', 'var(--muted-soft)'), marginTop: '16px' }}>
              최대 후회값 {decisionMaxRegret.toFixed(2)} — 낮을수록 하방 시나리오에서 안정적
            </div>
          )}
        </div>
      )}

      <div style={{ height: '80px' }} />
      <Footer />
      <DisclaimerBar />
    </div>
  );
}
