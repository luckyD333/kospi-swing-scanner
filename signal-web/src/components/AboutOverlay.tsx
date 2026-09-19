'use client';

import { useEffect, useState } from 'react';
import { ts } from '@/lib/typography';
import { fetchStrategyPerformance } from '@/lib/api';
import type { StrategyPerformanceResponse } from '@/types/performance';
import StrategyPerformanceChart from './StrategyPerformanceChart';

interface Props {
  open: boolean;
  onClose: () => void;
}

const STEPS = [
  { num: '01', title: '후보 확인', desc: '일봉 후보는 평일 장 마감 후 스캔으로 전날 확정 종가를 기준 삼아 뽑습니다. 현재가와 신호 상태는 장중 2분마다, 1시간봉 신호는 30분마다 갱신돼요.', accent: 'var(--accent)' },
  { num: '02', title: '주문 라벨대로 진입', desc: '일봉 신호는 뜬 다음 거래일 진입을 기준으로 설계했습니다. 진입가 아래 라벨이 주문 방법이에요. 역지정가는 진입가를 넘어설 때 체결되는 주문, 지정가는 눌림을 기다리는 주문, 상한 지정가는 표시된 금액까지만 따라가라는 뜻입니다.', accent: 'var(--quality-good)' },
  { num: '03', title: '유효기간 안에 정리', desc: '일봉 신호는 뜬 날과 다음 거래일까지만 유효합니다. 목표가에 닿거나 손절가를 이탈하면 그날 목록에서 빠져요.', accent: 'var(--warning)' },
] as const;

const STRATEGIES = [
  {
    num: '01', title: '전략 1', focus: '평균회귀 — 과매도 후 반등', tf: '일봉 · 주봉 · 1시간봉',
    principle: '과매도 구간에서 가격이 평균으로 되돌아오는 성질을 노려요. 네 가지 신호가 동시에 맞을 때만 진입해 오탐을 줄입니다. 7개 중 유일하게 추세를 거스르는 전략이에요.',
    entry: '최근 10봉 내 RSI(14) 32 이하 · 볼린저 하단 이탈 또는 연속 음봉 · 최근 3봉 내 쌍바닥 · 장악형 양봉 + 당일 양봉',
    caution: '목표가가 고정 수익률이 아니라 20일 이동평균선까지의 복귀예요. 이미 평균 가까이 올라온 종목은 남은 폭이 짧습니다. 2차 바닥이 최근 3봉 안에 있어야 하므로 하루만 늦어도 근거가 약해져요.',
  },
  {
    num: '02', title: '전략 2', focus: '상대강도 — 시장 대비 상위', tf: '일봉 · 1시간봉',
    principle: '최근 20일 수익률 순위가 높은 종목이 단기간 더 오르는 경향을 노려요. 절대 상승폭이 아니라 전체 종목 대비 순위를 봅니다.',
    entry: '20일 수익률 상위 20% 진입, 단 상위 5%는 제외 · 당일 거래량 20일 평균 이상 · 변동성 과대 구간은 점수 감점',
    caution: '가장 많이 오른 종목은 일부러 뺍니다. 폭등 끝물은 되돌림 위험이 커서예요. 그 종목이 횡보나 하락 국면으로 분류되면 신호 자체가 나오지 않습니다.',
  },
  {
    num: '03', title: '전략 3', focus: '채널 돌파 — 추세 추종', tf: '일봉 · 1시간봉',
    principle: '최근 20일 고점을 넘어서면 추세가 이어진다고 보고 올라타요. 가짜 돌파를 거르려고 돌파 폭이 일정 수준 이상일 때만 인정합니다.',
    entry: '직전 20봉 고가 상향 돌파 · 돌파 폭이 ATR(14)의 0.5배 이상 · 거래량 20일 평균 이상 · 전일 +30% 이상 급등 종목은 제외',
    caution: '손절가는 ATR 기준선과 20일 채널 저점 중 진입가에 가까운 쪽으로 정해져요. 채널이 깊은 종목은 ATR 기준선이 쓰여 손절폭이 변동성만큼 벌어집니다. 돌파 당일 종가 기준 신호라 하루 이상 지나면 전제가 달라져요.',
  },
  {
    num: '04', title: '전략 4', focus: '눌림목 — 추세 중 되돌림 매수', tf: '일봉 · 1시간봉',
    principle: '상승 추세가 살아 있는 종목이 잠깐 밀렸다 돌아오는 자리를 삽니다. 추세와 같은 방향이라 전략 1 같은 역추세 위험이 없어요.',
    entry: '종가가 MA20 위 · 최근 5봉 중 MA5 아래로 밀린 봉 존재 · 당일 MA5 회복 · 거래량 20일 평균의 80% 이상',
    caution: 'MA20 바로 아래가 손절가 후보로 들어가 손실 폭을 줄여줘요. 반대로 MA20을 종가로 깨면 추세 중 눌림이라는 전제 자체가 사라지니 기계적으로 정리하세요. 거래량 기준이 다른 전략보다 느슨해서 수급은 직접 확인할 값어치가 있어요.',
  },
  {
    num: '05', title: '전략 5', focus: '급등 후 재돌파 — Bull Flag', tf: '일봉 · 1시간봉',
    principle: '급등한 뒤 거래량이 줄면서 좁은 범위에 눌려 있다가 다시 뚫는 자리를 노려요. 쉬어가는 구간에서 매물이 소화됐다고 보는 패턴입니다.',
    entry: '15봉 내 +7% 이상 급등 · 직전 7봉 평균 거래량이 급등 구간의 70% 미만 · 7봉 고저 범위가 ATR의 2배 미만 · 당일 압축 구간 고점 돌파 + 거래량 동반',
    caution: '7개 중 손절 기준이 가장 좁고 목표가 가장 멉니다. 승률보다 한 번의 큰 수익을 노리는 구조라 연속 손절을 견딜 비중 조절이 필요해요. 압축 구간 저점을 깨면 패턴이 무효입니다.',
  },
  {
    num: '06', title: '전략 6', focus: '채널 격자 — 돌파 후 리테스트', tf: '일봉 · 주봉',
    principle: '뚫린 저항선이 지지선으로 역할을 바꾸는 성질을 씁니다. 하락 추세선을 거래량을 동반해 넘은 뒤, 그 선이나 위쪽 격자선까지 되밀렸다가 지지되면 매수해요.',
    entry: '고점 두 개를 이은 기준선을 ATR 0.5배 이상 + 거래량을 동반해 돌파(최근 30봉 내) · 이후 기준선 아래 종가 마감이 한 번도 없음 · 선 위에서 저가가 선에 닿고 종가는 선 위 유지',
    caution: '목표가가 수익률이 아니라 차트상 바로 위의 선이라 종목마다 거리가 크게 다릅니다. 1차·2차 목표가 같아 부분 익절 구간이 없어요. 돌파한 선을 종가로 다시 깨면 근거가 사라집니다.',
  },
  {
    num: '07', title: '전략 7', focus: '추세 전환 — 하이킨아시', tf: '일봉',
    principle: '평활 캔들인 하이킨아시의 방향이 하락에서 상승으로 바뀌는 첫 봉을 잡아요. 전환 자리가 매물대 위이거나 직전 파동의 되돌림 지점 근처일 때만 인정합니다.',
    entry: '하이킨아시 종가가 직전 5봉 채널 상단을 상향 돌파 · 매물대 POC 위 또는 피보나치 61.8% ±0.5 ATR 밴드 중 하나 충족',
    caution: '전환 첫 봉이라 되돌림이 잦아요. 추적 손절선이 손절가 후보로 들어가는데 이 선을 이탈하면 지표상 전환이 취소된 것이니 바로 정리하세요. 하이킨아시 값은 실제 종가와 달라서 일반 차트와 눈으로 비교하면 어긋나 보입니다.',
  },
] as const;

const TERMS = [
  { term: 'RSI',   def: '상대강도지수. 14일 기준 과매수·과매도를 재는 값. 30 아래면 과매도, 70 위면 과매수' },
  { term: 'ATR',   def: '14일 평균 변동폭. 손절 거리와 돌파 강도의 기준 단위로 쓰여요' },
  { term: 'MA5·MA20', def: '5일·20일 이동평균선. 단기 흐름과 추세선 역할' },
  { term: 'BB',    def: '볼린저 밴드. 20일 평균 ±2 표준편차로 그린 변동 범위' },
  { term: 'POC',   def: '매물대에서 거래가 가장 많이 몰린 가격' },
  { term: '하이킨아시', def: '연속된 봉을 평활해 추세 방향을 또렷하게 만든 캔들' },
  { term: '봉',    def: '캔들 하나. 일봉 1개가 1거래일, 주봉 1개가 1주' },
  { term: 'PER',   def: '주가수익비율' },
  { term: 'ROE',   def: '자기자본이익률' },
  { term: 'D+N',   def: '신호가 뜬 날로부터 N거래일 뒤' },
  { term: '1d·1h·1W', def: '신호를 만든 봉 단위. 각각 일봉·1시간봉·주봉' },
  { term: '시장 국면', def: 'BULL·NEUTRAL·BEAR 3단계. 점수 가중에 이미 반영되어 있어 따로 할 일은 없어요' },
  { term: '신호 등급', def: 'STRONG·MEDIUM·WEAK 3단계. 진입 근거가 얼마나 겹쳐 있는지 나타내요' },
  { term: 'STALE', def: '유효기간이 지난 신호. 목록에서는 자동으로 빠집니다' },
  { term: 'F&G',   def: 'Fear & Greed. 시장 심리 지수. 참고용이며 매수 판단에는 반영하지 않아요' },
  { term: 'V-KOSPI', def: '코스피200 옵션에서 산출한 변동성 지수. 참고용' },
] as const;

export default function AboutOverlay({ open, onClose }: Props) {
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [performance, setPerformance] = useState<StrategyPerformanceResponse | null>(null);
  const [performanceLoading, setPerformanceLoading] = useState(false);
  const [performanceError, setPerformanceError] = useState<string | null>(null);

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

  // 성과는 ABOUT을 열 때만 요청한다. catalog의 2분 signal refresh payload에는 포함하지 않는다.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPerformanceLoading(true);
    setPerformanceError(null);
    fetchStrategyPerformance()
      .then(data => {
        if (!cancelled) setPerformance(data);
      })
      .catch(() => {
        if (!cancelled) setPerformanceError('performance_fetch_failed');
      })
      .finally(() => {
        if (!cancelled) setPerformanceLoading(false);
      });
    return () => { cancelled = true; };
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
              borderRadius: 'var(--radius-sm)',
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
            margin: 0,
            lineHeight: 1.7,
          }}>
            매일 장 마감 후 KOSPI/KOSDAQ 전 종목을 분석해 다음 날 주목할 만한 종목 후보를 정리합니다. 7가지 전략이 각자의 기준으로 신호를 포착해 추천순으로 정렬합니다. 정렬 기준은 목록 위에서 바꿀 수 있어요. 매수 추천이 아닌 관찰 명세서입니다. 최종 판단은 직접 하세요.
          </p>
        </div>

        {/* 최근 6개월 성과 */}
        <div style={{ marginBottom: '80px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: '20px', marginBottom: '24px' }}>
            <p style={{ ...ts('caption', 'var(--muted)'), letterSpacing: '0.1em', margin: 0 }}>
              PERFORMANCE / LAST 6 MONTHS
            </p>
            <span style={ts('caption-sm', 'var(--muted-soft)')}>실제 signal 결과</span>
          </div>
          <StrategyPerformanceChart
            data={performance}
            loading={performanceLoading}
            error={performanceError}
          />
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
              <div key={s.num} style={{ background: 'var(--canvas)', padding: '40px 32px', borderTop: `3px solid ${s.accent}` }}>
                <div style={{
                  fontFamily: 'var(--f-mono-stack)',
                  fontSize: '11px',
                  color: s.accent,
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
                <div style={{ ...ts('caption', 'var(--warning)'), marginBottom: '4px' }}>
                  {s.focus}
                </div>
                <div style={{ ...ts('caption-sm', 'var(--muted-soft)'), marginBottom: '16px' }}>
                  {s.tf}
                </div>
                <div style={{ ...ts('body-md', 'var(--body)'), lineHeight: 1.6, marginBottom: '16px' }}>
                  {s.principle}
                </div>
                <div style={{ ...ts('caption-sm', 'var(--muted)'), letterSpacing: '0.08em', marginBottom: '4px' }}>
                  진입 조건
                </div>
                <div style={{ ...ts('caption', 'var(--body)'), lineHeight: 1.55, marginBottom: '16px' }}>
                  {s.entry}
                </div>
                <div style={{ ...ts('caption-sm', 'var(--muted)'), letterSpacing: '0.08em', marginBottom: '4px' }}>
                  주의
                </div>
                <div style={{ ...ts('caption', 'var(--body)'), lineHeight: 1.55 }}>
                  {s.caution}
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
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: '14px 32px',
          }}>
            {TERMS.map(t => (
              <div key={t.term} style={{ display: 'flex', gap: '12px' }}>
                <span style={{
                  fontFamily: 'var(--f-mono-stack)',
                  fontSize: '11px',
                  color: 'var(--warning)',
                  letterSpacing: '0.08em',
                  minWidth: '80px',
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
