# Strategy D v2 백테스트 엔진

TDD 방식으로 구축한 **Strategy D v2 (단기 스윙 반등 포착)** 백테스트 엔진과 다중 타임프레임 스크리너.

## 구조

```
backtest_engine/
├── core.py          # 타입 + 지표 (RSI/BB/MACD/ATR)
├── detectors.py     # 쌍바닥 감지 3가지 구현 + 캔들 패턴
├── scenarios.py     # 가상 OHLCV 시나리오 빌더
├── strategy.py      # Strategy D v2 진입/청산 로직
├── engine.py        # 백테스트 엔진 + 자금 배분 전략
├── screener.py      # 다중 타임프레임 스크리너
├── demo.py          # 통합 실행 데모
└── tests/           # 58개 pytest 테스트
```

## 빠른 실행

```bash
# 전체 테스트 (58개)
python -m pytest backtest_engine/tests/ -v

# 데모 실행 (백테스트 + 스크리너 시연)
python -m backtest_engine.demo
```

## TDD로 해결한 3가지 주요 우려점

### 1. 쌍바닥 감지 알고리즘 부재 → 3가지 경쟁 구현

| 구현 | 방식 | 장점 | 단점 |
|------|------|------|------|
| `DoubleBottomSimple` | 좌우 swing_window 봉 비교 | 빠름, 구현 간단 | 노이즈 민감 |
| `DoubleBottomFractal` | Williams Fractal (5봉) | 엄격, 품질 높음 | 감지 빈도 낮음 |
| `DoubleBottomProminence` | scipy prominence | 얕은 바닥 필터 | 파라미터 튜닝 필요 |

**핵심 발견**: 2차 바닥의 rightward swing은 실전에서 확인 불가능 (미래 봉 필요). 
**"최근 freshness 봉 내 최저점 + 좌측 swing만 확인"** 방식으로 통일.

### 2. 자금 부족 처리 로직 → 2가지 Allocation Strategy

- `CashAllocationConservative`: 슬롯 가득 차거나 현금 부족 시 skip (기본값)
- `CashAllocationAggressive`: 기존 저 confidence 포지션 교체 옵션

### 3. 장 마감 10분 전 수급 타이밍 문제 → 전일 수급만 활용

`strategy.py`의 confidence 가산 조건에서 당일 수급 제외.

## 핵심 발견: RSI 타이밍 역설

처음엔 **진입 봉에서 RSI ≤ 30**을 요구했으나, TDD로 검증하니 **모든 완벽 시나리오에서 진입 실패**. 
이유: 장악형 양봉이 출현한 시점엔 이미 RSI가 과매도에서 회복 중.

해결: **"최근 10봉 내 RSI 과매도 이력 있음"** 으로 완화 — 이게 바로 
*"과매도 구간에서 반등이 시작된 종목"* 을 찾는 전략의 핵심.

## Strategy D v2 진입 조건

```
모든 필수 조건 AND:
├─ [조건 1] 최근 10봉 내 RSI(14) ≤ 32 이력
├─ [조건 2a] 연속 음봉 ≥ 3봉 (전봉까지) 
│   또는
│  [조건 2b] 최근 5봉 내 BB 하단 이탈
├─ [조건 3] 당일 또는 직전 봉 상승 장악형 양봉
├─ [조건 4] 쌍바닥 감지 (3가지 알고리즘 중 선택)
└─ [조건 5] 당일 봉이 양봉

Confidence 가산 (base 0.55):
├─ 2차 바닥이 BB 내부 형성            → +0.10
├─ 1차 바닥 거래량 ≥ 평균 × 2.0       → +0.10
├─ 2차 바닥 거래량 < 1차 × 0.5       → +0.10
└─ MACD 히스토그램 상승 중            → +0.10
```

## 청산 규칙 (우선순위)

1. **갭다운 손절** (시가 -3% 이상, 보유 1봉 이상): 시가에 청산
2. **고정 손절** (저가 ≤ -2.5%): 손절가 또는 시가 중 낮은 값
3. **2차 목표** (보유 2봉 이상, 고가 ≥ +5%): target_2에 청산
4. **1차 목표** (고가 ≥ +3%): target_1에 청산
5. **시간 손절** (3봉 경과): 당일 종가 청산

## 검증된 6가지 시나리오

| 시나리오 | 예상 결과 | 실제 결과 | 거래 비용 포함 PnL |
|---------|----------|----------|-------------------|
| perfect_double_bottom | win | ✓ win | +3.00% (target_1) |
| fake_double_bottom_loss | loss | ✓ loss | -2.50% (stop_loss) |
| gap_down_loss | loss | ✓ loss | -4.00% (gap_down) |
| time_stop_breakeven | loss | ✓ loss | -0.02% (time_stop) |
| no_signal_uptrend | no_trade | ✓ no_trade | - |
| choppy_no_signal | no_trade | ✓ no_trade | - |

## 다중 타임프레임 스크리너 사용

```python
from backtest_engine.screener import MultiTimeframeScreener
from backtest_engine.strategy import StrategyDConfig

screener = MultiTimeframeScreener(
    strategy_config=StrategyDConfig(min_lookback_bars=25),
    timeframes=["30m", "1h", "2h", "4h", "1D"],
)

# universe = {ticker: {timeframe: DataFrame}}
result = screener.scan_multi(universe)

# 상위 N개
for hit in result.top_by_confidence(10):
    print(f"{hit.ticker} ({hit.timeframe}): "
          f"진입 {hit.entry_price:.0f}, "
          f"손절 {hit.stop_loss:.0f}, "
          f"목표 {hit.target_1:.0f}/{hit.target_2:.0f}")

# 여러 TF 동시 시그널
confluence = result.multi_timeframe_confluence(min_timeframes=3)
```

## 실전 통합 포인트 (다음 단계)

이 엔진을 실제 KOSPI 데이터에 연결하려면:

1. **데이터 소스 연결**: pykrx로 일봉, KIS API로 분봉 수집
2. **타임프레임별 데이터 준비**: 1분봉 → `screener.resample_ohlcv()`로 상위 TF 생성
3. **유니버스 필터**: 시총 2천억~3조 + 유동성 필터 (Strategy D v2 스펙 참고)
4. **스케줄러**: 장 마감 10분 전 (15:20) cron으로 스크리너 실행
5. **실매매 연동**: KIS API 주문 실행

이 엔진 자체는 데이터 소스에 독립적이므로 한국 주식뿐 아니라 미국 주식, 코인 등에도 적용 가능.
