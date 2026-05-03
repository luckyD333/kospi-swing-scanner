# Signal UI 시인성 개선 + 구조 정합화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** signal-web 카드 시인성을 design.md 정합 방향(모노크롬 luminance 위계)으로 개선하고, signal-api/web 양쪽의 NPE 위험·운영 가드·디자인 위반을 동시에 정리한다.

**Architecture:** 디자인 토큰(typography/color)을 CSS variable + 얇은 헬퍼 모듈로 추출해 inline style 반복을 제거하고, Pydantic optional 모델을 반영하도록 TS 타입을 좁힌 뒤 어댑터·카드에 null 가드를 채운다. 색상은 design.md `Text` 토큰만으로 luminance 계층을 만들고 의미 색은 데이터 품질 경고 1곳에만 사용.

**Tech Stack:** Next.js 15.3 (App Router) · React 19 · FastAPI 0.111+ · Pydantic 2.7 · pytest-asyncio · TypeScript 5.

---

## Purpose

카드 안 12개 숫자가 모두 `--body`/`--body-strong`로 평탄해서 정보 위계가 사라졌고, detail 페이지는 entry/stop/target에 link/loss/gain 4색을 입혀 design.md `Don't tint stop-loss values red or target values green` 룰을 직접 위반하고 있다. 동시에 `adapt.ts`/`types/signal.ts`가 Pydantic optional 모델을 반영하지 않아 `live_quote`나 `current_price`가 null인 시그널이 들어오면 페이지가 즉시 throw → error.tsx로 떨어진다. UI 시인성 개선 요구가 표면 증상이고, 그 아래에 타입 정합/디자인 위반/타이포 토큰 부재가 함께 있어 한 번에 정리한다.

## Context

- design.md `colors`: text 토큰 5단(`ink`/`body-strong`/`body`/`muted`/`muted-soft`)이 이미 정의되어 있음. 시인성 위계는 새 색을 추가하지 않고 이 5단을 카드에 깔기만 하면 만들어진다.
- design.md `Known Gaps`: data-quality warning 자리(`breakout_pct < 0.5%`, `current_price null`)가 미확정으로 남아 있음 — 좌측 4px 막대로 채울 자리.
- PLAN.md `signal-api/PLAN.md`: `lib/typography.ts` 도입은 PR #3 항목으로 이미 적혀있으나 미구현. `signal-web`은 inline style 도배로 진행됐다.
- Pydantic 모델(`signal-api/app/models/signal.py`)은 `LiveQuote.current_price: float | None`, `Signal.name: str | None`, `target_1/2: float | None`, `derived: TradePlanDerived | None` 등 다수 optional. `signal-web/src/types/signal.ts`는 모두 non-null로 선언되어 갭이 큼.
- `signal-api`는 atomic write + ETag/304 + 503/Retry-After까지 운영 가드를 갖췄지만 CORS origin 하드코딩, `/api/market`은 캐시 헤더 부재.

## Architecture Overview

### 1. 디자인 토큰 추출 — `signal-web/src/lib/typography.ts`, `tokens.css`
- design.md typography 18종 중 실사용 12종을 CSS custom property로 정의(`--ts-display-md`, `--ts-numeric-lg`, `--ts-caption-uppercase` 등). fontFamily/size/weight/lineHeight/letterSpacing/textTransform 묶음.
- 각 토큰은 `globals.css` 단일 파일에서 정의, 컴포넌트는 `style={{ font: 'var(--ts-numeric-lg)', ... }}` 또는 `className` 매핑.
- `lib/typography.ts`는 토큰 이름 → React.CSSProperties 매핑 헬퍼만 export(타입 안전 + IDE 자동완성). 신규 의존성 0.

### 2. TS ↔ Pydantic 타입 정합 — `types/signal.ts`, `lib/adapt.ts`
- `types/signal.ts`를 Pydantic 모델과 1:1 동기화: optional 필드는 `| null`, `Signal.name`까지 nullable.
- `adapt.ts`는 단일 `CardProps` non-null 표면을 유지하되 모든 입력 필드에 옵셔널 체이닝 + `??` fallback 적용. 누락치 표시값은 `'—'` 통일.
- `volume`/`current_price` null fallback: 표시 문자열은 `'—'`, 숫자 영역은 `null` 유지하고 카드/디테일에서 `null` 분기.

### 3. 카드 시인성 — `TickerCard.tsx` luminance 위계 (Tier 1)
- 종목명 `--ink`, 현재가 `--ink` (둘만 100% 화이트로 시선 앵커 2개), 매매파라미터 `--body-strong`, 보조지표(SCR/ATR) `--body`, 참고지표(RSI/PER) `--muted`, 라벨 전체 `--muted-soft`.
- 등락(change_pct)은 `--body-strong` + `▲ ▼ ─` 글리프(`▲` up, `▼` down, `─` flat), 색 제거. design.md "gain/loss는 realized P&L only" 엄격 적용.
- RR band 텍스트("SWEET"/"UNDER"/"OVER") 자체는 `--muted` 모노 톤 유지(현 코드의 색 분기 제거). 가이드: *"never colored, never highlighted"*.

### 4. 데이터 품질 플래그 — `TickerCard` 좌측 4px 막대 (Tier 3)
- `card.dataQuality: 'ok' | 'warn'` 필드 신설. `adapt.ts`에서 `current_price == null` 또는 `atr/entry < 0.005` 또는 `breakout_pct < 0.005`(있을 때) → `'warn'`.
- 카드 좌측 `border-left: 4px solid transparent`(ok) / `var(--warning)`(warn). design.md `Known Gaps` 직접 해소.

### 5. DetailClient 디자인 위반 롤백 — `DetailClient.tsx:172-175`
- entry/stop/target/target2 4종 색을 모두 `var(--ink)` 단색으로 통일. label/sub만 `--muted`/`--muted-soft`. RR band 셀의 `rrColor` 분기도 제거.

### 6. signal-api 운영 가드 — CORS env + market 헤더 + 캐시 정밀화
- `main.py`: `SIGNAL_API_CORS_ORIGINS` env(콤마 구분) 미설정 시 `http://localhost:3000` fallback.
- `market.py`: `MarketLoader` 신설(SignalLoader와 같은 mtime+size 캐시), ETag/Last-Modified 응답.
- `signal_loader.py`: 캐시 키를 `(mtime, size)` 페어로 변경. `LoadedSignals.by_ticker` 필드 추가, 단일 ticker 조회 O(1).

### 7. Korean font — `layout.tsx`
- `next/font/google`에서 `Pretendard`(display fallback), `Noto Serif KR`(body fallback) variable 추가. `--f-display`/`--f-body` 변수 값에 fallback chain으로 연결. CSS `font-family: var(--f-display), var(--f-display-ko), sans-serif` 형태.

## Progress

- [ ] PR #1 — TS 타입 정합 + adapt null 가드
- [ ] PR #2 — DetailClient 디자인 위반 롤백
- [ ] PR #3 — typography/color 토큰 추출
- [ ] PR #4 — TickerCard luminance 위계 + change 글리프 + warning 막대
- [ ] PR #5 — Korean font fallback
- [ ] PR #6 — signal-api CORS env + market 캐시 + signal_loader 정밀화

---

## Plan of Work

### PR #1 — TS 타입 정합 + adapt null 가드 (HIGH)

**Files:**
- Modify: `signal-web/src/types/signal.ts`
- Modify: `signal-web/src/lib/adapt.ts`
- Modify: `signal-web/src/components/TickerCard.tsx`
- Test: `signal-web/src/lib/__tests__/adapt.test.ts` (신규)

#### Task 1.1: 타입 정합 — `types/signal.ts`

- [ ] **Step 1: Pydantic 모델과 nullable 필드 동기화**

```typescript
// types/signal.ts 변경 요지
export interface LiveQuote {
  current_price: number | null;
  change_pct: number | null;
  volume: number | null;
  market_cap_krw: number | null;
  _display?: SignalDisplay;
}

export interface TradePlan {
  entry: number;
  stop: number;
  target_1: number | null;
  target_2: number | null;
  rr_ratio: number | null;
  rr_band: string | null;
  atr_14: number | null;
  derived: TradePlanDerived | null;
}

export interface Ranking {
  score: number | null;
  rank: number | null;
  percentile: number | null;
}

export interface Signal {
  ticker: string;
  name: string | null;
  name_en: string | null;
  strategy: StrategyInfo;
  trade_plan: TradePlan;
  ranking: Ranking | null;
  live_quote: LiveQuote | null;
  fundamentals: Fundamentals | null;
  flow: Flow | null;
  external_links: ExternalLinks | null;
}
```

기준: `signal-api/app/models/signal.py`의 optional 마킹과 1:1.

- [ ] **Step 2: `tsc --noEmit` 실행 — 깨진 사용처 식별**

Run: `cd signal-web && npx tsc --noEmit`
Expected: `adapt.ts`, `TickerCard.tsx`, `DetailClient.tsx`에서 다수 에러. 이 목록이 다음 태스크 입력.

- [ ] **Step 3: Commit**

```bash
git add signal-web/src/types/signal.ts
git commit -m "fix(types): Pydantic optional 필드를 TS 타입에 반영"
```

#### Task 1.2: adapt 옵셔널 체이닝

- [ ] **Step 1: 실패 테스트 작성 — `lib/__tests__/adapt.test.ts`**

```typescript
import { adaptSignal } from '@/lib/adapt';
import type { Signal } from '@/types/signal';

const minimal: Signal = {
  ticker: '000000',
  name: null,
  name_en: null,
  strategy: { id: 's', label: 'S', category: 'X', timeframe: '1D', description: null },
  trade_plan: {
    entry: 1000, stop: 950, target_1: null, target_2: null,
    rr_ratio: null, rr_band: null, atr_14: null, derived: null,
  },
  ranking: null,
  live_quote: null,
  fundamentals: null,
  flow: null,
  external_links: null,
};

test('adaptSignal: live_quote null이어도 throw 안 함', () => {
  const c = adaptSignal(minimal, '2026-05-03');
  expect(c.priceDisplay).toBe('—');
  expect(c.changeDisplay).toBe('—');
  expect(c.direction).toBe('flat');
  expect(c.target1).toBeNull();
  expect(c.score).toBeNull();
  expect(c.rrRatio).toBeNull();
  expect(c.naverUrl).toBeNull();
});

test('adaptSignal: dataQuality flag', () => {
  const flagged = { ...minimal, live_quote: { current_price: null, change_pct: null, volume: null, market_cap_krw: null } };
  const c = adaptSignal(flagged, '2026-05-03');
  expect(c.dataQuality).toBe('warn');
});
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd signal-web && npx vitest run src/lib/__tests__/adapt.test.ts`
Expected: 두 테스트 모두 throw 또는 assertion FAIL.

> 비고: 프로젝트에 vitest가 없으면 PR #1 시작 시 `npm i -D vitest @vitest/ui`로 설치하고 `package.json`에 `"test": "vitest"` 추가. (executor 결정사항 — 실행 가능 여부만 확인. 만약 jest 선호면 동일 테스트를 jest로 옮겨도 무방.)

- [ ] **Step 3: `adapt.ts` 옵셔널 + fallback 구현**

```typescript
// lib/adapt.ts 핵심 변경
export interface CardProps {
  ticker: string;
  name: string;
  nameEn: string | null;
  priceDisplay: string;          // null → '—'
  changeDisplay: string;         // null → '—'
  direction: 'up' | 'down' | 'flat';
  entry: number;
  stop: number;
  target1: number | null;
  target2: number | null;
  rrRatio: number | null;
  rrBand: string | null;
  atr: number | null;
  score: number | null;
  per: number | null;
  high52w: number | null;
  low52w: number | null;
  foreignRatioPct: number | null;
  volumeDisplay: string;         // null → '—'
  marketCapDisplay: string | null;
  riskPerShare: number | null;
  riskPct: number | null;
  reward1Pct: number | null;
  reward2Pct: number | null;
  strategyLabel: string;
  strategyCategory: string;
  timeframe: string;
  naverUrl: string | null;
  generatedAtDisplay: string;
  dataQuality: 'ok' | 'warn';
}

export function adaptSignal(signal: Signal, generatedAtDisplay: string): CardProps {
  const lq = signal.live_quote;
  const d = lq?._display;
  const cp = lq?.current_price ?? null;
  const ch = lq?.change_pct ?? null;

  const priceDisplay = d?.current_price
    ?? (cp != null ? `₩${cp.toLocaleString('ko-KR')}` : '—');
  const changeDisplay = d?.change
    ?? (ch != null ? `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%` : '—');
  const direction = d?.direction ?? 'flat';

  const tp = signal.trade_plan;
  const der = tp.derived;
  const atrEntryRatio = tp.atr_14 != null && tp.entry > 0 ? tp.atr_14 / tp.entry : null;
  const dataQuality: 'ok' | 'warn' =
    cp == null || (atrEntryRatio != null && atrEntryRatio < 0.005)
      ? 'warn' : 'ok';

  return {
    ticker: signal.ticker,
    name: signal.name ?? signal.ticker,
    nameEn: signal.name_en,
    priceDisplay,
    changeDisplay,
    direction,
    entry: tp.entry,
    stop: tp.stop,
    target1: tp.target_1,
    target2: tp.target_2,
    rrRatio: tp.rr_ratio,
    rrBand: tp.rr_band,
    atr: tp.atr_14,
    score: signal.ranking?.score ?? null,
    per: signal.fundamentals?.per ?? null,
    high52w: signal.fundamentals?.high_52w ?? null,
    low52w: signal.fundamentals?.low_52w ?? null,
    foreignRatioPct: signal.flow?.foreign_ratio_pct ?? null,
    volumeDisplay: d?.volume
      ?? (lq?.volume != null ? lq.volume.toLocaleString('ko-KR') : '—'),
    marketCapDisplay: d?.market_cap ?? null,
    riskPerShare: der?.risk_per_share ?? null,
    riskPct: der?.risk_pct ?? null,
    reward1Pct: der?.reward_1_pct ?? null,
    reward2Pct: der?.reward_2_pct ?? null,
    strategyLabel: signal.strategy.label,
    strategyCategory: signal.strategy.category,
    timeframe: signal.strategy.timeframe,
    naverUrl: signal.external_links?.naver_finance ?? null,
    generatedAtDisplay,
    dataQuality,
  };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd signal-web && npx vitest run src/lib/__tests__/adapt.test.ts`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add signal-web/src/lib/adapt.ts signal-web/src/lib/__tests__/adapt.test.ts signal-web/package.json signal-web/package-lock.json
git commit -m "fix(adapt): live_quote/optional 필드 null 가드 + dataQuality flag"
```

#### Task 1.3: TickerCard null 가드

- [ ] **Step 1: TickerCard.tsx 수정 — null fallback 처리**

```typescript
// TickerCard.tsx 핵심 변경 (전체 교체 아닌 부분 수정)
const fmtNum = (v: number | null): string =>
  v == null ? '—' : v.toLocaleString('ko-KR');
const fmtRR = (v: number | null): string => v == null ? '—' : v.toFixed(1);
const fmtScore = (v: number | null): string => v == null ? '—' : String(Math.round(v));
const fmtAtr = (v: number | null): string =>
  v == null ? '—' : `₩${v.toLocaleString('ko-KR')}`;
const fmtPer = (v: number | null): string => v == null ? '—' : `${v}x`;

// 기존 metrics 배열 교체
const metrics = [
  { label: 'RR',  value: fmtRR(rrRatio),     color: 'var(--body)' },  // 색은 PR #4에서 위계로
  { label: 'SCR', value: fmtScore(score),    color: 'var(--body)' },
  { label: 'ATR', value: fmtAtr(atr),        color: 'var(--body)' },
  { label: 'RSI', value: '—',                color: 'var(--muted)' },
  { label: 'PER', value: fmtPer(per),        color: 'var(--muted)' },
];

// 진입/손절/목표 행
{([['진입', entry], ['손절', stop], ['목표', target1]] as [string, number | null][]).map(([label, val], i) => (
  <div key={label} style={{...}}>
    <div style={{...}}>{label}</div>
    <div style={{ fontFamily: 'var(--f-mono)', fontSize: '15px', color: 'var(--body)' }}>
      {fmtNum(val)}
    </div>
  </div>
))}
```

- [ ] **Step 2: `tsc --noEmit` 통과 확인**

Run: `cd signal-web && npx tsc --noEmit`
Expected: 0 errors.

- [ ] **Step 3: 빌드 통과 확인**

Run: `cd signal-web && npm run build`
Expected: success.

- [ ] **Step 4: Commit**

```bash
git add signal-web/src/components/TickerCard.tsx
git commit -m "fix(card): target/score/atr/per null 가드"
```

---

### PR #2 — DetailClient 디자인 위반 롤백 (HIGH)

**Files:**
- Modify: `signal-web/src/components/DetailClient.tsx:71, 172-175, 217-220, 235`

#### Task 2.1: spec-cell 색 4종 → ink 단색

- [ ] **Step 1: 색 분기 제거**

```typescript
// DetailClient.tsx
// (1) line 71: rrColor 변수 삭제
// const rrColor = rrBand === 'SWEET' ? 'var(--gain)' : ...   ← 제거

// (2) line 172-175: spec 셀 color 키 제거
{[
  { label: '진입가', val: entry, sub: '지정가' },
  { label: '손절가', val: stop,  sub: `리스크 ₩${...}` },
  { label: '목표 1', val: target1, sub: target1 ? `+${reward1Pct?.toFixed(1)}%` : '' },
  { label: '목표 2', val: target2, sub: target2 ? `+${reward2Pct?.toFixed(1)}%` : '' },
].map(({ label, val, sub }, i) => (
  // PriceScramble 내부에서 이미 var(--ink) 사용 → 추가 색 주입 X
))}

// (3) line 217-220: RR/등급 셀 color 제거
{[
  { label: 'RR 비율', value: rrRatio != null ? rrRatio.toFixed(2) : '—' },
  { label: 'RR 등급', value: rrBand ?? '—' },
  { label: '점수', value: score != null ? String(Math.round(score)) : '—' },
  { label: 'ATR(14)', value: atr != null ? `₩${atr.toLocaleString('ko-KR')}` : '—', sub: '평균 변동폭' },
].map(({ label, value, sub }, i) => (
  // line 235 color 분기 → 'var(--ink)' 고정
  <div style={{ ..., color: 'var(--ink)' }}>{value}</div>
))}
```

- [ ] **Step 2: 비주얼 확인**

Run: `cd signal-web && npm run dev`, `http://localhost:3000/signal/006340` 방문.
Expected: 진입/손절/목표/RR/등급 모두 흰색 단색. label만 muted.

- [ ] **Step 3: Commit**

```bash
git add signal-web/src/components/DetailClient.tsx
git commit -m "fix(detail): spec 셀 색 분기 제거 (design.md '파라미터는 흰색')"
```

---

### PR #3 — typography/color 토큰 추출 (MED)

**Files:**
- Create: `signal-web/src/lib/typography.ts`
- Modify: `signal-web/src/app/globals.css`
- Modify: `signal-web/src/components/*.tsx` (헬퍼로 inline style 치환)

#### Task 3.1: 토큰 정의

- [ ] **Step 1: globals.css에 typography variable 추가**

```css
:root {
  /* design.md typography (실사용 12종) */
  --ts-display-md: 400 32px/1.2 var(--f-display, sans-serif);
  --ts-display-sm: 400 24px/1.3 var(--f-display, sans-serif);
  --ts-title-md:   400 20px/1.3 var(--f-display, sans-serif);
  --ts-ticker-sm:  400 32px/1   var(--f-mono, monospace);
  --ts-numeric-lg: 400 28px/1.1 var(--f-mono, monospace);
  --ts-numeric-md: 400 18px/1.2 var(--f-mono, monospace);
  --ts-caption:    400 11px/1.4 var(--f-mono, monospace);
  --ts-caption-sm: 400 10px/1.4 var(--f-mono, monospace);
  --ts-button:     400 14px/1   var(--f-mono, monospace);
  --ts-nav-link:   400 12px/1.4 var(--f-mono, monospace);
  --ts-wordmark:   400 14px/1   var(--f-display, sans-serif);
  --ts-body-md:    400 16px/1.5 var(--f-body, serif);
}

/* tracking helper classes — font shorthand로는 letter-spacing 안 들어감 */
.tk-2  { letter-spacing: 2px; text-transform: uppercase; }
.tk-25 { letter-spacing: 2.5px; text-transform: uppercase; }
.tk-6  { letter-spacing: 6px; text-transform: uppercase; }
.tk-1  { letter-spacing: 1px; }
```

- [ ] **Step 2: `lib/typography.ts` 헬퍼 작성**

```typescript
// signal-web/src/lib/typography.ts
import type { CSSProperties } from 'react';

export type TypoToken =
  | 'display-md' | 'display-sm' | 'title-md'
  | 'ticker-sm' | 'numeric-lg' | 'numeric-md'
  | 'caption' | 'caption-sm' | 'button' | 'nav-link'
  | 'wordmark' | 'body-md';

const TRACK: Record<TypoToken, string | undefined> = {
  'display-md': '2px', 'display-sm': '1.5px', 'title-md': '1px',
  'ticker-sm': '0px', 'numeric-lg': '0px', 'numeric-md': '0px',
  'caption': '2px', 'caption-sm': '2px',
  'button': '2.5px', 'nav-link': '2px',
  'wordmark': '6px', 'body-md': undefined,
};

const UPPER: Record<TypoToken, boolean> = {
  'display-md': true, 'display-sm': true, 'title-md': false,
  'ticker-sm': false, 'numeric-lg': false, 'numeric-md': false,
  'caption': true, 'caption-sm': true,
  'button': true, 'nav-link': true,
  'wordmark': true, 'body-md': false,
};

export function ts(token: TypoToken, color?: string): CSSProperties {
  return {
    font: `var(--ts-${token})`,
    letterSpacing: TRACK[token],
    textTransform: UPPER[token] ? 'uppercase' : 'none',
    color: color ?? 'var(--ink)',
  };
}
```

- [ ] **Step 3: Commit (토큰만, 사용처 미변경)**

```bash
git add signal-web/src/app/globals.css signal-web/src/lib/typography.ts
git commit -m "feat(tokens): design.md typography를 CSS variable + ts() 헬퍼로 추출"
```

#### Task 3.2: 점진적 치환 — TopNav부터

- [ ] **Step 1: TopNav.tsx의 inline style을 `ts()` 호출로 치환**

```typescript
// 예: market label
<span style={ts('caption-sm', 'var(--muted)')}>{item.label}</span>

// wordmark
<button style={{ ...ts('wordmark'), background: 'none', border: 'none', cursor: 'pointer' }}>
  SIGNAL
</button>
```

각 컴포넌트(TopNav → FilterBar → TickerCard → DetailClient → Footer → DisclaimerBar → error.tsx) 순서대로 치환.

- [ ] **Step 2: 빌드 + 시각 회귀 확인**

Run: `npm run build && npm run dev`
Expected: 모든 페이지 렌더링 동일.

- [ ] **Step 3: Commit (컴포넌트 단위 분할 가능)**

```bash
git add signal-web/src/components/
git commit -m "refactor(web): inline style → ts() 헬퍼로 통일"
```

---

### PR #4 — TickerCard luminance 위계 + change 글리프 + warning 막대 (MED, 색상 핵심)

**Files:**
- Modify: `signal-web/src/components/TickerCard.tsx`

#### Task 4.1: luminance 위계 적용

- [ ] **Step 1: 색 매핑 변경**

```typescript
// TickerCard.tsx — 색 결정 부
// 종목명: var(--ink) 유지
// ticker code: var(--muted) → var(--muted-soft)
// 현재가: var(--body-strong) → var(--ink)
// 등락: gain/loss 색 → var(--body-strong) + 글리프
const dirGlyph = direction === 'up' ? '▲' : direction === 'down' ? '▼' : '─';
const changeColor = 'var(--body-strong)';  // 색 제거

// 라벨(모든 caption): var(--muted) → var(--muted-soft)
// 진입/손절/목표 값: var(--body) → var(--body-strong)
// metrics 색: 1행 RR/SCR/ATR → var(--body), 2행 RSI/PER → var(--muted)
//   RR band 색 분기 제거 (rrColor 삭제) — 값은 var(--body), band 라벨은 var(--muted)
```

표시 형태:

```
{priceDisplay}  ▲ {changeDisplay}    ← 글리프 + 모노 텍스트
```

- [ ] **Step 2: 비주얼 확인 — 12개 카드 캡처**

Run: `npm run dev`, 카탈로그 페이지 접속.
Expected: 종목명·현재가만 흰색, 라벨은 거의 사라진 듯한 muted-soft, 데이터에 자연스러운 위계.

- [ ] **Step 3: Commit**

```bash
git add signal-web/src/components/TickerCard.tsx
git commit -m "feat(card): luminance 위계 + 등락 모노+글리프 (design.md 정합)"
```

#### Task 4.2: 데이터 품질 좌측 막대

- [ ] **Step 1: warning 막대 추가**

```typescript
// TickerCard.tsx 최외곽 div
<div
  style={{
    background: 'var(--canvas)',
    outline: hov ? '1px solid var(--hairline-strong)' : '1px solid transparent',
    outlineOffset: '-1px',
    borderLeft: card.dataQuality === 'warn'
      ? '4px solid var(--warning)'
      : '4px solid transparent',
    padding: '52px 32px 52px 28px',  // 좌측 4px 막대 보정
    ...
  }}
>
```

- [ ] **Step 2: 시각 확인 — fixture에 warn 케이스 강제 주입**

Run: `current_price: null` 시그널을 `data/signals.json`에 임시 추가해서 카드 좌측 황톳빛 막대 확인.

- [ ] **Step 3: Commit**

```bash
git add signal-web/src/components/TickerCard.tsx
git commit -m "feat(card): data-quality 좌측 4px 막대 (design.md known-gap 해소)"
```

---

### PR #5 — Korean font fallback (MED)

**Files:**
- Modify: `signal-web/src/app/layout.tsx`
- Modify: `signal-web/src/app/globals.css`

#### Task 5.1: Pretendard / Noto Serif KR variable 추가

- [ ] **Step 1: layout.tsx에 next/font 추가**

```typescript
import { Saira_Condensed, Cormorant_Garamond, JetBrains_Mono } from 'next/font/google';
// Pretendard, Noto Serif KR 추가
import { Noto_Serif_KR } from 'next/font/google';
// Pretendard는 next/font/google에 없음 → public/fonts에 woff2 + @font-face로 등록
// (next/font/local 사용)
import localFont from 'next/font/local';

const pretendard = localFont({
  src: '../../public/fonts/Pretendard-Regular.woff2',
  variable: '--f-display-ko',
  weight: '400',
  display: 'swap',
});

const notoSerifKr = Noto_Serif_KR({
  weight: '400',
  subsets: ['latin'],
  variable: '--f-body-ko',
  display: 'swap',
});

// html className에 두 variable 추가
```

- [ ] **Step 2: globals.css에서 fallback chain 변경**

```css
:root {
  --f-display-stack: var(--f-display), var(--f-display-ko), -apple-system, sans-serif;
  --f-body-stack:    var(--f-body), var(--f-body-ko), serif;
  --f-mono-stack:    var(--f-mono), ui-monospace, monospace;
}
/* 기존 --f-display 사용처를 --f-display-stack로 마이그레이션 */
```

- [ ] **Step 3: Pretendard woff2 다운로드 — `signal-web/public/fonts/Pretendard-Regular.woff2`**

Pretendard 라이선스: SIL OFL 1.1. `https://github.com/orioncactus/pretendard/releases` 최신 안정 버전에서 woff2 추출.

- [ ] **Step 4: 비주얼 확인 — 한글 종목명**

Run: `npm run dev`, 카탈로그에서 "대원전선" 등 한글 종목명이 Pretendard로 렌더되는지 dev tools 폰트 패널 확인.

- [ ] **Step 5: Commit**

```bash
git add signal-web/src/app/layout.tsx signal-web/src/app/globals.css signal-web/public/fonts/
git commit -m "feat(font): Pretendard / Noto Serif KR fallback 추가"
```

---

### PR #6 — signal-api 운영 가드 (MED+LOW)

**Files:**
- Modify: `signal-api/app/main.py`
- Create: `signal-api/app/services/market_loader.py`
- Modify: `signal-api/app/api/market.py`
- Modify: `signal-api/app/services/signal_loader.py`
- Modify: `signal-api/app/api/signals.py`
- Modify: `signal-api/tests/test_routes.py`
- Modify: `signal-api/tests/conftest.py`

#### Task 6.1: CORS env 추출

- [ ] **Step 1: 실패 테스트 추가 — `tests/test_cors.py`**

```python
import os
import pytest
from importlib import reload


@pytest.fixture
def app_with_origins(monkeypatch):
    monkeypatch.setenv("SIGNAL_API_CORS_ORIGINS", "https://signal.example.com,http://localhost:3000")
    import app.main
    reload(app.main)
    return app.main.app


async def test_cors_origins_from_env(app_with_origins):
    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app_with_origins)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.options("/api/health", headers={
            "Origin": "https://signal.example.com",
            "Access-Control-Request-Method": "GET",
        })
    assert r.headers.get("access-control-allow-origin") == "https://signal.example.com"
```

- [ ] **Step 2: 테스트 실행 — 실패**

Run: `cd signal-api && pytest tests/test_cors.py -v`
Expected: FAIL.

- [ ] **Step 3: main.py 수정**

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.signals import router as signals_router
from .api.market import router as market_router

app = FastAPI(title="Signal API", version="1.0.0")

_origins = os.getenv("SIGNAL_API_CORS_ORIGINS", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(signals_router, prefix="/api")
app.include_router(market_router, prefix="/api")
```

- [ ] **Step 4: 테스트 통과**

Run: `pytest tests/test_cors.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add signal-api/app/main.py signal-api/tests/test_cors.py
git commit -m "feat(api): CORS origins env 변수 추출"
```

#### Task 6.2: SignalLoader (mtime,size) + by_ticker 캐시

- [ ] **Step 1: 실패 테스트 — `tests/test_signal_loader.py`**

```python
import json
import time
from pathlib import Path
from app.services.signal_loader import SignalLoader


def _write(p: Path, payload: dict):
    p.write_text(json.dumps(payload), encoding="utf-8")


SAMPLE = {
    "schema_version": "1.0",
    "generated_at": "2026-05-03T18:16:11+09:00",
    "signals": [{"ticker": "000020", "strategy": {"id":"s","label":"S"}, "trade_plan":{"entry":1,"stop":1}}],
}


def test_loader_caches_by_ticker(tmp_path):
    p = tmp_path / "s.json"
    _write(p, SAMPLE)
    loader = SignalLoader(p)
    loaded = loader.load()
    assert loaded.by_ticker["000020"]["ticker"] == "000020"


def test_loader_invalidates_on_size_change_same_mtime(tmp_path):
    p = tmp_path / "s.json"
    _write(p, SAMPLE)
    loader = SignalLoader(p)
    first = loader.load()

    # 같은 mtime을 강제로 유지하면서 내용을 바꾼다
    bigger = {**SAMPLE, "extra": "x" * 1000}
    p.write_text(json.dumps(bigger), encoding="utf-8")
    import os
    os.utime(p, (first.mtime, first.mtime))  # mtime 동일

    second = loader.load()
    assert second is not first  # size 변경으로 캐시 invalidate
```

- [ ] **Step 2: 테스트 실행 — 실패**

Run: `pytest tests/test_signal_loader.py -v`
Expected: FAIL.

- [ ] **Step 3: signal_loader.py 수정**

```python
@dataclass
class LoadedSignals:
    raw: dict[str, Any]
    etag: str
    mtime: float
    size: int
    by_ticker: dict[str, dict[str, Any]]


class SignalLoader:
    def __init__(self, path: Path):
        self._path = path
        self._cache: LoadedSignals | None = None
        self._lock = threading.Lock()

    def load(self) -> LoadedSignals:
        with self._lock:
            if not self._path.exists():
                raise FileNotFoundError(self._path)

            stat = self._path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            if self._cache and self._cache.mtime == mtime and self._cache.size == size:
                return self._cache

            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise ValueError("malformed") from e

            try:
                SignalsResponse.model_validate(raw)
            except ValidationError as e:
                raise ValueError("schema_invalid") from e

            by_ticker = {s["ticker"]: s for s in raw.get("signals", [])}
            self._cache = LoadedSignals(
                raw=raw, etag=f'"{mtime}-{size}"',
                mtime=mtime, size=size, by_ticker=by_ticker,
            )
            return self._cache
```

- [ ] **Step 4: signals.py 단일 ticker 조회를 by_ticker 사용**

```python
@router.get("/signals/{ticker}")
async def get_signal(ticker: str, request: Request):
    loaded = _load_or_raise()
    if request.headers.get("if-none-match") == loaded.etag:
        return Response(status_code=304)
    signal = loaded.by_ticker.get(ticker)
    if signal is None:
        raise HTTPException(404, detail={"error": "ticker_not_found", "ticker": ticker})
    return JSONResponse(content=signal, headers={"ETag": loaded.etag, "Cache-Control": "no-cache"})
```

- [ ] **Step 5: 전체 테스트 통과**

Run: `cd signal-api && pytest -q`
Expected: 기존 + 신규 PASS.

- [ ] **Step 6: Commit**

```bash
git add signal-api/app/services/signal_loader.py signal-api/app/api/signals.py signal-api/tests/test_signal_loader.py
git commit -m "perf(loader): (mtime,size) 캐시 키 + by_ticker O(1) 조회"
```

#### Task 6.3: MarketLoader + ETag

- [ ] **Step 1: `services/market_loader.py` 신설**

```python
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LoadedMarket:
    indices: dict[str, Any]
    etag: str
    mtime: float
    size: int


class MarketLoader:
    def __init__(self, path: Path):
        self._path = path
        self._cache: LoadedMarket | None = None
        self._lock = threading.Lock()

    def load(self) -> LoadedMarket | None:
        with self._lock:
            if not self._path.exists():
                self._cache = None
                return None
            stat = self._path.stat()
            mtime, size = stat.st_mtime, stat.st_size
            if self._cache and self._cache.mtime == mtime and self._cache.size == size:
                return self._cache
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
            indices = data.get("market_indices", {})
            self._cache = LoadedMarket(
                indices=indices, etag=f'"{mtime}-{size}"', mtime=mtime, size=size,
            )
            return self._cache
```

- [ ] **Step 2: market.py 수정**

```python
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from ..services.market_loader import MarketLoader

router = APIRouter()
_MARKET_PATH = Path(os.getenv("SIGNAL_API_DATA_DIR", "data")) / "market_snapshot.json"
_loader = MarketLoader(_MARKET_PATH)


@router.get("/market")
async def get_market(request: Request):
    loaded = _loader.load()
    if loaded is None:
        return {"market_indices": {}}
    if request.headers.get("if-none-match") == loaded.etag:
        return Response(status_code=304)
    return JSONResponse(
        content={"market_indices": loaded.indices},
        headers={"ETag": loaded.etag, "Cache-Control": "no-cache"},
    )
```

- [ ] **Step 3: 기존 `with_market` fixture 호환 — `_MARKET_PATH` 대신 `_loader` monkeypatch**

```python
# tests/conftest.py 변경
@pytest.fixture
def with_market(market_file, monkeypatch):
    from app.services.market_loader import MarketLoader
    monkeypatch.setattr(market_module, "_loader", MarketLoader(market_file))


@pytest.fixture
def with_no_market(tmp_path, monkeypatch):
    from app.services.market_loader import MarketLoader
    monkeypatch.setattr(market_module, "_loader", MarketLoader(tmp_path / "missing.json"))
```

- [ ] **Step 4: ETag 테스트 추가 — `tests/test_routes.py`**

```python
async def test_market_etag_round_trip(with_market):
    async with _make_client() as c:
        r1 = await c.get("/api/market")
        etag = r1.headers["ETag"]
        r2 = await c.get("/api/market", headers={"If-None-Match": etag})
    assert r2.status_code == 304
```

- [ ] **Step 5: 전체 테스트 통과**

Run: `cd signal-api && pytest -q`
Expected: PASS (기존 + 신규).

- [ ] **Step 6: Commit**

```bash
git add signal-api/app/services/market_loader.py signal-api/app/api/market.py signal-api/tests/
git commit -m "perf(market): MarketLoader 캐시 + ETag/304"
```

---

## Validation

### 단위 — signal-web
```bash
cd signal-web
npx tsc --noEmit              # 0 errors
npx vitest run                # adapt + (옵션) ticker-card 테스트 PASS
npm run build                 # success
```

### 단위 — signal-api
```bash
cd signal-api
pytest -q                     # 기존 테스트 + 신규 cors/loader/market ETag PASS
```

### 통합 — 로컬 E2E
```bash
# 1) signal-api
cd signal-api && uvicorn app.main:app --reload &
# 2) signal-web
cd signal-web && npm run dev
# 3) http://localhost:3000 접속
```
- 카탈로그: 종목명·현재가만 흰색, 라벨이 한 톤 낮음, 등락이 모노+▲▼.
- detail 페이지(`/signal/006340`): entry/stop/target 4종 모두 흰색 단색.
- `data/signals.json`에서 한 시그널의 `live_quote.current_price`를 null로 바꿔 좌측 황톳빛 4px 막대 확인.
- 한글 종목명이 Pretendard로 렌더(devtools `Computed > font-family`).
- TopNav 시장 지표 row, 카드 호버 hairline outline 회귀 없음.

### 시각 회귀
PR #3 토큰 치환 직후 카탈로그 + detail 페이지 스크린샷을 PR #3 전후로 비교. PR #4 색상 적용 전후도 캡처해서 위계 변화 시각화.

## Decision Log

| 일자 | 결정 | 근거 |
|------|------|------|
| 2026-05-03 | 색상 위계만으로 시인성 개선, 신규 색 미도입 | design.md `Don't introduce any accent color outside link/semantic`. luminance 5단으로 충분. |
| 2026-05-03 | 등락(change_pct)에서 gain/loss 색 제거, 글리프(▲▼─)로 대체 | design.md "gain/loss는 realized P&L only" 엄격 해석. 일중 변동은 P&L 아님. |
| 2026-05-03 | data quality flag만 색(`--warning`) 사용 | design.md `Known Gaps`가 명시적으로 허락한 유일한 색 도입 자리. |
| 2026-05-03 | DetailClient의 entry/stop/target 색 분기 롤백 | design.md "Parameters stay white" 직접 위반. |
| 2026-05-03 | TS 타입을 Pydantic optional과 1:1 동기화 | API 변경 시 컴파일 타임에 cliff 발견, 런타임 NPE 제거. |
| 2026-05-03 | typography 토큰을 CSS variable + ts() 헬퍼로 추출 | inline style 18종 × 다수 사용처. 신규 의존성 0, IDE 자동완성 유지. |
| 2026-05-03 | Pretendard는 next/font/local로 자체 호스팅, Noto Serif KR은 next/font/google | Pretendard는 google fonts 미게재. SIL OFL 라이선스 자체 호스팅 OK. |
| 2026-05-03 | SignalLoader 캐시 키를 (mtime,size) 페어로 | atomic rename 후 mtime 충돌 가능성 + size까지 비교하면 손실 위험 0. |
| 2026-05-03 | MarketLoader 신설 (SignalLoader 재사용 X) | 모델 검증 무, 응답 shape 다름. 작은 별도 클래스가 명확. |

## Surprises

(실행 중 발견하는 예상 외 사실 기록)

## Outcomes

(완료 후 기록 — 측정 가능한 결과: 시각 회귀 캡처, 테스트 카운트, lighthouse 점수 등)

---

## Self-Review

- **Spec coverage:** 사용자 요청 두 갈래(구조 리뷰 / 카드 색상 제안)가 모두 plan에 매핑됨. HIGH 3개 + MED 4개 + LOW 2개로 PR 6개 분할.
- **Placeholder scan:** TBD/TODO/추후 등 placeholder 없음. 모든 코드 step에 실제 코드 포함.
- **Type consistency:** `CardProps.dataQuality: 'ok' | 'warn'`이 PR #1에서 정의되고 PR #4에서 소비. `LoadedSignals.by_ticker`는 PR #6의 Task 6.2에서 정의되고 같은 태스크 Step 4에서 소비. 일관됨.
- **Risk:** Pretendard woff2 다운로드는 외부 자원. 라이선스 SIL OFL이라 OK이나 PR #5는 woff2 파일이 repo에 들어가야 함을 PR description에 명시.
