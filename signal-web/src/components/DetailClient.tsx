'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import type { DetailProps, MatchProps } from '@/lib/adapt';
import type { MarketIndex, RegimeScore, BreadthScore, AxesScore, FearGreedSnapshot } from '@/types/signal';
import { ts } from '@/lib/typography';
import { confirmationColor, confirmationBg } from '@/lib/signal-colors';
import TopNav from './TopNav';
import PriceScramble from './PriceScramble';
import Footer from './Footer';
import AboutOverlay from './AboutOverlay';

interface Props {
  detail: DetailProps;
  marketIndices: Record<string, MarketIndex>;
  targetDateDisplay?: string;
  marketRegime?: Record<string, RegimeScore> | null;
  marketBreadth?: Record<string, BreadthScore> | null;
  marketAxes?: Record<string, AxesScore> | null;
  fearGreed?: FearGreedSnapshot | null;
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
        border: '1px solid var(--accent)',
        borderRadius: '9999px',
        padding: '14px 32px',
        height: '44px',
        cursor: 'pointer',
        textDecoration: 'none',
        display: 'inline-flex',
        alignItems: 'center',
        color: 'var(--accent)',
        background: hov ? 'rgba(41,151,255,0.08)' : 'transparent',
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

interface RankRationaleRow {
  label: string;
  value: string;
  mark: '✓' | '⚠' | '·' | '';
  note: string;
  tone: string;
}

const C_OPP  = '#30d158';  // 매수 기회 (그린)
const C_RISK = '#ff6b81';  // 위험/경고 (핑크)

function gradeTradability(s: number | null): { mark: RankRationaleRow['mark']; note: string; tone: string } {
  if (s == null) return { mark: '', note: '', tone: 'var(--muted-soft)' };
  if (s >= 70) return { mark: '✓', note: '양호', tone: C_OPP };
  if (s < 40) return { mark: '⚠', note: '낮음', tone: C_RISK };
  return { mark: '·', note: '보통', tone: 'var(--muted)' };
}

function gradeRR(rr: number | null, band: string | null): { mark: RankRationaleRow['mark']; note: string; tone: string } {
  if (rr == null) return { mark: '', note: '', tone: 'var(--muted-soft)' };
  if (band === 'SWEET') return { mark: '✓', note: '우수', tone: C_OPP };
  if (band === 'OVER') return { mark: '·', note: '여유 보상', tone: 'var(--muted)' };
  return { mark: '⚠', note: '낮음', tone: C_RISK };
}

function gradeRiskPct(p: number | null) {
  if (p == null) return { mark: '' as const, note: '', tone: 'var(--muted-soft)' };
  if (p <= 3) return { mark: '✓' as const, note: '안전', tone: C_OPP };
  if (p > 5) return { mark: '⚠' as const, note: '큼', tone: C_RISK };
  return { mark: '·' as const, note: '보통', tone: 'var(--muted)' };
}

function gradeReward(p: number | null) {
  if (p == null) return { mark: '' as const, note: '', tone: 'var(--muted-soft)' };
  if (p >= 5) return { mark: '✓' as const, note: '충분', tone: C_OPP };
  if (p < 3) return { mark: '⚠' as const, note: '얕음', tone: C_RISK };
  return { mark: '·' as const, note: '보통', tone: 'var(--muted)' };
}

function gradeChange(p: number | null) {
  if (p == null) return { mark: '' as const, note: '', tone: 'var(--muted-soft)' };
  if (p >= 3) return { mark: '✓' as const, note: '강한 모멘텀', tone: C_OPP };
  if (p <= -1) return { mark: '⚠' as const, note: '약세', tone: C_RISK };
  return { mark: '·' as const, note: '평이', tone: 'var(--muted)' };
}

function gradeRsi(r: number | null) {
  if (r == null) return { mark: '' as const, note: '', tone: 'var(--muted-soft)' };
  if (r > 70) return { mark: '⚠' as const, note: '과매수', tone: C_RISK };
  if (r < 30) return { mark: '✓' as const, note: '과매도', tone: C_OPP };
  return { mark: '·' as const, note: '중립', tone: 'var(--muted)' };
}

function grade52w(pct: number | null) {
  if (pct == null) return { mark: '' as const, note: '', tone: 'var(--muted-soft)' };
  if (pct > 85) return { mark: '⚠' as const, note: '고점 근처', tone: C_RISK };
  if (pct < 20) return { mark: '⚠' as const, note: '저점 근처', tone: C_RISK };
  if (pct >= 30 && pct <= 70) return { mark: '✓' as const, note: '중간대', tone: C_OPP };
  return { mark: '·' as const, note: '', tone: 'var(--muted)' };
}

function gradePer(per: number | null) {
  if (per == null) return { mark: '' as const, note: '', tone: 'var(--muted-soft)' };
  if (per < 0) return { mark: '⚠' as const, note: '적자', tone: C_RISK };
  if (per > 50) return { mark: '⚠' as const, note: '고평가', tone: C_RISK };
  if (per >= 5 && per <= 25) return { mark: '✓' as const, note: '적정', tone: C_OPP };
  return { mark: '·' as const, note: '', tone: 'var(--muted)' };
}

function gradeForeign(p: number | null) {
  if (p == null) return { mark: '' as const, note: '', tone: 'var(--muted-soft)' };
  if (p >= 10) return { mark: '✓' as const, note: '높음', tone: C_OPP };
  if (p < 2) return { mark: '·' as const, note: '낮음', tone: 'var(--muted)' };
  return { mark: '·' as const, note: '', tone: 'var(--muted)' };
}


export default function DetailClient({ detail, marketIndices, targetDateDisplay, marketRegime, marketBreadth, marketAxes, fearGreed }: Props) {
  const router = useRouter();
  const [aboutOpen, setAboutOpen] = useState(false);
  const onCloseAbout = useCallback(() => setAboutOpen(false), []);

  useEffect(() => {
    const id = setInterval(() => router.refresh(), 120_000);
    return () => clearInterval(id);
  }, []);
  const {
    name, nameEn, ticker,
    priceDisplay, changeDisplay, direction,
    potentialScore, potentialFactors,
    opportunityScore, opportunityFactors,
    topTradePlan,
    matches,
    rsi1d, rsi1h, rsi30m,
    per, high52w, low52w,
    foreignRatioPct, volumeDisplay, marketCapDisplay,
    atr14, changePct, currentPrice,
    naverUrl, generatedAtDisplay, signalDate,
    confirmationLevel, activeRegime, tradabilityScore,
  } = detail;

  // 대표 매매 파라미터 (matches[0] 기반)
  const entry = topTradePlan?.entry ?? 0;
  const stop = topTradePlan?.stop ?? 0;
  const target1 = topTradePlan?.target1 ?? null;
  const target2 = topTradePlan?.target2 ?? null;
  const rrRatio = topTradePlan?.rrRatio ?? null;
  const rrBand = topTradePlan?.rrBand ?? null;

  // 대표 match에서 risk/reward 계산
  const riskPerShare = entry > 0 && stop > 0 ? entry - stop : null;
  const riskPct = riskPerShare != null && entry > 0
    ? Math.round((riskPerShare / entry) * 10000) / 100
    : null;
  const reward1Pct = target1 != null && entry > 0
    ? Math.round(((target1 - entry) / entry) * 10000) / 100
    : null;
  const reward2Pct = target2 != null && entry > 0
    ? Math.round(((target2 - entry) / entry) * 10000) / 100
    : null;

  // statusBadge는 더 이상 사용되지 않음 (legacy)
  const statusBadge = null;

  const pct52w =
    currentPrice != null && high52w != null && low52w != null && high52w > low52w
      ? ((currentPrice - low52w) / (high52w - low52w)) * 100
      : null;

  return (
    <div style={{ background: 'var(--canvas)', minHeight: '100vh' }}>
      <TopNav
        marketIndices={marketIndices}
        generatedAtDisplay={generatedAtDisplay}
        targetDateDisplay={targetDateDisplay}
        marketRegime={marketRegime}
        marketBreadth={marketBreadth}
        marketAxes={marketAxes}
        fearGreed={fearGreed}
        onHome={() => router.push('/')}
        onOpenAbout={() => setAboutOpen(true)}
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
        <div style={{ ...LABEL, marginBottom: '32px', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <span>
            {matches.length > 1 ? `${matches.length}개 전략 매칭 · ` : ''}
            {matches?.[0] ? `${matches[0].strategy.label} · ${matches[0].strategy.timeframe} · ` : ''}
            {generatedAtDisplay}
            {signalDate ? ` · 신호 시각 ${signalDate}` : ''}
          </span>
        </div>

        {/* 종목명 + 코드 — 동적 clamp size */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', flexWrap: 'wrap', marginBottom: '20px' }}>
          <div style={{
            fontFamily: 'var(--f-display-stack)',
            fontSize: 'clamp(40px, 7vw, 72px)',
            fontWeight: 600, lineHeight: 1.0,
            letterSpacing: '-0.02em',
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
        <div className="params-grid" style={{ borderBottom: '1px solid var(--hairline)' }}>
          {[
            {
              label: '진입가',
              val: entry,
              sub: riskPerShare != null && riskPct != null ? `리스크 ${riskPerShare.toLocaleString('ko-KR')} (${riskPct.toFixed(1)}%)` : '',
              color: 'var(--link)',
            },
            { label: '손절가', val: stop,    sub: riskPerShare != null && riskPct != null ? `리스크 ${riskPerShare.toLocaleString('ko-KR')} (${riskPct.toFixed(1)}%)` : '', color: C_RISK },
            { label: '목표 1', val: target1, sub: target1 != null && reward1Pct != null ? `+${reward1Pct.toFixed(1)}%` : '', color: C_OPP },
            { label: '목표 2', val: target2, sub: target2 != null && reward2Pct != null ? `+${reward2Pct.toFixed(1)}%` : '', color: C_OPP },
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
            { label: 'PER',     value: per != null && per > 0 ? `${per}x` : '—', sub: '주가수익비율' },
            { label: '52주 고가', value: fmt(high52w), sub: '' },
            { label: '52주 저가', value: fmt(low52w),  sub: '' },
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
              <div style={{
                fontFamily: 'var(--f-mono-stack)', fontSize: '20px',
                color: value == null ? 'var(--ink)'
                  : value < 30 ? C_OPP
                  : value > 70 ? C_RISK
                  : 'var(--ink)',
              }}>
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
              <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '20px', color: 'var(--ink)', whiteSpace: 'nowrap' }}>
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

      {/* 잠재력 점수 섹션 */}
      {potentialScore != null && (() => {
        const dayRegime = marketRegime?.['1d'] ?? null;
        const regimeColor = dayRegime
          ? dayRegime.regime === 'BULL' ? 'var(--gain)'
            : dayRegime.regime === 'BEAR' ? 'var(--loss)'
            : 'var(--flat)'
          : 'var(--muted)';

        const sortedByContrib = potentialFactors ? [...potentialFactors].sort((a, b) => b.contribution - a.contribution) : [];
        const top1 = sortedByContrib[0];
        const top2 = sortedByContrib[1];
        const summarySentence =
          top1 && top2
            ? `${top1.label}(${top1.contribution.toFixed(1)})과 ${top2.label}(${top2.contribution.toFixed(1)}) 항목이 잠재력 점수에 가장 크게 기여했어요.`
            : top1
            ? `${top1.label}(${top1.contribution.toFixed(1)})이 잠재력 점수의 주요 기여 요인이에요.`
            : '기여 요인 데이터가 비어 있어요.';

        return (
          <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '56px 40px 0' }}>
            <div style={SECTION_HEAD}>
              잠재력 점수
            </div>

            {/* 최종 스코어 + 시장 국면 라벨 */}
            <div style={{
              display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
              gap: '16px', flexWrap: 'wrap',
              paddingBottom: '32px',
              borderBottom: '1px solid var(--hairline)',
            }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px' }}>
                <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '48px', color: 'var(--ink)', letterSpacing: '-1px' }}>
                  {potentialScore.toFixed(1)}
                </div>
                <div style={{ ...ts('caption', 'var(--muted)') }}>
                  / 100
                </div>
                {confirmationLevel && (
                  <span style={{
                    padding: '2px 10px', borderRadius: '4px',
                    background: confirmationBg(confirmationLevel),
                    color: confirmationColor(confirmationLevel),
                    fontSize: '12px', fontWeight: 600,
                  }}>
                    {confirmationLevel}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap' }}>
                {dayRegime && (
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                    <span style={{ ...ts('caption', regimeColor), letterSpacing: '0.5px' }}>
                      {dayRegime.regime}
                    </span>
                    <span style={ts('caption-sm', 'var(--muted-soft)')}>
                      {dayRegime.score} · 1D 시장 국면
                    </span>
                  </div>
                )}
                {activeRegime && activeRegime !== (dayRegime?.regime ?? '') && (
                  <span style={ts('caption-sm', 'var(--muted-soft)')}>
                    신호 시점 {activeRegime}
                  </span>
                )}
              </div>
            </div>

            {/* Summary */}
            <div style={{ ...ts('caption', 'var(--body)'), paddingTop: '24px', paddingBottom: '8px', lineHeight: 1.6 }}>
              {summarySentence}
            </div>

            {/* FACTOR BREAKDOWN 부제 */}
            <div style={{ ...ts('caption-sm', 'var(--muted)'), paddingTop: '32px', paddingBottom: '12px' }}>
              Factor Breakdown
            </div>

            {/* 컬럼 헤더 */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(80px, 160px) minmax(40px, 56px) 1fr minmax(40px, 56px)',
              alignItems: 'center',
              gap: '16px',
              padding: '12px 0',
              borderBottom: '1px solid var(--hairline)',
            }}>
              <div style={ts('caption-sm', 'var(--muted-soft)')}>요인</div>
              <div style={{ ...ts('caption-sm', 'var(--muted-soft)'), textAlign: 'right' }}>가중치</div>
              <div style={ts('caption-sm', 'var(--muted-soft)')}>기여도</div>
              <div style={{ ...ts('caption-sm', 'var(--muted-soft)'), textAlign: 'right' }}>값</div>
            </div>

            {/* Factor 행들 */}
            <div>
              {potentialFactors && potentialFactors.map((f) => {
                const fillPct = f.weight > 0 ? Math.min(100, (f.contribution / f.weight) * 100) : 0;
                return (
                  <div key={f.key} style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(80px, 160px) minmax(40px, 56px) 1fr minmax(40px, 56px)',
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
                        width: `${Math.max(fillPct, fillPct > 0 ? 1 : 0).toFixed(1)}%`,
                        height: '100%',
                        background: 'var(--accent)',
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

            <div style={{ ...ts('caption-sm', 'var(--muted-soft)'), marginTop: '16px', lineHeight: 1.6 }}>
              가중치는 weights.yml 정책 비중, 기여도 막대는 해당 요인의 percentile 1.0 대비 달성도 (가득 차면 후보 풀 내 1위), 값은 가중치 × percentile.
            </div>
          </div>
        );
      })()}

      {/* 기회 점수 독립 섹션 */}
      {opportunityScore != null && (
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '56px 40px 0' }}>
          <div style={SECTION_HEAD}>기회 점수</div>
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 3fr', gap: '32px',
            paddingBottom: opportunityFactors && opportunityFactors.length > 0 ? '32px' : '0',
            borderBottom: opportunityFactors && opportunityFactors.length > 0 ? '1px solid var(--hairline)' : 'none',
          }}>
            <div>
              <div style={{ ...LABEL, marginBottom: '12px' }}>기회 점수</div>
              <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '32px', color: 'var(--ink)', letterSpacing: '-1px' }}>
                {opportunityScore.toFixed(1)}
              </div>
              <div style={ts('caption-sm', 'var(--muted-soft)')}>/100</div>
            </div>
          </div>
          {opportunityFactors && opportunityFactors.length > 0 && (
            <div style={{ paddingTop: '32px' }}>
              <div style={ts('caption-sm', 'var(--muted)')}>Factor Breakdown</div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(80px, 160px) minmax(40px, 56px) 1fr minmax(40px, 56px)',
                alignItems: 'center',
                gap: '16px',
                padding: '12px 0',
                borderBottom: '1px solid var(--hairline)',
                marginTop: '12px',
              }}>
                <div style={ts('caption-sm', 'var(--muted-soft)')}>요인</div>
                <div style={{ ...ts('caption-sm', 'var(--muted-soft)'), textAlign: 'right' }}>가중치</div>
                <div style={ts('caption-sm', 'var(--muted-soft)')}>기여도</div>
                <div style={{ ...ts('caption-sm', 'var(--muted-soft)'), textAlign: 'right' }}>값</div>
              </div>
              <div>
                {opportunityFactors.map((f) => {
                  const fillPct = f.weight > 0 ? Math.min(100, (f.contribution / f.weight) * 100) : 0;
                  return (
                    <div key={f.key} style={{
                      display: 'grid',
                      gridTemplateColumns: 'minmax(80px, 160px) minmax(40px, 56px) 1fr minmax(40px, 56px)',
                      alignItems: 'center',
                      gap: '16px',
                      padding: '14px 0',
                      borderBottom: '1px solid var(--hairline)',
                    }}>
                      <div style={ts('caption', 'var(--ink)')}>{f.label}</div>
                      <div style={{ ...ts('caption', 'var(--muted)'), textAlign: 'right' }}>
                        {f.weight.toFixed(0)}%
                      </div>
                      <div style={{ background: 'var(--hairline)', borderRadius: '2px', height: '4px', overflow: 'hidden' }}>
                        <div style={{
                          width: `${Math.max(fillPct, fillPct > 0 ? 1 : 0).toFixed(1)}%`,
                          height: '100%',
                          background: 'var(--accent)',
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
            </div>
          )}
        </div>
      )}

      {/* 매칭 전략 리스트 섹션 */}
      {matches && matches.length > 0 && (
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '56px 40px 0' }}>
          {matches.length > 1 && (
            <div style={SECTION_HEAD}>
              매칭 전략 {matches.length}개
            </div>
          )}
          {matches.map((match, idx) => (
            <div key={idx} style={{
              marginBottom: idx < matches.length - 1 ? '48px' : '0',
              paddingBottom: idx < matches.length - 1 ? '48px' : '0',
              borderBottom: idx < matches.length - 1 ? '1px solid var(--hairline)' : 'none',
            }}>
              {/* 매칭 전략 헤더 */}
              <div style={{
                display: 'flex', alignItems: 'baseline', gap: '12px',
                marginBottom: '24px',
              }}>
                <div style={{ ...ts('caption', 'var(--ink)'), fontWeight: 600 }}>
                  {match.strategy.label}
                </div>
                <div style={ts('caption-sm', 'var(--muted)')}>
                  {match.strategy.timeframe}
                </div>
              </div>

              {/* 신호 강도 */}
              <div style={{ paddingBottom: '0' }}>
                <div style={{ ...LABEL, marginBottom: '12px' }}>신호 강도</div>
                <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '32px', color: 'var(--ink)', letterSpacing: '-1px' }}>
                  {match.signalStrength != null ? match.signalStrength.toFixed(1) : '—'}
                </div>
                <div style={ts('caption-sm', 'var(--muted-soft)')}>/100</div>
              </div>
            </div>
          ))}
        </div>
      )}


      <div style={{ height: '30px' }} />
      <Footer />
      <AboutOverlay open={aboutOpen} onClose={onCloseAbout} />
    </div>
  );
}
