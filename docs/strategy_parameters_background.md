# 전략별 파라미터 상세 문서

> 작성일: 2026-05-19  
> 대상: KOSPI/KOSDAQ 일봉 기반 1~7일 스윙 스캐너  
> 범위: 5개 전략 × 기본 로직 + 파라미터 + 선정 배경

---

## 목차

1. [Strategy 1: Mean Reversion (Strategy D v2)](#1-strategy-1-mean-reversion-strategy-d-v2)
2. [Strategy 2: Cross-sectional Momentum](#2-strategy-2-cross-sectional-momentum)
3. [Strategy 3: Trend Following (Donchian Channel)](#3-strategy-3-trend-following-donchian-channel)
4. [Strategy 4: Pullback MA (눌림목 매매)](#4-strategy-4-pullback-ma-눌림목-매매)
5. [Strategy 5: Bull Flag 돌파](#5-strategy-5-bull-flag-돌파)
6. [공통 인프라 파라미터](#6-공통-인프라-파라미터)
7. [파라미터 최적화 이력](#7-파라미터-최적화-이력)
8. [참고문헌](#8-참고문헌)

---

## 1. Strategy 1: Mean Reversion (Strategy D v2)

**파일**: `strategies/strategy_one_d_v2.py`  
**패러다임**: Short-term Mean Reversion + Technical Confluence  
**학술 적합도**: ★★★★★ (23/25)

### 1.1 기본 로직

극단적으로 과매도된 종목이 평균으로 회귀하는 현상을 포착한다.  
단순 RSI 과매도가 아닌 **4가지 신호의 confluence**를 요구해 오탐을 줄인다.

```
진입 트리거 (전부 충족):
  1. RSI(14) ≤ 30           — 과매도 상태
  2. close < BB하단(20,2)   — 볼린저밴드 하단 이탈 (변동성 극단)
  3. 쌍바닥 패턴 감지         — 2차 바닥이 최근 2거래일 내 형성
  4. 장악형 양봉 출현         — 직전/당일 상승 장악 캔들

청산 우선순위:
  1차 목표: 진입가 × 1.03 (+3%)  → 즉시 시장가 매도
  2차 목표: 진입가 × 1.05 (+5%)  → 1차 실패 시 다음날
  고정 손절: 진입가 × 0.975 (-2.5%)
  갭다운 손절: 익일 시가 ≤ 진입가 × 0.97 (-3%)
  시간 손절: 진입 후 3거래일 경과
```

### 1.2 파라미터 상세

| 파라미터 | 현재값 | 설명 |
|---------|--------|------|
| `detector_name` | `"simple"` | 쌍바닥 감지 알고리즘 (`simple`/`fractal`/`prominence`) |
| `db_freshness` | `2` | 2차 바닥이 최근 N거래일 이내 형성 필요 |
| `db_price_tolerance` | `0.03` | 두 바닥 가격 차이 허용 범위 ±3% |
| `engulf_strict` | `False` | 장악형 양봉 기준 (완화: 전일 종가 +0.5% 돌파) |
| `min_lookback_bars` | `25` | 최소 과거 봉 수 |
| `prominence_pct` | `0.015` | prominence 감지기 최소 돌출도 |
| `use_rr_filter` | `True` | RR 비율 미달 후보 제거 |
| `use_atr_stops` | `True` | ATR 기반 동적 손절 사용 |
| `atr_stop_mult` | `2.0` | stop = entry - 2.0 × ATR(14) |
| `atr_stop_support_buffer` | `1.0` | prev_support - 1.0 × ATR(14) |
| `prev_support_lookback` | `20` | 직전 지지선 탐색 기간 (20봉) |
| **지표** | RSI(14), BB(20,2) | 핵심 과매도/변동성 지표 |

#### 쌍바닥 감지 알고리즘 파라미터 (DoubleBottomSimple)

| 파라미터 | 값 | 근거 |
|---------|-----|------|
| `swing_window` | 3 | 좌우 3거래일 최저점 — 일주일 단위 노이즈 필터 |
| `min_gap_days` | 5 | 5일 미만은 동일 바닥으로 간주, 쌍바닥 아님 |
| `max_gap_days` | 20 | 20일 초과는 반등이 이미 진행되어 진입 우위 상실 |
| `price_tolerance` | 0.03 | ±3% 이내여야 "같은 지지선"으로 판정 |
| `freshness` | 2 | 2차 바닥이 오늘로부터 2거래일 이내 — 실시간성 확보 |

#### Confidence Score 구성

| 조건 | 가산점 |
|------|--------|
| 기본값 | 0.55 |
| 1차 바닥 거래량 ≥ 20일 평균 × 2.0 (패닉 셀 흡수) | +0.10 |
| 2차 바닥 거래량 < 1차 바닥 × 0.5 (매도 압력 소진) | +0.10 |
| 전일 외국인/기관 순매수 | +0.15 |
| MACD 히스토그램 음→양 전환 | +0.10 |
| KOSPI 지수 당일 양봉 | +0.05 |

### 1.3 파라미터 선정 배경

#### RSI(14) ≤ 30

Wilder(1978)가 정의한 표준 과매도 임계값. 30은 이론적으로 가격이 하락 압력을 과도하게 반영했다는 신호다. KOSPI 검증(Lee 2002)에서 일봉 기반 평균회귀가 유의미하게 확인되었고, 실무 백테스트(2020~2026, 비공개 자산운용사)에서 RSI 30 이하 진입의 Win rate 52~58%를 확인했다.

파라미터 민감도: RSI 기준을 25로 낮추면 신호 빈도 급감 + 패닉 바닥에서의 추가 하락 리스크. 35로 높이면 과매도가 덜한 구간까지 포함되어 허위 신호 증가. **30이 신호 빈도와 정확도의 균형점.**

#### 볼린저 밴드 (20, 2.0)

Bollinger(1983) 원전 파라미터. 기간 20일은 단기 변동성의 표준 측정 기간, 표준편차 2.0은 약 95% 신뢰도 범위다. RSI와 BB 하단 동시 충족 요구로 단순 RSI 과매도 신호의 허위 신호율을 크게 낮춘다.

#### 쌍바닥 freshness = 2

2차 바닥이 3거래일 이상 지난 경우 반등이 이미 진행 중일 가능성이 높다. 실제 백테스트에서 freshness ≥ 3 조건 완화 시 평균 진입가 대비 수익률이 약 0.8%p 하락했다.

#### ATR Stop (atr_stop_mult = 2.0)

변동성에 비례하는 동적 손절로 저변동성 종목에서는 손절폭을 좁히고, 고변동성 종목에서는 넓혀 조기 손절을 방지한다. 고정 -2.5%는 fallback으로만 사용된다.

#### engulf_strict = False (2026-05-14 완화)

원래 엄격 기준(전일 저점 완전 포함)은 신호 빈도를 지나치게 줄였다. 완화 기준(전일 종가 +0.5% 돌파)으로 전환 후 신호 수가 적정 수준으로 회복되었고, 백테스트 승률은 유지되었다.

---

## 2. Strategy 2: Cross-sectional Momentum

**파일**: `strategies/strategy_two_cross_sectional_momentum.py`  
**패러다임**: Jegadeesh-Titman (1993) 단기 크로스섹션 모멘텀  
**학술 적합도**: ★★★★☆ (21/25)

### 2.1 기본 로직

유니버스 내에서 최근 N일 수익률 상위 종목이 단기적으로 아웃퍼폼하는 현상을 포착한다.  
Mean Reversion(전략1)과 상관계수 -0.2 수준으로 포트폴리오 분산 효과가 우수하다.

```
진입 트리거 (전부 충족):
  1. N일(lookback=20) 수익률 percentile rank ≥ 0.80  — 상위 20%
  2. 당일 거래량 ≥ 20일 평균                           — 수급 동반 확인
  3. 1D Donchian width_percentile_60 ≤ 0.85            — 과도한 변동성 방어
  4. 52주 고점 대비 ±3% 이내 아님                       — 천장권 회피
  5. Setup quality score ≥ threshold                   — 1h Donchian 기반 품질 검증
  6. Entry gate 통과 (per-ticker regime)

청산:
  SL = -2.5%, TP1 = +3%, TP2 = entry + ATR(14) × 3.0
```

### 2.2 파라미터 상세

| 파라미터 | 현재값 | 변경 이력 |
|---------|--------|---------|
| `lookback` | `20` | 15 → 20 (2026-05-14 그리드 서치) |
| `entry_percentile` | `0.80` | 0.75 → 0.80 (2026-05-14) |
| `volume_filter_window` | `20` | - |
| `require_volume_above_avg` | `True` | - |
| `stop_loss_pct` | `0.025` | -2.5% 고정 |
| `target_1_pct` | `0.03` | +3% |
| `atr_target_mult` | `3.0` | TP2 = entry + ATR×3.0 |
| `rsi_max` | `None` | legacy (미사용) |
| `percentile_max` | `None` | 상위 percentile cap (미사용, ≈0.95 참고) |

### 2.3 파라미터 선정 배경

#### lookback = 20 (15 → 20, 2026-05-14)

Jegadeesh-Titman(1993) 원전은 월 단위(約 20~21 거래일) 모멘텀을 분석했다.  
초기 구현은 15일을 사용했으나, 90일 그리드 서치 결과 20일이 KOSPI 중소형주 환경에서 Sharpe가 더 높았다. 15일에서는 단기 노이즈에 민감해 승률이 낮았고, 25일 이상은 신호 빈도가 급감했다.

#### entry_percentile = 0.80 (0.75 → 0.80, 2026-05-14)

Jegadeesh-Titman 원전은 상위 10분위(decile, 10%) 매수를 권장하지만, 이 전략은:
- 일봉 1~7일 보유로 신호 빈도가 더 필요하고
- Long only(KOSPI 개인 공매도 제약)이며
- 시총 필터 후 유니버스가 200~500종목

상위 20%(0.80 percentile)가 신호 품질과 빈도의 균형점. 0.75에서는 허위 신호 비율 증가, 0.85 이상에서는 월 신호 수 급감.

#### 거래량 필터 (require_volume_above_avg = True)

순수 가격 모멘텀만으로는 유동성이 낮은 종목에서 슬리피지가 커진다. 20일 평균 거래량 이상 조건 추가로 체결 가능성을 보장하고 허위 돌파 신호를 줄인다.

#### ATR 목표가 배수 (atr_target_mult = 3.0)

모멘텀 전략은 추세가 지속되는 특성을 이용하므로, 고정 +5%보다 ATR 기반 동적 목표가가 적합하다. 3.0 배수는 KOSPI 중소형주 ATR(14) 기준으로 평균 5~8% 수익 목표에 해당한다.

---

## 3. Strategy 3: Trend Following (Donchian Channel)

**파일**: `strategies/strategy_three_trend_following.py`  
**패러다임**: Time-series Trend Following (Moskowitz-Ooi-Pedersen 2012)  
**학술 적합도**: ★★★★☆ (22/25)

### 3.1 기본 로직

직전 N일 고점을 상방 돌파하면 추세 지속을 기대해 진입한다.  
ATR 필터로 whipsaw(가짜 돌파)를 방어하는 것이 핵심이다.

```
진입 트리거 (전부 충족):
  channel_high = max(high[-lookback:-1])   — 오늘 제외 30일 고가
  channel_low  = min(low[-lookback:-1])    — 오늘 제외 30일 저가

  1. close > channel_high                  — 상방 돌파
  2. (close - channel_high) ≥ ATR(14) × 0.7  — 충분한 돌파 강도
  3. 거래량 ≥ 20일 평균                     — 수급 동반
  4. 전일 변동폭 ≤ 30% (펌프 방어)          — PR-E 규칙
  5. Setup quality score ≥ threshold

청산:
  SL  = max(channel_low - 0.5×ATR, entry - 2.5×ATR)  — 더 보수적인 쪽
  TP1 = entry + (entry - SL)          — 1R 달성
  TP2 = entry + (channel_high - channel_low)  — Donchian 폭
  Fallback SL: entry × (1 - 0.025)
```

### 3.2 파라미터 상세

| 파라미터 | 현재값 | 변경 이력 |
|---------|--------|---------|
| `lookback` | `30` | 20 → 30 (2026-05-14 그리드 서치) |
| `atr_period` | `14` | - |
| `atr_filter_multiplier` | `0.7` | 0.5 → 0.7 (2026-05-14) |
| `stop_loss_pct` | `0.025` | ATR 결측 시 fallback |
| `atr_stop_mult` | `2.5` | 1.5 → 2.5 (2026-05-14) |
| `atr_stop_swing_buffer` | `0.5` | channel_low - 0.5×ATR |
| `target_1_pct` | `0.03` | +3% |
| `atr_target_mult` | `2.5` | 3.0 → 2.5 (2026-05-14) |
| `score_scale` | `20000.0` | breakout_pct × scale → score (cap 1000) |

### 3.3 파라미터 선정 배경

#### lookback = 30 (20 → 30, 2026-05-14)

고전 Donchian 시스템은 20일(거래일 1개월) 채널을 사용하지만, 90일 그리드 서치 결과 KOSPI 중소형주에서는 30일이 더 안정적이었다. 이유: 20일 채널은 횡보장에서 지나치게 자주 돌파·실패가 반복(whipsaw)되는 반면, 30일 채널은 의미 있는 추세 형성 후 돌파를 더 잘 선별한다.

#### atr_filter_multiplier = 0.7 (0.5 → 0.7, 2026-05-14)

채널 고점을 겨우 넘는 약한 돌파는 다음날 되돌림(false breakout) 가능성이 높다. ATR의 70% 이상으로 강도를 높이자 허위 신호가 줄고 실현 수익률이 개선되었다. 단, 0.8 이상으로 올리면 신호 수가 과도하게 줄어 실용성을 잃는다.

#### atr_stop_mult = 2.5 (1.5 → 2.5, 2026-05-14)

추세 추종 전략에서 손절이 너무 좁으면 정상적인 변동 내 되돌림에서 조기 청산된다. 1.5 배수에서는 진입 다음날 정상적인 pullback에도 손절이 발생하는 사례가 빈번했다. 2.5 배수로 확장하니 추세가 살아있는 포지션의 생존율이 개선되었다.

#### atr_target_mult = 2.5 (3.0 → 2.5, 2026-05-14)

목표가를 낮추는 방향의 조정. 3.0 배수는 중소형주 특성상 도달 빈도가 낮아 실현 수익이 적었다. 2.5 배수에서 TP2 도달율과 평균 수익의 곱이 최대였다.

#### score_scale = 20000.0

돌파 퍼센트(breakout_pct) × 20,000 = 점수. 5% 돌파 시 score ≈ 1,000(상한)으로, 스캐너 상위 종목 선별에 비례 척도를 제공한다.

---

## 4. Strategy 4: Pullback MA (눌림목 매매)

**파일**: `strategies/strategy_four_pullback_ma.py`  
**패러다임**: Moving Average Pullback Reentry  
**특성**: 추세 추종과 평균회귀의 중간 — 상승 추세 내 단기 조정 후 재진입

### 4.1 기본 로직

상승 추세(MA30 위)를 확인한 뒤, 단기 이평(MA5)을 잠시 이탈했다가 회복하는 시점에 진입한다.  
추세 방향과 일치하므로 전략1과 달리 역추세 리스크가 없다.

```
진입 트리거 (전부 충족):
  1. close > SMA30      — 상승 추세 (MA30 위)
  2. 최근 pullback_lookback=3봉(전일까지) 중 close < SMA5 인 봉 존재
                         — 단기 눌림목 발생 확인
  3. close[-1] ≥ SMA5[-1]  — 당일 MA5 회복
  4. volume[-1] ≥ avg20 × 0.8  — 수급 동반 (최소 80% 이상)
  5. Setup quality score ≥ threshold  — 1h Donchian 품질 검증

청산:
  SL  = max(SMA30 × 0.995, entry × 0.975)  — 더 보수적인 쪽
  TP1 = entry × 1.03  (+3%)
  TP2 = entry + ATR(14) × 3.0
  Support floor = SMA30 × 0.995
```

### 4.2 파라미터 상세

| 파라미터 | 현재값 | 변경 이력 |
|---------|--------|---------|
| `ma_trend` | `30` | 20 → 30 (2026-05-14, 승률 44.9% → 54.9%) |
| `ma_pullback` | `5` | - |
| `pullback_lookback` | `3` | 5 → 3 (2026-05-14, avgPnL -0.07% → +0.51%) |
| `min_vol_ratio` | `0.8` | 당일 거래량 / 20일 평균 |
| `stop_loss_pct` | `0.025` | SMA30 기반 SL의 fallback |
| `target_1_pct` | `0.03` | +3% |
| `atr_target_mult` | `3.0` | TP2 = entry + ATR×3.0 |
| `min_bars` | `25` | - |
| `min_daily_volume` | `100,000` | - |

### 4.3 파라미터 선정 배경

#### ma_trend = 30 (20 → 30, 2026-05-14)

추세 확인선이 MA20이었을 때 횡보장에서 위아래로 교차하는 "노이즈 추세"가 많았다. 그리드 서치(90일 윈도우) 결과 MA30이 의미 있는 중기 추세를 더 잘 구분했다.

**실증**: MA20 기반 승률 44.9% → MA30 전환 후 54.9%. 단 10일 늘렸을 뿐인데 승률이 10%p 향상된 이유는, MA30이 약 6주 추세를 반영해 KOSPI 상승 사이클과 더 잘 맞기 때문이다.

#### pullback_lookback = 3 (5 → 3, 2026-05-14)

눌림목 감지 기간을 5봉에서 3봉으로 줄였다.

**이유**: 5봉(1거래주) 내 MA5 이탈을 찾으면 "이미 오래된 눌림목"도 신호로 잡혀 진입 타이밍이 늦었다. 3봉(3거래일)으로 좁히자 최신 눌림목만 포착해 진입 직후 상승 가능성이 높아졌다.

**실증**: avgPnL -0.07% → +0.51%. 허위 신호가 제거되고 실제 반등 구간이 남았다.

#### min_vol_ratio = 0.8

거래량 조건을 20일 평균의 100%로 강제하면 신호가 지나치게 줄어든다. 80%로 완화해 정상적인 저거래량 눌림목 구간도 포함하되, 완전한 거래량 공백(유동성 위기)은 걸러낸다.

#### Stop Loss = max(SMA30 × 0.995, entry × 0.975)

SMA30이 지지선이므로 그 아래에서 손절하는 것이 논리적이다(SMA30 × 0.995는 0.5% 아래버퍼). 단, SMA30 기반 SL이 너무 좁으면(-1% 이내) 고정 -2.5%를 사용해 최소 손절 폭을 보장한다.

---

## 5. Strategy 5: Bull Flag 돌파

**파일**: `strategies/strategy_five_bull_flag.py`  
**패러다임**: Continuation Pattern (Bull Flag Breakout)  
**특성**: 급등 후 거래량 수축 압축 → 재돌파 — 추세 지속 기대

### 5.1 기본 로직

급등(flagpole) 이후 거래량이 줄면서 가격이 좁은 범위(flag)에 압축되다가 다시 돌파하면 진입한다.  
"쉬어가는" 구간에서 수급이 소화된 뒤 재상승을 노리는 전략이다.

```
진입 트리거 (전부 충족):

[Flagpole]
  pole_low  = min(low[-15:])
  pole_high = max(high[-15:])
  pole_pct  = (pole_high - pole_low) / pole_low ≥ 0.07  — +7% 이상 급등

[Flag 압축 구간: 오늘 제외 최근 7봉]
  flag_high = max(high[-7:-1])
  flag_low  = min(low[-7:-1])
  flag_vol  = mean(volume[-7:-1])
  pole_vol  = mean(volume[-15:])

[압축 조건]
  vol_shrink: flag_vol < pole_vol × 0.9    — 거래량 수축 90% 이하
  tight_range: (flag_high - flag_low) < ATR(14) × 2.5  — 가격 범위 압축

[돌파]
  close > flag_high                         — flag 고가 돌파
  volume[-1] ≥ 20일 평균                    — 돌파 수급 동반

청산:
  SL  = flag_low × 0.975  (fallback: entry × 0.975)
  TP1 = entry × 1.03  (+3%)
  TP2 = entry + ATR(14) × 3.0
  Support floor = flag_low
```

### 5.2 파라미터 상세

| 파라미터 | 현재값 | 변경 이력 |
|---------|--------|---------|
| `pole_lookback` | `15` | - |
| `min_pole_pct` | `0.07` | 0.08 → 0.07 (2026-05-14) |
| `flag_bars` | `7` | - |
| `vol_shrink_ratio` | `0.9` | 0.7 → 0.9 (2026-05-14) |
| `tight_range_mult` | `2.5` | 1.5 → 2.5 (2026-05-14) |
| `stop_loss_pct` | `0.025` | -2.5% fallback |
| `min_bars` | `35` | pole(15) + flag(7) + 여유 13 |
| `min_daily_volume` | `100,000` | - |

### 5.3 파라미터 선정 배경

#### tight_range_mult = 2.5 (1.5 → 2.5, 2026-05-14) — 가장 중요한 변경

**실증**: 90일 그리드 서치에서 승률 50% → 80%, PF(Profit Factor) 0.81 → 4.57.

기존 1.5 배수는 "flag 범위 < ATR × 1.5"로 너무 엄격해 실제 유효한 Bull Flag 패턴을 대부분 걸러냈다. KOSPI 중소형주는 변동성이 높아 flag 구간에서도 ATR의 1.5배를 초과하는 경우가 잦다. 2.5 배수로 완화하니 실제 패턴이 포착되기 시작했고, PF가 4.57로 급등했다.

#### vol_shrink_ratio = 0.9 (0.7 → 0.9, 2026-05-14)

기존 0.7(30% 수축)은 지나치게 엄격해 신호 수가 4건에 불과했다. 0.9(10% 수축)로 완화하니 35건으로 늘어나 통계적 유의성이 확보되었다. flag 기간에 거래량이 10% 이상만 줄어도 "매도 압력이 소화되고 있다"는 신호로 충분하다.

#### min_pole_pct = 0.07 (0.08 → 0.07, 2026-05-14)

KOSPI 중소형주에서 flagpole 기준을 8%로 설정했을 때 월 신호 수가 지나치게 적었다. 7%로 완화해도 의미 있는 급등(약 1.4주 분 수익)을 기준으로 삼는다.

#### pole_lookback = 15

급등이 너무 오래 전에 발생했다면(20일 이상) 이미 Flag에서 Flat으로 변질되었을 가능성이 높다. 15거래일(3주)이 flagpole 탐색에 적절한 실무적 타협점.

#### flag_bars = 7

1거래주(5일)보다 조금 긴 7일이 flag 패턴이 "성숙"하는 데 필요한 최소 기간. 5일 미만은 충분한 압축이 이루어지지 않았고, 10일 이상은 Flag가 Base로 변질되어 돌파 기대치가 달라진다.

---

## 6. 공통 인프라 파라미터

모든 전략에 공통으로 적용되는 파라미터.

### 6.1 KRX 호가 단위 (price_utils.py)

| 가격대 | 호가 단위 |
|--------|---------|
| ≤ 1,000원 | 1원 |
| ≤ 5,000원 | 5원 |
| ≤ 10,000원 | 10원 |
| ≤ 50,000원 | 50원 |
| ≤ 100,000원 | 100원 |
| ≤ 500,000원 | 500원 |
| > 500,000원 | 1,000원 |

진입가·목표가는 `round_to_tick`, 손절가는 `floor_to_tick`으로 반올림한다.

### 6.2 ATR 기반 손절 (_atr_stop.py, PR-F)

```
stop = max(entry - atr_mult×ATR, support - support_buffer×ATR)

ATR 결측 또는 stop ≥ entry 시: entry × (1 - fallback_pct)
```

ATR이 있을 때 동적 계산, 없을 때 고정 -2.5% fallback.

### 6.3 유니버스 필터 (전략 공통)

| 항목 | 기준 |
|------|------|
| 20일 일평균 거래량 | ≥ 100,000주 |
| 시가총액 | 5,000억 ~ 30,000억 (중소형주 최적 구간, 2026-05-19 하한 상향) |
| 상장 경과일 | ≥ 120일 |
| 관리종목·투자유의 | 제외 |
| 우선주 | 제외 |
| ETN(7xxxxx 코드) | 제외 |

**시총 5,000억~30,000억 근거**: 이 구간이 일일 ±3~5% 이동이 빈번하면서 유동성이 충분한 구간. 대형주(30,000억 초과)는 +3% 달성이 어렵고, 소형주(5,000억 미만)는 베타 추정 불안정 + 슬리피지 위험이 크다. 2026-05-19 이전에는 하한 2,000억이었으나 잔차 모멘텀(S6) 후보 검토와 0.30% 거래비용 환경에 맞춰 상향.

### 6.4 포지션 관리

| 항목 | 값 |
|------|-----|
| 최대 동시 보유 종목 | 5개 |
| 종목당 포지션 크기 | 자본의 15~20% |
| 최소 현금 유지 | 10% |
| 피라미딩 | 금지 |
| 동시 진입 우선순위 | confidence 내림차순 → 시총 → 거래대금 |

---

## 7. 파라미터 최적화 이력

### 2026-05-14 일괄 최적화 (90일 그리드 서치 기반)

| 전략 | 파라미터 | 변경 전 | 변경 후 | 개선 지표 |
|------|---------|--------|--------|---------|
| Strategy 1 | `engulf_strict` | `True` | `False` | 신호 수 정상화 |
| Strategy 2 | `lookback` | 15 | 20 | Sharpe 개선 |
| Strategy 2 | `entry_percentile` | 0.75 | 0.80 | 허위 신호 감소 |
| Strategy 3 | `lookback` | 20 | 30 | Whipsaw 감소 |
| Strategy 3 | `atr_filter_multiplier` | 0.5 | 0.7 | 실현 수익 개선 |
| Strategy 3 | `atr_stop_mult` | 1.5 | 2.5 | 조기 손절 감소 |
| Strategy 3 | `atr_target_mult` | 3.0 | 2.5 | TP2 도달율 개선 |
| Strategy 4 | `ma_trend` | 20 | 30 | 승률 44.9% → 54.9% |
| Strategy 4 | `pullback_lookback` | 5 | 3 | avgPnL -0.07% → +0.51% |
| Strategy 5 | `tight_range_mult` | 1.5 | 2.5 | 승률 50% → 80%, PF 0.81 → 4.57 |
| Strategy 5 | `vol_shrink_ratio` | 0.7 | 0.9 | 신호 4건 → 35건 |
| Strategy 5 | `min_pole_pct` | 0.08 | 0.07 | 신호 수 적정화 |

### 파라미터 민감도 분석 계획

과최적화 여부 검증을 위해 각 파라미터를 ±20% 변동시켜 성과 안정성을 확인한다.

| 전략 | 대상 파라미터 | 테스트 범위 |
|------|------------|-----------|
| 전략1 | RSI 임계값 | 25, 30(현재), 35 |
| 전략1 | BB 표준편차 | 1.8, 2.0(현재), 2.2 |
| 공통 | 손절 비율 | -2%, -2.5%(현재), -3% |
| 공통 | 익절 목표 1 | +2%, +3%(현재), +4% |

성과가 특정 파라미터에만 몰리면 과최적화 → 재설계.

---

## 8. 참고문헌

### 학술 원전

| 논문 | 연관 전략 |
|------|---------|
| DeBondt & Thaler (1985). "Further Evidence on Investor Overreaction and Stock Market Seasonality." *Journal of Finance*, 40(3). | 전략1 |
| Jegadeesh, N. (1990). "Evidence of Predictable Behavior of Security Returns." *Journal of Finance*, 45(3). | 전략1 |
| Lehmann, B. N. (1990). "Fads, Martingales, and Market Efficiency." *Journal of Finance*, 45(4). | 전략1 |
| Jegadeesh & Titman (1993). "Returns to Buying Winners and Selling Losers." *Journal of Finance*, 48(1), 65-91. | 전략2 |
| Rouwenhorst (1998). "International Momentum Strategies." *Journal of Finance*, 53(1). | 전략2 |
| Moskowitz, Ooi & Pedersen (2012). "Time Series Momentum." *Journal of Financial Economics*, 104(2), 228-250. | 전략3 |
| Wilder, J. W. (1978). *New Concepts in Technical Trading Systems*. | 전략1 (RSI) |
| Bollinger, J. (1983). Bollinger Band 원전. | 전략1 (BB) |

### 한국 시장 검증

| 연구 | 주요 발견 | 연관 전략 |
|------|---------|---------|
| Lee (2002). KOSPI 일봉 평균회귀 특성. *한국재무학회지*. | KOSPI 일봉 분수적분 과정으로 평균회귀 유의 (p < 0.05) | 전략1 |
| Bae (2006). Mean Reversion in KOSPI and KOSDAQ. | 1997년 이후 약한 평균회귀, KOSDAQ이 KOSPI보다 강함 | 전략1 |
| Park & Lee (2010). "Momentum and Reversal Effects in the Korean Stock Market." *Journal of Empirical Finance*, 17(4), 611-626. | 1990~2008년 KOSPI 월단위 모멘텀 초과수익 확인 | 전략2 |

### 실무 백테스트 결과 (내부, 비공개)

| 구분 | 수치 |
|------|------|
| 기간 | 2020~2026년 KOSPI/KOSDAQ 중소형주(시총 2,000억~3조) |
| 전략1 Sharpe | 1.2~1.8 |
| 전략1 Win rate | 52~58% |
| 전략1 MDD | -8~-12% |
| 전략2 Sharpe | 0.9~1.4 |
| 전략3 Sharpe | 0.7~1.2 |
| 3전략 포트폴리오 Sharpe (추정) | 1.5~2.0 |

> **면책**: 한국 시장 실증 연구(Lee 2002, Bae 2006)는 저널·권호·페이지 정보가 불완전하다. 정량 기준으로 활용하기 전 KCI/RISS 또는 한국재무학회 저널에서 1차 출처를 재확인할 것을 권장한다.
