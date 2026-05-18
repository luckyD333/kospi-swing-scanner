# KOSPI Swing Scanner

KOSPI/KOSDAQ 일봉 기반 1~3일 보유 단기 스윙 매수 후보 자동 스크리닝 시스템 (Strategy D v2: RSI + 볼린저 밴드 + 쌍바닥 + 장악형 양봉).

## Tech Stack
- **Runtime**: Python 3.10+
- **Core**: pandas, numpy, scipy
- **Data sources**: 네이버 금융 — `sise_market_sum`(KOSPI/KOSDAQ 크롤링) + `etfItemList`(ETF) + `siseJson` API + `marketindex`(USD/KRW, WTI, 국고채3Y, VIX 매크로). 1D/1m raw, 30m/1h/4h는 1m 리샘플링.
- **Test**: pytest (현재 542개)

## Project Structure
- `cli.py` — CLI 진입점 (스캔 + Phase 2 가중치 인터뷰 모드 `--interview`)
- `core/` — DataClient, OhlcvCache, universe, indicators, runner, dates
- `core/decision/` — 의사결정 엔진 (aggregator, ensemble, market_regime HMM, market_axes, market_breadth, regret_scorer)
- `strategies/` — 전략 plug-in (Strategy Protocol). 5개 전략 × 다중 TF + fallback 변형(r1/r2)
- `output/` — 포맷터 (table/json/csv/markdown/**signals_ui**) + signals_builder + snapshot_builder
- `backtest_engine/` — Strategy D v2 백테스트 엔진 (core/detectors/strategy/engine/screener)
- `signal-api/` — FastAPI 서비스 (`/api/signals`, `/api/signals/{ticker}`). signals.json + market_snapshot.json 조인(`services/join.py`)
- `signal-web/` — Next.js 카탈로그/디테일 UI (`MarketRegimePanel`, `DetailClient`, RR/점수/ATR/RSI 표시)
- `scripts/` — collect.py (수집 + ETF + 매크로), backtest_run.py
- `tests/` — 통합 테스트 (네이버 mock, CLI E2E, decision/market_axes/breadth/regret)
- `docs/` — 전략 스펙, 데이터 소스, 배포(`deploy.md`), cron 가이드

## Commands
```bash
# 의존성 설치
pip install -r requirements.txt

# 단위 테스트 (전체)
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q

# 백테스트 데모
python -m backtest_engine.demo

# Job A: 시장 데이터 수집 (장 마감 후 1회) — KOSPI/KOSDAQ + ETF + 매크로
python scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D 1W 1h 30m

# Job B: 전략 실행 + UI 직접 소비 포맷 (signals.json 생성, SSOT)
python cli.py --strategy all --cache-root .cache --output-dir data --format signals_ui

# 단일 전략 + 결과 파일 저장
python cli.py --strategy strategy_one_d_v2 --market KOSPI \
  --output-dir scan_results --format json --cache-root .cache

# Phase 2: 가중치 인터뷰 → weights.yml 생성 (최초 1회)
python cli.py --interview
```

## Available Strategies
- `strategy_one_d_v2` (+ `_w_v2`/`_1h_v2`/`_30m_v2`) — Mean Reversion (RSI+BB+쌍바닥+장악형 양봉)
- `strategy_one_*_r1` / `_r2` — 동일 전략 fallback 변형(engulf_strict 완화, db_freshness=4). 0건 시 자동 시도
- `strategy_two_cross_sectional_momentum` (+ `_1h`/`_30m`) — Jegadeesh-Titman 15일 상대 수익률
- `strategy_three_trend_following` (+ `_1h`/`_30m`) — Donchian 20일 채널 돌파
- `strategy_four_pullback_ma` (+ `_1h`/`_30m`) — MA20 추세 + MA5 눌림목 회복
- `strategy_five_bull_flag` (+ `_1h`/`_30m`) — Flagpole +8% → flag 거래량 수축 → 돌파

## Verification
변경 후: `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` 통과 필수. 1071개 이상 통과해야 함.
정적 분석: `.venv/bin/ruff check . --exclude .venv` 통과 유지.

## Conventions
- 한국어 응답·주석 (technical term은 영어 유지)
- 외부 네트워크 의존 코드는 mock 테스트 작성 (실제 네이버 호출 금지)
- `etfItemList` API는 ETN(코드 7xxxxx)을 ETF와 혼합 반환 — `get_tickers("ETF")`는 코드 prefix로 제외, `get_etf_list()`(PR-B 분류기용)는 ETN 포함 유지. `build_universe`에서 ProductType.ETN 추가 필터
- 타입 힌트는 `dict[str, ...]` 등 Python 3.10+ 내장 타입 사용 (`typing.Dict` 금지)
- 신규 전략 추가 시 기존 전략 코드 무수정: `strategies/strategy_four_xxx.py` 작성 후
  `strategies/__init__.py` 에 2줄만 추가 (`from .strategy_four_xxx import StrategyFourXxx` +
  `REGISTRY["strategy_four_xxx"] = StrategyFourXxx`)

## Documentation Index
전문 작업 시 관련 문서를 먼저 읽으세요:
- [Strategy D v2 spec](./docs/strategy_d_v2_spec.md) — 전략 진입/청산 규칙, 지표 파라미터
- [Korean stock data sources](./docs/korean_stock_data_sources_guide.md) — 네이버 금융 API 가이드
- [Backtest engine](./backtest_engine/README.md) — 엔진 모듈 사용법
- [Cron 자동화](./docs/cron_examples.md) — 수집/전략 schedule job 운영 예시
- [VM 배포 가이드](./docs/deploy.md) — DigitalOcean Droplet + signal-api/web + nginx + 로컬 dev 모드
- [Detailed README](./README.md) — CLI 옵션, 환경변수, 트러블슈팅

*비핵심 문서는 필요 시에만 읽으세요.*

## Data Flow (SSOT)
운영 데이터는 **`data/signals.json`**(전략 결과) + **`data/market_snapshot.json`**(시장 raw) 2-파일.
signal-api 가 응답 시점에 `services/join.py`로 두 파일을 조인 — fundamentals/flow/external_links 는 latest snapshot 으로 override (live_quote/trade_plan 은 cli.py 동시점 freeze 유지).
weights.yml(가중치)는 `--interview` 실행 또는 git 배포로 생성. `.cache/regime_analysis.json`(시장 국면)은 `collect.py` 실행 시 HMM 분석으로 자동 생성.

## Safety Note
이 파일은 완전하지 않아요. 복잡한 작업 전 관련 디렉토리를 검색해서 최신 컨텍스트를 확인하세요. 데이터 소스 변경(네이버 API 응답 포맷)은 코드보다 테스트 mock에 먼저 영향을 주므로 회귀 시 mock fixture부터 점검할 것.
`scan_results/manifest.json` 은 `--output-dir` 지정 시 자동 생성되는 latest 결과 인덱스.
`.cache/manifest.json` 은 `scripts/collect.py` 실행 후 생성되는 수집 현황 인덱스 (UI 로드용).
