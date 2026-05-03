# Signal API — Implementation Plan

작성: 2026-05-03 (Eng Review 반영)

---

## 확정 사항

### 1. JSON 직접 서빙 — atomic write + Last-Modified

**Job B (signals.json 생성) 마지막 단계:**
```python
tmp = Path("data/signals.json.tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False))
tmp.rename("data/signals.json")  # POSIX atomic — 읽기 중 partial JSON 없음
```

**Job A (market_snapshot.json 생성) 동일 패턴:**
```python
tmp = Path("data/market_snapshot.json.tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False))
tmp.rename("data/market_snapshot.json")
```

**FastAPI 서빙:**
```python
from email.utils import formatdate

@app.get("/api/signals")
async def signals():
    path = Path("data/signals.json")
    return FileResponse(path, headers={
        "Last-Modified": formatdate(path.stat().st_mtime, usegmt=True)
    })
```

- 304 Not Modified는 `FileResponse`가 자동 처리
- 메모리 캐시 불필요 — OS page cache + FileResponse로 충분

---

### 2. market_snapshot 통합 — 별도 엔드포인트

signals.json은 pass-through. market_snapshot.json은 `/api/market` 별도 엔드포인트.

**이유:** TopNav 갱신 주기(Job A, 시간 단위)와 카탈로그 갱신 주기(Job B, 시그널 발행 시점)가 다름.
Next.js에서 두 fetch를 독립적으로 revalidate 가능.

```
GET /api/signals  → signals.json pass-through
GET /api/market   → market_snapshot.json의 market_indices만 추출
```

**market_snapshot.json 스키마 확장 (Job A 담당):**
```json
{
  "market_indices": {
    "kospi":   { "value": 2641.32, "change_pct": 0.84 },
    "kosdaq":  { "value": 748.21,  "change_pct": 1.12 },
    "usd_krw": { "value": 1374.50, "change_pct": -0.31 },
    "wti":     { "value": 78.42,   "change_pct": 0.67 },
    "vix":     { "value": 14.87,   "change_pct": -1.23 },
    "bond_3y": { "value": 3.28,    "change_pct": -0.02 }
  },
  "tickers": { ... }
}
```

Job A 확장 완료 전까지 `/api/market`은 존재하는 키만 반환하고
누락 키는 응답에서 생략 (TopNav가 graceful degradation 처리).

---

### 3. Next.js ISR — revalidate 300

```typescript
// app/page.tsx
export const revalidate = 300  // 5분

export default async function Page() {
  const [signals, market] = await Promise.all([
    fetch("http://localhost:8000/api/signals").then(r => r.json()),
    fetch("http://localhost:8000/api/market").then(r => r.json()),
  ])
  return <CatalogPage signals={signals} market={market} />
}
```

- 하루 288회 불필요 fetch 허용 (개인 툴 수준 무시)
- market 데이터도 동일 300초 — TopNav 최대 5분 지연 허용

---

### 4. Client Component 경계

`'use client'` 선언 대상:
- `components/TickerCard.tsx` — useScramble, hover state
- `components/PriceScramble.tsx` — useScramble, useEffect
- `components/FilterBar.tsx` — 필터/정렬 useState
- `components/DetailPage.tsx` — PriceScramble 포함

Server Component 유지 (fetch 담당):
- `app/page.tsx` — signals fetch
- `components/CatalogPage.tsx` — 레이아웃만, TickerCard에 props 전달
- `components/TopNav.tsx` — market props 수신, 렌더만

**hydration mismatch 위험 없음:** useScramble 초기값이
`target.replace(/./g, '0')`으로 서버/클라이언트 동일.

**tweaks-panel 제거:** Signal.html의 tweaks-panel.jsx는 포팅하지 않음.
모든 컴포넌트는 default 밀도/크기로 고정.

---

## Critical Gaps — 반드시 구현

### Gap 1: 파일 없음 핸들링

`data/signals.json` 미존재 (Job B 아직 미실행):
```python
@app.get("/api/signals")
async def signals():
    path = Path("data/signals.json")
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "signals_not_generated",
                "hint": "Run Job B: python scripts/collect.py --format signals_ui",
            },
            headers={"Retry-After": "3600"},
        )
    return FileResponse(path, headers={
        "Last-Modified": formatdate(path.stat().st_mtime, usegmt=True)
    })
```

`data/market_snapshot.json` 미존재 → degraded mode (시그널은 정상):
```python
@app.get("/api/market")
async def market():
    path = Path("data/market_snapshot.json")
    if not path.exists():
        return {"market_indices": {}}  # TopNav graceful degradation
    data = json.loads(path.read_text())
    return {"market_indices": data.get("market_indices", {})}
```

### Gap 2: 파일 손상 / Pydantic 검증 실패

```python
@app.get("/api/signals")
async def signals():
    path = Path("data/signals.json")
    if not path.exists():
        raise HTTPException(503, detail={"error": "signals_not_generated"})
    try:
        # Pydantic 검증 (스키마 불일치 조기 발견)
        raw = json.loads(path.read_text())
        SignalsResponse.model_validate(raw)
    except json.JSONDecodeError as e:
        logger.error("signals.json malformed: %s", e)
        raise HTTPException(503, detail={"error": "signals_malformed"})
    except ValidationError as e:
        logger.error("signals.json schema mismatch: %s", e)
        raise HTTPException(503, detail={"error": "signals_schema_invalid"})
    return FileResponse(path, headers={
        "Last-Modified": formatdate(path.stat().st_mtime, usegmt=True)
    })
```

**stale-while-error:** 복잡도 대비 효과 낮음 — 개인 툴에서 생략.
손상된 파일은 Job B 재실행으로 해결.

---

## 테스트 추가 대상

`signal-api/tests/test_routes.py`:
- `test_signals_returns_200_when_file_exists`
- `test_signals_returns_503_when_file_missing`
- `test_signals_returns_503_on_malformed_json`
- `test_market_returns_empty_when_file_missing` (degraded mode)
- `test_market_returns_indices_only`
- `test_last_modified_header_present`

`signal-web/components/__tests__/TickerCard.test.tsx`:
- `target2 null → "—" 렌더`
- `change < 0 → loss 색상`
- `currentPrice 천단위 포맷 (₩7,070)`

---

## 데이터 흐름

```
JobA (pykrx + 외부 API, 시간 단위)
  └→ data/market_snapshot.json.tmp → rename → market_snapshot.json

JobB (전략 + 랭킹 + 머지, 시그널 발행 시점)
  └→ data/signals.json.tmp → rename → signals.json

                   ↓                        ↓
          FastAPI /api/market      FastAPI /api/signals
          (market_indices 추출)    (pass-through + Last-Modified)
                   ↓                        ↓
              Next.js Server Component (revalidate=300)
                   ↓                        ↓
           TopNav (server)          CatalogPage (server)
           market bar                    │
                                    TickerCard ['use client']
                                    useScramble ✓
                                    FilterBar  ['use client']
```

---

## 구현 순서 (PR 분할)

| PR | 내용 | 검증 |
|----|------|------|
| #1 | signal-api: FastAPI 기본 구조 + Gap 1/2 핸들링 + 테스트 | pytest 8케이스 |
| #2 | Job A/B atomic write 패턴 적용 | 기존 268 테스트 유지 |
| #3 | signal-web: Next.js 셋업 + globals.css + lib/typography.ts | 빌드 통과 |
| #4 | signal-web: TickerCard, FilterBar, CatalogPage 포팅 | 컴포넌트 테스트 |
| #5 | signal-web: DetailPage + PriceScramble 포팅 | 컴포넌트 테스트 |
| #6 | signal-web: TopNav + market 연동 | E2E 기본 플로우 |
