# 의사결정 엔진 Recipes

`cli.py --interview` / `cli.py --decide` 워크플로우의 권장 `weights.yml` 시나리오 모음. 매매 인사이트 시스템 개선 5 요구사항을 의사결정 엔진(`core/decision/*`)으로 어떻게 활성화하는지를 정리해요.

## 5 요구사항 ↔ 엔진 매핑

| # | 사용자 요구 | 활용 메커니즘 |
|---|------------|---------------|
| 1 | 트리거(전략) 가중치 | 신규 `Priority(key="source_strategy")` 직접 사용 불가(string). 대신 `must_have` DSL 의 `source_strategy!=...` 또는 `source_strategy==...` 으로 특정 전략 후보 필터링 |
| 2 | 고품질 신호 강제 검토 큐 | `must_have` DSL 의 `?ensemble_count>=2` (다중 전략 교차 검출 후보만 통과) |
| 3 | 손익비 sweet spot 정렬 | `Priority(key="rr_ratio", direction="higher_better")` + `must_have` `?rr_ratio>=2.0` |
| 4 | 시간 기반 손절 | 백테스트 엔진 한정 (PR #5). 엔진과 무관 |
| 5 | ATR 기반 동적 손절 | 백테스트 엔진 한정 (PR #4). 엔진과 무관 |

전제: PR #1 metric bridge 가 머지되어 있어 모든 후보 Candidate.metadata 에 `source_strategy`, `rr_ratio`, `rr_band`, `atr_14` 가 채워짐.

## Recipe 1 — Sweet Spot Hunter

**목적**: 손익비 2.0 이상 후보 중 펀더멘털 우량 종목을 우선.

```yaml
# ~/.kospi-scanner/weights.yml
priorities:
  - key: rr_ratio
    weight: 40
    direction: higher_better
    label: 손익비
  - key: roe
    weight: 30
    direction: higher_better
    label: 고ROE
  - key: per
    weight: 20
    direction: lower_better
    label: 저PER
  - key: ensemble_count
    weight: 10
    direction: higher_better
    label: 전략 교차
must_have:
  - "?rr_ratio>=2.0"        # rr_ratio 결측은 통과, 있다면 2.0 이상
  - "?ensemble_count>=1"
```

**해석**: rr_ratio 가 가장 큰 가중(40%). must_have `?rr_ratio>=2.0` 으로 손익비 미달 후보 자동 배제 (단 metadata 결측 종목은 통과 — fundamentals 부족한 신규 상장 등).

## Recipe 2 — 강제 검토 큐 (다중 전략 교차)

**목적**: 2개 이상 전략에서 동시 검출된 후보만 검토 (사용자 요구사항의 "고품질 신호 강제 검토 큐").

```yaml
priorities:
  - key: ensemble_count
    weight: 40
    direction: higher_better
    label: 전략 교차
  - key: score
    weight: 30
    direction: higher_better
    label: 전략점수
  - key: rr_ratio
    weight: 30
    direction: higher_better
    label: 손익비
must_have:
  - "ensemble_count>=2"     # 필수 (옵션 ? 없음) — 단일 전략 후보는 모두 탈락
```

**해석**: must_have 에 `?` 없이 `ensemble_count>=2` 를 두면 단일 전략 후보는 결과에 포함 안 됨. 다중 전략 검출 후보만 ranking. ensemble_count 자체도 priority 로 가중.

## Recipe 3 — 트리거 회피 (저성과 전략 배제)

**목적**: 사용자 매매 일지 분석 결과 PF 0.42 인 `closing_strength_top` 같은 저성과 전략 후보를 시스템 차원에서 배제.

```yaml
priorities:
  - key: rr_ratio
    weight: 50
    direction: higher_better
    label: 손익비
  - key: score
    weight: 50
    direction: higher_better
    label: 전략점수
must_have:
  - "source_strategy!=closing_strength_top"
  - "?ensemble_count>=2"
```

**해석**: `source_strategy!=...` 는 string DSL (`==`/`!=` 만 허용). 특정 전략명 후보는 무조건 탈락. 여러 전략을 동시에 배제하려면 must_have 에 `!=` 항목을 여러 줄로 추가.

## 운영 절차

```bash
# 0) 데이터 수집 (전제)
python scripts/collect.py --market KOSPI --cache-root .cache

# 1) 신호 스캔 (전 전략)
python cli.py --strategy all --market KOSPI \
  --output-dir scan_results --format json --cache-root .cache

# 2) 가중치 인터뷰 (최초 1회)
python cli.py --interview
#   → ~/.kospi-scanner/weights.yml 자동 생성

# 3) 또는 위 Recipe 를 직접 weights.yml 에 복사

# 4) 의사결정 ranking (Top 5)
python cli.py --decide --top-n 5 --scan-results-dir scan_results
#   → scan_results/decision_top5.md

# 5) 최종 후보별 Decision Journal 생성
python cli.py --decide --select 005930,000660 \
  --notes "갭상승 모멘텀 + RR 2.3" \
  --scan-results-dir scan_results
#   → scan_results/journal_005930.md, journal_000660.md
```

## 주의 사항

- **DSL 부등호는 numeric 전용**: `<, <=, >, >=` 는 numeric value 만. string/boolean 에 부등호를 쓰면 평가 실패로 후보 탈락.
- **must_have `?` prefix**: 메트릭 결측 시 조건 skip (통과). prefix 없으면 결측 = 탈락.
- **string 값 큰따옴표 불요**: YAML 안에서 `"source_strategy==gap_up_momentum_top"` 처럼 따옴표는 YAML 문법 (DSL 자체에는 따옴표 불필요).
- **boolean DSL**: `is_high_quality==True` 형식. `True`/`False` 는 case-sensitive (Python True/False).
- **가중치 합 100% 검증**: priorities.weight 합이 100 이 아니면 `WeightConfig` 생성 시 ValueError.

## 동적 가중치 효과 발현 — `ensemble_score` priority 등록 필수

`scripts/compute_weights.py` 가 산출하는 `strategy_weights` 는 `_build_unique_pool` 에서
ticker 의 `ensemble_score` (= 등장 전략의 가중 합) 로 변환되어 metadata 에 주입돼요.
그러나 `aggregator.aggregate_candidates` 의 가중합은 `weights.yml` 의
`priorities[].key` 에 등재된 키만 반영하므로, 다음을 명시해야 효과가 ranking 에 발현돼요:

```yaml
priorities:
  - key: ensemble_score    # 이 항목이 없으면 strategy_weights 변경이 ranking 에 영향 0
    weight: 30.0
    direction: higher_better
    label: 다중 전략 합의도
```

리포 루트의 `weights.yml.example` 을 복사해 시작하세요. (`cp weights.yml.example weights.yml`)

## 시장 국면 (regime_score) 효과 범위

regime_score 는 두 경로로 ranking 에 영향을 줄 수 있어요:

**1) 간접 영향 (기본 활성)** — `apply_regime_overlay`

priority weight 자체를 BULL 시 `momentum_pct × 1.3`, BEAR 시 `per/roe × 1.2`,
`momentum_pct × 0.7` 로 조정 후 합=100 으로 정규화. 즉 priority 의 **영향력 비중**이
시장 국면에 따라 변해요.

**2) 직접 가산 (사용자 옵션)** — `regime_score` priority 등록

`weights.yml` 의 priorities 에 `regime_score` 를 등록하면 모든 후보가 동일
regime_score 를 metadata 에 보유하고, percentile_rank 정규화 후 weight 만큼
contribution 으로 가산돼요. 예:

```yaml
priorities:
  - key: regime_score
    weight: 10.0
    direction: higher_better
    label: 시장 국면
```

BULL=85 시: 모든 후보가 동일 값이라 percentile_rank 가 1/m..1.0 분포로 균등 (m=후보 수).
효과는 후보 분포의 **base 점수 shift** 로 작용 — BULL 시 전체 후보 ranking 의 절대값이
상승, BEAR 시 하락. 같은 값이라도 `aggregator._percentile_rank` 의 정렬 안정성 덕에
contribution 이 0 이 되지 않아요.

추가로 `regime_label` (BULL/NEUTRAL/BEAR) 도 metadata 에 함께 주입되므로 must_have
DSL 에서 `regime_label==BEAR` 같은 조건으로 후보 필터에 활용 가능해요.

사용 시점:
- BULL/BEAR 신호가 명확할 때 후보 분포 자체를 위/아래로 이동시키고 싶을 때
- 다른 priority 와 가중치 합 100 을 유지해야 함 (예: rr_ratio 30 → 20, regime_score 10 추가)

## 동적 가중치 파이프라인 실패 진단

`scan_results/<date>/manifest.json` (또는 `.cache/manifest.json`) 의
`dynamic_weights_computed` 필드를 확인하세요:

- `true` — `compute_weights.py` 정상 종료, `.cache/dynamic_weights.json` 생성
- `false` — `dynamic_weights_error` 필드에 stderr 메시지 (최대 500자)
  - `weights.yml not found at ...` — `cp weights.yml.example weights.yml` 후 재실행
  - HMM 실패: `.cache/dynamic_weights.json` 의 `meta.regime_failure` 확인
    - `hmmlearn_not_installed` → `pip install hmmlearn>=0.3.0`
    - `insufficient_data` → 수집 종목 수/기간 부족
    - `unknown` → 로그 확인
