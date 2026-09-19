# KOSPI Swing Scanner

KOSPI/KOSDAQ 일봉 기반 1~7일 보유 단기 스윙 매수 후보 자동 스크리닝 시스템 (Strategy D v2: RSI + 볼린저 밴드 + 쌍바닥 + 장악형 양봉).

## Tech Stack
- **Runtime**: Python 3.10+
- **Core**: pandas, numpy, scipy
- **Data sources**: 네이버 금융 — `stock.naver.com` 주식 목록 JSON(KOSPI/KOSDAQ 종목·시총·거래량·PER/ROE/외인비율) + `etfItemList`(ETF) + `siseJson` API + `m.stock` 지수·`marketIndex/productDetail`(USD/KRW, WTI, 국고채3Y) + VIX(yfinance). 1D/1m raw, 30m/1h/4h는 1m 리샘플링.
- **Test**: pytest (현재 1319개)

## Project Structure
- `cli.py` — CLI 진입점 (스캔 + Phase 2 가중치 인터뷰 모드 `--interview`)
- `core/` — DataClient, OhlcvCache, universe, indicators, runner, dates
- `core/decision/` — 의사결정 엔진 (운영 신호 경로 순):
  - 기반: product_type(상품분류)·donchian(채널)·aggregator·ensemble(regime-aware)
  - 시장 국면: market_regime(HMM)·market_axes·market_breadth·per_ticker_regime·atr_volatility·fear_greed(Job A 수집)
  - 전략 공통: entry_gate(전략별 진입 게이트)·setup_quality(셋업 점수)·multi_timeframe·confirmation_strength(S1 한정)
  - runner 후처리: tradability_filter(거래가능 hard filter)·max_filter(급등 가드 EXCLUDE/PENALTY)
  - 출력/랭킹: regret_scorer·order_type_classifier(주문타입)·signal_status·factors/(momentum_3m·liquidity·signal_freshness)
  - 오프라인: factor_performance(weights.yml 산출, scripts/compute_weights)
  - 미배선(dormant): squeeze·donchian_levels(use_donchian_levels 기본 False)
- `strategies/` — 전략 plug-in (Strategy Protocol). 6개 전략 × 다중 TF + fallback 변형(r1/r2)
- `output/` — 포맷터 (table/json/csv/markdown/**signals_ui**) + signals_builder + snapshot_builder + holding_recommender
- `backtest_engine/` — Strategy D v2 백테스트 엔진 (core/detectors/strategy/engine/screener)
- `signal-api/` — FastAPI 서비스 (`/api/signals`, `/api/signals/{ticker}`). signals.json + market_snapshot.json 조인(`services/join.py`)
- `signal-web/` — Next.js 카탈로그/디테일 UI (`MarketRegimePanel`, `DetailClient`, RR/점수/ATR/RSI 표시)
- `scripts/` — collect.py (수집 + ETF + 매크로), backtest_run.py, wf_validate_*.py (WF 검증, wf_validate_s6.py 포함), wf_strategy_compare.py (6 전략 OOS 비교), aggregate_holding_recommendations.py (상황별 holding 집계)
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
- `strategy_six_channel_grid` — 추세선·채널 격자. 고점 2개 하락 추세선(레벨 0) 상향 돌파 후 격자선/상승 지지선을 위에서 리테스트하면 매수. 일봉 + 주봉(`strategy_six_channel_grid_w`, 같은 봉 수 규칙). 주봉 80봉 확보를 위해 일봉 수집·스캔 깊이 2년(`_DAILY_HISTORY_FLOOR_DAYS=760`, runner/cli `lookback_days=600`)(HMM 국면 창은 `REGIME_LOOKBACK_DAYS=180` 으로 고정). 목표가는 선 값(`apply_dynamic_trade_plan` 미호출)

## Verification
변경 후: `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` 통과 필수. 1319개 이상 통과해야 함.
정적 분석: `.venv/bin/ruff check . --exclude .venv` 통과 유지.

## Conventions
- 한국어 응답·주석 (technical term은 영어 유지)
- 외부 네트워크 의존 코드는 mock 테스트 작성 (실제 네이버 호출 금지)
- `etfItemList` API는 ETN(코드 7xxxxx)을 ETF와 혼합 반환 — `get_tickers("ETF")`는 코드 prefix로 제외, `get_etf_list()`(PR-B 분류기용)는 ETN 포함 유지. `build_universe`에서 ProductType.ETN 추가 필터
- 타입 힌트는 `dict[str, ...]` 등 Python 3.10+ 내장 타입 사용 (`typing.Dict` 금지)
- 신규 전략 추가 시 기존 전략 코드 무수정: `strategies/strategy_<n>_xxx.py` 작성(무인자 생성 가능 클래스면 `_autodiscover` 가 REGISTRY 등록) 후 **정책 맵 등록 필수**: `core/decision/entry_gate.py`(`ENTRY_GATE_POLICY` + `_normalize_family`), `core/trade_plan_calc.py`(`STRATEGY_PARAMS` + 정규식), `core/runner.py`(`_INVERSE_EXCLUDED_FAMILIES`, 추세 계열이면), `weights.yml` 3표, `output/signals_builder.py`(`_base_strategy`·`strategy_score_weights`·`_STRATEGY_LABELS`), `output/signal_components.py`, `core/strategy_performance.py`, `output/holding_recommender.py`, `signal-web/.../StrategyPerformanceChart.tsx`. 누락 시 대부분 예외 없이 조용히 실패한다(`tests/test_strategy_six_registration.py` 패턴으로 동기 테스트 작성)

## Documentation Index
전문 작업 시 관련 문서를 먼저 읽으세요:
- [Strategy D v2 spec](./docs/strategy_d_v2_spec.md) — 전략 진입/청산 규칙, 지표 파라미터
- [Korean stock data sources](./docs/korean_stock_data_sources_guide.md) — 네이버 금융 API 가이드
- [Backtest engine](./backtest_engine/README.md) — 엔진 모듈 사용법
- [Cron 자동화](./docs/cron_examples.md) — 수집/전략 schedule job 운영 예시
- [VM 배포 가이드](./docs/deploy.md) — DigitalOcean Droplet + signal-api/web + nginx + 로컬 dev 모드
- [Detailed README](./README.md) — CLI 옵션, 환경변수, 트러블슈팅
- [Trading system audit](./docs/audit/trading_system_audit.md) — 거래 시스템 감사 (CONDITIONAL PASS, High/Medium 이슈 + F1~F6 민감도)

*비핵심 문서는 필요 시에만 읽으세요.*

## Data Flow (SSOT)
운영 데이터는 **`data/signals.json`**(전략 결과) + **`data/market_snapshot.json`**(시장 raw) 2-파일.
signal-api 가 응답 시점에 `services/join.py`로 두 파일을 조인 — fundamentals/flow/external_links 는 latest snapshot 으로 override (live_quote/trade_plan 은 cli.py 동시점 freeze 유지).
weights.yml(가중치)는 `--interview` 실행 또는 git 배포로 생성. `strategy_weights_by_regime` (3-label BULL/NEUTRAL/BEAR 매트릭스)로 regime-aware ensemble을 적용한다. 구형 `fng_modifier`는 설정 호환용이며 runtime에는 적용하지 않는다. `.cache/regime_analysis.json`(시장 국면)은 `collect.py` 실행 시 HMM 분석으로 자동 생성.
`data/holding_recommendations.json`(상황별 최적 holding 추천)은 `scripts/aggregate_holding_recommendations.py` 로 WF 백테스트 결과를 marginal table 로 집계해 생성. signals_builder 가 응답 시점에 DecisionMeta.recommended_holding_bars/holding_confidence/holding_status 채움.

## Safety Note
이 파일은 완전하지 않아요. 복잡한 작업 전 관련 디렉토리를 검색해서 최신 컨텍스트를 확인하세요. 데이터 소스 변경(네이버 API 응답 포맷)은 코드보다 테스트 mock에 먼저 영향을 주므로 회귀 시 mock fixture부터 점검할 것.
`scan_results/manifest.json` 은 `--output-dir` 지정 시 자동 생성되는 latest 결과 인덱스.
`.cache/manifest.json` 은 `scripts/collect.py` 실행 후 생성되는 수집 현황 인덱스 (UI 로드용).
