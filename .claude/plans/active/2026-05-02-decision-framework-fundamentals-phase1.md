---
slug: decision-framework-fundamentals-phase1
status: active
created: 2026-05-02
---

# Plan: 의사결정 프레임워크 통합 — Phase 1 (메타데이터 확장)

## Context

KOSPI 스윙 스캐너는 Strategy 1/2/3가 각각 후보를 산출하지만, 후보들 사이에서 *실제 투자할 종목을 결정*하는 단계가 없어요. 사용자는 의사결정 프레임워크(Step 1 우선순위+가중치 → Step 2 평가 → Step 4 Decision Journal)를 적용하려고 합니다.

문제: Step 1의 우선순위 항목이 *측정 가능*해야 하는데, 현재 Candidate 메타데이터는 `score`, `market_cap_bil`, `volume_20d_avg`, 전략별 시그널 지표뿐이에요. 밸류에이션(PER/PBR), 수익성(ROE), 수급(외국인 비율), 섹터 같은 의사결정 변수가 없어요.

**본 plan의 범위 (Phase 1)**: 네이버에서 *추가 비용이 작은* 메타데이터를 캐시·Candidate 구조에 통합. 의사결정 엔진(가중 점수 산출, 후보 ranking, Decision Journal 자동 생성)은 **Phase 2 별도 plan**으로 분리.

## Architecture Overview

### 현재 데이터 흐름

```
scripts/collect.py
  → core/data_fetch.py.DataClient
    → core/data_sources/naver.py
       ├─ get_ohlcv()        L78-126   siseJson API (5컬럼 + 외국인소진율 버려짐 L116-119)
       ├─ get_tickers()      L182-186  sise_market_sum.naver 크롤링 (a 태그만)
       └─ get_market_cap()   L61-76    같은 페이지 (종목명+시총만 추출 L206-210)

core/universe.py.build_universe   tickers / cap_lookup / name_lookup 반환

core/runner.py   → ScanContext { names, market_caps, market, ohlcv_by_tf }

strategies/*   → Candidate {
                   ticker, name, score, entry_price, stop_loss, target_1/2,
                   current_price, market_cap_bil, volume_20d_avg,
                   conditions_met: dict, metadata: dict   ← 자유형식, 확장 가능
                 }

output/formatters.py _CSV_FIELDS   고정 17개 컬럼
output/comparison.py.overlap_summary   2개+ 전략 교집합만 (depth ranking 없음)
```

### 확장 지점 (코드 단서)

1. **`naver.py` L116-119**: rename 매핑에 `"외국인소진율": "foreign_rate"` 추가하면 OHLCV에 시계열 컬럼 동행.
2. **`_crawl_market_sum` L182-226**: `sise_market_sum.naver` HTML 테이블 셀에 PER/ROE/외인비율/거래량이 *이미 렌더되어 있어요*. BeautifulSoup으로 컬럼 인덱스 추가만.
3. **`ScanContext`**: 새 dict 필드 (`fundamentals: dict[ticker, dict]`) 추가하면 전략에서 접근 가능.
4. **`Candidate.metadata`**: 자유형식이라 전략 코드 손대지 않고 ScanContext에서 주입 가능 (단, *어디서* 주입할지가 핵심 — 아래 Step 3 참조).
5. **`output/formatters.py _CSV_FIELDS`**: 컬럼 추가만으로 CSV/JSON 확장.

## 추가 수집 후보 — 비용·가치 매트릭스

| 필드 | 출처 | 추가 HTTP 호출 | 의사결정 가치 | Phase |
|------|------|---------------|--------------|-------|
| 외국인소진율 (시계열) | siseJson API (이미 응답) | **0** | 수급 추세 | 1 |
| PER | sise_market_sum 테이블 | **0** (페이지 이미 호출) | 밸류에이션 | 1 |
| ROE | sise_market_sum 테이블 | **0** | 수익성 | 1 |
| 외국인비율 (스냅샷) | sise_market_sum 테이블 | **0** | 외인 보유율 | 1 |
| **naver_url** | ticker로 패턴 생성 | **0** (HTTP 0) | UI 클릭 이동 | 1 |
| 거래량 (스냅샷) | sise_market_sum 테이블 | 0 (OHLCV에 있음, 중복) | 낮음 | 제외 |
| 액면가 | sise_market_sum 테이블 | 0 | 거의 없음 | 제외 |
| PBR | item/main.naver | 종목당 1 호출 | 자산가치 | 2 |
| 업종 분류 | item/main.naver | 종목당 1 호출 | 섹터 분산 | 2 |
| 배당수익률 | item/main.naver | 종목당 1 호출 | 중간 | 2 |

**Phase 1 결정**: 비용 0인 5개 필드 (외국인소진율 + PER + ROE + 외인비율 + naver_url). 종목당 호출이 필요한 PBR/업종은 Phase 2.

### 검증된 사실 (실제 fixture 기반, 2026-05-02 fetch)

`tests/fixtures/sise_market_sum/{kospi,kosdaq}_p1_default.utf8.html` 1페이지 fetch 결과:

- **컬럼 순서 KOSPI=KOSDAQ 동일**: `N | 종목명 | 현재가 | 전일비 | 등락률 | 액면가 | 시가총액 | 상장주식수 | 외국인비율 | 거래량 | PER | ROE | 토론`
- **컬럼 인덱스 (BeautifulSoup `td` 추출 기준)**: 외인비율=8, PER=10, ROE=11
- **결측치 표기**: `N/A` 문자열 (예: 삼성전자우 ROE)
- **음수 표기**: `-100.44` 같은 일반 음수 (적자 종목). `-` 한 글자 결측은 관찰 안 됨
- **데이터 행 수**: 페이지당 50개 (`table.type_2 a.tltle` 셀렉터)
- **naver detail URL**: `https://finance.naver.com/item/main.naver?code={ticker}` (사용자 제공 패턴)

### UI 친화 저장 요구사항 (사용자 추가 요청)

펀더멘털 데이터는 향후 UI에서 표시될 예정이므로:
- **안정적 키 이름** (snake_case): `per`, `roe`, `foreign_pct`, `foreign_rate_avg`, `naver_url`
- **JSON 호환 타입**: 결측은 `None` (JSON `null`), NaN/Infinity 금지
- **저장 3곳**: (1) `Candidate.metadata` (2) `.cache/manifest.json` 의 `tickers_meta[ticker]` (UI 로드 인덱스) (3) `scan_results/.../scan_*.json` (UI 결과 표시용)
- **naver_url**: 종목당 항상 채움 (단순 패턴이라 결측 없음)

## Plan of Work — TDD bite-sized

### Step 1. `sise_market_sum` HTML 컬럼 확장
- **Test first**: `tests/test_naver_market_sum.py` (신규) — fixture HTML 1페이지 → `_crawl_market_sum`이 PER/ROE/외인비율 파싱 검증. 결측 셀 처리 (`-` 또는 빈 칸 → None).
- **구현**: `core/data_sources/naver.py` L182-226에서 `<tr>`의 컬럼 인덱스를 명시적으로 추출. `_ticker_cache[ticker]`에 `"per", "roe", "foreign_pct"` 추가.
- **API 노출**: 새 메서드 `get_fundamentals(market, target_date) -> pd.DataFrame` (인덱스 ticker, 컬럼 per/roe/foreign_pct). 기존 `get_market_cap` 시그니처 유지 (BC).
- **Critical files**: `core/data_sources/naver.py`, `core/data_sources/base.py`, `tests/test_naver_market_sum.py`

### Step 2. siseJson 외국인소진율 시계열 복구
- **Test first**: `tests/test_naver_minute.py` 또는 신규 — 모킹된 응답에 `foreign_rate` 컬럼 포함 검증.
- **구현**: `core/data_sources/naver.py` L116-119 rename 매핑에 `"외국인소진율": "foreign_rate"` 추가. dropna는 OHLC 기준만 적용 (foreign_rate가 None이어도 행 유지).
- **캐시 호환성**: parquet 스키마 변경 → 기존 `.cache/{tf}/{ticker}.parquet` 재수집 필요. `OhlcvCache` 로딩 시 컬럼 부재 → 기본값 NaN으로 백워드 호환. 이 부분 명시적 결정 필요 (Surprises 참조).
- **Critical files**: `core/data_sources/naver.py`, `core/cache/ohlcv_disk.py` (스키마 검증), `tests/test_naver_minute.py`

### Step 3. ScanContext + Candidate 메타 주입
- **Test first**: `tests/test_core_strategy_base.py`에 `ScanContext.fundamentals` 필드 + strategy_one_d_v2가 후보의 `metadata`에 펀더멘털을 복사하는지 검증.
- **구현 방향 — 전략 무수정 원칙 충돌 회피**:
  - `ScanContext.fundamentals: dict[str, dict[str, float]]` 신규 필드 추가
  - 전략 코드 *내부*에서 metadata 주입은 코드 수정 필요 → **runner.py 사후 주입** 패턴 채택
  - `core/runner.py`에서 전략 실행 후, 반환된 Candidate 리스트를 순회하며 `cand.metadata.update({"per": ..., "roe": ..., "foreign_pct": ...})` 일괄 주입
  - 이 방식이면 `strategies/*.py`는 *전혀 수정 안 함* (CLAUDE.md "신규 전략 추가 시 기존 전략 코드 무수정" 원칙과 정합)
- **Critical files**: `core/strategy_base.py`, `core/runner.py`, `tests/test_core_runner.py`

### Step 4. 출력 단 컬럼 확장
- **Test first**: `tests/test_output_formatters.py`에 fundamentals 메타데이터 포함된 Candidate → CSV/JSON에 per/roe/foreign_pct 컬럼 출력 검증.
- **구현**: 
  - `output/formatters.py` `_CSV_FIELDS`에 `per`, `roe`, `foreign_pct` 추가 (Candidate.metadata에서 추출 헬퍼 함수)
  - JSON metrics 객체에 동일 필드 추가
  - Table 출력은 *상위 5 상세 블록*에만 표시 (메인 표는 가독성 유지)
- **Critical files**: `output/formatters.py`, `tests/test_output_formatters.py`

### Step 5. 수집 매니페스트 + collect.py 통합
- **Test first**: `tests/test_collect.py`에 `--with-fundamentals` 플래그(기본 ON) → manifest에 `tickers_meta[ticker].per/roe` 기록 검증.
- **구현**: `scripts/collect.py`에서 `client.get_fundamentals()` 호출 후 결과를 `.cache/manifest.json`의 `tickers_meta`에 병합.
- **Critical files**: `scripts/collect.py`, `tests/test_collect.py`

## Validation

- `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` — 268+ 통과 유지 (신규 테스트로 +20 전후 예상)
- `.venv/bin/ruff check . --exclude .venv` — 통과 유지
- E2E:
  ```bash
  python scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D
  # → .cache/manifest.json 의 tickers_meta 에 per/roe/foreign_pct 키 존재 확인
  python cli.py --strategy strategy_one_d_v2 --market KOSPI --format json
  # → 출력 candidates[].metrics 에 per/roe/foreign_pct 표시 확인
  python cli.py --strategy all --format markdown
  # → 비교 표에 펀더멘털 컬럼 추가 (또는 별도 섹션) 확인
  ```
- 회귀: 기존 백테스트 엔진(`backtest_engine.demo`)은 OHLCV만 사용 → 영향 없어야 함

## Decision Log

- **DL-1 (사용자 확정)**: Phase 1 범위 = **데이터 확장만**. 의사결정 엔진(가중 점수, 후보 ranking, Decision Journal 자동 생성)은 Phase 2 별도 plan으로 분리. 이유: 프레임워크 적용은 우선순위 가중치 정의가 선행되어야 하는데, 우선순위 자체에 사용자 인터뷰가 필요. 데이터 없는 상태에서 가중치를 먼저 정하면 가설성 답변 위험. 실제 후보+펀더멘털을 보면서 우선순위를 정의하는 것이 의사결정 프레임워크의 Step 1 원칙(*"가중치는 후보를 보기 전에 정한다"*)과도 정합 — 단, 그 "후보를 보기 전"의 *후보*는 본 Phase 1 결과로 만들어지는 *완전한 후보 데이터*를 의미.
- **DL-2 (사용자 확정)**: 수집 범위는 **비용 0 필드만** (외국인소진율 시계열 + PER + ROE + 외국인비율). PBR/업종/배당은 Phase 2 또는 그 이후. 이유: ROI 검증. 4개 필드로 의사결정 변별력이 충분한지 사용 후 판단.
- **DL-3 (사용자 확정)**: 메타데이터 주입은 `runner.py` 사후 주입 패턴. ScanContext에 fundamentals를 두지만 전략은 사용하지 않고, runner가 후보 반환 후 `metadata.update()`로 일괄 주입. CLAUDE.md "전략 코드 무수정" 원칙 준수.
- **DL-4**: 본 plan에서 의사결정 엔진 코드(`output/decision_engine.py` 등) 작성 **금지**. 출력 단(Step 4)은 *추가 컬럼 표시*까지만. 자동 ranking/가중 점수 산출은 Phase 2.

## Surprises

- 네이버 siseJson API는 *이미* 외국인소진율을 응답에 포함하지만 `naver.py` L116-119 rename에서 명시적으로 제외 → 사실상 의도된 누락. 복구 시 다른 의도가 있었는지 확인 필요 (e.g., 데이터 노이즈, 결측 빈도).
- `core/universe.py` L24, 67의 `min_daily_volume` 파라미터는 선언되지만 build_universe에서 미사용. 별건이지만 Phase 2 정리 후보.
- `_crawl_market_sum`의 페이지 테이블 컬럼 순서가 KOSPI/KOSDAQ에서 일치한다는 가정 검증 필요 (실제 HTML 비교 후 fixture 작성).

## Outcomes

### 통과 테스트
- **297 passed** (기존 268 → +29 신규). ruff lint 0 issue.
- 신규 테스트 파일:
  - `tests/test_naver_market_sum.py` (8) — sise_market_sum HTML 컬럼 + naver_url 헬퍼
  - `tests/test_runner_fundamentals_injection.py` (7) — runner 사후 주입
- 기존 파일 추가:
  - `tests/test_naver_minute.py` (+3) — 외국인소진율 시계열 복구
  - `tests/test_output_formatters.py` (+8) — 펀더멘털 컬럼 + 전략 metadata + JSON 직렬화
  - `tests/test_collect.py` (+2) — manifest tickers_meta에 펀더멘털 병합

### 결정 변경 로그
- **DL-5 (사용자 추가 요구, Step 1 진행 중)**: UI 활용을 위한 `naver_url` 필드 추가 (코드/HTTP 비용 0). 모든 출력 단 (Candidate.metadata, scan_*.json, CSV, manifest.json) 에 일관 노출.
- **DL-6 (사용자 확인, Step 4 진행 중)**: 전략 고유 metadata(momentum_pct, channel_high 등) + conditions_met 을 JSON metrics 에 전체 merge. CSV 는 고정 컬럼만 유지 (DictWriter extrasaction='ignore' 효과). UI 가 "왜 후보인지" 근거 표시 가능.
- **DL-7 (Step 4 회귀 대응)**: numpy.bool_ 등 비-호환 객체를 위한 `_json_default` 핸들러 추가 (numpy scalar `.item()` + Timestamp `.isoformat()` fallback).

### 변경 파일 (8개)
- `core/data_sources/naver.py` — `naver_detail_url`, `_to_optional_float`, `get_fundamentals`, OHLCV에 foreign_rate 컬럼, `pd.read_html(flavor="lxml")`
- `core/data_sources/base.py` — `get_fundamentals` 선택 인터페이스
- `core/data_fetch.py` — `DataClient.get_fundamentals` 위임
- `core/strategy_base.py` — `ScanContext.fundamentals` dict 필드
- `core/runner.py` — fundamentals 1회 fetch + ScanContext 주입 + 후보 metadata 사후 주입 (`_collect_fundamentals`, `_none_if_nan`)
- `output/formatters.py` — `_CSV_FIELDS` 4컬럼 추가, JSON metrics에 metadata + conditions_met merge, table 상위 5 상세에 펀더멘털 + naver_url 표시, `_json_default` 핸들러
- `scripts/collect.py` — `_collect_fundamentals`, `_build_tickers_metadata` fundamentals 인자 추가, manifest 통합
- `core/data_sources/{fdr,krx_proxy,pykrx}.py` 등 기 삭제 파일은 본 plan 밖
- `tests/fixtures/sise_market_sum/{kospi,kosdaq}_p1_default.html` (UTF-8 변환 1회 fetch fixture)

### 검증 결과
- `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` → **298 passed** (schema migration 테스트 포함)
- `.venv/bin/ruff check core/ output/ scripts/ tests/ --exclude .venv` → All checks passed
- 실제 fixture 1페이지로 컬럼 순서 KOSPI=KOSDAQ 동일 확인. 결측치 패턴 `N/A` 검증.

### E2E 실시 (실제 네이버 호출, KOSPI 50종목)
1. `python scripts/collect.py --market KOSPI --cache-root .cache --max-universe 50 --timeframes 1D --no-etf`
   - 50개 1D OHLCV 수집 + KOSPI 2443종목 펀더멘털 1회 크롤링 (15초)
   - `manifest.json.tickers_meta["000660"]` → `{per: 21.81, roe: 44.15, foreign_pct: 52.92, naver_url: "https://finance.naver.com/item/main.naver?code=000660"}` ✓
   - 펀더멘털 결측 카운트: per 1, roe 2 (전체 50개 중 우선주 ROE 결측 — 정상)
2. `python cli.py --strategy strategy_two_cross_sectional_momentum --market KOSPI --max-universe 50 --format json`
   - candidates[0] (HD현대에너지솔루션, 322000) metrics에 `per=62.08, roe=10.59, foreign_pct=6.29, naver_url=…/322000, momentum_pct=0.4068, conditions_met={momentum_top_quartile,volume_above_avg}` 모두 노출 ✓
3. `python cli.py --strategy all --format markdown` → 멀티 전략 비교 markdown 정상 (펀더멘털은 markdown에 미포함 — 현 plan 범위 밖)

### Surface to user (advisor 지적 사항)
- **rank 키 의미 충돌** (실제 E2E로 확인됨): `candidate.rank=1`(UI 표시 순위, int) vs `candidate.metrics.rank=1.0`(Strategy 2 percentile, float). 같은 키 이름 다른 의미. UI 빌드 시 `metrics.rank`를 `metrics.percentile_rank`로 rename 권장 — 별건 cleanup 작업.
- **Parquet schema migration은 forward-only**: 기존 `.cache/1D/*.parquet`(5컬럼)는 *gap fetch 발생 시점*에 자연 union으로 foreign_rate 컬럼 추가됨. 즉시 일괄 migration은 안 일어남 (의도된 동작). 단위 테스트로 검증 완료 (`test_append_unions_columns_for_schema_migration`).
- **markdown 포맷에는 펀더멘털 미노출**: `format_markdown`은 가격 중심 단순 표 (현 범위 외). UI가 markdown을 쓰려면 별도 확장 필요.

### Phase 2 후속 (out-of-scope)
- 종목 상세 페이지 호출로 PBR/업종/배당 추가
- 의사결정 엔진 (가중 점수, 후보 ranking, Decision Journal 자동 생성)
- `core/universe.py` 의 unused `min_daily_volume` 정리 (별건)
