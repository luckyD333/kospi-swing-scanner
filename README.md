# KOSPI Swing Scanner — Strategy D v2

KOSPI/KOSDAQ 일봉 기반 단기 스윙(1~3일 보유) 매수 후보 자동 스크리닝 시스템.

- **Strategy**: 로스 카메론의 RSI + 볼린저 밴드 + 쌍바닥 + 장악형 양봉
- **데이터**: KRX Proxy(공식) + 네이버 금융(수정주가) + pykrx(보조)
- **타깃**: 시총 2천억~3조원 중소형주, Long Only, 1~3일 보유

## 🚀 빠른 시작 (5분)

### 1. 프로젝트 받기

```bash
# 옵션 A: zip 압축 해제 후 디렉토리로 이동
cd kospi-swing-scanner

# 옵션 B: 빈 디렉토리에서 시작 (수동 다운로드 시)
mkdir kospi-swing-scanner && cd kospi-swing-scanner
# (파일 리스트는 아래 "📁 파일 구조" 참고)
```

### 2. Python 가상환경 생성

```bash
# Python 3.10+ 권장
python3 -m venv .venv

# 활성화 (macOS/Linux)
source .venv/bin/activate

# 활성화 (Windows PowerShell)
.venv\Scripts\Activate.ps1
```

### 3. 의존성 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 동작 검증 (실제 네트워크 없이 mock 테스트)

```bash
# [1] 백테스트 엔진 단위 테스트 (58개)
pytest backtest_engine/tests/ -v

# [2] KRX Proxy + Circuit Breaker 테스트 (18개)
python tests/test_krx_proxy_mock.py

# [3] Strict 모드 엔드투엔드 검증 (3개)
python tests/test_strict_mode_e2e.py

# [4] 전체 스캐너 mock 데이터 테스트
python tests/test_daily_scanner_mock.py

# [5] 백테스트 엔진 데모 (6가지 시나리오)
python -m backtest_engine.demo
```

전부 통과하면 셋업 완료. 4개 스위트 합계 **80개 이상의 테스트**가 통과해야 합니다.

### 5. 실전 스캔 실행 (실제 KRX 데이터)

```bash
# 일반 모드 (KRX 실패 시 네이버 fallback)
python daily_only_scanner.py --market KOSPI --top 20

# 엄격 모드 (KRX 장애 시 즉시 중단 — 실전 권장)
python daily_only_scanner.py --market KOSPI --strict

# KRX 비활성화 (네이버만)
python daily_only_scanner.py --no-krx --market KOSPI

# 특정 날짜 기준
python daily_only_scanner.py --date 20260418 --top 30

# 시총 범위 조정 (기본 2천억~3조)
python daily_only_scanner.py --min-cap 1000 --max-cap 50000

# 다른 쌍바닥 detector 사용
python daily_only_scanner.py --detector fractal
python daily_only_scanner.py --detector prominence
```

### 6. 결과 확인

스캔 완료 후 콘솔에 매수 후보 + 진입가/손절/목표가가 출력되며, `scan_results/` 디렉토리에 JSON으로 저장됩니다.

```
────── #1  [005930] 삼성전자  ──────
   시총               :        3,500,000 억원
   20일 평균 거래량    :       12,345,678 주
   Confidence          :          75.0%

   💰 진입가 (매수)    :           75,000 원
   🛑 손절가           :           73,125 원 (-2.50%)
   🎯 1차 목표 (익절)  :           77,250 원 (+3.00%)
   🎯 2차 목표 (익절)  :           78,750 원 (+5.00%)
   ⏰ 최대 보유        : 3 거래일 (미도달 시 시간 손절)
```

## 📁 파일 구조

```
kospi-swing-scanner/
├── README.md                      # 이 문서
├── requirements.txt               # Python 의존성
├── .gitignore                     # Git 제외 파일
│
├── daily_only_scanner.py          # 메인 실전 스캐너 (CLI 진입점)
│
├── backtest_engine/               # Strategy D v2 백테스트 엔진
│   ├── __init__.py
│   ├── README.md
│   ├── core.py                    # 타입 + 지표 (RSI, BB, MACD, ATR)
│   ├── detectors.py               # 쌍바닥 감지 3가지 구현
│   ├── scenarios.py               # 가상 OHLCV 시나리오 6가지
│   ├── strategy.py                # Strategy D v2 진입/청산 로직
│   ├── engine.py                  # 백테스트 실행 엔진
│   ├── screener.py                # 다중 타임프레임 스크리너
│   ├── demo.py                    # 통합 실행 데모
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py            # pytest fixture
│       ├── test_core.py           # 8개 테스트
│       ├── test_detectors.py      # 11개 테스트
│       ├── test_strategy.py       # 17개 테스트
│       ├── test_engine.py         # 13개 테스트
│       └── test_screener.py       # 9개 테스트
│
├── tests/                         # 통합 테스트 (mock 데이터)
│   ├── test_krx_proxy_mock.py     # KRX Proxy + Circuit Breaker (18개)
│   ├── test_strict_mode_e2e.py    # Strict mode 동작 검증 (3개)
│   └── test_daily_scanner_mock.py # 스캐너 end-to-end (5개 검증)
│
└── docs/
    ├── strategy_d_v2_spec.md           # 전략 설계 문서
    └── korean_stock_data_sources_guide.md   # 데이터 소스 비교 가이드
```

## 📋 다운로드해야 할 파일 목록 (전체 22개)

수동으로 받는 경우 아래 순서대로 디렉토리/파일을 만드세요.

### 루트 (3개)

- [ ] `README.md` — 이 문서
- [ ] `requirements.txt`
- [ ] `.gitignore`

### CLI 메인 (1개)

- [ ] `daily_only_scanner.py`

### `backtest_engine/` (9개)

- [ ] `backtest_engine/__init__.py` (빈 파일)
- [ ] `backtest_engine/README.md`
- [ ] `backtest_engine/core.py`
- [ ] `backtest_engine/detectors.py`
- [ ] `backtest_engine/scenarios.py`
- [ ] `backtest_engine/strategy.py`
- [ ] `backtest_engine/engine.py`
- [ ] `backtest_engine/screener.py`
- [ ] `backtest_engine/demo.py`

### `backtest_engine/tests/` (7개)

- [ ] `backtest_engine/tests/__init__.py` (빈 파일)
- [ ] `backtest_engine/tests/conftest.py`
- [ ] `backtest_engine/tests/test_core.py`
- [ ] `backtest_engine/tests/test_detectors.py`
- [ ] `backtest_engine/tests/test_strategy.py`
- [ ] `backtest_engine/tests/test_engine.py`
- [ ] `backtest_engine/tests/test_screener.py`

### `tests/` (3개)

- [ ] `tests/test_krx_proxy_mock.py`
- [ ] `tests/test_strict_mode_e2e.py`
- [ ] `tests/test_daily_scanner_mock.py`

### `docs/` (2개)

- [ ] `docs/strategy_d_v2_spec.md`
- [ ] `docs/korean_stock_data_sources_guide.md`

**합계: 25개 파일** (빈 `__init__.py` 2개 포함)

## ⚙️ 환경변수 (선택)

```bash
# KRX Proxy URL 변경 (기본: https://k-skill-proxy.nomadamas.org)
export KSKILL_PROXY_BASE_URL="https://your-proxy.example.com"

# 로그 레벨 (Python logging)
export LOG_LEVEL=DEBUG
```

## 🛠 데이터 소스 우선순위

| 단계 | 소스 | 역할 |
|------|------|------|
| 1차 | KRX Proxy `trade-info` | 공식 시총 + 종가 (유니버스 필터) |
| 2차 | 네이버 `siseJson` | N일 OHLCV 시계열 (지표 계산) |
| 3차 | pykrx | KRX 라이브러리 (백업) |
| 4차 | FinanceDataReader | 추가 fallback |

`--strict` 옵션을 사용하면 KRX Proxy 장애 시 **스캔 전체 중단**합니다 (실전 안전 모드).

## 🧪 테스트 결과 (예상)

```
============================== 58 passed in 5s ===============================
🎉 모든 KRX Proxy 테스트 통과! (18개)
🎉 엄격 모드 동작 검증 완료 (3개)
🎉 모든 검증 통과! (Daily Scanner E2E)

총 80개 이상 테스트 통과
```

## 🆘 문제 해결

### `ModuleNotFoundError: No module named 'backtest_engine'`

테스트 실행 시 프로젝트 루트에서 실행하세요:
```bash
cd kospi-swing-scanner
PYTHONPATH=. pytest tests/
```

### `pykrx` 설치 실패

pykrx는 KRX 사이트 변경에 민감합니다. 실패 시 `--no-krx` 옵션으로 회피:
```bash
python daily_only_scanner.py --no-krx
```

### KRX Proxy 503 에러

서버 측 API 키 문제일 수 있습니다. 잠시 후 재시도하거나 `--no-krx` 옵션 사용:
```bash
python daily_only_scanner.py --no-krx --market KOSPI
```

### 네이버 크롤링 차단

너무 많은 요청을 보내면 네이버에서 임시 차단할 수 있습니다. 잠시 대기 후 재시도하세요.

## 📚 문서

- [`docs/strategy_d_v2_spec.md`](docs/strategy_d_v2_spec.md) — Strategy D v2 전략 설계
- [`docs/korean_stock_data_sources_guide.md`](docs/korean_stock_data_sources_guide.md) — 데이터 소스 비교
- [`backtest_engine/README.md`](backtest_engine/README.md) — 백테스트 엔진 사용법

## ⚠️ 면책 조항

본 도구는 정보 제공 및 학습 목적이며, 투자 조언이 아닙니다. 실제 투자 결정과 그 결과는 사용자 본인의 책임입니다. KRX 공식 데이터 기준이지만 데이터 정확성을 보증하지 않습니다.

## 라이선스

개인 사용. 상업적 사용 시 KRX 및 네이버 금융 데이터 사용 약관을 확인하세요.
