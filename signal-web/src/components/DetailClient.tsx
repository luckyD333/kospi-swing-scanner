'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import type { CardProps } from '@/lib/adapt';
import type { MarketIndex, RegimeScore, BreadthScore, AxesScore, FearGreedSnapshot } from '@/types/signal';
import { ts } from '@/lib/typography';
import TopNav from './TopNav';
import PriceScramble from './PriceScramble';
import Footer from './Footer';

interface Props {
  card: CardProps;
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

function getScoreCaption(strategyId: string): string {
  if (strategyId.startsWith('strategy_one_')) return 'Mean Reversion 신호 강도 (RSI/BB/쌍바닥/장악형)';
  if (strategyId.startsWith('strategy_two_')) return '15일 상대 수익률 순위';
  if (strategyId.startsWith('strategy_three_')) return 'Donchian 20일 채널 돌파 강도';
  if (strategyId.startsWith('strategy_four_')) return 'MA20 추세 + MA5 눌림목 회복도';
  if (strategyId.startsWith('strategy_five_')) return 'Bull flag 돌파 강도';
  return '전략 점수';
}

export default function DetailClient({ card, marketIndices, targetDateDisplay, marketRegime, marketBreadth, marketAxes, fearGreed }: Props) {
  const router = useRouter();

  useEffect(() => {
    const id = setInterval(() => router.refresh(), 120_000);
    return () => clearInterval(id);
  }, []);
  const {
    name, nameEn, ticker,
    priceDisplay, changeDisplay, direction,
    entry, stop, target1, target2,
    score,
    rsi1d, rsi1h, rsi30m,
    per, high52w, low52w,
    foreignRatioPct, volumeDisplay, marketCapDisplay,
    riskPerShare, riskPct, reward1Pct, reward2Pct,
    rrRatio, rrBand, atr14, changePct, currentPrice,
    strategyId, strategyLabel, strategyCategory, timeframe,
    naverUrl, generatedAtDisplay, signalDate,
    decisionScore, decisionFactors, decisionMaxRegret,
    rank,
  } = card;

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
          {rank != null ? `#${rank} · ` : ''}{strategyLabel} · {strategyCategory} · {timeframe} · {generatedAtDisplay}
          {signalDate ? ` · 신호 시각 ${signalDate}` : ''}
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
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0',
          borderBottom: '1px solid var(--hairline)',
        }}>
          {[
            { label: '진입가', val: entry,   sub: '지정가', color: 'var(--link)' },
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
      {decisionScore != null && decisionFactors != null && (() => {
        const dayRegime = marketRegime?.['1d'] ?? null;
        const regimeColor = dayRegime
          ? dayRegime.regime === 'BULL' ? 'var(--gain)'
            : dayRegime.regime === 'BEAR' ? 'var(--loss)'
            : 'var(--flat)'
          : 'var(--muted)';

        const sortedByContrib = [...decisionFactors].sort((a, b) => b.contribution - a.contribution);
        const top1 = sortedByContrib[0];
        const top2 = sortedByContrib[1];
        const summarySentence =
          top1 && top2
            ? `${top1.label}(${top1.contribution.toFixed(1)})과 ${top2.label}(${top2.contribution.toFixed(1)}) 항목이 종합점수에 가장 크게 기여했어요.`
            : top1
            ? `${top1.label}(${top1.contribution.toFixed(1)})이 종합점수의 주요 기여 요인이에요.`
            : '기여 요인 데이터가 비어 있어요.';

        return (
          <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '56px 40px 0' }}>
            <div style={SECTION_HEAD}>
              의사결정 스코어
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
                  {decisionScore.toFixed(1)}
                </div>
                <div style={{ ...ts('caption', 'var(--muted)') }}>
                  / 100
                </div>
              </div>
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
            </div>

            {/* Summary */}
            <div style={{ ...ts('caption', 'var(--body)'), paddingTop: '24px', paddingBottom: '8px', lineHeight: 1.6 }}>
              {summarySentence}
              {decisionMaxRegret != null && (
                <>{' '}최대 후회값 {decisionMaxRegret.toFixed(2)}로 하방 시나리오에서도 안정적이에요.</>
              )}
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
              {decisionFactors.map((f) => {
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

      {/* 랭킹 산출 근거 */}
      {(() => {
        const scoreCaption = getScoreCaption(strategyId);

        const rows: RankRationaleRow[] = [
          {
            label: '손익비',
            value: rrRatio != null ? `${rrRatio.toFixed(1)}${rrBand ? ` / ${rrBand}` : ''}` : '—',
            ...gradeRR(rrRatio, rrBand),
          },
          {
            label: '손절 폭',
            value: riskPct != null ? `${riskPct.toFixed(1)}%` : '—',
            ...gradeRiskPct(riskPct),
          },
          {
            label: '목표(T2)',
            value: reward2Pct != null ? `+${reward2Pct.toFixed(1)}%` : '—',
            ...gradeReward(reward2Pct),
          },
          {
            label: '당일 등락',
            value: changePct != null ? `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%` : '—',
            ...gradeChange(changePct),
          },
          {
            label: 'RSI(1D)',
            value: rsi1d != null ? rsi1d.toFixed(1) : '—',
            ...gradeRsi(rsi1d),
          },
          {
            label: '52주 위치',
            value: pct52w != null ? `${pct52w.toFixed(0)}%` : '—',
            ...grade52w(pct52w),
          },
          {
            label: 'PER',
            value: per != null && per > 0 ? `${per.toFixed(1)}x` : '—',
            ...gradePer(per),
          },
          {
            label: '외국인 비율',
            value: foreignRatioPct != null ? `${foreignRatioPct.toFixed(1)}%` : '—',
            ...gradeForeign(foreignRatioPct),
          },
        ];

        return (
          <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '56px 40px 0' }}>
            <div style={SECTION_HEAD}>
              랭킹 산출 근거
            </div>

            {/* 헤드라인 */}
            <div style={{
              display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
              gap: '16px', flexWrap: 'wrap',
              paddingBottom: '24px',
              borderBottom: '1px solid var(--hairline)',
            }}>
              <div style={{ ...ts('caption', 'var(--body)'), lineHeight: 1.6 }}>
                {strategyLabel} ({strategyCategory}) 후보 풀에서{' '}
                <span style={{ color: 'var(--ink)' }}>{rank != null ? `#${rank}위` : '—'}</span>
                {score != null ? <>, 점수 <span style={{ fontFamily: 'var(--f-mono-stack)', color: 'var(--ink)' }}>{score.toFixed(1)}</span></> : null}
              </div>
              <div style={ts('caption-sm', 'var(--muted-soft)')}>
                {scoreCaption}
              </div>
            </div>

            {/* 지표 행들 */}
            <div>
              {rows.map((r) => (
                <div key={r.label} style={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(80px, 160px) 1fr minmax(80px, 140px)',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '14px 0',
                  borderBottom: '1px solid var(--hairline)',
                }}>
                  <div style={ts('caption', 'var(--ink)')}>{r.label}</div>
                  <div style={{ fontFamily: 'var(--f-mono-stack)', fontSize: '15px', color: 'var(--ink)' }}>
                    {r.value}
                  </div>
                  <div style={{ ...ts('caption-sm', r.tone), textAlign: 'right' }}>
                    {r.mark}{r.mark && r.note ? ' ' : ''}{r.note}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ ...ts('caption-sm', 'var(--muted-soft)'), marginTop: '16px', lineHeight: 1.6 }}>
              순위는 전략별 점수 내림차순 정렬 결과예요. 위 8개 지표는 진입 안정성·모멘텀·펀더멘탈 관점에서 산출 근거를 보조적으로 평가하기 위한 참고치이며 ATR(14)는 {atr14 != null ? atr14.toLocaleString('ko-KR') : '—'} 입니다.
            </div>
          </div>
        );
      })()}

      <div style={{ height: '30px' }} />
      <Footer />
    </div>
  );
}
