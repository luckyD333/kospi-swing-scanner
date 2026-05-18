# KOSPI Swing Scanner

KOSPI/KOSDAQ 스윙 매매 후보 자동 스크리닝 시스템.
전략 실행 → 랭킹 산출 → UI 직접 소비 가능한 signals.json 생성.

## 빠른 시작

### 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3-Job 운영 워크플로우

| Job | 명령어 | 출력 | 주기 |
|-----|--------|------|------|
| A: 시장 데이터 수집 | `python scripts/collect.py ...` | `.cache/{tf}/{ticker}.parquet` + `data/market_snapshot.json` | 매일 장 마감 후 1회 |
| B-일봉 | `python cli.py --format signals_ui ...` | `data/signals.json` (SSOT) | Job A 완료 후 1회 |
| B-장중 (30m/1h) | `collect.py + cli.py 페어링` | `data/signals.json` | 장 중 30분마다 (09:01, 09:31 …) |
| C: 실시간 현재가 | `python scripts/collect_live.py` | `data/market_snapshot.json` 부분 갱신 | 장 중 2분마다 (09:00~15:59) |

> **TF별 재계산 필요 주기**: 1D/1W 전략은 장 마감 후 1회로 충분. 30m/1h 전략은 새 캔들이 확정되는 시점마다 재실행이 필요해요.
> 30m 파일은 디스크에 캐시되지 않고 매 실행마다 `.cache/1m/` parquet에서 리샘플링해 즉석 생성돼요.

#### Job A: 시장 데이터 수집

```bash
python scripts/collect.py --market KOSPI --cache-root .cache
```

출력: `data/market_snapshot.json` — KOSPI 전 종목 시장 데이터 (OHLCV + 펀더멘털 + 매크로)

#### Job B: 전략 실행 + 시그널 생성

```bash
python cli.py --strategy all --cache-root .cache --format signals_ui --output-dir data
```

출력: `data/signals.json` — UI 직접 소비 포맷 (Pydantic 검증 통과)

#### Job C: 실시간 현재가 갱신

```bash
python scripts/collect_live.py
```

`data/market_snapshot.json`의 `market_indices`(KOSPI/KOSDAQ/VIX/환율/WTI)와 시그널 종목 `current_price`만 경량 갱신해요.
Job A/B의 전체 OHLCV 수집 없이 수초 안에 완료되며, 2분 cron으로 장중 실시간성을 유지해요.
signal-api는 응답 시 이 값을 `live_quote`에 자동 반영해요.

### cron 예시

```cron
# Job A: 장 마감 후 시장 데이터 수집
0 16 * * 1-5  /path/to/.venv/bin/python scripts/collect.py --market KOSPI --cache-root .cache

# Job B (일봉): 수집 완료 후 1D/1W 전략 실행
30 16 * * 1-5 /path/to/.venv/bin/python cli.py --strategy all --cache-root .cache --format signals_ui --output-dir data

# Job B (장중): 30m/1h 전략 — bar close + 1분 지연 (09:01, 09:31, …, 15:31)
1,31 9-15 * * 1-5 /path/to/scripts/run_30m.sh

# Job C: 실시간 현재가 — 2분 주기 경량 갱신 (09:00~15:59)
*/2 9-15 * * 1-5 /path/to/.venv/bin/python scripts/collect_live.py
```

---

## 출력 포맷

### market_snapshot.json (Job A)

종목별 raw 시장 데이터. signals_builder가 Job B에서 읽음.

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-03T18:00:00+09:00",
  "market_indices": {"kospi": {"value": 2641.32, "change_pct": 0.84}},
  "tickers": {
    "001390": {
      "ticker": "001390", "name": "KG케미칼",
      "current_price": 7120, "change_pct": 0.71,
      "fundamentals": {"per": 11.2, "high_52w": 9120, "low_52w": 5050},
      "flow": {"foreign_ratio_pct": 18.5}
    }
  }
}
```

### signals.json (Job B)

UI 직접 소비. `_display` 서브객체로 포매팅 완료.

```json
{
  "signals": [{
    "ticker": "001390",
    "trade_plan": {"entry": 7070, "stop": 6820, "rr_ratio": 2.04, "rr_band": "SWEET"},
    "live_quote": {
      "current_price": 7120,
      "_display": {"current_price": "₩7,120", "change": "+0.71%", "direction": "up"}
    }
  }]
}
```

---

## 개발

### 테스트

```bash
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q
```

### 전략 추가

1. `strategies/strategy_four_xxx.py` 작성
2. `strategies/__init__.py`에 2줄 추가:
   ```python
   from .strategy_four_xxx import StrategyFourXxx
   REGISTRY["strategy_four_xxx"] = StrategyFourXxx
   ```

---

## 아키텍처

### 멀티 전략 구조

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
   │   │   └─ _r1/_r2 fallback (engulf 완화 → 0건 시 자동)     │
   │   ├─ strategy_two_cross_...  Cross-sectional Momentum     │
   │   ├─ strategy_three_trend_.. Donchian 20일 채널 돌파       │
   │   ├─ strategy_four_pullback_ma  MA20+MA5 눌림목 회복      │
   │   └─ strategy_five_bull_flag    Flagpole+8% → 압축 돌파   │
   │   * 모든 전략 1D / 1h / 30m 변형 (자동 등록)               │
   └──────────────────────────────────────────────────────────┘
                            │
                            ▼
   ┌──────────────────────────────────────────────────────────┐
   │  core/decision/  (Phase 2 의사결정 엔진)                   │
   │   ├─ aggregator       다축 가중합 ranking + breakdown     │
   │   ├─ ensemble         교차전략 합의도 점수                 │
   │   ├─ market_regime    HMM BULL/BEAR/SIDEWAYS              │
   │   ├─ market_axes      Trend score + Volatility regime     │
   │   ├─ market_breadth   상승비율 / MA20 상회 / 거래대금 상위 │
   │   └─ regret_scorer    "안 사면 후회" 비대칭 점수           │
   └──────────────────────────────────────────────────────────┘
```

동일 `ScanContext` 에서 모든 전략이 동일 데이터를 본다. `OhlcvCache` 가 같은 (ticker, start, end) 키 재요청을 캐시 처리하여 **fetch 1회**.

### 파일 구조

```
kospi-swing-scanner/
├── README.md
├── requirements.txt
├── CLAUDE.md
│
├── cli.py                            # 스캔 CLI 진입점
├── scripts/
│   ├── collect.py                    # 데이터 수집 전용 (Job A/B-장중)
│   ├── collect_live.py               # 실시간 현재가 경량 갱신 (Job C, 2분 cron)
│   └── backtest_run.py               # 백테스트 일괄 실행
│
├── core/                             # 공통 모듈
│   ├── cache/                        # OhlcvDiskCache (parquet R/W)
│   ├── data_sources/                 # DailyDataSource ABC + 네이버 구현 (ETF + 매크로)
│   ├── data_fetch.py                 # DataClient + OhlcvCache
│   ├── dates.py                      # 영업일 / 다중 TF 시간 유틸
│   ├── universe.py                   # build_universe + UniverseFilter
│   ├── indicators.py                 # RSI/BB/MACD/ATR/MA/모멘텀
│   ├── strategy_base.py              # Strategy Protocol + ScanContext
│   ├── runner.py                     # ScanRunner
│   └── decision/                     # Phase 2 의사결정 엔진
│       ├── aggregator.py / ensemble.py / config.py
│       ├── market_regime.py          # HMM BULL/BEAR/SIDEWAYS
│       ├── market_axes.py            # Trend score + Volatility regime
│       ├── market_breadth.py         # 상승비율 / MA20 상회 / 거래대금 상위
│       ├── regret_scorer.py          # 비대칭 후회 점수
│       └── runner.py / interview.py / factor_performance.py
│
├── strategies/                       # 전략 구현체 (plug-in)
│   ├── __init__.py                   # REGISTRY dict + autodiscover + FALLBACKS
│   ├── strategy_one_d_v2.py          # Mean Reversion (1D/1W/1h/30m + r1/r2)
│   ├── strategy_two_cross_sectional_momentum.py  # (1D/1h/30m)
│   ├── strategy_three_trend_following.py         # (1D/1h/30m)
│   ├── strategy_four_pullback_ma.py              # (1D/1h/30m)
│   └── strategy_five_bull_flag.py                # (1D/1h/30m)
│
├── output/                           # 출력 포맷터
│   ├── formatters.py                 # table/json/csv/markdown/signals_ui
│   ├── signals_builder.py            # signals.json 빌드 (Pydantic 검증)
│   ├── snapshot_builder.py           # market_snapshot.json 빌드
│   ├── models.py                     # 스키마
│   └── comparison.py                 # 멀티 전략 비교
│
├── signal-api/                       # FastAPI 서비스 (:8000)
│   └── app/
│       ├── api/signals.py            # /api/signals + /api/signals/{ticker}
│       └── services/
│           ├── signal_loader.py      # signals.json 로드
│           ├── market_loader.py      # market_snapshot.json 로드
│           └── join.py               # 응답 시 overlay (fundamentals/flow/RSI/links/live_quote)
│
├── signal-web/                       # Next.js UI (:3000)
│   └── src/
│       ├── app/                      # 라우트 (/, /signals/[ticker])
│       └── components/               # CatalogClient, DetailClient, MarketRegimePanel, ...
│
├── backtest_engine/                  # 백테스트 엔진
│   ├── core.py / detectors.py / strategy.py / engine.py / screener.py
│   ├── demo.py
│   └── tests/
│
├── tests/                            # 통합 테스트
│   ├── fixtures/
│   ├── test_core_*.py / test_dates.py
│   ├── test_market_axes.py / test_market_breadth.py / test_regret_scorer.py
│   ├── test_signals_builder.py / test_snapshot_builder.py
│   ├── test_decision_aggregator.py
│   ├── test_cli.py / test_collect.py
│   ├── test_ocp.py
│   └── test_integration.py
│
├── weights.yml                       # Phase 2 다축 가중치 (--interview 생성)
│
└── docs/
    ├── strategy_d_v2_spec.md
    ├── korean_stock_data_sources_guide.md
    ├── cron_examples.md
    ├── deploy.md                     # VM 배포 + 로컬 dev 모드
    └── research/
```

### 데이터 소스

| 종류 | 소스 | 비고 |
|------|------|------|
| 종목 리스트 + 추정 시총 | 네이버 `sise_market_sum` (크롤링) | KOSPI/KOSDAQ |
| ETF 유니버스 | 네이버 `etfItemList.nhn` JSON | 거래대금 상위 200 |
| 일봉/분봉 OHLCV | 네이버 `siseJson` API (수정주가) | timeframe=day 또는 minute |
| 30m / 1h / 4h | 네이버 1m → 리샘플링 | core/runner.py 내부 처리 |
| 매크로 지수 | 네이버 `marketindex` 스크래핑 | USD/KRW, WTI, 국고채3Y, VIX |

---

## 고급 사용법

### 캐시 기반 오프라인 스캔

```bash
# 캐시로만 스크리닝 (네트워크 요청 없음)
python cli.py --cache-root .cache --strategy strategy_one_d_v2
```

### 멀티 전략 비교

```bash
# 모든 전략 동시 실행 — markdown 테이블
python cli.py --strategy all --format markdown

# JSON 저장
python cli.py --strategy all --format json --output-dir scan_results
```

### Phase 2 — 가중치 인터뷰

```bash
# 가중치 인터뷰 (최초 1회) → weights.yml
python cli.py --interview
```

`weights.yml`은 ranking factor breakdown(`ensemble_score`, `momentum_pct`, `rr_ratio`, `roe`, `per`, `regime_score`)의 가중치를 정의해요. signals.json 의 `ranking.decision` 필드는 이 weights 로드 성공 시에만 채워져요.

### 필터 조정

```bash
# KOSDAQ
python cli.py --market KOSDAQ

# 소형주 집중 (1천억~5천억)
python cli.py --min-cap 1000 --max-cap 5000

# lookback 기간 조정
python cli.py --lookback-days 60    # 짧은 lookback
```

### 저장된 결과 조회

```bash
# manifest에서 latest 파일 경로 확인
python -c "
import json
from pathlib import Path
manifest = json.loads(Path('scan_results/manifest.json').read_text())
for key, entry in manifest.items():
    print(f'{key}: {entry[\"latest_file\"]} ({entry[\"date\"]})')
"

# 결과 로드
python -c "
import json
from pathlib import Path
manifest = json.loads(Path('scan_results/manifest.json').read_text())
entry = manifest['strategy_one_d_v2__1D']
result = json.loads((Path('scan_results') / entry['latest_file']).read_text())
for c in result['candidates'][:5]:
    print(f'#{c[\"rank\"]} {c[\"ticker\"]} {c[\"name\"]}  score={c[\"score\"]:.3f}')
"
```

---

## 트러블슈팅

### `ModuleNotFoundError: No module named 'core'`

프로젝트 루트에서 실행:
```bash
cd kospi-swing-scanner
PYTHONPATH=. pytest tests/
```

### 네이버 응답 변경

`core/data_sources/naver.py` 의 셀렉터/엔드포인트 업데이트 필요.
회귀 발생 시 `tests/fixtures/` 의 mock fixture 먼저 점검.

### `signals.json` 또는 `manifest.json` 없음

`--output-dir` 옵션 필수:
```bash
python cli.py --strategy all --format signals_ui --output-dir data
```

---

## 문서

- [Strategy D v2 spec](./docs/strategy_d_v2_spec.md) — 전략 진입/청산 규칙
- [Korean stock data sources](./docs/korean_stock_data_sources_guide.md) — 데이터 소스 가이드
- [Backtest engine](./backtest_engine/README.md) — 엔진 모듈 사용법
- [Cron 자동화](./docs/cron_examples.md) — schedule job 운영 예시
- [VM 배포 가이드](./docs/deploy.md) — DigitalOcean Droplet + signal-api/web + nginx + 로컬 dev 모드

## 면책 조항

본 도구는 정보 제공 및 학습 목적이며, 투자 조언이 아닙니다. 실제 투자 결정과 그 결과는 사용자 본인의 책임입니다.

## 라이선스

개인 사용. 상업적 사용 시 KRX 및 네이버 금융 데이터 사용 약관을 확인하세요.
