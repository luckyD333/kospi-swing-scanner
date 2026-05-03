# 팩터 동적 가중치 (HMM Regime + Factor Momentum + 전략별 가중치) 구현 계획

## Context

현재 `--decide`는 static `weights.yml`로 후보를 ranking한다.
세 가지 기능을 추가한다:

1. **HMM Regime Score**: 시장 국면을 1~100 연속 점수로 표현 (UI 노출용 이력 저장 포함)
2. **Factor Momentum**: 과거 scan_results 팩터-수익률 상관계수 → 가중치 자동 조정
3. **전략별 가중치**: strategy_one_d_v2 등장 시 높은 신뢰도 부여 (드물게 등장 → 높은 가중치)

**아키텍처 분리 원칙**: 계산-저장-읽기 완전 분리.
`scripts/compute_weights.py` (주기 실행) → JSON 저장 → `cli.py --decide` (읽기만)

---

## 수정된 파일 영향 분석 (PR #1~3)

| PR | 변경 | 현재 계획 영향 |
|----|------|--------------|
| PR #1 | `Candidate.metadata`에 `source_strategy`, `rr_ratio`, `rr_band`, `atr_14` 추가 | **직접 활용**: `source_strategy`로 전략별 가중치 구현, `rr_ratio`를 Factor Momentum 팩터에 추가 |
| PR #2 | must_have DSL string/boolean 지원 (`rr_band==sweet` 등) | `WeightConfig`에 `strategy_weights` 섹션 추가 시 동일 파싱 인프라 활용 |
| PR #3 | 백테스트 RR Sweet Spot 진입 필터 | 동적 가중치 계획에 직접 영향 없음 |

**현재 테스트**: 387개 통과 (PR #3 완료 기준). 이 계획 구현 후 검증 기준.

---

## 전략별 가중치 설계

`source_strategy` (PR #1에서 이미 metadata에 존재) 기반으로 `ensemble_count`를 **weighted_ensemble_score**로 가중화.

**weights.yml 확장**:
```yaml
priorities:
  - key: per
    weight: 30
    direction: lower_better
    label: 저PER
  # ... 기존 priorities ...
  - key: ensemble_count          # 이 key 이름 유지 (aggregator 수정 불필요)
    weight: 10
    direction: higher_better
    label: 다중전략

strategy_weights:                # 신규 섹션 (선택적, 없으면 모두 1.0)
  strategy_one_d_v2: 2.0         # 드물게 등장 → 높은 신뢰
  strategy_two_cross_sectional_momentum: 1.0
  strategy_three_trend_following: 1.0

must_have:
  - per<30
```

**ensemble_count 가중화 로직** (`core/decision/ensemble.py` 수정):
```python
# 기존: ensemble_count = 등장 전략 개수
# 변경: weighted_ensemble_score = sum(strategy_weights[s] for s in strategies_appeared)

# strategy_one_d_v2 단독 → 2.0
# strategy_two + strategy_three → 2.0
# 셋 모두 → 4.0
```

`aggregator.py`는 수정 불필요 — `ensemble_count` key 값만 float으로 바뀜.

---

## HMM Regime Score

**2-state GaussianHMM**: BEAR / BULL 두 상태, `P(BULL) × 100` → 1~100 연속 점수.
- 80+: 강한 bull / 50: 전환 구간 / 20-: 강한 bear
- SIDEWAYS 이산 분류 제거 → 연속 점수로 정도 표현

**Market proxy**: 캐시 677개 종목 등가중 log-return + 20일 rolling std (2-feature)

**가중치 조정 방식**: regime_score가 낮을수록 → weights.yml의 보수적 팩터(PER, ROE) 가중치 올리고, momentum 가중치 내림. 구체적으로:
```
regime_score → 조정 multiplier
  ≥ 70 (bull): momentum_pct weight +30%, per/roe 그대로
  30~69 (neutral): 조정 없음
  < 30 (bear): per/roe weight +20%, momentum_pct -30%
```

이 조정은 Factor Momentum 상관계수 결과에 overlay. Factor Momentum이 비활성이면 regime 조정만 적용.

---

## Factor Momentum

**활성 조건**: scan_results ≥ 30일 누적 (현재 0개 → 당장은 비활성)

**팩터 후보** (PR #1 추가분 포함):
- `per`, `roe`, `momentum_pct` (기존)
- `rr_ratio` (PR #1 신규) — 손익비가 수익률과 상관될 경우 반영
- `score` (전략 내부 점수)

**증분 계산**: `.cache/factor_records.parquet`에 (날짜, ticker, 팩터값, 3일후수익률) 누적.
이미 처리된 날짜는 skip.

---

## 저장 파일

### `.cache/dynamic_weights.json` (결정 엔진용)
```json
{
  "computed_at": "2026-05-02T09:00:00",
  "regime_score": 72,
  "factor_momentum_active": false,
  "weight_config": {
    "priorities": [{"key": "per", "weight": 28.5, ...}],
    "must_have": ["per<30"],
    "strategy_weights": {"strategy_one_d_v2": 2.0, ...}
  },
  "meta": {
    "n_samples": 0,
    "correlations": {},
    "regime_adjustment_applied": true,
    "hmm_n_tickers": 677,
    "hmm_n_days": 81
  }
}
```

### `.cache/regime_analysis.json` (UI용)
```json
{
  "computed_at": "2026-05-02T09:00:00",
  "current_score": 72,
  "history": [
    {"date": "2026-04-30", "score": 72, "log_return": 0.0041, "volatility": 0.0089, "prob_bull": 0.72}
  ],
  "hmm_meta": {"n_components": 2, "n_tickers": 677, "n_days": 81,
                "bull_state_mean_return": 0.0038, "bear_state_mean_return": -0.0021}
}
```

---

## 파일 구조

```
core/decision/
    market_regime.py        ← 신규: HMM 학습 + regime_score
    factor_performance.py   ← 신규: 팩터 상관계수 + 가중치 변환
scripts/
    compute_weights.py      ← 신규: 주기 실행 entry point
.cache/
    dynamic_weights.json    ← 결정 엔진이 읽음
    regime_analysis.json    ← UI가 읽음
    factor_records.parquet  ← 증분 누적
```

---

## 신규: `core/decision/market_regime.py`

```python
@dataclass
class RegimePoint:
    date: str; score: int; log_return: float; volatility: float; prob_bull: float

@dataclass
class RegimeAnalysis:
    current_score: int          # 1~100
    history: list[RegimePoint]
    bull_state_mean_return: float
    bear_state_mean_return: float
    n_tickers: int; n_days: int

def build_market_proxy(cache_root: Path, max_tickers: int = 100) -> pd.DataFrame:
    """등가중 log_return + volatility 시계열.
    종목 선택: manifest.json tickers_meta의 market_cap_bil 내림차순 상위 max_tickers개."""

def analyze_regime(cache_root: Path) -> RegimeAnalysis:
    """GaussianHMM(n_components=2) → RegimeAnalysis. 실패 시 ValueError."""

def apply_regime_overlay(
    base_config: WeightConfig, regime_score: int
) -> WeightConfig:
    """regime_score 기반으로 priority weight 조정. 원본 불변, 새 WeightConfig 반환.
    조정 후 전체 weight 를 합=100 으로 비율 정규화 (WeightConfig.__post_init__ 불변식 유지).
    bear(<30): per/roe ×1.2, momentum_pct ×0.7 → normalize
    bull(≥70): momentum_pct ×1.3 → normalize
    neutral(30-69): 조정 없음"""
```

---

## 신규: `core/decision/factor_performance.py`

```python
def update_factor_records(scan_root, cache_root, hold_days=3) -> pd.DataFrame:
    """factor_records.parquet 증분 append.
    cutoff = today - timedelta(days=hold_days + 2)  # +2 주말 보정
    scan_date > cutoff 인 날짜는 수익률 미확정 → skip.
    이미 처리된 날짜도 skip."""

def measure_factor_correlations(records, min_samples=15) -> dict[str, float]:
    """팩터별 Spearman 상관계수. 빈 dict → 균등 가중치."""

def correlations_to_weights(correlations, base_config, floor_pct=5.0) -> WeightConfig:
    """음수 클리핑 → softmax → floor → WeightConfig."""
```

---

## 수정: `core/decision/ensemble.py`

```python
def compute_weighted_ensemble_score(
    by_strategy: dict[str, list[Candidate]],
    strategy_weights: dict[str, float],  # weights.yml의 strategy_weights
) -> dict[str, float]:
    """ticker → weighted_ensemble_score (float).
    strategy_weights 없으면 모두 1.0 (기존 ensemble_count와 동일)."""
```

`_build_unique_pool()` (runner.py)에서 metadata 주입 시 두 키 분리:
- `ensemble_count`: `int(round(weighted_score))` — 표시용 (decision_journal.py 기존 코드 무수정)
- `ensemble_score`: `weighted_score` (float) — aggregator percentile 정렬용

`weights.yml` 기본 priorities 의 key 를 `ensemble_count` → `ensemble_score` 로 변경 필요.

---

## 수정: `core/decision/config.py`

```python
@dataclass
class WeightConfig:
    priorities: list[Priority]
    must_have: list[str]
    strategy_weights: dict[str, float] = field(default_factory=dict)  # 신규

    @classmethod
    def load_dynamic(cls, path: Path) -> "WeightConfig":
        """dynamic_weights.json → WeightConfig."""
```

YAML 로드 시 `strategy_weights` 섹션 파싱 추가. 없으면 빈 dict (backward compatible).
`save()` 수정: `if self.strategy_weights: payload['strategy_weights'] = dict(self.strategy_weights)` 추가.

---

## 수정: `scripts/collect.py`

`CollectConfig` 에 `scan_root: Path = Path('scan_results')` 필드 추가 (CLI arg `--scan-root`).

```python
# run_collect() 마지막 단계
scan_root = cfg.scan_root  # 기본값 Path('scan_results')
subprocess.run(
    [sys.executable, "scripts/compute_weights.py",
     "--cache-root", str(cfg.cache_root),
     "--scan-root", str(scan_root)],
    capture_output=True,
)
# 실패해도 수집 성공으로 처리
```

`compute_weights.py` CLI: `--cache-root`, `--scan-root`, `--output` (기본값 `{cache_root}/dynamic_weights.json`).

---

## 수정: `core/decision/runner.py`

```python
def run_decide_ranking(scan_root, target_date, top_n, weight_config,
                       *, dynamic_weights_path=None) -> Path:
    if dynamic_weights_path and dynamic_weights_path.exists():
        weight_config = WeightConfig.load_dynamic(dynamic_weights_path)
```

---

## 수정: `cli.py`

```python
decision_grp.add_argument("--dynamic-weights", action="store_true",
    help=".cache/dynamic_weights.json 로드 (없으면 --weights fallback)")
```

---

## 수정 대상 파일 요약

| 파일 | 변경 |
|------|------|
| `core/decision/market_regime.py` | 신규 |
| `core/decision/factor_performance.py` | 신규 |
| `scripts/compute_weights.py` | 신규 |
| `core/decision/config.py` | `strategy_weights` 필드 + `load_dynamic()` |
| `core/decision/ensemble.py` | `compute_weighted_ensemble_score()` 추가 |
| `core/decision/runner.py` | `dynamic_weights_path` 파라미터, weighted ensemble 호출 |
| `cli.py` | `--dynamic-weights` 플래그 |
| `scripts/collect.py` | compute_weights.py subprocess 호출 |
| `requirements.txt` | `hmmlearn>=0.3.0` |

`aggregator.py`, `interview.py` — **수정 없음**.

---

## 엣지 케이스

| 상황 | 처리 |
|------|------|
| dynamic_weights.json 없음 | static weights.yml fallback (경고 없음) |
| 캐시 < 30일 / 종목 < 10개 | HMM skip, regime_score=50 |
| HMM 수렴 실패 | regime_score=50 + 경고 |
| scan_results < 30일 | factor_momentum_active=false |
| strategy_weights 미정의 전략 | weight=1.0 (기본값) |
| 모든 상관계수 ≤ 0 | 균등 가중치 |
| factor_records.parquet 손상 | 삭제 후 전체 재구성 |

---

## 새 세션 시작 지침

새 세션에서 이 계획을 이어받으려면:
1. `.claude/plans/active/2026-05-02-dynamic-weights-hmm-factor-momentum.md` 읽기
2. `requirements.txt`에 `hmmlearn>=0.3.0` 추가 후 구현 시작
3. 구현 순서 (병렬화 포함):
   - `requirements.txt` hmmlearn 추가
   - **Lane A (독립)**: `market_regime.py` + `tests/test_market_regime.py`
   - **Lane B (독립)**: `factor_performance.py` + `tests/test_factor_performance.py`
   - Merge A + B 후: `config.py` → `ensemble.py` → `runner.py` → `compute_weights.py` → `collect.py` → `cli.py`
   - 기존 테스트 파일 확장 (test_decision_config, test_decision_ensemble, test_cli_decide)

## 검증

```bash
pip install "hmmlearn>=0.3.0"

.venv/bin/python -m pytest \
  tests/test_market_regime.py tests/test_factor_performance.py \
  tests/test_decision_config.py tests/test_decision_ensemble.py \
  tests/test_cli_decide.py -v
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q  # 387개+ 통과

.venv/bin/ruff check . --exclude .venv

# 실동작
python scripts/collect.py --market KOSPI --cache-root .cache --max-universe 50
# → compute_weights.py 자동 실행
# → .cache/dynamic_weights.json, .cache/regime_analysis.json 생성 확인

python cli.py --strategy all --market KOSPI --max-universe 50 --output-dir scan_results --format json
python cli.py --decide --top-n 5 --dynamic-weights --cache-root .cache
# → decision_top5.md에 ensemble_count 정수 표시, regime_score 헤더 확인

# dynamic_weights.json 없을 때 fallback 확인
mv .cache/dynamic_weights.json /tmp/ && \
python cli.py --decide --top-n 5 --dynamic-weights --cache-root .cache && \
mv /tmp/dynamic_weights.json .cache/
```

**테스트 픽스처** (신규 파일):
- `tests/test_market_regime.py`: `OhlcvDiskCache.read` mock — 2개 국면 합성 시계열, 캐시 부족/HMM 수렴 실패 케이스, regime_overlay 경계값(30/70) + 합=100 검증
- `tests/test_factor_performance.py`: mock scan_results (30일), cutoff 필터, min_samples 충족/미충족, 모든 상관계수 ≤ 0

**기존 파일 확장**:
- `tests/test_decision_config.py`: `test_strategy_weights_yaml_roundtrip`, `test_load_dynamic_applies_regime_weights`, `test_save_includes_strategy_weights`
- `tests/test_decision_ensemble.py`: `test_weighted_ensemble_score_strategy_one_d_v2` (score=2.0), `test_weighted_ensemble_fallback_unknown_strategy` (weight=1.0)
- `tests/test_cli_decide.py`: `test_dynamic_weights_flag_loads_json`, `test_dynamic_weights_missing_falls_back_to_static`

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 5 issues resolved (D1-D5), 26 test gaps mapped (D6), 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT**: ENG CLEARED — 구현 시작 가능.
