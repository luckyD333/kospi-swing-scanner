# KOSPI Swing Scanner — Multi-Strategy

KOSPI/KOSDAQ 일봉 기반 단기 스윙 매수 후보 자동 스크리닝 시스템.
plug-and-play 가능한 전략 아키텍처(Strategy Protocol)를 채택해 신규 패러다임을
파일 추가만으로 등록할 수 있다.

- **Strategy 1**: Strategy D v2 — RSI + 볼린저 밴드 + 쌍바닥 + 장악형 양봉 (Mean Reversion)
- **Strategy 2**: Cross-sectional Momentum (Jegadeesh-Titman 1993) — 15일 상대 수익률 상위 25%
- **Strategy 3**: Time-series Trend-Following (Moskowitz-Ooi-Pedersen 2012) — Donchian 20일 채널 돌파
- 학술·실무 리서치 출처: [`docs/research/2026-04-30-screening-theories.md`](docs/research/2026-04-30-screening-theories.md)
- **데이터**: 네이버 금융 (sise_market_sum 크롤링 + siseJson API). 1D/1m raw, 30m/1h/4h는 1m 리샘플링.
- **타깃**: 시총 2천억~3조원 중소형주, Long Only, 1~3일 보유

---

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

### 2. 동작 검증 (네트워크 없이)

```bash
# 전체 테스트 (268+ tests)
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q
```

### 3. 실전 스캔 실행

```bash
# 단일 전략 (기본 — 네트워크 필요)
python cli.py --strategy strategy_one_d_v2 --market KOSPI --top 20

# 멀티 전략 동시 실행 — 비교 테이블 출력
python cli.py --strategy all --top 10 --format markdown

# 전체 옵션
python cli.py --help
```

---

## 📋 시나리오별 실행 방법

### 시나리오 1: [매일 운영] 수집 → 스캔 → 결과 저장

장 마감 후 매일 실행하는 기본 운영 플로우.

```bash
# 1단계: 데이터 수집 (장 마감 후, KOSPI 일봉·주봉·1h·30m)
python scripts/collect.py \
  --market KOSPI \
  --cache-root .cache \
  --timeframes 1D 1W 1h 30m \
  --smart-skip               # 이미 최신 데이터가 있는 종목 skip

# 2단계: 전략별 스캔 — 결과를 파일로 저장 (각 전략 독립 실행)
python cli.py \
  --strategy strategy_one_d_v2 \
  --cache-root .cache \
  --output-dir scan_results \
  --format json

python cli.py \
  --strategy strategy_two_cross_sectional_momentum \
  --cache-root .cache \
  --output-dir scan_results \
  --format json

# 3단계: manifest 확인 — UI가 읽을 latest 결과 인덱스
cat scan_results/manifest.json | python -m json.tool
```

결과 파일 위치: `scan_results/{YYYY-MM-DD}/{tf}/scan_*.json`
Latest 인덱스: `scan_results/manifest.json`

---

### 시나리오 2: [결과 조회] 저장된 파일 로드

`scan_results/manifest.json` 을 기준으로 최신 결과를 찾아 읽어요.

```bash
# manifest에서 전략별 latest 파일 경로 확인
python -c "
import json
from pathlib import Path
manifest = json.loads(Path('scan_results/manifest.json').read_text())
for key, entry in manifest.items():
    print(f'{key}: {entry[\"latest_file\"]} ({entry[\"date\"]})')
"
```

Python 코드에서 직접 로드:

```python
import json
from pathlib import Path

# 스캔 결과 로드
manifest = json.loads(Path("scan_results/manifest.json").read_text())
entry = manifest["strategy_one_d_v2__1D"]
result = json.loads((Path("scan_results") / entry["latest_file"]).read_text())

# 상위 후보 출력
for c in result["candidates"][:5]:
    print(f"#{c['rank']} {c['ticker']} {c['name']}  score={c['score']:.3f}")

# 수집 현황 로드
collect_manifest = json.loads(Path(".cache/manifest.json").read_text())
print(f"수집 완료: {collect_manifest['collected_at']}")
print(f"총 종목: {collect_manifest['summary']['total_tickers']}")
```

---

### 시나리오 3: [오프라인 스캔] 캐시 기반 스캔 (네트워크 없음)

`--cache-root` 지정 시 수집된 parquet 만 읽고 네트워크 OHLCV 요청을 하지 않아요.

```bash
# 캐시로 일봉 스크리닝
python cli.py --cache-root .cache --strategy strategy_one_d_v2

# 30분봉 분석
python cli.py --cache-root .cache --timeframes 30m --top 10 --format markdown

# 특정 날짜 기준
python cli.py --cache-root .cache --timeframes 30m --date 20260501

# 30분봉 + 일봉 멀티 TF 비교
python cli.py --cache-root .cache --timeframes 1D 30m --format markdown
```

---

### 시나리오 4: [수동 스캔] 실시간 단독 실행

캐시 없이 네트워크에서 직접 수집 + 스캔 (개발·테스트용).

```bash
# Mean Reversion 일봉 (기본)
python cli.py --strategy strategy_one_d_v2

# 1시간봉 (단기 노이즈 감지)
python cli.py --strategy strategy_one_1h_v2

# 주봉 (큰 그림)
python cli.py --strategy strategy_one_w_v2

# Cross-sectional Momentum (Jegadeesh-Titman)
python cli.py --strategy strategy_two_cross_sectional_momentum

# Trend Following — Donchian 20일 채널
python cli.py --strategy strategy_three_trend_following
```

---

### 시나리오 5: [멀티 전략 비교]

```bash
# 모든 전략 동시 실행 — markdown 비교 테이블
python cli.py --strategy all --format markdown

# CSV로 저장해 스프레드시트 분석
python cli.py --strategy all --format csv > results_$(date +%Y%m%d).csv

# JSON — 프로그래매틱 처리
python cli.py --strategy all --format json | python -m json.tool
```

---

### 시나리오 6: [필터 조정] 시장·시총·유동성

```bash
# KOSDAQ
python cli.py --market KOSDAQ

# 소형주 집중 (1천억~5천억)
python cli.py --min-cap 1000 --max-cap 5000

# 대형주 제외 + 유동성 강화 (최소 거래량 50만주)
python cli.py --max-cap 20000 --min-volume 500000

# 빠른 테스트 (상위 100종목만)
python cli.py --max-universe 100

# lookback 기간 조정
python cli.py --lookback-days 60    # 짧은 lookback (최근 추세 반영)
python cli.py --lookback-days 120   # 긴 lookback (안정적)
```

---

### 시나리오 7: [특정 날짜 분석]

```bash
# 지난 금요일 기준
python cli.py --date 20260424 --top 30

# 날짜 + JSON 출력
python cli.py --date 20260418 --format json | python -m json.tool
```

---

### 시나리오 8: [증분 수집] 이미 있는 데이터 재사용

```bash
# 기본 수집 (90일, KOSPI 일봉·주봉·1h·30m)
python scripts/collect.py

# 이미 수집된 종목 skip (빠른 재실행)
python scripts/collect.py --timeframes 1D 30m --skip-collected

# 10분 주기 cron용 — TF별 마지막 수집 시각 기준 skip
python scripts/collect.py --timeframes 1D 30m --smart-skip

# KOSDAQ + 유니버스 제한
python scripts/collect.py --market KOSDAQ --max-universe 300
```

`scripts/collect.py` 주요 옵션:

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--market` | `KOSPI` | `KOSPI` / `KOSDAQ` / `KRX` |
| `--cache-root` | `.cache` | parquet 저장 루트 |
| `--timeframes` | `1D` | 수집할 TF 목록 |
| `--max-universe` | `500` | 시총 상위 N 종목 |
| `--lookback-days` | `90` | 수집 기간 |
| `--skip-collected` | off | 캐시 파일 이미 있는 종목 skip |
| `--smart-skip` | off | TF별 마지막 수집 시각 기준 skip |

---

### 시나리오 9: [cron 자동화] 매일 스케줄 등록

자세한 crontab entry 예시 → [`docs/cron_examples.md`](docs/cron_examples.md)

요약:

```bash
# crontab -e 로 등록 (예시)

# 매일 23:00 수집
0 23 * * 1-5 cd /path/to/kospi-swing-scanner && .venv/bin/python scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D 1W 1h 30m --smart-skip >> logs/collect.log 2>&1

# 매일 23:30 전략1 스캔 (수집 완료 후)
30 23 * * 1-5 cd /path/to/kospi-swing-scanner && .venv/bin/python cli.py --strategy strategy_one_d_v2 --cache-root .cache --output-dir scan_results --format json >> logs/scan_strategy_one.log 2>&1

# 매일 23:35 전략2 스캔
35 23 * * 1-5 cd /path/to/kospi-swing-scanner && .venv/bin/python cli.py --strategy strategy_two_cross_sectional_momentum --cache-root .cache --output-dir scan_results --format json >> logs/scan_strategy_two.log 2>&1
```

---

### 시나리오 10: [신규 전략 추가] 기존 전략 무수정

1. `strategies/strategy_four_xxx.py` 작성

   ```python
   from core.strategy_base import Candidate, ScanContext

   class StrategyFourXxx:
       name = "strategy_four_xxx"
       def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
           ...
   ```

2. `strategies/__init__.py` 에 2줄 추가 (기존 코드 수정 없음)

   ```python
   from .strategy_four_xxx import StrategyFourXxx
   REGISTRY["strategy_four_xxx"] = StrategyFourXxx
   ```

3. 단위 테스트 + `tests/test_ocp.py` 통과 확인
4. cron entry 한 줄 추가

이후 `python cli.py --strategy strategy_four_xxx` 또는 `--strategy all` 로 자동 노출.

---

### 시나리오 11: [개발] 테스트 + 정적 분석

```bash
# 전체 테스트
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q

# 특정 모듈만
.venv/bin/python -m pytest tests/test_cli.py -v
.venv/bin/python -m pytest tests/test_integration.py -v

# 정적 분석
.venv/bin/ruff check . --exclude .venv

# 백테스트 데모
python -m backtest_engine.demo
```

---

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
   │   └─ Strategy.scan()   ×  N개 전략                        │
   └────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │  strategies/  (Strategy Protocol 구현체들)                 │
   │   ├─ strategy_one_d_v2       Mean Reversion + Confluence  │
   │   ├─ strategy_two_cross_...  Cross-sectional Momentum     │
   │   └─ strategy_three_trend_.. Donchian 20일 채널 돌파       │
   └──────────────────────────────────────────────────────────┘
```

- 동일 `ScanContext` (universe + OHLCV + 시총) 입력에서 모든 전략이 동일 데이터를 본다.
- `OhlcvCache` 가 같은 (ticker, start, end) 키 재요청을 캐시 처리하여 **fetch 1회**.
- 각 전략 실행은 격리되어, 한 전략의 예외가 다른 전략을 막지 않는다.

---

## 📁 파일 구조

```
kospi-swing-scanner/
├── README.md
├── requirements.txt
├── CLAUDE.md
│
├── cli.py                            # 스캔 CLI 진입점
│
├── scripts/                          # 독립 실행 스크립트
│   ├── collect.py                    #   데이터 수집 전용 (parquet → .cache/)
│   └── backtest_run.py               #   백테스트 일괄 실행
│
├── core/                             # 공통 모듈
│   ├── cache/                        #   OhlcvDiskCache (parquet R/W)
│   ├── data_sources/                 #   DailyDataSource ABC + 네이버 구현
│   ├── data_fetch.py                 #   DataClient + OhlcvCache
│   ├── universe.py                   #   build_universe + UniverseFilter
│   ├── indicators.py                 #   RSI/BB/MACD/ATR/MA/모멘텀/거래량 z-score
│   ├── strategy_base.py              #   Strategy Protocol + ScanContext + Candidate
│   └── runner.py                     #   ScanRunner (단일 fetch, N전략)
│
├── strategies/                       # 전략 구현체들 (plug-in)
│   ├── __init__.py                   #   REGISTRY dict + register/unregister
│   ├── strategy_one_d_v2.py          #   Strategy 1: Mean Reversion + Confluence
│   ├── strategy_two_cross_sectional_momentum.py  # Strategy 2: 상대 수익률
│   └── strategy_three_trend_following.py         # Strategy 3: Donchian 돌파
│
├── output/                           # 출력 포맷터
│   ├── formatters.py                 #   table / json(표준 schema) / csv / markdown
│   └── comparison.py                 #   멀티 전략 비교 포맷
│
├── backtest_engine/                  # 백테스트 엔진
│   ├── core.py / detectors.py / strategy.py / engine.py / screener.py
│   ├── demo.py                       #   통합 데모
│   └── tests/                        #   엔진 단위 테스트
│
├── tests/                            # 통합 테스트 (네이버 mock, CLI E2E)
│   ├── fixtures/
│   ├── test_core_*.py
│   ├── test_cli.py / test_collect.py
│   ├── test_ocp.py                   #   Open-Closed 검증
│   └── test_integration.py
│
└── docs/
    ├── strategy_d_v2_spec.md
    ├── korean_stock_data_sources_guide.md
    ├── cron_examples.md              # schedule job 운영 예시
    └── research/
```

---

## 🛠 데이터 소스

| 종류 | 소스 | 비고 |
|------|------|------|
| 종목 리스트 + 추정 시총 | 네이버 `sise_market_sum` (페이지 크롤링) | KOSPI/KOSDAQ |
| 일봉/분봉 OHLCV | 네이버 `siseJson` API (수정주가) | `timeframe=day` 또는 `minute` |
| 30m / 1h / 2h / 4h | 네이버 1m → 리샘플링 | `core/runner.py` 내부 처리 |

---

## 🧪 테스트 구성

```
backtest_engine/tests/   엔진 단위 (core/detectors/strategy/engine/screener)
tests/test_core_*        core/ 모듈 단위 (indicators/data_fetch/universe/runner)
tests/test_collect.py    collect.py + manifest 검증
tests/test_cli.py        CLI argparse + 4종 출력 포맷 + manifest E2E
tests/test_ocp.py        Open-Closed (신규 전략 등록·실행)
tests/test_integration   멀티 전략 fetch 공유 + 비교 테이블
tests/test_daily_scanner_mock  E2E 시나리오
```

---

## 🆘 트러블슈팅

### `ModuleNotFoundError: No module named 'core'`
프로젝트 루트에서 실행하세요:
```bash
cd kospi-swing-scanner
PYTHONPATH=. pytest tests/
```

### 네이버 응답 변경/차단
사이트 구조 변경 시 `core/data_sources/naver.py` 의 셀렉터/엔드포인트 업데이트 필요.
회귀 발생 시 `tests/fixtures/` 의 mock fixture 먼저 점검.

### `scan_results/manifest.json` 없음
`--output-dir` 옵션 없이 실행하면 파일을 저장하지 않아요. 저장하려면:
```bash
python cli.py --strategy strategy_one_d_v2 --output-dir scan_results --format json
```

---

## 📚 문서

- [`docs/strategy_d_v2_spec.md`](docs/strategy_d_v2_spec.md) — Strategy D v2 전략 설계
- [`docs/korean_stock_data_sources_guide.md`](docs/korean_stock_data_sources_guide.md) — 데이터 소스 비교
- [`docs/cron_examples.md`](docs/cron_examples.md) — 수집/전략 schedule job 운영 예시
- [`backtest_engine/README.md`](backtest_engine/README.md) — 백테스트 엔진 사용법

---

## ⚠️ 면책 조항

본 도구는 정보 제공 및 학습 목적이며, 투자 조언이 아닙니다. 실제 투자 결정과 그 결과는
사용자 본인의 책임입니다. KRX 공식 데이터 기준이지만 데이터 정확성을 보증하지 않습니다.

## 라이선스

개인 사용. 상업적 사용 시 KRX 및 네이버 금융 데이터 사용 약관을 확인하세요.
