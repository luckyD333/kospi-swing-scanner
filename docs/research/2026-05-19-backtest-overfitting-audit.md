# 백테스트 방법론 감사 및 전략 개선 제안

> 작성일: 2026-05-19
> 트리거: 백테스트 정석 (생존자 편향, look-ahead bias, walk-forward, CPO) 검토 요청
> 대상: 5개 전략, 2026-05-14 파라미터 일괄 최적화 결과 + 시스템 전체

---

## 0. Executive Summary

**진단**: 현재 시스템은 학술적 토대(Jegadeesh, Moskowitz 등)는 견고하나, **백테스트 방법론에서 3가지 치명적 과적합 위험**을 안고 있다.

| 위험 | 증거 | 우선순위 |
|------|------|---------|
| **단일 윈도우 그리드 서치 과적합** | 2026-05-14 12개 파라미터를 90일 단일 윈도우로 동시 최적화 — basin 비판 "값이 급격히 변하는건 안좋겠죠"에 정면 위배 | P1 (Critical) |
| **Walk-Forward 검증 부재** | `backtest_engine/`에 WF 프레임워크 없음. OOS는 spec 문서에 "권장"만 언급 | P1 (Critical) |
| **Regime-Conditional Parameters 미사용** | HMM regime detection 인프라(`market_regime.py`) 존재하나 전략 파라미터에 미연결. 라플라스의악마 결론 "세팅값은 시장환경에 따라 변하게 됩니다"가 미구현 | P1 (Critical) |

**제안 요약**: 신규 전략 추가보다 **기존 시스템의 검증 인프라 보강이 선행되어야 한다**. 안 검증된 5개 전략 위에 6번째를 쌓는 것은 과적합을 가중시킬 뿐이다. 단, 검증 인프라가 확보된 후 Residual Momentum(S6) 추가는 합리적 확장이다.

---

## 1. 현재 시스템 진단 (Audit)

### 1.1 2026-05-14 파라미터 변경에 대한 의심 신호

| 전략 | 파라미터 | 변경 | 의심 수준 | 사유 |
|------|---------|------|---------|------|
| S5 | `tight_range_mult` | 1.5 → 2.5 (+67%) | 🔴 매우 높음 | PF 0.81 → 4.57 jump on 90-day window. PF >3은 통계적으로 의미 없음 |
| S5 | `vol_shrink_ratio` | 0.7 → 0.9 | 🔴 매우 높음 | 신호 수 4건 → 35건. n=4 기반 임계값 추출은 곡선 적합 |
| S4 | `pullback_lookback` | 5 → 3 | 🟡 높음 | avgPnL 부호 뒤집힘(-0.07% → +0.51%). 부호 변화는 노이즈 가능성 |
| S4 | `ma_trend` | 20 → 30 (+50%) | 🟡 높음 | 단일 파라미터 변경으로 승률 10%p 점프(44.9% → 54.9%). 너무 큰 단일 변수 효과 |
| S3 | 4개 동시 변경 | lookback·ATR필터·stop·target | 🔴 매우 높음 | 4축 동시 최적화는 차원의 저주 — 후행 검증 필수 |
| S2 | `lookback` | 15 → 20 (+33%) | 🟢 낮음 | Jegadeesh-Titman 원전이 월 단위(약 20일)이라 학술 정합성 회복 |

### 1.2 basin 비판 기준 점검

basin이 제시한 3가지 검증 기준에 대한 현재 시스템 점수:

| 기준 | 현재 상태 | 점수 |
|------|----------|-----|
| 인접 윈도우 간 세팅값 변화 정도 | 측정 안 함 — 단일 윈도우 사용 | ❌ |
| 세팅값에 ±variation 시 OOS 성과 안정성 | spec에 ±20% 민감도 분석 "계획" 명시되어 있으나 자동화 미구현 | ❌ |
| 훈련/검증 윈도우 길이 자체에 대한 robustness | 90일 단일 윈도우만 사용. 60일/120일 비교 없음 | ❌ |

3가지 모두 미충족. 현재 시스템은 basin의 비판을 정면으로 받는다.

### 1.3 라플라스의악마 시나리오와 비교

라플라스의악마: "이평선 크로스 매매 — 추세구간 100MA, 횡보구간 20MA, 시장에 따라 변함"

| 시장 환경 | 이 시스템이 해야 할 일 | 현재 시스템 |
|----------|---------------------|----------|
| 추세 강화 (HMM=Bull) | S3, S5 강화 / S1 약화 — 추세 추종 우위 | 모든 전략 동등 가중 |
| 횡보 (HMM=Sideways) | S1, S4 강화 / S2, S3 약화 — 평균회귀 우위 | 모든 전략 동등 가중 |
| 고변동·하락 (HMM=Bear) | 모든 전략 비활성 또는 S1만 엄격한 stop으로 | 진입 게이트만 부분 작동 |

**핵심 갭**: HMM 인프라는 있으나, 결과가 전략 선택/파라미터 조정에 반영되지 않음. `entry_gate.py`가 통과/차단 이분법만 적용.

### 1.4 학술 논거 vs 한국 시장 검증

| 전략 | 학술 토대 | KOSPI 검증 | 갭 |
|------|---------|----------|-----|
| S1 (MR) | DeBondt-Thaler ★5 | Lee 2002, Bae 2006 ★4 | 1997년 이후 평균회귀 강도 약화. HMM regime 필요 |
| S2 (CSM) | Jegadeesh-Titman ★5 | Park-Lee 2010 ★3 | 원전은 월 단위. 1~3일 보유와 시간 스케일 불일치 |
| S3 (TF) | Moskowitz ★5 | KOSPI 직접 검증 부족 ★2 | **가장 검증 약함**. 회전율 50~80배 → 거래비용 누적 위험 |
| S4 (Pullback) | 학술 원전 명시 안 됨 | 검증 없음 | **순수 경험칙**. 학술 근거 보강 필요 |
| S5 (Bull Flag) | 기술적 분석 고전 | 검증 없음 | **순수 차트 패턴**. PF 4.57은 n=35로 통계적 부족 |

---

## 2. 개선 제안

### P1. Walk-Forward Optimization 프레임워크 (Critical)

**문제**: 단일 윈도우 그리드 서치 → 과적합 보장.

**제안**: 롤링 윈도우 검증 자동화.

```
[Walk-Forward 표준 프로토콜]

훈련 윈도우: 90일 (in-sample)
검증 윈도우: 30일 (out-of-sample, no peek)
이동 단위: 30일

타임라인:
  W1: train[2024-01-01 ~ 2024-03-31] → test[2024-04-01 ~ 2024-04-30]
  W2: train[2024-02-01 ~ 2024-04-30] → test[2024-05-01 ~ 2024-05-31]
  W3: train[2024-03-01 ~ 2024-05-31] → test[2024-06-01 ~ 2024-06-30]
  ...

각 윈도우에서:
  1. 훈련 구간에서 그리드 서치로 best 파라미터 추출
  2. 검증 구간에서 그 파라미터로 OOS 성과 측정
  3. 파라미터 + OOS Sharpe를 기록

산출:
  - param_stability_score = stdev(W_i 파라미터) / mean(W_i 파라미터)
  - oos_sharpe_decay = (mean_train_sharpe - mean_oos_sharpe) / mean_train_sharpe
```

**구현 위치**: `backtest_engine/walk_forward.py` (신규).

**판정 기준**:
- `param_stability_score < 0.30` (CV 30% 이내) → 안정
- `oos_sharpe_decay < 0.40` (성과 저하 40% 이내) → 견고
- 둘 다 위반 시 해당 파라미터/전략 사용 금지

**즉시 실행 액션**: 2026-05-14 변경된 12개 파라미터 전부 WF 재검증. 통과 못 한 변경은 롤백.

### P2. Regime-Conditional Parameter Optimization (Critical)

**문제**: HMM regime은 추정만 하고 전략 선택에 반영 안 됨.

**제안**: 4 regime × 5 strategy 가중치 매트릭스.

```
[Regime × Strategy 가중치 매트릭스 (초기 제안)]

                  Bull   Sideways  Bear   HighVol
S1 (MR)           0.5    1.2       0.8    0.6
S2 (CSM)          1.5    0.7       0.3    0.0   ← Bear/HighVol 비활성
S3 (TF)           1.5    0.3       0.5    0.0
S4 (Pullback)     1.3    1.0       0.5    0.0
S5 (Bull Flag)    1.5    0.5       0.0    0.0

* 1.0 = 기본 가중치, 0.0 = 신호 무시, > 1.0 = 가중치 가산
* HMM regime은 daily 단위 추정. 시그널 발생 시 현재 regime 조회 후 가중치 적용
```

**구현**:
1. `core/decision/regime_weights.yml` 신규 — 매트릭스 정의
2. `core/decision/aggregator.py` 수정 — confidence × regime_weight 적용
3. 가중치 ≤ 0.3 종목은 후보 리스트에서 제외

**검증**: WF 윈도우 각각에서 regime 통계 + 가중치 적용 전후 OOS Sharpe 비교.

**기대 효과**: basin/라플라스의악마 두 사람의 결론 — "세팅값(혹은 전략 선택)이 시장에 따라 변해야 한다"를 직접 구현.

### P3. 파라미터 민감도 자동화 (Critical)

**문제**: spec에 "±20% 변동 테스트" 명시되어 있으나 자동 실행 없음.

**제안**: 단위 테스트로 강제.

```python
# tests/test_param_sensitivity.py (신규)

import pytest
from itertools import product

@pytest.mark.parametrize("delta", [-0.2, -0.1, 0.0, +0.1, +0.2])
def test_strategy_one_rsi_sensitivity(delta):
    base = 30
    cfg = StrategyOneDv2Config(rsi_threshold=int(base * (1 + delta)))
    result = run_backtest(cfg, period="2024-01-01:2024-12-31")
    
    # 베이스라인 대비 Sharpe 40% 이내 저하
    assert result.sharpe >= BASELINE_SHARPE_S1 * 0.6, \
        f"S1 fragile to RSI={cfg.rsi_threshold}: Sharpe {result.sharpe}"
```

각 전략의 핵심 파라미터(전략당 2~3개)에 대해 ±10%, ±20% 자동 검증. CI에서 실행.

### P4. 파라미터 수 축소 (Simplification)

basin과 article 모두 강조: "성과가 무너지지 않는 선에서 모델을 최대한 단순화".

**현재 전략당 free parameter 수**:
- S1: 12개 (config 7 + detector 5)
- S2: 10개
- S3: 9개
- S4: 9개
- S5: 8개

목표: **전략당 ≤ 5개**.

**즉시 정리 가능 항목**:

| 전략 | 후보 | 단순화 방안 |
|------|------|----------|
| S1 | `prominence_pct`, `db_price_tolerance`, `prev_support_lookback` | detector 1개로 고정(simple), price_tolerance를 ATR 비율로 변환 |
| S1 | Confidence booster 5개 (+0.10/+0.10/+0.15/+0.10/+0.05) | 가중치 데이터 기반 회귀로 재추정. 또는 booster 3개로 축소 |
| S3 | `score_scale` | 정규화 공식으로 대체 (배수 파라미터 제거) |
| S4 | `min_vol_ratio = 0.8` | 거래량 percentile rank ≥ 40 으로 대체 (절대값 → 상대값) |
| S5 | `vol_shrink_ratio`, `tight_range_mult` | 단일 파라미터(volatility_compression_score) 합성 후 임계값만 노출 |

### P5. 신뢰도 부스터 가중치 데이터 기반 재추정

**문제**: S1의 confidence booster (+0.10/+0.10/+0.15/+0.10/+0.05)는 **직관적 수동 할당**이다. 데이터 기반 검증 없음.

**제안**: 로지스틱 회귀로 가중치 재추정.

```python
# 각 시그널의 5개 booster를 features로, 실제 +3% 도달 여부를 label로
X = [panic_vol, second_low_vol, prev_inst_buy, macd_recovery, kospi_bullish]
y = signal_succeeded  # binary

logreg = LogisticRegression()
logreg.fit(X_train, y_train)

# 회귀 계수가 새로운 booster 가중치
# 음의 계수가 나오는 booster는 제거 후보
```

산출물: `data/booster_weights.json` — WF 윈도우별 갱신.

### P6. Multi-Strategy Ensemble Voting

**문제**: 현재 5개 전략 결과를 단순 union/concat. 같은 종목이 여러 전략에서 나오면 의미가 다른데 동등 취급.

**제안**: Confluence 가산 가중치.

```
ensemble_score[ticker] = sum(
    strategy_confidence[ticker] × regime_weight[strategy][regime]
    for strategy in active_strategies if ticker in strategy.candidates
)

후보 채택: ensemble_score >= threshold (예: 1.5)
포지션 크기: ensemble_score 비례 (단, 캡 적용)
```

**효과**: 3개 전략이 동시에 추천하는 종목 → 강한 매수 신호. 1개 전략만 → 약한 신호.

### P7. 거래비용 현실화 (Reality Filter)

article 강조: "Sharpe 4.47 → 5bp 적용 시 -3.19".

**현재 가정**: 거래비용 0.25% 왕복 (spec).

**검증 필요 항목**:
- 슬리피지: 시총 2,000억~30,000억 구간에서 실측 분포 확인
- 동시호가 체결 가능성: 진입가 = 종가 가정이 현실적인가
- 일중 변동성: 15:20 종가 추정 vs 실제 15:30 동시호가 체결 가격 차이

**즉시 액션**: paper trading 2주 → 실측 슬리피지 분포 수집 → 백테스트 비용 파라미터 보정.

---

## 3. 신규 전략 후보 (조건부)

**전제**: P1~P3 완료(검증 인프라 확보) 후에만 추가 검토.

### S6 (조건부 추가): Residual Momentum (Blitz-Huij-Martens 2011)

**채택 근거**: 학술 적합도 18/25 (research doc 평가). S2(raw CSM)와 차별점:
- S2: 종목 절대 수익률 순위 → KOSPI 시장 전체 상승 시 모든 종목이 후보
- S6: 시장 베타 제거 후 잔차 수익률 순위 → 시장 무관 알파만 추출

**제안 룰**:
```
1. 종목별 60일 KOSPI 회귀 → beta_i, residual_i = return_i - beta_i × kospi_return
2. residual_momentum = sum(residual_i[-20:])
3. cross-sectional percentile rank ≥ 0.80 진입
4. 그 외 SL/TP는 S2와 동일
```

**S2와의 상관**: 추정 0.3~0.5 (낮은 양의 상관). 분산 효과 있음.

**리스크**: 베타 추정 노이즈 — 저유동성 종목에서 불안정. 시총 5,000억 이상으로 유니버스 추가 좁힐 것.

**구현 부담**: 낮음. S2 코드 80% 재사용 가능.

### 권장하지 않는 후보

| 후보 | 미권장 이유 |
|------|----------|
| Intraday Momentum (S7 안) | 30m/1m 인프라는 있으나 동시호가/장마감 효과 정밀 모델링 필요. 1~3일 스윙 스코프 밖 |
| Crash-Day Reversal | 신호 빈도 극소(연 5~10건). 통계적 유의성 확보 불가 |
| Pair Trading | KOSPI 페어 안정성 낮음. 보유 1~3일과 시간 스케일 불일치 |
| Multi-Factor Smart Beta | 분기 재무 데이터 의존. 일봉 자급도 ★2/5로 부적합 |

### 차라리 변경: **S3, S4, S5는 "신규 전략 후보"가 아닌 "통합 후보"**

현재 5개 전략 중 일부는 학술 검증이 약하고 파라미터 동시 변경(2026-05-14)으로 신뢰도가 낮다. **차라리 통합/제거**가 더 시급:

- S3 (Donchian) + S5 (Bull Flag): 본질적으로 둘 다 돌파 전략. S3는 절대 채널, S5는 상대 압축. 합성 단일 "Breakout 전략"으로 단순화 가능.
- S4 (Pullback): 학술 원전 부재. WF 검증 실패 시 제거 후보.

P1 WF 검증 결과에 따라 5개 → 3~4개로 축소가 합리적이다.

---

## 4. 우선순위 매트릭스

| ID | 항목 | 영향도 | 구현 부담 | 우선순위 |
|----|------|------|---------|---------|
| P1 | Walk-Forward 프레임워크 | 매우 높음 | 중 | **1** |
| P2 | Regime-Conditional weights | 매우 높음 | 중 | **2** |
| P3 | 파라미터 민감도 자동화 | 높음 | 낮음 | **3** |
| P7 | 슬리피지/거래비용 현실화 | 높음 | 중 | **4** |
| P4 | 파라미터 수 축소 | 중 | 중 | 5 |
| P6 | Ensemble voting | 중 | 낮음 | 6 |
| P5 | Confidence 가중치 재추정 | 낮음 | 중 | 7 |
| S6 | Residual Momentum 추가 | 낮음 | 중 | **P1~P3 완료 후 검토** |

---

## 5. 실행 권장 순서 (Phased Rollout)

### Phase 1: 검증 인프라 (2~3주)
- P1 Walk-Forward 프레임워크 구현
- P3 민감도 자동화 단위 테스트 추가
- P7 paper trading 슬리피지 측정 시작

### Phase 2: 검증 실행 (1주)
- 2026-05-14 변경된 12개 파라미터 전부 WF 검증
- 통과 못 한 변경 롤백 (예상: S5의 3개 변경, S4의 2개 변경 중 일부)
- 기존 전략 중 OOS Sharpe < 0.5 인 것 비활성화

### Phase 3: Regime CPO (2주)
- P2 Regime weights 매트릭스 구현
- P6 Ensemble voting 통합
- WF 검증으로 가중치 매트릭스 튜닝

### Phase 4: 단순화 (1주)
- P4 파라미터 수 축소
- P5 Confidence 부스터 재추정

### Phase 5: (선택) 신규 전략
- P1~P4 완료 후 S6 (Residual Momentum) 추가 검토
- 단, "현재 5개 전략 → 6개"가 아니라 "정리된 3~4개 + S6"가 되어야 함

---

## 6. 핵심 메시지 (article의 결론과 매핑)

| article 원칙 | 본 제안 매핑 |
|------------|------------|
| "백테스트보다 로직이 중요" (basin) | P2 (regime CPO) — 로직을 시장에 맞게 적응 |
| "세팅값이 윈도우 전진하며 변하는 게 정상" (라플라스의악마) | P1, P2 — WF + regime-conditional |
| "값이 급격히 변하면 과적합" (basin) | P1 — param_stability_score < 0.30 강제 |
| "전략을 단순화하라" (article §7) | P4 — 파라미터 수 ≤ 5 목표 |
| "5bp 수수료에 Sharpe 붕괴" (article §7) | P7 — 슬리피지 현실화 |
| "Free parameter ≤ 5" (article §6) | P4 — 동일 |
| "Train/Test 분리" (article §6) | P1 — WF 표준 프로토콜 |
| "Paper trading 최종 점검" (article §6) | P7 — 슬리피지 측정 |

---

## 7. 의사결정 필요 항목

다음을 사용자가 확인해야 진행 가능:

1. **2026-05-14 12개 파라미터 롤백 권한**: WF 검증 통과 못 한 변경은 즉시 롤백할지, 옵션 플래그로 유지할지
2. **HMM regime 임계값 확정 권한**: 4-regime 분류(Bull/Sideways/Bear/HighVol) 기준값
3. **유니버스 축소 권한**: 시총 5,000억 이상으로 좁히면 S6 추가 가능. 현재 2,000억 유지 시 S6 베타 추정 불안정
4. **S6 추가 vs S3·S4·S5 통합/제거**: 둘 중 어느 방향 우선
5. **거래비용 가정 변경**: 0.25% → 실측 기반(0.30~0.40% 예상) 상향 시 일부 전략 무력화 가능

---

## 부록 A. 2026-05-14 변경 롤백 위험 분석

각 변경의 롤백 시 영향:

| 변경 | 현재 의존도 | 롤백 시 영향 |
|------|----------|----------|
| S5 `tight_range_mult` 1.5→2.5 | 매우 높음 (PF 4.57 의존) | 신호 거의 0 — S5 사실상 비활성 |
| S5 `vol_shrink_ratio` 0.7→0.9 | 매우 높음 | 신호 35건 → 4건 |
| S4 `ma_trend` 20→30 | 높음 | 승률 54.9% → 44.9% |
| S4 `pullback_lookback` 5→3 | 매우 높음 | avgPnL 부호 뒤집힘 |
| S3 4개 동시 변경 | 매우 높음 | Whipsaw 증가 예상 |
| S2 `lookback` 15→20 | 낮음 | Sharpe 약간 저하 |

**권고**: 일괄 롤백 대신, P1 WF 검증으로 변경별 개별 판정. 통과한 것만 유지.
