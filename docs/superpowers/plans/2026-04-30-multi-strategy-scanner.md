# 멀티 전략 스캐너 — 구현 계획 (2026-04-30)

## Context

현재 `daily_only_scanner.py`(1,355줄)는 단일 전략(Strategy D v2: Mean Reversion + Technical Confluence) 위에 데이터 페치·universe 필터·CLI·출력이 모두 섞여 있다. Plug-and-play 가능한 멀티 전략 아키텍처로 전환해 신규 패러다임(전략2·3) 추가 시 기존 코드 수정 0줄(OCP)을 보장한다.

전략2·3 신규 구현은 **별도 plan**(Phase 1 학술·실무 리서치 결과 의존)에서 진행. 본 plan은 **공통 모듈 추출 + 전략1 마이그레이션 + CLI** 까지.

### 핵심 제약

1. **전략1 회귀 금지** — 동일 입력 → 동일 top N (순서·점수·가격 모두 일치)
2. **신규 의존성 최소** — Python 표준 + 기존 deps(pandas/numpy/scipy/pykrx/FDR) 우선
3. **단일 fetch** — 같은 날 여러 전략 실행 시 OHLCV 1회 페치
4. **OCP** — 신규 전략 추가 시 기존 전략·데이터·CLI 파일 수정 0
5. **TDD** — 각 모듈은 테스트 먼저 작성, 실패 확인 후 구현

---

## 합의된 설계 결정 (이전 plan에서 동의 완료)

| 항목 | 결정 |
|------|------|
| 전략 등록 방식 | Protocol + 명시 import + dict registry |
| 인디케이터 캐시 | 메모리 dict (per-run), parquet은 후속 |
| 전략 파라미터 | frozen dataclass (TOML override 옵션) |
| 백테스트 훅 | 인터페이스 의무화만 (Candidate dataclass), 러너 통합 보류 |
| 출력 통합 | 단독(전략1 회귀용) + 멀티(`--strategy all`) 모두 |
| 데이터 소스 | 기존 `DailyDataSource` ABC 그대로 추출 |
| `daily_only_scanner.py` | Sub-3에서 즉시 삭제, 사전 snapshot 캡처로 회귀 보장 |
| PR 단위 | Sub-1·2·3 각각 독립 |

---

## 패키지 구조 (사용자 새 지시 반영)

```
kospi-swing-scanner/
├── cli.py                         ← 신규 진입점 (Sub-3)
├── daily_only_scanner.py          ← Sub-0 직후 immutable snapshot, Sub-3에서 삭제
│
├── core/                          ← Sub-1
│   ├── __init__.py
│   ├── universe.py                (KOSPI/KOSDAQ 종목 리스트, 시총·유동성·관리종목 필터)
│   ├── data_fetch.py              (OHLCV 페치 + 메모리 캐시 + DataClient fallback 체인)
│   ├── data_sources/              (현 daily_only_scanner.py L51~977 추출)
│   │   ├── __init__.py
│   │   ├── base.py                (DailyDataSource ABC)
│   │   ├── pykrx.py               (PykrxSource)
│   │   ├── fdr.py                 (FDRSource)
│   │   ├── krx_proxy.py           (KRXProxySource + CircuitBreaker)
│   │   └── naver.py               (NaverSource)
│   ├── indicators.py              (RSI/BB/MACD/ATR/MA/거래량 z-score/모멘텀 — backtest_engine.core wrap)
│   ├── strategy_base.py           (Strategy Protocol, ScanContext, Candidate)
│   └── runner.py                  (ScanRunner — 단일 fetch 후 여러 전략 실행, top N 추출, 출력)
│
├── strategies/                    ← Sub-2
│   ├── __init__.py                (REGISTRY = {"strategy_one_d_v2": StrategyOneDv2})
│   └── strategy_one_d_v2.py       (기존 로직 마이그레이션, backtest_engine.StrategyD adapter)
│
├── output/                        ← Sub-3
│   ├── __init__.py
│   ├── formatters.py              (TableFormatter, JsonFormatter, CsvFormatter)
│   └── comparison.py              (ComparisonTable — 멀티 전략 동일자 비교)
│
├── backtest_engine/               ← 변경 없음
└── tests/
    ├── fixtures/
    │   └── legacy_scanner_snapshot.json  ← Sub-0에서 생성, Sub-3까지 immutable
    ├── conftest.py                ← 기존 + 신규 mock fixture 통합
    ├── test_core_universe.py
    ├── test_core_data_fetch.py
    ├── test_core_indicators.py
    ├── test_core_strategy_base.py
    ├── test_core_runner.py
    ├── test_strategy_one_regression.py     (회귀: snapshot vs 신규)
    ├── test_strategy_one_unit.py
    ├── test_cli.py                          (argparse 동작 + 출력 포맷)
    ├── test_integration.py                  (멀티 전략 동일자 실행 + 비교 테이블)
    ├── test_ocp.py                          (더미 전략 등록만으로 동작)
    └── (기존 test_krx_proxy_mock·test_strict_mode_e2e·test_daily_scanner_mock 유지)
```

---

## 태스크 분해 (TDD, 각 2-5분)

### Sub-0 — 스냅샷 캡처 (회귀 baseline)

| # | 태스크 | 파일 | 검증 |
|---|--------|------|------|
| 0.1 | `.gitignore` 작성 (`scan_results/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `.venv/`, `.cache/`) | `.gitignore` | `git status` 깨끗 |
| 0.2 | mock 데이터 기반 snapshot 생성기 작성 — `tests/test_daily_scanner_mock.py`의 mock client 재사용해 top 20 결과를 JSON으로 캡처 | `tests/fixtures/legacy_scanner_snapshot.json`, `tests/_capture_snapshot.py` | snapshot JSON 존재, 20개 후보 |
| 0.3 | 초기 commit ("Sub-0: legacy snapshot baseline") | git commit | `git log` 1개 |

### Sub-1 — 공통 모듈 추출 (refactor only, 행동 변화 0)

| # | 태스크 | 파일 | 검증 |
|---|--------|------|------|
| 1.1 | 테스트 작성: `core.indicators` (RSI/BB/MACD/ATR/MA/vol z-score/모멘텀) — `backtest_engine.core` 결과와 일치 | `tests/test_core_indicators.py` | 테스트 실행 시 ImportError (의도된 fail) |
| 1.2 | `core/__init__.py`, `core/indicators.py` 작성 — backtest_engine 함수 wrap + 신규 `momentum(prices, k)`, `vol_zscore(volume, window)` | `core/indicators.py` | 1.1 테스트 green |
| 1.3 | 테스트 작성: `core.data_sources` (4개 소스 + ABC 인터페이스) | `tests/test_core_data_fetch.py` (sources 부분) | 테스트 실행 시 fail |
| 1.4 | `daily_only_scanner.py` L51~890 를 `core/data_sources/{base,pykrx,fdr,krx_proxy,naver}.py` 로 분할 이동 (코드 동일, import만 갱신) | 5개 파일 | 1.3 테스트 green + 기존 `test_krx_proxy_mock.py` 통과 |
| 1.5 | 테스트 작성: `core.data_fetch.DataClient` + `OhlcvCache` (`get_or_fetch` 1회만 페치) | `tests/test_core_data_fetch.py` | fail |
| 1.6 | `core/data_fetch.py` 작성 — `DataClient` (기존 L893 이동) + `OhlcvCache` (메모리 dict, `dict[str, pd.DataFrame]`) | `core/data_fetch.py` | 1.5 통과 + 기존 mock 테스트 유지 |
| 1.7 | 테스트 작성: `core.universe` (시총·거래량·상장경과·관리종목 필터, Strategy D §3.4) | `tests/test_core_universe.py` | fail |
| 1.8 | `core/universe.py` 작성 — `daily_only_scanner._filter_universe` 추출 + 관리종목 stub (실데이터 의존 부분은 source에 위임) | `core/universe.py` | 1.7 통과 |
| 1.9 | 테스트 작성: `core.strategy_base` (Protocol, ScanContext, Candidate dataclass invariants) | `tests/test_core_strategy_base.py` | fail |
| 1.10 | `core/strategy_base.py` — Protocol + ScanContext + Candidate (`__post_init__`로 sl<entry<t1<t2 검증) | `core/strategy_base.py` | 1.9 통과 |
| 1.11 | 테스트 작성: `core.runner` — 단일 fetch 후 N개 전략 실행, 같은 ticker는 1번만 페치 (mock counter) | `tests/test_core_runner.py` | fail |
| 1.12 | `core/runner.py` — `ScanRunner.run(strategies, target_date, top_n)` → `dict[str, list[Candidate]]` | `core/runner.py` | 1.11 통과 |
| 1.13 | 기존 `daily_only_scanner.py` 가 신규 모듈로부터 import 하도록 갱신 (코드 흐름 그대로, 단 단일 진입점 보존) | `daily_only_scanner.py` | snapshot 회귀 0건 |
| 1.14 | Sub-1 commit ("Sub-1: core/ 공통 모듈 추출") | git | snapshot diff 0 |

### Sub-2 — 전략1 마이그레이션

| # | 태스크 | 파일 | 검증 |
|---|--------|------|------|
| 2.1 | 회귀 테스트 작성: `tests/test_strategy_one_regression.py` — snapshot vs `StrategyOneDv2.scan()` 결과 동일 | 테스트 파일 | fail (구현 전) |
| 2.2 | 단위 테스트 작성: `tests/test_strategy_one_unit.py` — 7조건 개별 on/off, confidence 가산 | 테스트 파일 | fail |
| 2.3 | `strategies/strategy_one_d_v2.py` 작성 — `Strategy` Protocol 구현, 내부적으로 `backtest_engine.StrategyD` 호출 후 `TradeSignal → Candidate` 변환 | `strategies/strategy_one_d_v2.py` | 2.1·2.2 green |
| 2.4 | `strategies/__init__.py` — REGISTRY dict 정의 + `register(name, cls)` 헬퍼 (OCP) | `strategies/__init__.py` | import 확인 |
| 2.5 | OCP 테스트: 더미 전략 임시 등록 후 runner가 발견하는지 (런타임 등록만으로) | `tests/test_ocp.py` | green |
| 2.6 | Sub-2 commit ("Sub-2: 전략1 마이그레이션 + Strategy Protocol") | git | 회귀 0 |

### Sub-3 — CLI + 출력 + legacy 삭제

| # | 태스크 | 파일 | 검증 |
|---|--------|------|------|
| 3.1 | 테스트 작성: `tests/test_cli.py` — argparse 옵션, --help, --strategy 검증 (subprocess) | 테스트 파일 | fail |
| 3.2 | 테스트 작성: 출력 포맷 3종 (table·json·csv) 각 구조 검증 | `tests/test_cli.py` | fail |
| 3.3 | `output/formatters.py` — `TableFormatter`(stdout), `JsonFormatter`, `CsvFormatter` | `output/formatters.py` | 3.2 일부 green |
| 3.4 | `output/comparison.py` — `ComparisonTable.merge(results: dict[str, list[Candidate]])` → markdown/csv | `output/comparison.py` | 단위 테스트 |
| 3.5 | `cli.py` — argparse(--strategy/--top/--date/--format/--market/--strict/--no-krx/--config/--output-dir) → ScanRunner 호출 → formatter | `cli.py` | 3.1 green |
| 3.6 | 통합 테스트: `tests/test_integration.py` — 같은 날 1개 전략 실행 (전략2·3 미구현이므로 multi는 placeholder) → 비교 테이블 생성 가능 검증 | 테스트 파일 | green |
| 3.7 | snapshot 최종 회귀 — `python cli.py --strategy strategy_one_d_v2 ...` 결과 = `legacy_scanner_snapshot.json` | bash 검증 | diff 0 |
| 3.8 | `daily_only_scanner.py` 삭제 + import 경로 정리 | `rm daily_only_scanner.py` | `python -c "import daily_only_scanner"` 실패 |
| 3.9 | `README.md` 업데이트 — 새 CLI 사용 예시, 전략별 설명, OCP 가이드 ("새 전략 추가 = strategies/<name>.py + REGISTRY 등록 한 줄") | `README.md` | 수동 검토 |
| 3.10 | 최종 commit ("Sub-3: CLI + legacy 삭제 + README 갱신") | git | 모든 테스트 green |

---

## Strategy Protocol 명세

```python
# core/strategy_base.py
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
import pandas as pd

@dataclass(frozen=True)
class ScanContext:
    target_date: str                     # YYYYMMDD
    universe: tuple[str, ...]            # 필터 통과 ticker (frozen 호환 위해 tuple)
    ohlcv: dict[str, pd.DataFrame]       # ticker → 일봉 (지표 미포함, 전략별로 prepare)
    market_caps: dict[str, float]        # 억원
    market: str                          # KOSPI|KOSDAQ

@dataclass
class Candidate:
    ticker: str
    name: str
    strategy: str                        # registry key
    signal_date: pd.Timestamp
    score: float                         # 0.0~1.0
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    conditions_met: dict[str, bool] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        assert 0.0 <= self.score <= 1.0
        assert self.stop_loss < self.entry_price < self.target_1 < self.target_2

@runtime_checkable
class Strategy(Protocol):
    name: str
    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]: ...
```

---

## CLI 설계

```bash
python cli.py --strategy strategy_one_d_v2 --market KOSPI --top 20
python cli.py --strategy all --top 10 --format markdown            # 멀티 (전략2·3 추가 후 의미 있음)
python cli.py --strategy strategy_one_d_v2 --format json --top 30
python cli.py --help

옵션:
  --strategy {strategy_one_d_v2|all}     본 plan에서는 1개만, 후속 plan에서 추가
  --market {KOSPI|KOSDAQ|KRX}
  --date YYYYMMDD                        기본: 최근 영업일
  --top N                                기본 20
  --format {table|json|csv|markdown}     기본 table (stdout)
  --strict                               KRX Proxy 실패 시 중단
  --no-krx                               KRX Proxy 비활성화
  --output-dir PATH                      JSON/CSV 저장 디렉토리
  --config TOML                          frozen dataclass override (옵션)
```

---

## Definition of Done

| 항목 | 검증 명령 | 통과 기준 |
|------|-----------|-----------|
| 전략1 회귀 | `pytest tests/test_strategy_one_regression.py -v` | snapshot vs 신규 diff 0 |
| 단위 테스트 | `pytest tests/ backtest_engine/tests/ -v` | 모든 테스트 green |
| OCP | `pytest tests/test_ocp.py -v` | 더미 전략 등록·실행 |
| 통합 | `pytest tests/test_integration.py -v` | 멀티 전략 placeholder 실행 |
| CLI | `python cli.py --help`, 3종 포맷 동작 | 정상 출력 |
| README | 시각적 검토 | 사용 예시 + OCP 가이드 |
| Type/Lint | `python -m py_compile` (전 파일) | 0 에러 |
| Legacy 삭제 | `ls daily_only_scanner.py` | not found |

---

## 후속 (본 plan 외)

- **Phase 1 리서치 plan** — `docs/superpowers/plans/2026-04-30-screening-theories-research.md` (학술·실무 패러다임 8개 검토 → 권고 2개)
- **Sub-4 plan** — 전략2 신규 구현 (Phase 1 권고 #1)
- **Sub-5 plan** — 전략3 신규 구현 (Phase 1 권고 #2)
- **Disk parquet 캐시** — 백테스트 반복 효율화 (선택)
- **TOML config override** — 실험 자동화 시 도입

---

## Critical Files (read-only 참조)

- `daily_only_scanner.py` (1,355줄) — 마이그레이션 원본
- `backtest_engine/strategy.py:97-215` — StrategyD.check_entry (재사용)
- `backtest_engine/core.py:162-234` — RSI/BB/MACD/ATR (재사용)
- `backtest_engine/detectors.py` — 쌍바닥 3종 (재사용)
- `tests/test_daily_scanner_mock.py` — mock fixture 패턴 차용
