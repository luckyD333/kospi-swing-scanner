# KOSPI Swing Scanner

KOSPI/KOSDAQ 일봉 기반 1~3일 보유 단기 스윙 매수 후보 자동 스크리닝 시스템 (Strategy D v2: RSI + 볼린저 밴드 + 쌍바닥 + 장악형 양봉).

## Tech Stack
- **Runtime**: Python 3.10+
- **Core**: pandas, numpy, scipy
- **Data sources**: 네이버 금융 (sise_market_sum 크롤링 + siseJson API). 1D/1m raw, 30m/1h/4h는 1m 리샘플링.
- **Test**: pytest

## Project Structure
- `cli.py` — CLI 진입점 (실전 스캐너, 멀티 전략)
- `core/` — DataClient, OhlcvCache, universe, indicators, runner
- `strategies/` — 전략 plug-in 디렉토리 (Strategy Protocol)
- `output/` — 출력 포맷터 (table/json/csv/markdown, 비교 포맷)
- `backtest_engine/` — Strategy D v2 백테스트 엔진 (core/detectors/strategy/engine/screener)
- `backtest_engine/tests/` — 엔진 단위 테스트
- `tests/` — 통합 테스트 (네이버 mock, CLI E2E)
- `scripts/` — collect.py (수집 전용), backtest_run.py
- `docs/` — 전략 스펙 + 데이터 소스 가이드

## Commands
```bash
# 의존성 설치
pip install -r requirements.txt

# 단위 테스트 (전체)
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q

# 백테스트 데모
python -m backtest_engine.demo

# 데이터 수집 (전략 실행 전 선행)
python scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D 1W 1h 30m

# 실전 스캔 — Strategy D v2 (결과 파일 저장)
python cli.py --strategy strategy_one_d_v2 --market KOSPI \
  --output-dir scan_results --format json --cache-root .cache

# 멀티 전략 비교
python cli.py --strategy all --format markdown
```

## Available Strategies
- `strategy_one_d_v2` — Mean Reversion (RSI+BB+쌍바닥+장악형 양봉), 일봉
- `strategy_one_1h_v2` / `strategy_one_30m_v2` / `strategy_one_w_v2` — 동일 전략, 타임프레임 변형
- `strategy_two_cross_sectional_momentum` — Jegadeesh-Titman 15일 상대 수익률
- `strategy_three_trend_following` — Donchian 20일 채널 돌파

## Verification
변경 후: `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` 통과 필수. 268개 이상 통과해야 함.
정적 분석: `.venv/bin/ruff check . --exclude .venv` 통과 유지.

## Conventions
- 한국어 응답·주석 (technical term은 영어 유지)
- 외부 네트워크 의존 코드는 mock 테스트 작성 (실제 네이버 호출 금지)
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
- [Detailed README](./README.md) — CLI 옵션, 환경변수, 트러블슈팅

*비핵심 문서는 필요 시에만 읽으세요.*

## Safety Note
이 파일은 완전하지 않아요. 복잡한 작업 전 관련 디렉토리를 검색해서 최신 컨텍스트를 확인하세요. 데이터 소스 변경(네이버 API 응답 포맷)은 코드보다 테스트 mock에 먼저 영향을 주므로 회귀 시 mock fixture부터 점검할 것.
`scan_results/manifest.json` 은 `--output-dir` 지정 시 자동 생성되는 latest 결과 인덱스.
`.cache/manifest.json` 은 `scripts/collect.py` 실행 후 생성되는 수집 현황 인덱스 (UI 로드용).
