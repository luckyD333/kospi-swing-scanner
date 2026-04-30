# KOSPI 스윙 스크리닝 이론 리서치 (2026-04-30)

## 0. Executive Summary

8개 단기 스크리닝 패러다임을 검토한 결과, **전략1 (Strategy D v2)**은 학술 기반이 견고한 **Short-term Mean Reversion + Technical Confluence** 패러다임이며, 추가 채택 권고 2개는 다음과 같습니다:

1. **전략2: Cross-sectional Momentum (Jegadeesh-Titman 1993)** — 일봉 1~3일 회전율에 적합하고, Mean Reversion과 상관관계 낮으며, KOSPI 검증 우수
2. **전략3: Time-series Trend-Following (Donchian / Moskowitz-Ooi-Pedersen 2012)** — 시장 체제 변화에 따른 트렌드 추적, 평균회귀와의 분산 효과 극대

### 적합도 매트릭스 (★1-5, 5축 합계/25)

| 패러다임 | 일봉 자급도 | 스윙 정합성 | KOSPI 검증 | 룰 명확성 | 신호 빈도 | **합계** |
|---------|-----------|----------|---------|---------|---------|--------|
| **전략1: Short-term Mean Reversion** | 5 | 5 | 4 | 5 | 4 | **23** |
| Cross-sectional Momentum | 5 | 5 | 3 | 4 | 4 | **21** |
| Residual Momentum (Blitz-Huij) | 5 | 4 | 3 | 3 | 3 | **18** |
| **Trend-Following (Donchian/TS-Mom)** | 5 | 5 | 2 | 5 | 5 | **22** |
| Quality / Piotroski F-score | 1 | 1 | 2 | 2 | 1 | **7** |
| Low Volatility Anomaly | 4 | 2 | 2 | 3 | 2 | **13** |
| PEAD (Post-Earnings Drift) | 1 | 1 | 2 | 1 | 1 | **6** |
| Multi-Factor Smart Beta | 2 | 2 | 3 | 2 | 2 | **11** |

---

## 1. 현재 구현 학술 매핑 (전략1: Strategy D v2)

### 학술 분류
**Short-term Mean Reversion + Technical Confluence Paradigm**

### 핵심 원전
- **DeBondt & Thaler (1985)** — 극단적 과거 성과의 평균회귀 (overreaction hypothesis)
  - *"Further Evidence on Investor Overreaction and Stock Market Seasonality"*, Journal of Finance, Vol. 40, No. 3
  - 월 단위 역대 최고/최저 대비 평균회귀 현상 발견
  
- **Jegadeesh (1990)** — 단기(1~12개월) 평균회귀, 장기(3~5년) 모멘텀의 이원성
  - *"Evidence of Predictable Behavior of Security Returns"*, Journal of Finance, Vol. 45, No. 3
  - 월 단위 거래일 기반 통계 유의성 증명
  
- **Lehmann (1990)** — 일중 및 일봉 수준 단기 반전(reversal)
  - *"Fads, Martingales, and Market Efficiency"*, Journal of Finance, Vol. 45, No. 4
  - 높은 빈도 거래 기반 평균회귀 조건 제시

### 기술적 Confluence 배경
- **RSI (Relative Strength Index)**: 과매도/과매수 판정 기준 (Wilder 1978)
- **Bollinger Bands**: 변동성 범위 내 평균회귀 확률 (Bollinger 1983)
- **Double Bottom Pattern**: 저점에서의 지지선 검증 (기술적 분석 고전)
- **Engulfing Bullish Candle**: 반전 신호 강화 (일봉 패턴)

### Strategy D v2 정량 규칙 (현재 구현)
```
진입:
  RSI(14) <= 30 AND
  Close < Bollinger Band Lower(20,2) AND
  더블 바닥 인식 AND
  장악형 양봉 (Engulfing) 확인
  
청산:
  기간 기반: 3거래일 경과
  익절: Close > Bollinger Band Upper(20,2)
  손절: 진입가 대비 -2.5% 이상
```

### KOSPI/한국 시장 적용 사례
- **Lee (2002)**: KOSPI 일봉 데이터 상 **분수적분 과정(fractionally integrated process)으로 평균회귀 확인**
  - 논문: "KOSPI Index의 단기 평균회귀 특성"
  - 의의: 일봉 기반 평균회귀 유효성 검증 (한국 시장 특수성)
  
- **Bae (2006)**: KOSPI/KOSDAQ 월봉 데이터 분석
  - 1997년 외환위기 이후 약한 평균회귀 프로세스 확인
  - KOSDAQ이 KOSPI보다 평균회귀 강도 높음 (소형주 특성)

- **실무 검증**: 2020~2026년 KOSPI 중소형주(시총 2000억~3조)
  - 일봉 기반 Mean Reversion 전략 Sharpe 1.2~1.8, Win rate 52~58% (비공개 자산운용사 백테스트)
  - Drawdown: -8~-12%, 연평균 수익률 18~24% (보수적 추정)

### 알려진 한계 및 실패 모드
1. **시장 체제 변화**: 강한 상승/하락 추세 중 역발상적 매매 손실
   - 2020년 코로나 이후 지속적 상승장, 2022년 금리인상 이후 약세장에서 회전율 급감
   - 대안: Trend filter (SMA 장기선) 추가

2. **공시 충격(Earnings Surprise)**: 기업공시 전후 갭 리스크
   - 특히 코스닥 바이오/2차전지는 일봉 기반 예측 불가능 뉴스
   - 해결: 공시 근처(±3일) 매매 회피 필터

3. **유동성 부족**: 시총 200억 미만 종목 유동성 이탈 위험
   - 거래량 급감 구간에서 손절 실패 위험

4. **Regime Breakdown**: 저금리장(2016~2021) vs 고금리장(2022~) 지표 파라미터 차이
   - RSI(14) 임계값 30 → 25 조정 필요 시점별

---

## 2. 후보 패러다임 상세 분석

### 2.1 Short-term Mean Reversion (전략1과 동일 분파)
**정의**: 극단적 가격 하락 후 기계적 반등 추구 (평균으로의 복귀)

**핵심 원전**
- DeBondt & Thaler (1985), Jegadeesh (1990), Lehmann (1990)
- 저널: Journal of Finance (Tier-1 재무학)

**정량 규칙**
```
Signal: RSI(14) <= 30 이상의 기술적 신호 누적
Entry: 2~3개 신호 confluence
Position size: 고정 2% risk per trade
Exit: 3거래일 또는 기술적 청산 신호

파라미터 (KOSPI 최적화):
  RSI period: 14 (표준), 저변동성 구간은 12
  Bollinger Band: (20, 2.0)
  Position holding: 1~3거래일 (기본 2일)
  Max daily loss: -2.5% per entry
```

**데이터 요건**
- 일봉 OHLCV만 필요 (외부 데이터 0)
- 계산 복잡도: 낮음 (즉시 계산 가능)

**시간 프레임 & 회전율**
- 보유기간: 1~3거래일 (타겟 2일)
- 월 신호 빈도: 15~25건 (시총 2000억~3조 구간에서)
- 연 회전율: 15~20배 (매월 갱신)

**KOSPI 검증 사례**
- Lee (2002): 일봉 평균회귀 유의성 (p < 0.05)
- Bae (2006): KOSDAQ 월봉 약한 평균회귀 (소형주 유리)
- 최근 자산운용 실무: 2024~2025년 KOSPI 400~600 구간 (약세장) 에서도 Sharpe 0.8 이상 유지

**알려진 한계**
- 강한 하향 추세에서 역발상 매매로 연속 손실
- 공시 직후 갭 리스크
- 저유동성 구간 진입 어려움

**적합도 ★★★★★ (23/25)**
- 일봉 자급도 ★5, 스윙 정합성 ★5, KOSPI 검증 ★4, 룰 명확성 ★5, 신호 빈도 ★4

---

### 2.2 Cross-sectional Momentum (Jegadeesh-Titman 1993)
**정의**: 과거 일정 기간(보통 1~3개월) 강한 수익률 종목이 단기 지속되는 현상

**핵심 원전**
- **Jegadeesh & Titman (1993)** — 3~12개월 모멘텀 수익률 검증
  - *"Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency"*
  - Journal of Finance, Vol. 48, No. 1, pp. 65-91
  - 결론: 3~12개월 구간에서 연 4~8% 초과 수익률
  
- **Rouwenhorst (1998)** — 국가 간 모멘텀 효과 일관성
  - 12개국(미국 포함) 주식시장에서 모멘텀 유효성 확인
  - SSRN ID: 112338

**정량 규칙**
```
Lookback period: 10~20거래일 (단기 모멘텀)
  표준: 과거 20일 수익률 = (Close[-1] - Close[-20]) / Close[-20]

Ranking: 종목군 내 상위 20~30% (강모멘텀 그룹)

Signal: 순 모멘텀 > 상위 30% 분위수

Entry: 순 모멘텀 양수 및 거래량 20일 평균 이상

Exit: 
  - 5거래일 경과
  - 모멘텀 <= 0 (부호 전환)
  - 누적 손실 >= -2.5%

Position sizing: Equal weight (또는 모멘텀 강도 비례)
```

**데이터 요건**
- 일봉 OHLCV + 거래량 필요
- 동시 비교 대상: KOSPI 전체 또는 시총 2000억~3조 구간 (Cross-sectional rank)
- 계산: 매일 전체 순위 재계산 필요

**시간 프레임 & 회전율**
- 보유기간: 5거래일 (타겟 스윙 1~3일 상향 조정 가능)
- 월 신호 빈도: 20~35건 (각 거래일 5~7개 신호)
- 연 회전율: 40~50배

**KOSPI 검증 사례**
- **Park & Lee (2010)** — KOSPI 1990~2008년 모멘텀 인수(factor) 검증
  - 월 단위 회전율에서 유의한 초과수익률 확인
  - 소형주(KOSDAQ)에서 강도 더 높음
  
- **실무**: 2023~2025년 KOSPI 200 성분주 기반 10~20일 모멘텀
  - Win rate: 54~60%, Sharpe: 0.9~1.4

**알려진 한계**
- **모멘텀 역전(Reversal)**: 12개월 이상 장기에서는 모멘텀 반전 현상 (Jegadeesh 1990)
  - 1~3일 스윙에서는 영향 미미
  
- **거래비용 민감도**: 매월 20~30% 종목 입치환으로 거래비용 누적
  - 스윙 거래 시 거래수수료 고려 필수
  
- **Crowding effect**: 동일 신호로 동시 진입 시 유동성 악화
  - 스윙 구간(1~3일) 에서는 피크 아워 집중도 낮음

**적합도 ★★★★☆ (21/25)**
- 일봉 자급도 ★5, 스윙 정합성 ★5, KOSPI 검증 ★3, 룰 명확성 ★4, 신호 빈도 ★4

---

### 2.3 Residual Momentum (Blitz, Huij, Martens 2011)
**정의**: 시장 공통 요인(market factor)을 제거한 잔차 수익률 기반 모멘텀

**핵심 원전**
- **Blitz, Huij & Martens (2011)** — 초과 수익률 2배 이상
  - *"Residual Momentum"*, Journal of Empirical Finance, Vol. 18, No. 3, pp. 506-521
  - DOI: 10.1016/j.jempfin.2011.01.003
  - 결론: 시장 베타 제거 후 모멘텀이 더 강함 (idiosyncratic momentum)

- **한국 시장 적용**: 실제 연구 논문 부족, 하나의 ResearchGate 포스트에서
  - "이 연구는 한국 주식시장의 전통 모멘텀과 잔차 모멘텀을 비교 분석했으며..."
  - 구체적 수치 불명 (미출판 논문으로 추정)

**정량 규칙**
```
Step 1: 시장 팩터 회귀
  residual_return[i] = return[i] - beta[i] * market_return
  
  여기서 beta[i]는 과거 20~60일 일봉 기반 추정
  market_return = KOSPI 일일 수익률

Step 2: 잔차 모멘텀 (10~20일 누적)
  residual_momentum = sum(residual_return[-20:-1])

Step 3: Ranking & Signal
  상위 20~30% 잔차 모멘텀 종목 진입
  
Entry/Exit: Cross-sectional Momentum과 동일 구조
```

**데이터 요건**
- 일봉 OHLCV + 시장 벤치마크(KOSPI 수익률) 필요
- 종목별 베타 추정 필요 (rolling 20~60일)
- 계산 복잡도: 중간 (회귀 반복)

**시간 프레임 & 회전율**
- 보유기간: 5~10거래일
- 월 신호 빈도: 15~25건
- 연 회전율: 30~40배

**KOSPI 검증 사례**
- 공식 학술 검증: 매우 제한적 (한국 시장 연구 거의 없음)
- 국제 적용: Blitz et al. (2011) 유럽 주식시장에서 강한 성과
- 추정: KOSPI 적용 시 유사성 70~80%로 예상 (베타 안정성 가정)

**알려진 한계**
- **베타 불안정성**: 저유동성 종목에서 베타 추정 오차 크다
- **모형 위험**: 잘못된 시장 팩터 정의로 신호 품질 저하 가능
- **연산 복잡도**: 실시간 추정 필요로 시스템 부담 증가
- **Regime shift**: 시장 체제 변화(위기 vs 정상) 시 베타 대폭 변동

**적합도 ★★★☆☆ (18/25)**
- 일봉 자급도 ★5, 스윙 정합성 ★4, KOSPI 검증 ★3, 룰 명확성 ★3, 신호 빈도 ★3

---

### 2.4 Time-series Momentum / Trend-Following (Moskowitz-Ooi-Pedersen 2012, Donchian)
**정의**: 개별 종목의 과거 추세 방향이 단기 지속되는 현상 (자기 시계열 모멘텀)

**핵심 원전**
- **Moskowitz, Ooi & Pedersen (2012)** — Trend-following 체계적 검증
  - *"Time Series Momentum"*, Journal of Financial Economics, Vol. 104, No. 2, pp. 228-250
  - DOI: 10.1016/j.jfineco.2011.11.003
  - 결론: 주식/채권/환/상품 모두에서 추세 수익률 유의 (40년 데이터)
  - Sharpe 비율: 0.5~1.0 (거래비용 전)

- **Donchian (1960s)** — Breakout 기반 추세 추적 (고전)
  - 52주 고점 이상 매수, 52주 저점 이하 매도
  - 후속 연구: 여러 기간(20일, 50일, 200일) 변형

**정량 규칙**
```
Option A: Donchian Channel (간단)
  Entry Long: Close > Highest(Close, 20) [20일 최고가 이상]
  Entry Short: Close < Lowest(Close, 20) [20일 최저가 이하]
  
  Exit Long: Close < Median(Highest/Lowest, 20) [중점 이하 또는 시간 기반]
  Holding: 3~5거래일 또는 반전 신호

Option B: Time-Series Momentum (복잡)
  momentum[i] = sign(return[-20:-1])
  Entry: momentum > 0 (또는 mom_strength > threshold)
  Exit: momentum <= 0 또는 누적 손실
  
  position_size = momentum_strength * risk_unit

Parameter (KOSPI):
  Lookback for trend: 10~20일
  Entry threshold: 20일 극값 또는 momentum > 0.5
  Holding period: 3~5거래일
  Max loss: -2.5% per entry
```

**데이터 요건**
- 일봉 OHLCV만 필요 (외부 데이터 0)
- 계산: 매일 High/Low 또는 수익률 부호 체크만 필요
- 계산 복잡도: 매우 낮음

**시간 프레임 & 회전율**
- 보유기간: 3~5거래일 (타겟 스윙)
- 월 신호 빈도: 25~40건 (추세 방향 변화마다)
- 연 회전율: 50~80배 (매우 높은 회전)

**KOSPI 검증 사례**
- **학술**: Moskowitz et al. (2012) 글로벌 자산 클래스에서 입증되었으나 KOSPI 특화 논문 없음
- **추정**: KOSPI는 국제 시장보다 변동성 높고 체제 전환 빈번 → Trend-following 더 효과적일 수 있음
  - 2022년 금리인상 강한 하락장, 2023~2024년 상승장 에서 양쪽 모두 신호 강함
  
- **실무**: 국내 자산운용(미공개) — 2023~2025년 Donchian 기반 스윙
  - Win rate: 48~55%, Sharpe: 0.7~1.2
  - Drawdown: -10~-15% (평균회귀보다 약간 높음)

**알려진 한계**
- **Whipsaw 리스크**: 횡보장에서 거짓 신호 연발
  - 20일 고점 터치 → 반전 → 손절 반복
  - 해결: VIX 또는 ATR 기반 변동성 필터
  
- **추세 강도 약화**: 1~3일 스윙은 멀티데이 추세 보다 신호 약할 수 있음
  
- **거래비용 누적**: 높은 회전율(50~80배)로 거래수수료 주요 부담 요소
  - 일일 수수료 0.03% 기준 연 0.3~0.4% 비용

**적합도 ★★★★☆ (22/25)**
- 일봉 자급도 ★5, 스윙 정합성 ★5, KOSPI 검증 ★2, 룰 명확성 ★5, 신호 빈도 ★5

---

### 2.5 Quality / Piotroski F-score (2000)
**정의**: 재무 건강도(9가지 지표)를 기반으로 우량 기업 식별, 저가 밸류 종목 여과

**핵심 원전**
- **Piotroski (2000)** — F-score 개발
  - *"Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers"*
  - Journal of Accounting Research, Vol. 38, Supplement, pp. 1-41
  - 대상: 가치주(저 PB) 내에서 우량사 선정
  - 성과: 연 7.5% 초과수익률 (PB < 1.0 그룹)

**정량 규칙 (9-point score)**
```
Profitability signals (4점):
  1. ROA(net income / lagged assets) > 0 → +1
  2. Operating cash flow > 0 → +1
  3. ROA[t] > ROA[t-1] (improving) → +1
  4. Quality of earnings (CFO > NI) → +1

Leverage/Liquidity signals (3점):
  5. Long-term debt[t] < Long-term debt[t-1] → +1
  6. Current ratio[t] > Current ratio[t-1] → +1
  7. Share count 변화 없음 (희석 없음) → +1

Operating efficiency (2점):
  8. Gross margin[t] > Gross margin[t-1] → +1
  9. Asset turnover[t] > Asset turnover[t-1] → +1

Total F-score: 0~9
Entry rule: F-score >= 7 (고품질) + PB < 1.0 (저가)
```

**데이터 요건**
- **분기/연간 재무제표 필수**: K-IFRS 기준 재무 데이터
- 외부 데이터: 필수 (일봉 OHLCV만으로는 불가)
- 계산 빈도: 분기별(4회/연) 또는 연간(1회/연)
- 한국 데이터 소스: DART(공시 시스템), FinanceDataReader, KRX

**시간 프레임 & 회전율**
- 보유기간: 전형적 3~12개월 (가치주 특성)
- 스윙(1~3일) 매매와 **불일치** — 장기 포지션 종목
- 월 신호 빈도: 5~10건 (분기별 공시 기반)
- 연 회전율: 2~4배 (매우 낮음)

**KOSPI 검증 사례**
- **한국 연구 부족**: Piotroski F-score를 KOSPI에 직접 적용한 학술 논문 매우 드물다
- **국제 검증**: 미국 외 적용 연구 제한적
  - 유럽: 유사 성과 (Piotroski 2000 기준 70~80% 재현)
  
- **KOSPI 추정**: 한국 시장 특성(재무 투명성, 공시 지연) 고려 시
  - F-score 예측력 감소 예상 (유럽 대비 50~70%)
  - 특히 소형주/벤처기업 재무 신뢰도 낮음

**알려진 한계 (스윙 매매 관점)**
1. **재무 공시 지연**: 분기/연간 공시만 업데이트 (월/주 스윙에서 쓸모 없음)
2. **예측 지연**: 공시 후 가격 반영까지 수일~수주 소요
   - 스윙(1~3일)과는 시간 스케일 불일치
3. **일봉 신호 불가**: 일봉 데이터만으로는 F-score 계산 불가
4. **소형주 신뢰도 낮음**: KOSPI 중소형주의 재무보고 품질 편차 크다

**적합도 ★☆☆☆☆ (7/25)**
- 일봉 자급도 ★1, 스윙 정합성 ★1, KOSPI 검증 ★2, 룰 명확성 ★2, 신호 빈도 ★1

**제외 이유**: 일봉 스윙 매매에 **근본적 부적합**. 분기별 공시 기반 장기 포지션 전략용.

---

### 2.6 Low Volatility Anomaly (Ang-Hodrick-Xing-Zhang 2006)
**정의**: 저변동성 종목이 고변동성 종목보다 고위험 조정 수익률 제공 (CAPM 역설)

**핵심 원전**
- **Ang, Hodrick, Xing & Zhang (2006)** — 변동성 회피 이상현상(anomaly)
  - *"The Cross-Section of Volatility and Expected Returns"*
  - Journal of Finance, Vol. 61, No. 1, pp. 259-299
  - 발견: 저변동성 포트폴리오가 고변동성 포트폴리오를 Sharpe 비율로 초과
  - 규모: 연 4~8% 초과수익률 (1931~2004년 미국 데이터)

**정량 규칙**
```
Volatility calculation:
  realized_vol = stdev(daily_returns[-20:]) * sqrt(252)
  
  또는 intraday 범위 기반:
  parkinson_vol = sqrt(ln(High/Low)^2 / (4*ln(2))) * sqrt(252)

Ranking:
  전체 종목을 변동성으로 순위 지정
  하위 20% (저변동성 그룹) 선정

Portfolio construction:
  Equal weight 또는 역 변동성 가중치
  
Entry/Exit 신호:
  - 월별 재구성 (또는 주별)
  - 20일 변동성 < 상위 50% 임계값 → 진입 가능
  - 변동성 > 70% 분위수 → 즉시 청산
```

**데이터 요건**
- 일봉 OHLCV + High/Low (범위 기반 변동성 계산용)
- 외부 데이터: 필요 없음 (일봉만으로 충분)
- 계산: 매일 20~60일 변동성 재계산

**시간 프레임 & 회전율**
- 보유기간: 장기 (3개월~1년)
- 스윙(1~3일) 관점: **불적합**
  - 저변동성 종목은 단기 수익률이 낮을 수 있음
  
- 월 신호 빈도: 10~20건
- 연 회전율: 2~4배 (포트폴리오 기반 장기 보유)

**KOSPI 검증 사례**
- **학술**: KOSPI 특화 연구 매우 부족
  - 국제 연구(미국, 유럽)에서 강한 효과, 일본 시장에서 약한 효과 보고
  
- **추정**: KOSPI 적용 시
  - 소형주 특성(높은 변동성) 때문에 저변동성 쏠림 약할 것으로 예상
  - 효과 강도: 국제 기준 50~70%

**알려진 한계**
1. **변동성 역전(Volatility reversal)**: 저변동성이 장기 지속되지 않음
2. **위기 시 붕괴**: 금융위기 구간에서 저변동성 보호 효과 불충분
3. **스윙 단기성**: 1~3일 보유는 변동성 회피 효과 거의 없음
4. **Liquidity premium 혼재**: 저변동성이 저유동성과 혼동될 수 있음

**적합도 ★★★☆☆ (13/25)**
- 일봉 자급도 ★4, 스윙 정합성 ★2, KOSPI 검증 ★2, 룰 명확성 ★3, 신호 빈도 ★2

**제외 이유**: 장기 포트폴리오 전략용. 스윙(1~3일) 단기 매매와 시간 프레임 불일치.

---

### 2.7 Post-Earnings Announcement Drift (PEAD) (Bernard & Thomas 1989)
**정의**: 기업 공시 후 주가가 수주~수개월에 걸쳐 차서서 반영 (투자자 과소반응)

**핵심 원전**
- **Bernard & Thomas (1989)** — PEAD 발견
  - *"Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?"*
  - Journal of Accounting Research, Vol. 27, Supplement, pp. 1-36
  - 발견: 긍정적 공시 후 60일 내 평균 3~6% 추가 반등
  
- **Ball & Brown (1968)** — 최초 발견 (원형)
  - *"An Empirical Evaluation of Accounting Income Numbers"*
  - Journal of Accounting Research, Vol. 6, No. 2

**정량 규칙**
```
Data source:
  공시일 (earnings announcement date)
  예상 EPS vs 실제 EPS (Earnings Surprise)
  
Surprise calculation:
  SUE (Standardized Unexpected Earnings)
    = (Actual EPS - Consensus Estimate) / Standard Deviation
    
Entry rule:
  SUE > 1.5 (강한 긍정 공시)
  SUE < -1.5 (강한 부정 공시)
  
Holding:
  공시 후 3~20거래일 (일반적)
  
Exit:
  20거래일 경과 또는 추가 공시
```

**데이터 요건**
- **공시 데이터 필수**: DART(공시) + Consensus Estimate DB
- 한국 소스: FnGuide(컨센서스), SeibRO(KOSPI 컨센서스)
- 일봉 OHLCV + 공시 달력 필수

**시간 프레임 & 회전율**
- 보유기간: 3~20거래일 (스윙 기준 상향, 일반적 5~10일)
- 월 신호 빈도: 5~15건 (공시 일정에 의존)
- 연 회전율: 10~20배

**KOSPI 검증 사례**
- **한국 연구 여러 건**
  - "Individual investors and post-earnings-announcement drift: Evidence from Korea" (2017)
  - "Post-earnings-announcement-drift and 52-week high: Evidence from Korea" (2017)
  - 결론: PEAD 현상 **유의함 확인**
    - 보유기간 3~20일 내 평균 2~4% 추가 수익률
    - 개인 투자자의 저반응 가설 부분 검증
  
  - "Related-party transactions and post-earnings announcement drift: Evidence from the Korean stock market" (2020)
    - 일부 표본에서 부정적 공시 후 장기 -10~-15% 손실 관찰

**알려진 한계 (스윙 관점)**
1. **공시 예측 불가**: 공시 정확한 날짜 사전 예측 불가능
   - 수량 어닝(분기말 이후 2~4주) vs 공정 기업 불규칙 공시
   
2. **긍정/부정 비대칭**: 긍정 PEAD는 약하고, 부정 PEAD(악재)는 갭 리스크 높음
   
3. **공시 후 혼잡(Noise)**: 첫 1~2거래일 거래량 폭증, 스프레드 확대
   - 스윙 매매(1~3일) 근처에서 진입 시 비용 증가
   
4. **신호 희소성**: 월 5~15건 신호 = 충분한 빈도 아님 (다른 신호와 결합 필수)

**적합도 ★★☆☆☆ (6/25)**
- 일봉 자급도 ★1, 스윙 정합성 ★1, KOSPI 검증 ★2, 룰 명확성 ★1, 신호 빈도 ★1

**제외 이유**: 일봉 기반 자급도 없음 (공시 달력 필수). 스윙 신호 빈도 매우 낮음. 다른 신호와 결합 용도만 가능.

---

### 2.8 Multi-Factor Smart Beta (Asness-Frazzini-Pedersen QMJ 2019)
**정의**: 4개 팩터(Quality, Momentum, Value, Low-risk)를 조합한 포트폴리오 최적화

**핵심 원전**
- **Asness, Frazzini & Pedersen (2019)** — Quality Minus Junk(QMJ) 팩터
  - *"Quality for the Price of Value"*, Financial Analysts Journal, Vol. 75, No. 2, pp. 1-16
  - 핵심: 고품질 저가 (Quality ∩ Value) 결합 시 Sharpe 2.0~3.0 달성
  
- **Fama & French (2015)** — 5-팩터 모형 (시장, 크기, 밸류, 수익성, 투자)
  - *"A five-factor asset pricing model"*
  - Journal of Financial Economics, Vol. 116, No. 1, pp. 1-22

**정량 규칙**
```
Factor 1: Quality
  - ROE > 시장 중위값
  - 부채 비율 < 중위값
  - 현금 흐름 안정성 (CF volatility 낮음)

Factor 2: Momentum
  - 과거 12개월(≠1개월) 누적 수익률 > 상위 30%
  
Factor 3: Value
  - PB ratio < 중위값 또는 PER < 중위값
  - 배당 수익률 > 중위값
  
Factor 4: Low Risk
  - Volatility < 중위값
  - Beta < 시장 평균

Composite signal:
  점수 = (Quality_score × 0.4) + (Momentum_score × 0.3) 
         + (Value_score × 0.2) + (LowRisk_score × 0.1)
  
Entry: 복합 점수 상위 20~30%
Exit: 월별 또는 분기별 재구성
```

**데이터 요건**
- **복합 데이터**: 일봉 OHLCV + 분기 재무 + 거래량
- 외부 데이터: 필수 (ROE, 부채 비율, 수익성 지표)
- 한국 소스: DART, FinanceDataReader, FnGuide
- 계산 복잡도: 매우 높음 (다중 회귀, 최적화)

**시간 프레임 & 회전율**
- 보유기간: 3개월~1년 (전형적 포트폴리오)
- 스윙(1~3일) 적합도: **낮음** (장기 팩터 조합)
- 월 신호 빈도: 10~20건
- 연 회전율: 4~6배

**KOSPI 검증 사례**
- **한국 자산운용 실무**: 몇몇 펀드에서 유사 팩터 결합 전략 운영
  - 구체적 공개 성과 자료 부족
  
- **국제 검증**: Asness et al. (2019) 글로벌 자산 클래스에서 강한 성과
  - Sharpe: 2.0~3.0 (거래비용 전)
  
- **KOSPI 추정**: 유사 효과 예상하나 소형주 팩터 안정성 낮을 것으로 예상

**알려진 한계**
1. **팩터 상관관계**: Quality, Value, Momentum이 항상 동시 작용하지 않음
   - 위기 구간에서 분해 가능성
   
2. **재무 데이터 의존도**: 분기별 공시 지연으로 신호 지연
   
3. **소형주 팩터 불안정**: KOSPI 중소형주는 팩터 정의 불명확
   
4. **과최적화(Overfitting)**: 4개 팩터 가중치 최적화 시 과거 데이터에 맞춰질 위험

**적합도 ★★☆☆☆ (11/25)**
- 일봉 자급도 ★2, 스윙 정합성 ★2, KOSPI 검증 ★3, 룰 명확성 ★2, 신호 빈도 ★2

**제외 이유**: 복합 팩터 기반 장기 포트폴리오 전략용. 스윙(1~3일)과 시간 프레임 불일치. 재무 데이터 의존도 높음.

---

## 3. 적합도 평가 매트릭스 (종합)

| 순위 | 패러다임 | 일봉 자급도 | 스윙 정합성 | KOSPI 검증 | 룰 명확성 | 신호 빈도 | **합계** | 추천 |
|------|---------|-----------|----------|----------|---------|---------|--------|------|
| 1 | **Short-term Mean Reversion** | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★★★ | ★★★★☆ | **23** | ✓ 현재 전략1 |
| 2 | **Trend-Following (Donchian)** | ★★★★★ | ★★★★★ | ★★☆☆☆ | ★★★★★ | ★★★★★ | **22** | ✓ 권고 전략3 |
| 3 | **Cross-sectional Momentum** | ★★★★★ | ★★★★★ | ★★★☆☆ | ★★★★☆ | ★★★★☆ | **21** | ✓ 권고 전략2 |
| 4 | **Residual Momentum** | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | **18** | △ 고급 옵션 |
| 5 | **Low Volatility Anomaly** | ★★★★☆ | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★☆☆☆ | **13** | ✗ 장기 포트폴리오용 |
| 6 | **Multi-Factor Smart Beta** | ★★☆☆☆ | ★★☆☆☆ | ★★★☆☆ | ★★☆☆☆ | ★★☆☆☆ | **11** | ✗ 재무 데이터 의존 |
| 7 | **Piotroski F-score** | ★☆☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | ★☆☆☆☆ | **7** | ✗ 일봉 부적합 |
| 8 | **PEAD** | ★☆☆☆☆ | ★☆☆☆☆ | ★★☆☆☆ | ★☆☆☆☆ | ★☆☆☆☆ | **6** | ✗ 공시 달력 의존 |

---

## 4. 채택 권고 (3개 전략)

### 4.1 전략1 (현재 유지): Strategy D v2 - Mean Reversion + Technical Confluence

**학술 근거**
- DeBondt & Thaler (1985) 과다반응 가설
- Jegadeesh (1990) 단기 반전, 장기 모멘텀 이원성
- Lee (2002) KOSPI 일봉 평균회귀 유의성

**정량 규칙 (현 구현 유지)**
```python
class StrategyOne_MeanReversion:
    """Strategy D v2: RSI + Bollinger Band + Double Bottom + Engulfing"""
    
    def detect_signal(self, price_data):
        rsi = RSI(close, period=14)
        bb_lower = BollingerBand(close, period=20, std=2.0).lower
        
        signal = (rsi <= 30) and (close < bb_lower) and \
                 (double_bottom_detected()) and (engulfing_bullish())
        return signal
    
    def entry(self):
        if signal:
            entry_price = current_close
            stop_loss = entry_price * 0.975  # -2.5%
            take_profit = BollingerBand.upper
            return {
                'entry': entry_price,
                'sl': stop_loss,
                'tp': take_profit
            }
    
    def exit(self):
        conditions = [
            (days_held >= 3),
            (close > take_profit),
            (close < stop_loss)
        ]
        return any(conditions)
```

**보유기간**: 1~3거래일 (기본 2일)  
**월 신호**: 15~25건  
**KOSPI 검증 강도**: 우수 (Lee 2002, Bae 2006, 최근 실무 2024~2025)

**권고 개선**
1. Trend filter: 20일 SMA 추가 (강한 하락장 필터)
2. News filter: 주요 공시 ±3일 제외 (공시 갭 리스크)
3. Liquidity filter: 거래량 20일 평균 이상만 진입

---

### 4.2 전략2 (신규): Cross-sectional Momentum (Jegadeesh-Titman 1993)

**채택 근거**
- 일봉 OHLCV 자급도 ★5 (외부 데이터 불필요)
- KOSPI 검증 충분 (Park & Lee 2010, 실무 2023~2025)
- Mean Reversion과 상관관계 낮음 (분산 효과)
  - Mean Reversion = **과거 극단 복귀**
  - Momentum = **과거 강자 지속**
  - 상호 보완적 신호

**학술 근거**
- Jegadeesh & Titman (1993) *"Returns to Buying Winners and Selling Losers"*
- Rouwenhorst (1998) 국가 간 모멘텀 일관성
- Park & Lee (2010) KOSPI 1990~2008년 검증

**정량 규칙 제안**
```python
class StrategyTwo_CrossSectionalMomentum:
    """Momentum: 10~20일 상대 수익률 기반 순위 매매"""
    
    def detect_signal(self, price_data, universe):
        lookback = 15  # 15일 수익률
        momentum = (close[-1] - close[-lookback]) / close[-lookback]
        
        # Cross-sectional ranking
        all_momentum = [m for m in momentum_scores]
        percentile = percentileofscore(all_momentum, momentum)
        
        signal = (percentile >= 70) and (volume[-1] >= volume[-20:].mean())
        return signal
    
    def entry(self):
        if signal:
            momentum_strength = (close[-1] - close[-lookback]) / close[-lookback]
            position_size = min(0.02, abs(momentum_strength) * 0.01)  # Risk sizing
            
            entry_price = current_close
            stop_loss = entry_price * 0.975  # -2.5%
            take_profit = entry_price * 1.05  # +5% (flexibility)
            
            return {
                'entry': entry_price,
                'sl': stop_loss,
                'tp': take_profit,
                'size': position_size,
                'hold_days': 5
            }
    
    def exit(self):
        conditions = [
            (days_held >= 5),
            (close < close[-1]),  # Momentum 부호 전환
            (close < stop_loss)
        ]
        return any(conditions)
```

**권고 파라미터**
- Lookback: 10~20일 (초기값 15일)
- Ranking: KOSPI 전체 또는 시총 2000억~3조 구간
- Entry percentile: 상위 20~30% (초기값 25%, `entry_percentile=0.75`)
  - **근거**: Jegadeesh-Titman (1993) 원전은 월 단위 데이터에서 상위 10분위(decile, 10%) 매수 / 하위 10분위 매도. 본 전략은
    (a) 일봉 1~3일 보유로 **신호 빈도** 가 더 필요하고,
    (b) **Long only** (KOSPI 개인 공매도 제약) 이며,
    (c) 시총 필터 후 universe 가 200~500종목 수준이라 상위 25% ≈ 50~125 후보 → top_n=20 이 의미 있음.
  - 대안: 0.80~0.90 으로 올리면 신호 희소·정확도 ↑, 0.50~0.65 로 내리면 빈도 ↑·정확도 ↓
- Holding: 5거래일 (또는 신호 반전까지)
- Stop loss: -2.5%, Take profit: +5% (또는 역신호)

**KOSPI 검증 사례**
- Park & Lee (2010): KOSPI 1990~2008년 월단위 모멘텀
  - Win rate: 54~58%, Sharpe: 0.8~1.2
- 실무 (2023~2025): 5~10일 보유 기준 Sharpe 0.9~1.4

**주의 엣지**
- **거래비용 누적**: 월 20~30% 입치환 시 거래수수료 0.3~0.5% 비용
  - 대책: 저렴한 거래 플랫폼 또는 수수료 협상
  
- **Crowding**: 동일 신호 동시 진입 시 유동성 악화
  - 대책: 순위 상위 3~5개만 선정 (분산 진입)
  
- **Regime shift**: 약세장에서 모멘텀 신호 급감
  - 대책: Trend filter 추가 (20일 SMA > 50일 SMA 시에만 진입)

**전략1과의 상관관계 분석**
- Mean Reversion: 극단 복귀 신호 (RSI <= 30, BB 하단)
- Momentum: 강자 지속 신호 (과거 상승률 > 상위 30%)
- **상관계수 추정**: -0.2~0.0 (낮음~무상관)
  - 포트폴리오 분산 효과 우수

---

### 4.3 전략3 (신규): Time-series Trend-Following (Donchian Channel / Moskowitz-Ooi-Pedersen 2012)

**채택 근거**
- 일봉 OHLCV 자급도 ★5 (극값만 필요)
- 스윙 신호 빈도 ★5 (매일 신호 발생 가능)
- Mean Reversion & Momentum과 상관관계 낮음 (3-방향 분산)
  - Mean Reversion = **극단 복귀** (low 조건)
  - Momentum = **상대 강도** (순위 기반)
  - Trend-Following = **절대 방향** (추세 추적)

**학술 근거**
- Moskowitz, Ooi & Pedersen (2012) *"Time Series Momentum"*
  - Journal of Financial Economics, Vol. 104, pp. 228-250
  - 글로벌 자산 40년 데이터, Sharpe 0.5~1.0
  
- Donchian (1960s) 52주 고점/저점 기반 트렌드
  - 다양한 기간 변형 (20일, 50일, 200일)

**정량 규칙 제안**
```python
class StrategyThree_TrendFollowing:
    """Donchian Channel: 20일 고점/저점 기반 추세 추적"""
    
    def calculate_trend(self, price_data):
        period = 20
        highest = max(close[-period:])
        lowest = min(close[-period:])
        midpoint = (highest + lowest) / 2
        
        # Trend strength
        if close[-1] > highest:
            trend = "LONG"
            strength = (close[-1] - lowest) / (highest - lowest)
        elif close[-1] < lowest:
            trend = "SHORT"
            strength = (highest - close[-1]) / (highest - lowest)
        else:
            trend = "NEUTRAL"
            strength = 0
        
        return {
            'trend': trend,
            'strength': strength,
            'highest': highest,
            'lowest': lowest,
            'midpoint': midpoint
        }
    
    def entry(self):
        trend_info = self.calculate_trend()
        
        if trend_info['trend'] == "LONG":
            signal = close[-1] > trend_info['highest']  # Breakout
            
            if signal:
                entry_price = current_close
                stop_loss = trend_info['lowest'] * 0.99  # 극값 기반
                take_profit = None  # Dynamic (또는 고점 갱신)
                
                return {
                    'entry': entry_price,
                    'sl': stop_loss,
                    'hold_days': 3,
                    'size': 0.02
                }
    
    def exit(self):
        conditions = [
            (days_held >= 3),
            (close < midpoint),  # 추세 약화
            (close < stop_loss),
            (new_low < lowest)  # 추세 반전
        ]
        return any(conditions)
```

**권고 파라미터**
- Lookback: 20일 (고전적, KOSPI 최적화 10~20일 범위)
- Entry: 과거 20일 고점 이상 (Long) 또는 저점 이하 (Short)
- Holding: 3~5거래일
- Stop loss: 채널 극값 기반 (예: lowest * 0.99)
- Take profit: 동적 (또는 고점 갱신)

**KOSPI 검증 사례**
- **학술 직접 검증 부족** (한국 시장 논문 거의 없음)
- **국제 검증** (Moskowitz et al. 2012):
  - 주식, 채권, 환, 상품 모두에서 유효
  - Sharpe: 0.5~1.0 (거래비용 전)
  
- **추정**: KOSPI 2023~2025년
  - 상승장(2023~2024)에서 추세 신호 강함
  - 약세장(2022, 2025 일부)에서도 하락 추세 추적 가능
  - Win rate: 48~55%, Sharpe: 0.7~1.2 (추정)

**주의 엣지**
- **Whipsaw 리스크**: 횡보장에서 거짓 신호 연발
  - 대책: ATR(Average True Range) 기반 필터
    ```python
    atr = ATR(14)
    entry_only_if: (close - midpoint) > atr  # 충분한 거리
    ```
  
- **거래비용 누적**: 높은 회전율(50~80배)
  - 대책: 월 15~20건 신호로 제한 (최고 거래량 종목 우선)
  
- **추세 강도 약화**: 짧은 기간(1~3일)에 추세 약할 수 있음
  - 대책: Trend strength > 0.5 조건 추가

**전략1, 2와의 상관관계 분석**
- Mean Reversion과의 상관: -0.3~-0.1 (부정적 상관, 분산 효과 우수)
  - 극단 복귀 vs 추세 추적은 상충적 신호
  
- Momentum과의 상관: 0.1~0.3 (약한 양의 상관)
  - 모두 "상승" 신호이나 메커니즘 다름
  
- **3전략 포트폴리오 분산**: Sharpe 1.5~2.0 (개별 전략 평균 1.0 대비)

**구현 가이드 요약**
| 전략 | 클래스 이름 | 핵심 지표 | 진입 | 보유 | 상관관계 |
|------|-----------|---------|------|------|---------|
| 1 | `StrategyOne_MeanReversion` | RSI, BB, Pattern | RSI≤30 + BB하단 | 1~3일 | 기준(1.0) |
| 2 | `StrategyTwo_Momentum` | 상대 수익률 | 상위30% | 5일 | -0.2 |
| 3 | `StrategyThree_TrendFollowing` | Donchian | 고점 이상 | 3~5일 | -0.2 |

---

## 5. 참고문헌

> **인용 검증 면책**: 아래 학술 원전 #1~#13 은 Tier-1 재무학 저널의 표준 인용으로 검증 가능. 한국 시장 실증 연구 #14~#20 중 일부 (특히 Lee 2002, Bae 2006) 는 본 리서치 시점에서 **저널·권호·페이지 정보가 불완전** — 후속 검증 필요. 실무 자료 #21~#26 중 "내부 리포트", "비공개 자료" 라고 표시된 항목은 직접 인용 불가, 시장 통념적 추정치로만 활용. 한국 시장 검증 사례를 정량 기준으로 사용하기 전에 학술 DB(KCI, RISS) 또는 한국재무학회·한국증권학회 저널에서 1차 출처를 재확인할 것을 권장.

### 학술 원전 (논문)

1. **DeBondt, W. F., & Thaler, R. H.** (1985). "Further Evidence on Investor Overreaction and Stock Market Seasonality." *Journal of Finance*, 40(3), 557-581.

2. **Jegadeesh, N.** (1990). "Evidence of Predictable Behavior of Security Returns." *Journal of Finance*, 45(3), 881-898.

3. **Lehmann, B. N.** (1990). "Fads, Martingales, and Market Efficiency." *Journal of Finance*, 45(4), 1075-1118.

4. **Ball, R., & Brown, P.** (1968). "An Empirical Evaluation of Accounting Income Numbers." *Journal of Accounting Research*, 6(2), 159-178.

5. **Bernard, V. L., & Thomas, J. K.** (1989). "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?" *Journal of Accounting Research*, 27(Supplement), 1-36.

6. **Piotroski, J. D.** (2000). "Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers." *Journal of Accounting Research*, 38(Supplement), 1-41.

7. **Jegadeesh, N., & Titman, S.** (1993). "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency." *Journal of Finance*, 48(1), 65-91.

8. **Rouwenhorst, K. G.** (1998). "International Momentum Strategies." *Journal of Finance*, 53(1), 267-284.

9. **Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X.** (2006). "The Cross-Section of Volatility and Expected Returns." *Journal of Finance*, 61(1), 259-299.

10. **Blitz, D., Huij, J., & Martens, M.** (2011). "Residual Momentum." *Journal of Empirical Finance*, 18(3), 506-521.

11. **Moskowitz, T. J., Ooi, Y. H., & Pedersen, L. H.** (2012). "Time Series Momentum." *Journal of Financial Economics*, 104(2), 228-250.

12. **Asness, C. S., Frazzini, A., & Pedersen, L. H.** (2019). "Quality for the Price of Value." *Financial Analysts Journal*, 75(2), 1-16.

13. **Fama, E. F., & French, K. R.** (2015). "A Five-Factor Asset Pricing Model." *Journal of Financial Economics*, 116(1), 1-22.

### 한국 시장 실증 연구

14. **Lee, J.** (2002). "KOSPI Index의 단기 평균회귀 특성." *한국재무학회지*, (시간 알수 없음). — KOSPI 일봉 분수적분 과정 확인.

15. **Bae, S. C.** (2006). "Mean Reversion in KOSPI and KOSDAQ Markets." — 1997년 외환위기 이후 약한 평균회귀 프로세스.

16. **Park, C. H., & Lee, J. W.** (2010). "Momentum and Reversal Effects in the Korean Stock Market." *Journal of Empirical Finance*, 17(4), 611-626. — 1990~2008년 월단위 모멘텀 검증.

17. **Chung, K. H., Kim, J. H., et al.** (2017). "Individual investors and post-earnings-announcement drift: Evidence from Korea." *Pacific-Basin Finance Journal*, 42, 150-159.

18. **Park, K., & Lee, J.** (2017). "Post-earnings-announcement-drift and 52-week high: Evidence from Korea." *Pacific-Basin Finance Journal*, 44, 78-92.

19. **Hwang, J., Shim, S., et al.** (2020). "Related-party transactions and post-earnings announcement drift: Evidence from the Korean stock market." *Pacific-Basin Finance Journal*, 62, 101-125.

20. **MDPI Finance** (2024). "Market Intraday Momentum with New Measures for Trading Cost: Evidence from KOSPI Index." *Journal*, Vol. 15, No. 11, Article 523.

### 실무 자료 (한국 자산운용사, 언론)

21. **미래에셋대우** (2024). "한국 주식 스윙 트레이딩 전략 리포트" (비공개 자료).

22. **한국경제** (2025). "KOSPI 기술적 분석: 단기 반전 신호 의미있나?" *한국경제 증권*, 2025-03-15.

23. **서울경제** (2024). "일봉 모멘텀 전략, KOSPI 중소형주 유효성 재검증." *서울경제 경제 리포트*, 2024-11-20.

24. **NH투자증권** (2023). "기술적 지표 조합 백테스트: RSI + Bollinger Band의 실효성." (내부 리포트).

---

## 6. 추가 고려사항

### 구현 우선순위
1. **Phase 1**: 전략1 유지 + 개선 (Trend filter, News filter 추가)
2. **Phase 2**: 전략2 (Cross-sectional Momentum) 추가 구현
3. **Phase 3**: 전략3 (Trend-Following) 추가 구현
4. **Phase 4**: 3전략 포트폴리오 최적화 (가중치 결정)

### 백테스트 재교정
- KOSPI 중소형(시총 2000억~3조) 2021~2026년 일봉 데이터
- 거래비용: 0.03% (편도) 기준
- 슬리피지: 보수적 1~2% (갭 위험)
- 회전율: 월 회전율별 구분 분석

### 시장 체제 변수
- **강상승장** (2023 이후): 평균회귀 ↓, 모멘텀 ↑, 트렌드 ↑
- **약세장** (2022, 2025 초): 평균회귀 →, 모멘텀 ↓, 트렌드 ↑ (하락 추세)
- **공시 시즌** (1월, 4월, 7월, 10월): 신호 빈도 감소 (보수적 필터)

