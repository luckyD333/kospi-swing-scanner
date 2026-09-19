import type { Signal, DecisionFactor, RegretFactor, SignalStatus, SignalFreshness } from '@/types/signal';
import { formatStrategyLabel } from '@/lib/strategy';

export type SignalComponentStatus = 'ok' | 'warn' | 'miss';

export interface SignalComponent {
  key: string;
  label: string;
  status: SignalComponentStatus;
  value: string | null;
}

export function normalizeSignalComponents(raw: unknown): SignalComponent[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((c): c is Record<string, unknown> =>
      c != null && typeof c === 'object' && typeof (c as Record<string, unknown>).key === 'string',
    )
    .map((c) => ({
      key: String(c.key),
      label: typeof c.label === 'string' ? c.label : String(c.key),
      status: (c.status === 'ok' || c.status === 'warn' || c.status === 'miss')
        ? c.status
        : 'ok',
      value: typeof c.value === 'string' ? c.value : null,
    }));
}

export interface MatchProps {
  strategy: {
    id: string;
    label: string;
    timeframe: string;
  };
  signalStrength: number | null;
  opportunityScore: number | null;
  opportunityFactors: RegretFactor[] | null;
  signalComponents: SignalComponent[];
  signalStatus: SignalStatus;  // VALID | TARGET_REACHED | STOPPED_OUT | STALE
  signalFreshness?: SignalFreshness;
}

export interface DetailProps {
  ticker: string;
  name: string;
  nameEn: string | null;
  priceDisplay: string;
  changeDisplay: string;
  direction: 'up' | 'down' | 'flat';
  per: number | null;
  high52w: number | null;
  low52w: number | null;
  foreignRatioPct: number | null;
  volumeDisplay: string;
  marketCapDisplay: string | null;
  currentPrice: number | null;
  changePct: number | null;
  naverUrl: string | null;
  generatedAtDisplay: string;
  signalDate: string | null;
  potentialScore: number | null;
  potentialFactors: DecisionFactor[] | null;
  // 기회 점수 — matches[0] (top 매칭) 대표값. 잠재력과 동급의 ticker 단위 노출용.
  opportunityScore: number | null;
  opportunityFactors: RegretFactor[] | null;
  topTradePlan: {
    entry: number;
    stop: number;
    target1: number | null;
    target2: number | null;
    rrRatio: number | null;
    rrBand: string | null;
    orderTypeLabel: string | null;   // 역지정가 / 지정가 / 시장가 / 상한 지정가
    maxChase: number | null;         // 감사 F6: 갭상승 추격 상한
  } | null;
  matches: MatchProps[];
  rsi1d: number | null;
  rsi1w: number | null;
  rsi1h: number | null;
  atr14: number | null;
  confirmationLevel: string | null;
  activeRegime: string | null;
  tradabilityScore: number | null;
  // Phase 3 (2026-05-19) — regime-aware ensemble wiring 노출
  ensembleScore: number | null;
  regimeLabel: string | null;
  // 2026-05-20 상황별 holding 추천
  recommendedHoldingBars: number | null;
  holdingConfidence: number | null;
  holdingStatus: string | null;
}

export interface CardProps {
  ticker: string;
  name: string;
  priceDisplay: string;
  changeDisplay: string;
  direction: 'up' | 'down' | 'flat';
  entry: number;                 // UI 주 진입가 (EOD 종가)
  stop: number;                  // UI 주 손절가
  target1: number | null;
  reward1Pct: number | null;
  currentPrice: number | null;
  signalComponents: SignalComponent[];
  strategyId: string;
  strategyLabel: string;
  timeframe: string;
  rsi: number | null;
  generatedAtDisplay: string;
  signalDate: string | null;
  decisionScore: number | null;
  signalStrength: number | null;          // c.score / 10 (0~100)
  decisionRegretScore: number | null;     // 기회 점수 (0~100, 높을수록 매수 우선순위)
  rank: number | null;
  allStrategyTags?: Array<{ label: string; timeframe: string }>;
  signalStatus: SignalStatus;    // VALID | TARGET_REACHED | STOPPED_OUT | STALE
  orderTypeLabel: string | null;
  maxChase: number | null;       // 감사 F6: 갭상승 추격 상한 (IMMEDIATE 한정)
  // PR-B (P0-2): 상품 유형 + 풀
  productType: string | null;
  pool: string | null;
  // PR-K (P3-1): 거래 용이성 점수
  // PR-H/PR-J: confirmation 등급 + 시장 국면
  confirmationLevel: string | null;
  perTickerRegime: string | null;
  atrBucket: string | null;
  signalFreshness?: SignalFreshness;
  // Phase 3 (2026-05-19) — regime-aware ensemble wiring 노출
  recommendedHoldingBars: number | null;
  holdingConfidence: number | null;
  holdingStatus: string | null;
}

// Factor 라벨 매핑
export function getFactorLabel(key: string): string {
  const labelMap: Record<string, string> = {
    // 잠재력 점수 factor
    'momentum_3m': '가격 모멘텀 (3개월)',
    'regime_score': '시장 국면',
    'roe': 'ROE (수익성)',
    'per': 'PER (저평가)',
    'liquidity': '유동성',
    // 기회 점수 factor
    'bull_reward': '목표 수익',
    'max_drawdown': '손절 위험 (역)',
    'dist_to_stop': '손절까지 여유',
    'signal_freshness': '신호 신선도',
    // 기존 deprecated key (호환성)
    'momentum_pct': '가격 모멘텀',
    'rr_ratio': '손익비',
    'ensemble_score': '다전략 합의도',
    'ensemble': '다전략 합의도',
    'breakout_strength': '돌파 강도',
    'trend_consistency': '추세 일관성',
  };
  return labelMap[key] || key;
}

export function adaptDetailV2(raw: any): DetailProps {
  const ticker = raw.ticker || '';
  const name = raw.name || ticker;
  const nameEn = raw.name_en || null;

  const lq = raw.live_quote;
  const d = lq?._display;
  const cp = lq?.current_price ?? null;
  const ch = lq?.change_pct ?? null;

  const rawPrice = d?.current_price
    ?? (cp != null ? cp.toLocaleString('ko-KR') : '—');
  const priceDisplay = rawPrice.replace(/^₩\s*/, '');
  const changeDisplay = d?.change
    ?? (ch != null ? `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%` : '—');
  const direction = d?.direction ?? 'flat';

  // matches 배열 처리
  const matches: MatchProps[] = (raw.matches || []).map((m: any) => ({
    strategy: {
      id: m.strategy?.id || '',
      // 카탈로그 카드와 동일한 "전략 N" 표기로 통일
      label: formatStrategyLabel(m.strategy?.id || '', m.strategy?.label || 'Unknown'),
      timeframe: m.strategy?.timeframe || '',
    },
    signalStrength: m.signal_strength ?? null,
    opportunityScore: m.opportunity_score ?? null,
    opportunityFactors: m.opportunity_factors
      ? (m.opportunity_factors as any[]).map((f: any) => ({
          ...f,
          label: getFactorLabel(f.key),
        }))
      : null,
    signalComponents: normalizeSignalComponents(m.signal_components),
    signalStatus: (m.signal_status ?? 'VALID') as SignalStatus,
    signalFreshness: m.signal_freshness ?? undefined,
  }));

  const firstMatch = raw.matches?.[0];

  const potentialFactors = (raw.potential_factors || []).map((f: any) => ({
    ...f,
    label: getFactorLabel(f.key),
  }));

  // 기회 점수: matches[0] (top 매칭) 대표값을 ticker 단위로 끌어올림.
  // matches[0].opportunityFactors 와 동일한 reference 를 공유하므로 매칭별 매핑과 일관.
  const topOpportunityScore: number | null = matches[0]?.opportunityScore ?? null;
  const topOpportunityFactors: RegretFactor[] | null = matches[0]?.opportunityFactors ?? null;

  return {
    ticker,
    name,
    nameEn,
    priceDisplay,
    changeDisplay,
    direction,
    per: raw.fundamentals?.per ?? null,
    high52w: raw.fundamentals?.high_52w ?? null,
    low52w: raw.fundamentals?.low_52w ?? null,
    foreignRatioPct: raw.flow?.foreign_ratio_pct ?? null,
    volumeDisplay:
      d?.volume ??
      (lq?.volume != null ? lq.volume.toLocaleString('ko-KR') : '—'),
    marketCapDisplay: d?.market_cap ?? null,
    currentPrice: cp,
    changePct: ch,
    naverUrl: raw.external_links?.naver_finance ?? null,
    generatedAtDisplay: raw.generated_at_display || '',
    signalDate: raw.signal_date ?? null,
    potentialScore: raw.potential_score ?? null,
    potentialFactors,
    opportunityScore: topOpportunityScore,
    opportunityFactors: topOpportunityFactors,
    topTradePlan: firstMatch?.trade_plan
      ? {
          entry: firstMatch.trade_plan.entry ?? 0,
          stop: firstMatch.trade_plan.stop ?? 0,
          target1: firstMatch.trade_plan.target_1 ?? null,
          target2: firstMatch.trade_plan.target_2 ?? null,
          rrRatio: firstMatch.trade_plan.rr_ratio ?? null,
          rrBand: firstMatch.trade_plan.rr_band ?? null,
          orderTypeLabel: firstMatch.trade_plan.order_type_label_ko ?? null,
          maxChase: firstMatch.trade_plan.max_chase ?? null,
        }
      : null,
    matches,
    rsi1d: firstMatch?.trade_plan?.rsi_1d ?? null,
    rsi1w: firstMatch?.trade_plan?.rsi_1w ?? null,
    rsi1h: firstMatch?.trade_plan?.rsi_1h ?? null,
    atr14: firstMatch?.trade_plan?.atr_14 ?? null,
    confirmationLevel: raw.confirmation_level ?? null,
    activeRegime: raw.active_regime ?? null,
    tradabilityScore: raw.tradability_score ?? null,
    ensembleScore: raw.ensemble_score ?? null,
    regimeLabel: raw.regime_label ?? null,
    recommendedHoldingBars: raw.recommended_holding_bars ?? null,
    holdingConfidence: raw.holding_confidence ?? null,
    holdingStatus: raw.holding_status ?? null,
  };
}

export function adaptSignal(signal: Signal, generatedAtDisplay: string): CardProps {
  const lq = signal.live_quote;
  const d = lq?._display;
  const cp = lq?.current_price ?? null;
  const ch = lq?.change_pct ?? null;

  // ₩ 기호 제거 (백엔드 캐시 데이터 호환)
  const rawPrice = d?.current_price
    ?? (cp != null ? cp.toLocaleString('ko-KR') : '—');
  const priceDisplay = rawPrice.replace(/^₩\s*/, '');
  const changeDisplay = d?.change
    ?? (ch != null ? `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%` : '—');
  const direction = d?.direction ?? 'flat';

  const tp = signal.trade_plan;
  const der = tp.derived;
  const displayEntry = tp.entry;
  const displayStop = tp.stop;
  const displayReward1Pct = der?.reward_1_pct ?? null;

  return {
    ticker: signal.ticker,
    name: signal.name ?? signal.ticker,
    priceDisplay,
    changeDisplay,
    direction,
    entry: displayEntry,
    stop: displayStop,
    target1: tp.target_1,
    reward1Pct: displayReward1Pct,
    currentPrice: lq?.current_price ?? null,
    signalComponents: normalizeSignalComponents(signal.signal_components),
    rsi: tp.rsi_14 ?? null,
    strategyId: signal.strategy.id,
    strategyLabel: formatStrategyLabel(signal.strategy.id, signal.strategy.label),
    timeframe: signal.strategy.timeframe ?? '',
    generatedAtDisplay,
    signalDate: signal.signal_date ?? null,
    decisionScore: signal.ranking?.decision?.final_score ?? null,
    // 신규 매핑 — backend 신규 필드 우선, 구버전 fallback
    signalStrength:
      signal.ranking?.signal_strength
      ?? signal.ranking?.score
      ?? null,
    decisionRegretScore:
      signal.ranking?.decision?.regret_score
      ?? signal.ranking?.decision?.max_regret
      ?? null,
    rank: signal.ranking?.rank ?? null,
    signalStatus: signal.signal_status ?? 'VALID',
    orderTypeLabel: tp.order_type_label_ko ?? null,
    maxChase: tp.max_chase ?? null,
    productType: signal.product_type ?? null,
    pool: signal.pool ?? null,
    confirmationLevel: signal.confirmation_level ?? null,
    perTickerRegime: signal.per_ticker_regime ?? null,
    atrBucket: signal.atr_bucket ?? null,
    signalFreshness: signal.signal_freshness ?? undefined,
    recommendedHoldingBars: signal.ranking?.decision?.recommended_holding_bars ?? null,
    holdingConfidence: signal.ranking?.decision?.holding_confidence ?? null,
    holdingStatus: signal.ranking?.decision?.holding_status ?? null,
  };
}
