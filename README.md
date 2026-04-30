# KOSPI Swing Scanner — Multi-Strategy

KOSPI/KOSDAQ 일봉 기반 단기 스윙 매수 후보 자동 스크리닝 시스템.
plug-and-play 가능한 전략 아키텍처(Strategy Protocol)를 채택해 신규 패러다임을
파일 추가만으로 등록할 수 있다.

- **Strategy 1**: Strategy D v2 — RSI + 볼린저 밴드 + 쌍바닥 + 장악형 양봉 (Mean Reversion)
- **Strategy 2**: Cross-sectional Momentum (Jegadeesh-Titman 1993) — 15일 상대 수익률 상위 25%
- **Strategy 3**: Time-series Trend-Following (Moskowitz-Ooi-Pedersen 2012) — Donchian 20일 채널 돌파
- 학술·실무 리서치 출처: [`docs/research/2026-04-30-screening-theories.md`](docs/research/2026-04-30-screening-theories.md)
- **데이터**: KRX Proxy(공식) → 네이버 금융(수정주가) → pykrx → FDR fallback 체인
- **타깃**: 시총 2천억~3조원 중소형주, Long Only, 1~3일 보유

## 🚀 빠른 시작 (5분)

### 1. Python 가상환경

```bash
cd kospi-swing-scanner

python3 -m venv .venv
source .venv/bin/activate              # macOS/Linux
# .venv\Scripts\Activate.ps1           # Windows PowerShell

pip install --upgrade pip
pip install -r requirements.txt
```

### 2. 동작 검증 (실제 네트워크 없이)

```bash
# 전체 테스트 (153+ tests)
pytest backtest_engine/tests/ tests/ -v
```

### 3. 실전 스캔 실행

```bash
# 단일 전략 (기본)
python cli.py --strategy strategy_one_d_v2 --market KOSPI --top 20

# 출력 포맷 변경 (table | json | csv | markdown)
python cli.py --strategy strategy_one_d_v2 --format json --top 30

# 멀티 전략 동시 실행 (등록된 전략 모두) — 비교 테이블 출력
python cli.py --strategy all --top 10 --format markdown

# 엄격 모드 (KRX Proxy 장애 시 즉시 중단)
python cli.py --strategy strategy_one_d_v2 --strict

# 특정 날짜
python cli.py --date 20260418 --top 30

# 결과 파일 저장
python cli.py --strategy strategy_one_d_v2 --output-dir scan_results

# 전체 옵션
python cli.py --help
```

## 🧠 멀티 전략 아키텍처

### 핵심 컨셉

```
   ┌──────────────────────────────────────────────────────────┐
   │   cli.py  (argparse + 출력 포맷)                          │
   └────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │  ScanRunner            (단일 fetch → N전략 격리 실행)      │
   │   ├─ build_universe    (시총·유동성·관리종목 필터)          │
   │   ├─ OhlcvCache        (ticker 당 1회 fetch, 메모리)       │
   │   └─ Strategy.scan()   ×  N개 전략                          │
   └────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │  strategies/  (Strategy Protocol 구현체들)                  │
   │   ├─ strategy_one_d_v2    Mean Reversion + Confluence     │
   │   ├─ (전략 2 — 후속 plan)                                  │
   │   └─ (전략 3 — 후속 plan)                                  │
   └──────────────────────────────────────────────────────────┘
```

- 동일 `ScanContext` (universe + OHLCV + 시총) 입력에서 모든 전략이 동일 데이터를 본다.
- `OhlcvCache` 가 같은 (ticker, start, end) 키 재요청을 캐시 처리하여 **fetch 1회**.
- 각 전략 실행은 격리되어, 한 전략의 예외가 다른 전략을 막지 않는다.

### 새 전략 추가 가이드 (OCP)

기존 코드 수정 없이 신규 전략을 plug-in:

1. `strategies/<name>.py` 작성 — `Strategy` Protocol 충족 (`name` 속성 + `scan(ctx, top_n) -> list[Candidate]`).
   ```python
   from core.strategy_base import Candidate, ScanContext

   class MyStrategy:
       name = "my_strategy"
       def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
           ...
   ```
2. `strategies/__init__.py` 에 한 줄 추가:
   ```python
   from .my_strategy import MyStrategy
   REGISTRY[MyStrategy.name] = MyStrategy
   ```
3. 단위 테스트 + `tests/test_ocp.py` 통과 확인.

이후 `python cli.py --strategy my_strategy` 또는 `--strategy all` 로 자동 노출.

## 📁 파일 구조

```
kospi-swing-scanner/
├── README.md                         # 이 문서
├── requirements.txt
├── .gitignore
├── CLAUDE.md
│
├── cli.py                            # CLI 진입점
│
├── core/                             # 공통 모듈
│   ├── data_sources/                 #   데이터 소스 ABC + 4종 구현
│   │   ├── base.py                   #     DailyDataSource ABC
│   │   ├── pykrx.py
│   │   ├── fdr.py
│   │   ├── krx_proxy.py              #     CircuitBreaker 포함
│   │   └── naver.py
│   ├── data_fetch.py                 #   DataClient (fallback) + OhlcvCache
│   ├── universe.py                   #   build_universe + UniverseFilter
│   ├── indicators.py                 #   RSI/BB/MACD/ATR/MA/모멘텀/거래량 z-score
│   ├── strategy_base.py              #   Strategy Protocol + ScanContext + Candidate
│   └── runner.py                     #   ScanRunner (단일 fetch, N전략)
│
├── strategies/                       # 전략 구현체들 (plug-in)
│   ├── __init__.py                   #   REGISTRY dict + register/unregister
│   ├── strategy_one_d_v2.py          #   Strategy 1: Mean Reversion + Confluence
│   ├── strategy_two_cross_sectional_momentum.py
│   │                                 #   Strategy 2: 상대 수익률 상위 percentile
│   └── strategy_three_trend_following.py
│                                     #   Strategy 3: Donchian 20일 채널 돌파
│
├── output/                           # 출력 포맷터
│   ├── formatters.py                 #   table / json / csv / markdown (단일)
│   └── comparison.py                 #   markdown / csv / json (멀티 전략 비교)
│
├── backtest_engine/                  # 백테스트 엔진 (변경 없음)
│   ├── core.py                       #   타입 + 지표 (RSI, BB, MACD, ATR)
│   ├── detectors.py                  #   쌍바닥 3가지 구현
│   ├── scenarios.py                  #   가상 OHLCV 시나리오
│   ├── strategy.py                   #   Strategy D v2 진입/청산
│   ├── engine.py                     #   백테스트 실행 엔진
│   ├── screener.py                   #   다중 타임프레임 스크리너
│   ├── demo.py                       #   통합 데모
│   └── tests/                        #   엔진 단위 테스트 (71개)
│
├── tests/                            # 통합 테스트
│   ├── fixtures/
│   │   └── legacy_scanner_snapshot.json   회귀 baseline (Sub-0 immutable)
│   ├── test_core_*.py                #   core/ 모듈 단위 테스트
│   ├── test_strategy_one_*.py        #   전략 1 회귀 + 단위
│   ├── test_ocp.py                   #   Open-Closed 검증
│   ├── test_cli.py                   #   CLI E2E
│   ├── test_integration.py           #   멀티 전략 비교
│   ├── test_krx_proxy_mock.py        #   KRX Proxy + Circuit Breaker
│   ├── test_strict_mode_e2e.py       #   strict_mode 엔드투엔드
│   └── test_daily_scanner_mock.py    #   MockKOSPIDataSource fixture + E2E
│
└── docs/
    ├── strategy_d_v2_spec.md
    ├── korean_stock_data_sources_guide.md
    └── superpowers/plans/                 # 진행/완료 plan 보관
```

## ⚙️ 환경변수 (선택)

```bash
# KRX Proxy URL 변경 (기본: https://k-skill-proxy.nomadamas.org)
export KSKILL_PROXY_BASE_URL="https://your-proxy.example.com"
```

## 🛠 데이터 소스 우선순위

| 단계 | 소스 | 역할 |
|------|------|------|
| 1차 | KRX Proxy `trade-info` | 공식 시총 + 종가 (유니버스 보강) |
| 2차 | 네이버 `siseJson` | N일 OHLCV 시계열 (수정주가) |
| 3차 | pykrx | KRX 라이브러리 (백업) |
| 4차 | FinanceDataReader | 추가 fallback |

`--strict` 옵션은 KRX Proxy 장애 시 **스캔 전체 중단** (실전 안전 모드).

## 🧪 테스트 구성

```
backtest_engine/tests/   71 tests   엔진 단위 (core/detectors/strategy/engine/screener)
tests/test_core_*        ~30 tests   core/ 모듈 단위 (indicators/data_fetch/universe/runner/strategy_base)
tests/test_strategy_*    ~12 tests   Strategy 1 회귀 + 단위
tests/test_ocp.py         6 tests    Open-Closed (신규 전략 등록·실행)
tests/test_cli.py         12 tests   CLI argparse + 4종 출력 포맷 + main() E2E
tests/test_integration    5 tests    멀티 전략 fetch 공유 + 비교 테이블
tests/test_*_mock         18 tests   KRX Proxy mock + Circuit Breaker
tests/test_strict_mode    3 tests    strict_mode 엔드투엔드
tests/test_daily_scanner_mock  1     E2E 시나리오
```

전체 178+ 통과해야 셋업 완료.

## 🆘 트러블슈팅

### `ModuleNotFoundError: No module named 'core'`
프로젝트 루트에서 실행하세요:
```bash
cd kospi-swing-scanner
PYTHONPATH=. pytest tests/
```

### `pykrx` 설치 실패
```bash
python cli.py --no-krx
```

### KRX Proxy 503 에러
서버 측 일시 장애일 수 있습니다.
```bash
python cli.py --no-krx --market KOSPI
```

## 📚 문서

- [`docs/strategy_d_v2_spec.md`](docs/strategy_d_v2_spec.md) — Strategy D v2 전략 설계
- [`docs/korean_stock_data_sources_guide.md`](docs/korean_stock_data_sources_guide.md) — 데이터 소스 비교
- [`backtest_engine/README.md`](backtest_engine/README.md) — 백테스트 엔진 사용법
- [`docs/superpowers/plans/`](docs/superpowers/plans/) — 구현 plan 이력

## ⚠️ 면책 조항

본 도구는 정보 제공 및 학습 목적이며, 투자 조언이 아닙니다. 실제 투자 결정과 그 결과는
사용자 본인의 책임입니다. KRX 공식 데이터 기준이지만 데이터 정확성을 보증하지 않습니다.

## 라이선스

개인 사용. 상업적 사용 시 KRX 및 네이버 금융 데이터 사용 약관을 확인하세요.
