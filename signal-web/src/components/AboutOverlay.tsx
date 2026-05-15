'use client';

import { useEffect, useState } from 'react';
import { ts } from '@/lib/typography';

interface Props {
  open: boolean;
  onClose: () => void;
}

const STEPS = [
  { num: '01', title: '장 열기 전 확인', desc: '전날 종가 기준으로 뽑은 후보 목록입니다. 장 시작 전 미리 검토하세요.' },
  { num: '02', title: '오전 중 진입', desc: '시초가 전후 오전 시간대가 진입에 유리합니다. 이미 크게 오른 상태라면 넘기세요.' },
  { num: '03', title: '손절가 먼저 확인', desc: '진입 전 손절가 위치를 확인하고, 감당 가능한 손실인지 먼저 따져보세요.' },
  { num: '04', title: '1~3일 안에 정리', desc: '목표가 도달 시 분할 익절, 손절가 이탈 시 즉시 매도. 보유가 길어질수록 유리함이 줄어들 수 있어요.' },
  { num: '05', title: '전략 성격 파악', desc: '하단 전략별 참고사항을 보고, 어떤 상황에서 뽑힌 종목인지 확인하세요.' },
] as const;

const STRATEGIES = [
  { num: '01', title: '전략 1', focus: '단기 과매도 후 반등', tip: '패턴이 형성된 당일 빠르게 진입하는 편이 유리해요.' },
  { num: '02', title: '전략 2', focus: '시장 대비 상대 강도 상위', tip: '추세가 살아있는 동안 짧게 탄다는 느낌으로 접근하세요.' },
  { num: '03', title: '전략 3', focus: '가격 범위 상향 돌파', tip: '돌파 직후 진입이 핵심. 다음 날 이상 끌면 의미가 옅어져요.' },
  { num: '04', title: '전략 4', focus: '추세 중 눌림목 회복', tip: '추세가 살아있는지 먼저 확인하세요. 추세가 꺾인 종목엔 해당 없어요.' },
  { num: '05', title: '전략 5', focus: '단기 급등 후 재상승', tip: '오전 거래량을 함께 보세요. 거래량 없이 오르면 허수 가능성 있어요.' },
] as const;

const TERMS = [
  { term: 'RR',  def: 'Risk-Reward. 손익비. 목표폭 ÷ 손절폭' },
  { term: 'SCR', def: 'Score. 전략별 종합 점수 (0~100)' },
  { term: 'ATR', def: 'Average True Range. 14일 평균 변동폭' },
  { term: 'RSI', def: 'Relative Strength Index. 14일 과매수·과매도 지표' },
  { term: 'PER', def: 'Price-Earnings Ratio. 주가수익비율' },
  { term: 'BB',  def: 'Bollinger Band. 이동평균 ± 표준편차' },
] as const;

export default function AboutOverlay({ open, onClose }: Props) {
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);

  // mount/unmount 제어 — fade 완료 후 unmount
  useEffect(() => {
    if (open) {
      setMounted(true);
      requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
    } else {
      setVisible(false);
      const t = setTimeout(() => setMounted(false), 340);
      return () => clearTimeout(t);
    }
  }, [open]);

  // ESC 닫기
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  // body scroll lock
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  if (!mounted) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        background: 'rgba(0,0,0,0.92)',
        backdropFilter: 'blur(14px)',
        opacity: visible ? 1 : 0,
        transition: 'opacity 240ms ease',
        overflowY: 'auto',
        display: 'flex',
        justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          maxWidth: '1080px',
          width: '100%',
          padding: '0 40px 80px',
          transform: visible ? 'translateY(0)' : 'translateY(-12px)',
          transition: 'transform 320ms cubic-bezier(0.22, 1, 0.36, 1)',
        }}
      >
        {/* 헤더 */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          height: '72px',
          borderBottom: '1px solid var(--hairline)',
          marginBottom: '80px',
        }}>
          <span style={{ ...ts('wordmark', 'var(--muted)'), letterSpacing: '0.12em' }}>
            SIG-BORA — ABOUT
          </span>
          <button
            onClick={onClose}
            style={{
              ...ts('caption', 'var(--muted)'),
              background: 'none',
              border: '1px solid var(--hairline)',
              borderRadius: '4px',
              padding: '6px 14px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'color 150ms, border-color 150ms',
            }}
          >
            ✕ 닫기 <span style={{ ...ts('caption-sm', 'var(--muted-soft)') }}>[ESC]</span>
          </button>
        </div>

        {/* HERO */}
        <div style={{ marginBottom: '80px' }}>
          <p style={{
            ...ts('body-md', 'var(--body)'),
            maxWidth: '640px',
            margin: 0,
            lineHeight: 1.7,
          }}>
            매일 장 마감 후 KOSPI/KOSDAQ 전 종목을 분석해 다음 날 주목할 만한 종목 후보를 정리합니다.
            5가지 전략이 각자의 기준으로 신호를 포착하고, 점수·손익비 순으로 정렬합니다.
            매수 추천이 아닌 관찰 명세서입니다. 최종 판단은 직접 하세요.
          </p>
        </div>

        {/* 3-스텝 그리드 */}
        <div style={{ marginBottom: '80px' }}>
          <p style={{ ...ts('caption', 'var(--muted)'), letterSpacing: '0.1em', marginBottom: '32px' }}>
            어떻게 사용하나요
          </p>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '1px',
            background: 'var(--hairline)',
            border: '1px solid var(--hairline)',
          }}>
            {STEPS.map(s => (
              <div key={s.num} style={{ background: 'var(--canvas)', padding: '40px 32px' }}>
                <div style={{
                  fontFamily: 'var(--f-mono-stack)',
                  fontSize: '11px',
                  color: 'var(--muted-soft)',
                  letterSpacing: '0.1em',
                  marginBottom: '16px',
                }}>
                  {s.num}
                </div>
                <div style={{ ...ts('title-md', 'var(--ink)'), marginBottom: '12px' }}>
                  {s.title}
                </div>
                <div style={{ ...ts('body-md', 'var(--body)'), lineHeight: 1.6 }}>
                  {s.desc}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 전략별 참고사항 */}
        <div style={{ marginBottom: '80px' }}>
          <p style={{ ...ts('caption', 'var(--muted)'), letterSpacing: '0.1em', marginBottom: '32px' }}>
            전략별 참고사항
          </p>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '1px',
            background: 'var(--hairline)',
            border: '1px solid var(--hairline)',
          }}>
            {STRATEGIES.map(s => (
              <div key={s.num} style={{ background: 'var(--canvas)', padding: '40px 32px' }}>
                <div style={{
                  fontFamily: 'var(--f-mono-stack)',
                  fontSize: '11px',
                  color: 'var(--muted-soft)',
                  letterSpacing: '0.1em',
                  marginBottom: '16px',
                }}>
                  {s.num}
                </div>
                <div style={{ ...ts('title-md', 'var(--ink)'), marginBottom: '8px' }}>
                  {s.title}
                </div>
                <div style={{ ...ts('caption', 'var(--warning)'), marginBottom: '12px' }}>
                  {s.focus}
                </div>
                <div style={{ ...ts('body-md', 'var(--body)'), lineHeight: 1.6 }}>
                  {s.tip}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 약어 사전 (full-width 2-column grid) */}
        <div style={{ marginBottom: '60px' }}>
          <p style={{ ...ts('caption', 'var(--muted)'), letterSpacing: '0.1em', marginBottom: '24px' }}>
            약어 사전
          </p>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '12px 40px',
          }}>
            {TERMS.map(t => (
              <div key={t.term} style={{ display: 'flex', gap: '12px' }}>
                <span style={{
                  fontFamily: 'var(--f-mono-stack)',
                  fontSize: '11px',
                  color: 'var(--warning)',
                  letterSpacing: '0.08em',
                  minWidth: '36px',
                  flexShrink: 0,
                  paddingTop: '1px',
                }}>
                  {t.term}
                </span>
                <span style={{ ...ts('caption', 'var(--body)'), lineHeight: 1.5 }}>
                  {t.def}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 주의 박스 */}
        <div style={{
          border: '1px solid var(--hairline)',
          borderLeft: '3px solid var(--warning)',
          padding: '24px 28px',
          background: 'rgba(212,160,23,0.04)',
        }}>
          <p style={{ ...ts('caption', 'var(--warning)'), letterSpacing: '0.08em', marginBottom: '8px' }}>
            투자 위험 안내
          </p>
          <p style={{ ...ts('body-md', 'var(--muted)'), margin: 0, lineHeight: 1.7 }}>
            본 시그널은 알고리즘이 생성한 결과로 투자 권유가 아닙니다.
            주식 투자는 원금 손실의 위험이 있으며, 모든 투자 결정의 책임은 투자자 본인에게 있습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
