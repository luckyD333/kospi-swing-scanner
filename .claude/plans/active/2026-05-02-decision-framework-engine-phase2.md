---
slug: decision-framework-engine-phase2
status: active
created: 2026-05-02
---

# Plan: 의사결정 프레임워크 — Phase 2 (의사결정 엔진 + Phase 1 cleanup)

## Context

Phase 1에서 KOSPI 스윙 스캐너에 펀더멘털 수집 인프라(PER/ROE/외인비율/foreign_rate 시계열/naver_url)가 들어왔어요. 후보들의 metadata 가 풍부해졌지만, **여전히 어떤 후보를 실제 투자 대상으로 결정할지 사용자가 수동으로 판단**해야 해요.

본 Phase 2는 의사결정 프레임워크 SKILL.md 의 핵심 자동화를 구현해요:
- Step 1 (우선순위 + 가중치 정의) — CLI 인터뷰
- Step 2 (후보 평가) — 가중 점수 자동 산출
- Step 2.5 (Minimax Regret) — 동률/불확실 케이스 자동 처리
- Step 4 (Decision Journal) — 결정 메모 템플릿 자동 채움

추가로 Phase 1 회고에서 user/advisor 가 발견한 **3가지 cleanup**(rank 키 충돌, markdown 펀더멘털 미노출, 일괄 schema migration 옵션)을 함께 정리해요.

> **본 plan의 비-범위**: 웹 UI(React/Streamlit), 자동매매 연동, Phase 3 (PBR/업종/배당 추가 수집).

## Architecture Overview

### 데이터 흐름

```
[Phase 1 산출물]
  scan_results/{date}/{tf}/scan_*.json   ─┐
  .cache/manifest.json.tickers_meta      ─┤
  ~/.kospi-scanner/weights.yml           ─┤  ← 사용자가 인터뷰로 정의
                                          ▼
[Phase 2 신규]
  core/decision/config.py        WeightConfig (가중치 + 필수 조건)
  core/decision/interview.py     CLI 인터뷰 → WeightConfig
  core/decision/aggregator.py    후보 + metadata → 가중 점수
  core/decision/ensemble.py      교집합 boost + Minimax Regret
  output/decision_report.py      markdown ranking + Decision Journal
                                          ▼
  scan_results/{date}/decision_top{N}.md
  scan_results/{date}/journal_{ticker}.md   (선택된 후보별)
```

### 신규/수정 모듈

| 파일 | 역할 | 신규? |
|------|------|------|
| `core/decision/__init__.py` | 패키지 진입점 | 신규 |
| `core/decision/config.py` | `WeightConfig` (priorities/필수 조건/yaml load) | 신규 |
| `core/decision/interview.py` | CLI 인터뷰 워크플로우 | 신규 |
| `core/decision/aggregator.py` | 가중 점수 + 정규화 | 신규 |
| `core/decision/ensemble.py` | 교집합 boost + Minimax Regret | 신규 |
| `output/decision_report.py` | markdown ranking 보고서 | 신규 |
| `output/decision_journal.py` | Decision Journal 자동 생성 | 신규 |
| `cli.py` | `--decide` / `--interview` 서브 명령 | 수정 |
| `strategies/strategy_two_cross_sectional_momentum.py` | metadata `rank` → `percentile_rank` rename | 수정 (cleanup 1) |
| `output/formatters.py` `format_markdown` | 펀더멘털 컬럼 추가 | 수정 (cleanup 3) |
| `scripts/collect.py` | `--force-refetch` 옵션 | 수정 (cleanup 2) |

### Phase 1 산출물 활용 지점

- **scan_*.json `candidates[].metrics`** — 가중 점수 입력 (per/roe/foreign_pct + 전략 고유 momentum_pct/breakout_pct + score + conditions_met)
- **manifest.json `tickers_meta`** — 후보 외 종목 펀더멘털 lookup (UI 인덱스이지만 aggregator도 활용 가능)
- **`naver_url`** — Decision Journal 에 종목 링크로 자동 삽입

## 사용자 워크플로우 (UX)

```
[1] 평소: 매일 cron 으로 collect.py + cli.py 가 scan_results 갱신
[2] 의사결정 첫 사용 시:
    $ python cli.py --interview
    > "투자 종목 선정 시 가장 중요한 5~9개 항목과 가중치를 정해요."
    > 1. 항목명? 모멘텀 신뢰도(다중 전략 교집합)
    > 1. 가중치(%)? 25
    > 2. 항목명? 밸류에이션(낮은 PER)
    > 2. 가중치(%)? 20
    > ... (합 100%)
    > "필수 조건 (충족 못하면 자동 탈락)?"
    > 1. PER < 30 ?  Y/N
    > ...
    > 저장: ~/.kospi-scanner/weights.yml ✓
[3] 매 결정 시:
    $ python cli.py --decide --top-n 5
    → scan_results/20260502/decision_top5.md (가중 점수 ranking)
    → 사용자가 N개 선택:
    $ python cli.py --decide --select 005930,000660 --notes "확신 70%, 약간 불안"
    → scan_results/20260502/journal_005930.md (Decision Journal 자동 채움)
    → scan_results/20260502/journal_000660.md
```

## Plan of Work — TDD bite-sized

### Step 0. (Cleanup 1) Strategy 2 `rank` → `percentile_rank` rename
- **Test first**: `tests/test_strategy_two_unit.py` 에 metadata 키 `percentile_rank` 검증 케이스 추가, 기존 `rank` 검증은 제거
- **구현**: `strategies/strategy_two_cross_sectional_momentum.py` 의 metadata dict 에서 `"rank": rank` → `"percentile_rank": rank`
- **회귀**: 기존 `tests/test_strategy_two_unit.py` 통과 + `output/formatters.py` JSON metrics 에서 `rank` 키 충돌 해소 검증
- **Critical files**: `strategies/strategy_two_cross_sectional_momentum.py`, `tests/test_strategy_two_unit.py`

### Step 1. WeightConfig 데이터 모델
- **Test first**: `tests/test_decision_config.py` — yaml 로드, 가중치 합 100% 검증, 필수 조건 dataclass
- **구현**: `core/decision/config.py`
  ```python
  @dataclass
  class Priority:
      key: str          # 메트릭 키 (per, roe, momentum_pct, score, ensemble_count, ...)
      weight: float     # 0~100
      direction: str    # "lower_better" | "higher_better"
      label: str        # 사용자 표기

  @dataclass
  class WeightConfig:
      priorities: list[Priority]
      must_have: list[str]   # ["per<30", "roe>5", "ensemble_count>=2"] DSL
  ```
- **검증**: weights 합 == 100, key 중복 없음, must_have DSL 파싱
- **Critical files**: `core/decision/config.py`, `tests/test_decision_config.py`

### Step 2. CLI 인터뷰 워크플로우
- **Test first**: `tests/test_decision_interview.py` — `input()` mock 으로 5개 항목 + 가중치 입력 시뮬레이션
- **구현**: `core/decision/interview.py`
  - `interactive_interview() -> WeightConfig` (stdin 기반 + `argparse` 헬퍼)
  - SKILL.md Step 0 분류 (Type 1/2 + 검토 상한) 자동 안내
  - 가중치 합 != 100% 시 재입력 유도
  - 결과를 `~/.kospi-scanner/weights.yml` 저장
- **Critical files**: `core/decision/interview.py`, `tests/test_decision_interview.py`

### Step 3. 후보 통합 + 가중 점수 산출
- **Test first**: `tests/test_decision_aggregator.py` — fixture 후보 리스트 + WeightConfig → 정규화된 점수 + ranking 결정론 검증
- **구현**: `core/decision/aggregator.py`
  - `RankedCandidate` dataclass (Candidate + final_score + 가중 항목별 점수)
  - 메트릭 정규화 (min-max scaling 또는 percentile)
  - `direction="lower_better"` 면 (max - x) / (max - min) 으로 reverse
  - 가중 합산 점수 산출
  - 필수 조건(must_have) 미충족 후보 자동 탈락
- **Critical files**: `core/decision/aggregator.py`, `tests/test_decision_aggregator.py`

### Step 4. 다중 전략 교집합 + Minimax Regret
- **Test first**: `tests/test_decision_ensemble.py`
  - 2개+ 전략 동시 등장 후보 → `ensemble_count` 값 검증
  - 동률 케이스에 Minimax Regret 적용 → 후회 분산 작은 후보 우위
- **구현**: `core/decision/ensemble.py`
  - `compute_ensemble_count(scan_results) -> dict[ticker, int]`
  - `apply_minimax_regret(ranked, scenarios) -> list[RankedCandidate]`
    - 시나리오는 사용자 입력 또는 자동(예: bull/bear 미래)
    - 후회 매트릭스 (각 후보 × 각 시나리오 → 후회 점수)
    - 최대 후회가 가장 작은 후보 선호
  - aggregator 와 직렬 결합
- **Critical files**: `core/decision/ensemble.py`, `tests/test_decision_ensemble.py`

### Step 5. Decision Journal 자동 생성
- **Test first**: `tests/test_decision_journal.py` — RankedCandidate + 사용자 notes → markdown 템플릿 채움 검증
- **구현**: `output/decision_journal.py`
  - SKILL.md "Decision Journal 메모" 템플릿을 markdown 으로 생성
  - 자동 채움 항목:
    - 결정 일시, ticker, name, naver_url 링크
    - 그때 가진 정보: 펀더멘털 (per/roe/foreign_pct) + 전략 시그널 (score/momentum_pct/breakout_pct) + conditions_met
    - 적용한 프로세스: 가중치 + 가중 점수 결과
    - 예상 시나리오: target_1/target_2 도달 확률 (간단한 변동성 기반 추정)
    - 처음에 비어있는 항목: 감정 상태, 확신 수준 (사용자 후속 입력)
- **Critical files**: `output/decision_journal.py`, `tests/test_decision_journal.py`

### Step 6. CLI 통합 (`--decide` / `--interview` 서브 명령)
- **Test first**: `tests/test_cli_decide.py` — argparse + run_decide(weights, top_n) 통합
- **구현**: `cli.py` 에 서브 명령 추가
  - `python cli.py --interview` → Step 2 워크플로우
  - `python cli.py --decide --top-n 5 [--weights PATH]` → 최신 scan_results manifest 로딩 → aggregator → markdown
  - `python cli.py --decide --select TICKERS --notes "..."` → 선택 후보별 Decision Journal
- **출력 경로**: `scan_results/{date}/decision_top{N}.md`, `scan_results/{date}/journal_{ticker}.md`
- **Critical files**: `cli.py`, `tests/test_cli_decide.py`

### Step 7. (Cleanup 3) Markdown 포맷에 펀더멘털 컬럼 추가
- **Test first**: `tests/test_output_formatters.py` 에 markdown 출력에 PER/ROE/외인비율 컬럼 검증
- **구현**: `output/formatters.py` `format_markdown` 헤더에 `| PER | ROE | 외인% |` 추가, row 생성 시 metadata 에서 추출
- **결측치**: `-` 또는 `N/A` 표기
- **Critical files**: `output/formatters.py`, `tests/test_output_formatters.py`

### Step 8. (Cleanup 2) `--force-refetch` 옵션 (선택)
- **Test first**: `tests/test_collect.py` 에 `--force-refetch` 시 기존 parquet 무시하고 전 구간 재수집 검증
- **구현**: `scripts/collect.py` argparse 에 `--force-refetch` flag 추가, OhlcvCache.get_or_fetch 호출 전 disk.write 로 빈 DF 덮어쓰거나 별도 force-fetch 헬퍼
- **목적**: 사용자가 schema migration을 *즉시* 일괄 적용하고 싶을 때 (ex: foreign_rate 컬럼이 모든 종목에 채워진 상태)
- **Critical files**: `scripts/collect.py`, `tests/test_collect.py`

## Validation

### 단위 테스트
- `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` → 298+ 통과 유지 (신규 ~30개 테스트로 +330 예상)
- `.venv/bin/ruff check . --exclude .venv` → 통과

### E2E 시나리오 (실제 네이버 호출, KOSPI 50종목)
1. `python cli.py --interview` → `~/.kospi-scanner/weights.yml` 생성 확인
2. `python scripts/collect.py --market KOSPI --max-universe 50 --timeframes 1D` → 기존 흐름 정상
3. `python cli.py --strategy all --market KOSPI --max-universe 50 --format json` → 다중 전략 결과 생성
4. `python cli.py --decide --top-n 5` → `scan_results/{date}/decision_top5.md` 생성 + 가중 점수 ranking 확인
5. `python cli.py --decide --select 005930 --notes "확신 70%"` → `scan_results/{date}/journal_005930.md` 생성

### 검증 포인트
- decision_top5.md 에 가중 점수 + 항목별 기여도 + ensemble_count 표시
- journal_*.md 에 펀더멘털 + 시그널 + naver_url 자동 채움
- Strategy 2 후보의 metadata 키가 `percentile_rank` (rank 충돌 해소)
- markdown 출력에 PER/ROE/외인비율 노출

## Decision Log

- **DL-1**: 의사결정 엔진은 *CLI 기반*. Streamlit/Gradio 같은 GUI 는 별도 Phase. 이유: Phase 1 도 CLI 우선이었고, GUI 는 추가 의존성과 디자인 결정이 필요. CLI 인터뷰는 SKILL.md 의 텍스트 기반 인터뷰와 자연 매핑.
- **DL-2**: 가중치는 `~/.kospi-scanner/weights.yml` 에 저장하고 *재사용*. SKILL.md 의 "가중치는 후보를 보기 전에 정한다" 원칙과 정합. 매 결정마다 재정의 X (분석 마비 회피).
- **DL-3**: Minimax Regret 의 시나리오는 자동 추정 우선 (예: bull/bear 변동성 기반). 사용자 정의 시나리오는 Phase 3 옵션.
- **DL-4**: Decision Journal 의 감정 상태/확신 수준은 자동 추론 *불가*. 사용자가 후속으로 markdown 직접 편집하도록 빈 칸 + 안내 코멘트로 생성.
- **DL-5 (cleanup)**: Strategy 2 metadata `rank` → `percentile_rank` rename 은 *Step 0* 으로 분리. 이유: Phase 2 의사결정 엔진이 metadata 키를 사용하므로 충돌 해소가 *선행*되어야 함.
- **DL-6 (cleanup)**: `--force-refetch` 는 *선택 사항* (Step 8). Phase 1 surface 우려가 자연스러운 incremental 동작으로 이미 해소됨. 사용자가 명시적으로 일괄 migration 원할 때만 필요.

## Surprises (검증 필요 가정)

- **메트릭 정규화 방식**: min-max vs percentile rank vs z-score. 50종목 같은 작은 universe 에서 outlier (예: 적자 종목 PER=-100) 가 min-max 분포 왜곡. → percentile rank 또는 z-score winsorized 가 안전. 구현 시 비교 검증 필요.
- **Minimax Regret 시나리오 자동 생성**: 시계열 변동성만으로 미래 시나리오를 만드는 게 의미 있는지 검증 필요. 단순 변동성 추정이 부적절하면 사용자 입력 옵션으로 회귀.
- **`weights.yml` 위치**: 홈 디렉토리(`~/.kospi-scanner/`) vs 프로젝트(`.kospi-scanner/`). 홈에 두면 다중 프로젝트 공유, 프로젝트에 두면 git ignore 대상. → 홈 우선 + `--weights PATH` 로 override 허용.
- **Strategy 2 rename 의 backtest 영향**: backtest_engine 이 `metadata["rank"]` 를 직접 읽지는 않을 가능성이 높지만 grep 으로 확인 필요. 회귀 시 backtest 어댑터에서도 키 변경 동반.
- **CLI 인터뷰 vs YAML 직접 편집**: 인터뷰가 번거롭다면 사용자가 weights.yml 을 직접 편집할 수도 있음. 인터뷰는 *처음 한 번* 만 사용. 이 비대칭을 README 에 명시.

## Outcomes

### 통과 테스트 (fresh 검증, 2026-05-02)

- `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` → **370 passed** (Phase 1 후 298 → +72)
- `.venv/bin/ruff check core/ output/ scripts/ tests/ cli.py` → **All checks passed**

### Phase 2 신규/수정 파일 (12개)

**신규 모듈 (8)**:
- `core/decision/__init__.py`
- `core/decision/config.py` (`Priority`, `WeightConfig`, `MustHaveOp`, `parse_must_have`, `eval_must_have`)
- `core/decision/interview.py` (`interactive_interview`, `default_weights_path`)
- `core/decision/aggregator.py` (`RankedCandidate`, `aggregate_candidates`)
- `core/decision/ensemble.py` (`compute_ensemble_count`, `apply_minimax_regret`, `auto_volatility_scenarios`)
- `core/decision/runner.py` (`load_candidates_from_manifest`, `run_decide_ranking`, `run_decide_journal`)
- `output/decision_journal.py` (`format_decision_journal`, `format_ranking_report`)
- `tests/test_decision_*.py` 5개 + `test_cli_decide.py`

**수정 (4)**:
- `cli.py` — `--interview/--decide/--top-n/--select/--notes/--weights/--scan-results-dir` argparse + `_run_interview` + `_run_decide`
- `output/formatters.py` `format_markdown` — PER/ROE/외인% 컬럼 추가, N/A 결측 표기
- `scripts/collect.py` — `CollectConfig.force_refetch` + `--force-refetch` argparse + 디스크 캐시 clear 흐름
- `core/cache/ohlcv_disk.py` — `clear()` 메서드 (force-refetch 지원)
- `strategies/strategy_two_cross_sectional_momentum.py` — metadata `rank` → `percentile_rank` (top-level rank 충돌 해소)
- `requirements.txt` — `PyYAML>=6.0`

### 코드 리뷰 fix 적용 결과 (HIGH 2 + MEDIUM 4)

| 이슈 | 수정 | 검증 |
|---|---|---|
| HIGH-1 (`eval_must_have` 결측 처리) | DSL `?` prefix optional marker | tests/test_decision_config.py +5 |
| HIGH-2 (score 누락 무음) | `_candidate_from_json` logger.warning + 0.0 fallback | runner.py:97-103 |
| M-1 (break-even 음수) | `_break_even_winrate` NaN 반환 + markdown "❌ N/A" | decision_journal.py:14, 110-116 |
| M-2 (동률 분할 의도) | percentile_rank stable sort 주석 | aggregator.py:55-62 |
| M-3 (인터뷰 권한 에러 무음) | `_run_interview` try/except | cli.py:355-364 |
| M-4 (final_score 단위) | 0~100 스케일 주석 + contribution 단위 명시 | aggregator.py:90-94 |

### 사용자 surface 항목 처리 결과

- ✓ Strategy 2 metadata `rank` → `percentile_rank` rename → JSON metrics 키 충돌 해소
- ✓ Markdown 포맷 (`format_markdown`) 에 PER/ROE/외인% 컬럼 추가, N/A 결측 표기
- ✓ collect.py `--force-refetch` flag → 일괄 schema migration 즉시 적용 가능

### 사용자 워크플로우 (실제 동작)

```
$ python cli.py --interview
  → ~/.kospi-scanner/weights.yml 생성 (Step 1: 우선순위+가중치 정의)

$ python cli.py --decide --top-n 5
  → scan_results/{date}/decision_top5.md 생성 (가중 점수 ranking + minimax)

$ python cli.py --decide --select 005930,000660 --notes "확신 70%"
  → scan_results/{date}/journal_005930.md, journal_000660.md
    (Decision Journal — hindsight bias 차단)
```

### Phase 2 비-범위 / followup

- E2E (cli.py --interview는 stdin 필요라 자동화 어려움) — 사용자 직접 시연 권장
- LOW/NIT 5건 (cleanup PR 후보):
  - test_decision_aggregator.py 모든 후보 결측 케이스
  - ensemble.py regret_fn 반환 타입 검증
  - decision_journal.py naver_url 결측 시 빈 `[link]()` → `-`로
  - config.py `VALID_DIRECTIONS` 주석
  - interview.py direction alias 가이드 명시
