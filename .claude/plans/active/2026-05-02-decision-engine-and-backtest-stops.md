---
slug: decision-engine-and-backtest-stops
status: active
created: 2026-05-02
updated: 2026-05-02
---

# 매매 인사이트 시스템 개선 — 의사결정 엔진 metric 확장 + 백테스트 엔진 손절 정밀화

## 목표

별도 매매 인사이트 시스템에서 도출한 5개 시스템 개선안을 `kospi-swing-scanner` 의 **두 레이어** (Decision Layer + Backtest Layer)에 매핑하여 적용한다.

- **Decision Layer**: 의사결정 엔진(`core/decision/*`, `cli.py --decide --interview`)에 신규 metric (`rr_band`, `rr_ratio`, `atr_14`, `source_strategy`)을 노출하고, must_have DSL 로 강제 검토 큐·sweet spot 필터를 활성화한다.
- **Backtest Layer**: `backtest_engine/strategy.py` 의 진입 필터·손절 계산을 개선한다 (RR sweet spot 진입 필터, ATR 동적 손절, 조건부 시간 손절).

기대효과: ① 의사결정 엔진이 사용자 가중치/우선순위로 후보를 거를 때 RR/ATR/소속전략을 활용 가능 ② 백테스트에서 노이즈 손절 감소·고변동성 종목 대응 ③ 변경 후 백테스트 PF/승률 향상 측정 (`python -m backtest_engine.demo` 회귀 비교).

## 배경

### 기존 시스템 (관련 부분만)

**의사결정 엔진** (커밋 5072095 도입, plug-in 아키텍처):

- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/config.py:30-42` — `Priority(key, weight 0-100, direction lower_better/higher_better, label)`
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/config.py:58-112` — `WeightConfig.priorities + must_have`. YAML 위치 `~/.kospi-scanner/weights.yml`.
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/config.py:119-134` — must_have DSL: `'per<30'` (필수), `'?per<30'` (optional, 결측 시 skip).
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/aggregator.py:35-39` — metric 추출: `getattr(cand, "score", 0)` 또는 `cand.metadata.get(key)`. **plug-in: metadata 에 키만 추가하면 자동 인식**.
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/aggregator.py:42-67` — percentile rank 정규화 (cross-sectional, 결측은 rank 0).
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/aggregator.py:99-119` — final_score = Σ(percentile × priority.weight), 0~100 범위.
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/ensemble.py:25-36` — `compute_ensemble_count()` → metadata['ensemble_count'].
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/ensemble.py:65-90` — `auto_volatility_scenarios()` (bull regret = max(reward) - my_reward, bear regret = my_risk - min(risk)) + Minimax Regret 정렬.
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/runner.py:138-194` — `run_decide_ranking()` / `run_decide_journal()`.
- `/Users/user/PycharmProjects/kospi-swing-scanner/output/decision_journal.py:35-217` — Decision Journal markdown (펀더멘털 + 가중치 기여도 + R:R + 사용자 메모).
- `/Users/user/PycharmProjects/kospi-swing-scanner/cli.py:345-393` — `--interview` / `--decide --top-n / --select / --notes / --weights / --scan-results-dir`.

**백테스트 엔진** (`StrategyD v2` 한정):

- `/Users/user/PycharmProjects/kospi-swing-scanner/backtest_engine/core.py:223-231` — `calc_atr(high, low, close, period=14)` (EWM, 이미 구현). Strategy 3 진입 필터에만 사용, 손절 미연동.
- `/Users/user/PycharmProjects/kospi-swing-scanner/backtest_engine/strategy.py:StrategyDConfig` — `stop_loss_pct=0.025`, `target_1_pct=0.03`, `target_2_pct=0.05`, `time_stop_bars=3` (모두 고정 %, 무조건 시간 손절).
- `/Users/user/PycharmProjects/kospi-swing-scanner/backtest_engine/strategy.py:113-231` — `StrategyD.check_entry()` (RSI+BB+쌍바닥+장악형 양봉, RR 필터 없음).
- `/Users/user/PycharmProjects/kospi-swing-scanner/backtest_engine/strategy.py:236-272` — `StrategyD.check_exit()` 우선순위: STOP_LOSS → TARGET_1/2 → TIME_STOP (무조건 N봉).
- `/Users/user/PycharmProjects/kospi-swing-scanner/backtest_engine/screener.py:38-53` — `risk_pct`, `reward_pct_target_2`, `risk_reward_ratio` 프로퍼티 (계산만, 진입 필터 미반영).
- `/Users/user/PycharmProjects/kospi-swing-scanner/backtest_engine/tests/conftest.py` — `ScenarioBuilder` fixture (perfect_double_bottom, fake_double_bottom_loss).

**전략 → Candidate metadata 채움**:

- `/Users/user/PycharmProjects/kospi-swing-scanner/strategies/strategy_one_d_v2.py:scan` — Candidate 생성. 현재 `metadata={"market": ctx.market}` 등.
- `/Users/user/PycharmProjects/kospi-swing-scanner/output/formatters.py:_CSV_FIELDS` (라인 ~20-45) — CSV 컬럼 헤더.

**테스트 베이스라인**: 370개 통과 (커밋 5072095 시점). `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q`.

### 사용자 5개 요구사항 → 두 레이어 매핑

| # | 사용자 요구 | 레이어 | 매핑 위치 |
|---|------------|-------|----------|
| 1 | 트리거(전략) 가중치 시스템 | Decision | `WeightConfig.priorities` (사용자 인터뷰로 입력) + 신규 metadata 키 `source_strategy` |
| 2 | 고품질 신호 강제 검토 큐 | Decision | must_have DSL: `?ensemble_count>=2` 또는 신규 `is_high_quality` boolean |
| 3 | 손익비 sweet spot 정렬 | Decision + Backtest | metadata `rr_ratio`, `rr_band` + `Priority(key='rr_band', direction=higher_better)` + 백테스트 진입 필터 |
| 4 | 시간 기반 손절 (조건부) | Backtest | `StrategyD.check_exit` 우선순위 분기 |
| 5 | ATR 기반 동적 손절 | Backtest | `StrategyD.check_entry` 의 stop/target 계산 (max 결합) |

## 접근 방식

### 핵심 원칙

1. **Bridge first**: 의사결정 엔진의 plug-in 아키텍처를 활용하려면 전략이 metadata 에 키를 채워야 한다. 따라서 PR #1 (metric bridge) 를 모든 변경의 전제로 삼는다.
2. **Backward compatible**: 모든 신규 옵션은 디폴트 OFF 또는 None. 기본 호출 시 기존 370개 테스트 통과.
3. **Decision vs Backtest 독립성**: Decision Layer 변경(PR #2)은 백테스트 엔진을 건드리지 않는다. Backtest Layer 변경(PR #3·4·5)은 의사결정 엔진을 건드리지 않는다. PR #1 만 양쪽을 잇는다.
4. **재사용 우선**: `calc_atr`, `risk_reward_ratio` 프로퍼티, `ScenarioBuilder` fixture, `aggregate_candidates`, `format_decision_journal` 등 기존 함수를 그대로 사용한다. 신규 추상화 추가 금지.
5. **사용자 명시 결정**: ATR 손절은 `max(fixed_pct, ATR×mult)` (사용자 확인). 모든 옵션 디폴트 OFF (사용자 확인).

### 매매 일지 / 트레일링 스톱 / 알림 큐 처리

- **매매 일지** = `output/decision_journal.py` 로 대체 (이미 존재). 진입 결정 + 펀더멘털 + R:R + 사용자 메모를 markdown 으로 기록. 실매매 PF 추적 시스템은 별도 프로젝트 영역으로 명시적 out of scope.
- **강제 검토 큐 알림** = 알림 인프라 부재. must_have DSL + Minimax Regret 정렬로 **출력 상단 노출**만 처리, push 알림은 out of scope.
- **트레일링 스톱** = 현재 미구현, 본 작업에서도 추가하지 않음 (사용자 프롬프트 요구사항 5번에서도 명시 제외).

## 단계별 계획

### PR #1 — Metric Bridge: Strategy → Decision Engine + Output

**목적**: 모든 후속 PR 의 전제. 전략이 Candidate.metadata 에 의사결정 엔진 / 출력에 필요한 키를 채운다.

**변경 대상**:

- `strategies/strategy_one_d_v2.py:scan` — Candidate.metadata 에 `source_strategy=self.name`, `rr_ratio = reward_pct_t2 / max(risk_pct, eps)`, `rr_band = "sweet"|"over"|"below"`, `atr_14 = calc_atr(...).iloc[-1]` 추가.
- `strategies/strategy_two_cross_sectional_momentum.py:scan` 및 `strategies/strategy_three_trend_following.py:scan` — 동일 키 채움 (Strategy 2/3 도 일관 노출, 의사결정 엔진이 같은 후보 풀에서 비교 가능).
- `output/formatters.py:_CSV_FIELDS` — 신규 옵션 컬럼: `rr_ratio`, `rr_band`, `atr_14`, `source_strategy`. metadata 키 존재 시만 채우고, 없으면 빈 문자열 (기존 출력 깨지지 않음).
- `output/formatters.py:_candidate_to_row` — metadata 추출 로직 추가.
- `output/formatters.py:format_markdown` — RR/ATR 컬럼 추가 (기존 PER/ROE 옆).

**산출물**:

- `tests/test_output_formatters.py` 에 `test_csv_includes_rr_atr_when_metadata_present`, `test_csv_handles_missing_metadata` (회귀 가드).
- `backtest_engine/tests/test_strategy.py` 또는 `tests/test_strategy_one_unit.py` 에 `test_candidate_metadata_includes_rr_atr`.
- 변경 후 `.venv/bin/python cli.py --strategy strategy_one_d_v2 --format csv` 출력 헤더에 신규 컬럼 등장.

**검증 방법**:

```bash
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q
# 기대: 370 → 374 (신규 4개 통과)
.venv/bin/python -m ruff check . --exclude .venv
.venv/bin/python cli.py --strategy strategy_one_d_v2 --market KOSPI --format csv --cache-root .cache | head -1
# 기대: 헤더에 rr_ratio, rr_band, atr_14, source_strategy 포함
```

---

### PR #2 — Decision Engine 확장: must_have 활용 + sweet spot priority

**목적**: 사용자 요구 1·2·3 의 Decision 측면을 만족. WeightConfig priority 추가 + must_have DSL 활용.

**변경 대상**:

- `core/decision/config.py:_parse_must_have` (라인 ~119-134) — DSL 에 boolean 비교 (`is_high_quality==True`) 와 string 비교 (`source_strategy!=closing_strength_top`) 가 이미 지원되는지 검증. 미지원이면 추가.
- `core/decision/aggregator.py:_extract_metric` (라인 35-39) — `rr_band` 같은 string metric 을 percentile rank 정규화 시 처리하는 로직 검증. string 인 경우 ordinal mapping (`sweet=2, over=1, below=0`) 추가 또는 numeric `rr_ratio` 로 우회.
- 권장: PR #2 본체는 **코드 변경 최소화** — 사용자가 `--interview` 로 priority 를 추가하기만 하면 plug-in 아키텍처 덕에 기존 코드가 작동. 코드 변경은 **DSL 확장 + 문서화** 한정.
- `docs/decision_engine_recipes.md` 신규 — 사용자가 5개 요구사항을 의사결정 엔진에서 어떻게 활성화하는지 권장 weights.yml 예시 (sweet spot rr_ratio priority weight 25, must_have `?ensemble_count>=2`, `?rr_ratio>=2.0` 등).
- `tests/test_decision_aggregator.py` 에 신규 metric (`rr_ratio`) 통합 테스트.
- `tests/test_decision_config.py` 에 must_have DSL 신규 비교 연산자 (`!=`, boolean 등) 테스트.

**산출물**:

- 권장 `~/.kospi-scanner/weights.yml` 샘플 (sweet spot 시나리오, 강제 검토 시나리오, 트리거 가중치 시나리오 3종).
- DSL 확장 단위 테스트 3개.
- aggregator string→ordinal 정규화 (또는 numeric 우회) 단위 테스트 2개.

**검증 방법**:

```bash
.venv/bin/python cli.py --interview  # 신규 priority 입력 가능 확인
.venv/bin/python cli.py --decide --top-n 5 --weights tests/fixtures/sweet_spot.yml
# 기대: rr_ratio 가중치가 적용된 ranking, must_have 필터 적용
.venv/bin/python -m pytest tests/test_decision_*.py -v
```

---

### PR #3 — 백테스트: RR Sweet Spot 진입 필터

**목적**: 백테스트 엔진의 `StrategyD.check_entry` 에 RR 필터 추가. 의사결정 엔진과 독립.

**변경 대상**:

- `backtest_engine/strategy.py:StrategyDConfig` — `use_rr_filter: bool = False`, `min_rr_ratio: float = 2.0`, `sweet_spot_rr_low: float = 2.0`, `sweet_spot_rr_high: float = 2.5`.
- `backtest_engine/strategy.py:StrategyD.check_entry` — entry/stop/target 계산 직후 RR 산출, `use_rr_filter=True` 시 `min_rr_ratio` 미만 후보 reject. TradeSignal.metadata 에 `rr_band` 채움 (이미 PR #1 에서 metadata 패턴 정착).
- 정렬 우선순위: 백테스트 엔진은 단일 종목당 1 시그널이라 정렬 불필요. metadata 만 노출.
- `backtest_engine/tests/test_strategy.py` 에 신규 테스트 4개:
  - `test_rr_filter_excludes_below_min` (RR=1.5 → reject)
  - `test_rr_filter_allows_sweet_spot` (RR=2.2 → accept, rr_band="sweet")
  - `test_rr_filter_allows_above_sweet_spot` (RR=3.0 → accept, rr_band="over")
  - `test_rr_filter_disabled_default` (회귀 가드)

**검증 방법**:

```bash
.venv/bin/python -m pytest backtest_engine/tests/test_strategy.py -v
# 기대: 374 → 378 (신규 4개)
.venv/bin/python -m backtest_engine.demo > /tmp/demo_after_pr3.txt
diff <(.venv/bin/python -m backtest_engine.demo) /tmp/demo_baseline.txt
# 기대: use_rr_filter=False 디폴트라 출력 동일
```

---

### PR #4 — 백테스트: ATR 기반 동적 손절·목표가

**목적**: `calc_atr` 결과를 진입 시점 스냅샷하여 stop_loss = `entry - max(fixed_pct_distance, ATR×atr_stop_mult)`, target_2 = `entry + ATR×atr_target_mult`.

**변경 대상**:

- `backtest_engine/strategy.py:StrategyDConfig` — `use_atr_stops: bool = False`, `atr_stop_mult: float = 1.5`, `atr_target_mult: float = 3.0`, `atr_min_threshold: float = 0.0` (저유동성 가드).
- `backtest_engine/core.py:TradeSignal` (또는 동일 위치) — `atr_at_entry: float | None = None`.
- `backtest_engine/strategy.py:_compute_stops_and_targets(entry_price, atr14)` 헬퍼 함수 신설 (테스트 가능성).
- `backtest_engine/strategy.py:StrategyD.check_entry` — `use_atr_stops=True` 시:
  ```python
  atr14 = calc_atr(df.high, df.low, df.close, 14).iloc[idx]
  if pd.isna(atr14) or atr14 < self.config.atr_min_threshold:
      # fallback to fixed % (기존 로직)
  else:
      stop_distance = max(entry * self.config.stop_loss_pct, atr14 * self.config.atr_stop_mult)
      stop_loss = entry - stop_distance
      target_2 = entry + atr14 * self.config.atr_target_mult
  ```
- `backtest_engine/engine.py` Position — atr_at_entry 전달·저장.
- 신규 테스트 5개:
  - `test_atr_stop_uses_max_when_atr_wider` (고변동성 → ATR×1.5 채택)
  - `test_atr_stop_uses_max_when_pct_wider` (저변동성 → fixed % 채택)
  - `test_atr_target_uses_atr_mult` (target_2 = ATR×3.0)
  - `test_atr_nan_falls_back_to_fixed_pct` (상장 직후 종목)
  - `test_atr_below_threshold_falls_back` (저유동성 가드)

**검증 방법**:

```bash
.venv/bin/python -m pytest backtest_engine/tests/test_strategy.py -v
# 기대: 378 → 383
# ATR 활성화 백테스트 비교 (사용자 직접 검증):
.venv/bin/python -c "
from backtest_engine.strategy import StrategyDConfig
from backtest_engine.demo import run
print('ATR off:', run(StrategyDConfig()))
print('ATR on :', run(StrategyDConfig(use_atr_stops=True)))
"
```

---

### PR #5 — 백테스트: 조건부 시간 손절

**목적**: 기존 무조건 N봉 시간 손절을 **수익률 미달성 시에만** 발동하도록 개선.

**변경 대상**:

- `backtest_engine/strategy.py:StrategyDConfig`:
  - `use_conditional_time_stop: bool = False`, `conditional_time_stop_bars: int = 3`, `min_progress_pct: float = 0.01`.
  - `force_time_stop_bars: int | None = None` (기존 `time_stop_bars: int = 3` 의 deprecated alias 로 유지, 두 파라미터 동시 설정 시 경고).
- `backtest_engine/strategy.py:ExitReason` enum — `CONDITIONAL_TIME_STOP` 멤버 추가.
- `backtest_engine/strategy.py:StrategyD.check_exit` (라인 236-272) — 우선순위 재정의:
  ```
  1) STOP_LOSS (low ≤ position.stop_loss)
  2) TARGET_1 / TARGET_2 (high ≥ target_*)
  3) CONDITIONAL_TIME_STOP (use_conditional_time_stop ON
                            and bars_held >= conditional_time_stop_bars
                            and current_pnl_pct < min_progress_pct)
  4) TIME_STOP (force_time_stop_bars 설정 시 bars_held ≥ N)
  ```
- 신규 테스트 5개:
  - `test_conditional_time_stop_triggers_on_no_progress` (3봉 + PnL+0.5% → 청산)
  - `test_conditional_time_stop_skipped_with_progress` (3봉 + PnL+1.5% → 미청산)
  - `test_conditional_time_stop_disabled_default`
  - `test_force_time_stop_still_works` (alias 회귀)
  - `test_priority_stop_loss_beats_time_stop` (같은 봉 STOP_LOSS 우선)

**검증 방법**:

```bash
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q
# 기대: 383 → 388 (신규 5개)
.venv/bin/python -m backtest_engine.demo
# 기대: 디폴트 설정에서 변경 전과 동일 PF/승률 (회귀 가드)
```

## 리스크 및 대안

| 리스크 | 대안 / 안전장치 |
|--------|----------------|
| string metric (`rr_band`) 의 percentile rank 정규화가 의도와 다름 (sweet/over/below 가 cross-sectional 비교에서 ordinal 로 풀리지 않음) | numeric `rr_ratio` 만 priority key 로 사용. `rr_band` 는 must_have 필터 + 출력 라벨 용도로만 사용. PR #2 의 핵심 결정. |
| ATR 14일 lookback 부족 (상장 직후 종목 → NaN) | `pd.isna(atr14)` 체크 후 fixed % fallback. PR #4 단위 테스트로 보장. |
| 저유동성 종목 ATR 비현실적으로 작아 손절 폭이 fixed % 보다 좁아짐 | `atr_min_threshold` 가드 (디폴트 0.0 = 비활성, 운영 중 필요시 설정). max() 결합이라 ATR 작더라도 fixed % 가 floor. |
| `force_time_stop_bars=None` 디폴트 변경이 기존 사용자 코드 회귀 (기존 `StrategyDConfig()` 호출 → time_stop_bars=3 무조건 청산) | `time_stop_bars` 를 deprecated alias 로 유지, 둘 중 하나만 설정된 경우 기존 동작 보존. 두 파라미터 동시 설정 시 경고. 회귀 단위 테스트 (`test_force_time_stop_still_works`). |
| 의사결정 엔진 must_have DSL 이 `!=` `==` boolean 비교를 미지원할 수 있음 | PR #2 첫 단계: `core/decision/config.py:_parse_must_have` 의 현재 지원 연산자 확인 후 필요 시 확장. 미확장 시 numeric 우회 (예: `rr_ratio>=2.0` 만 사용). |
| RR sweet spot 후보가 너무 적어 진입 0건 | sweet spot 은 정렬 우선순위로만, 배제 기준은 `min_rr_ratio=2.0` 단독. RR≥2.0 후보가 모두 진입 가능. PR #3 의 default 정책. |
| 전략 2·3 metadata 추가가 기존 백테스트 회귀 가능성 | acc5ccf 커밋의 `strategies/__init__.py:99 라인 변경` 영향도 확인. 회귀 단위 테스트 (`test_strategy_two_unit.py`, `test_strategy_three_unit.py`) 신규 metadata 키 검증. |

### 단순화 옵션 (사용자 부담 시)

- **MVP**: PR #1 (bridge) + PR #3 (RR 필터) + PR #5 (조건부 시간 손절) 만. PR #2 (Decision 확장) + PR #4 (ATR) 보류. PR #1 만으로도 의사결정 엔진이 신규 metric 활용 가능.

## 성공 기준

- [ ] PR #1 머지 후 `.venv/bin/python cli.py --strategy strategy_one_d_v2 --format csv` 헤더에 `rr_ratio,rr_band,atr_14,source_strategy` 등장.
- [ ] PR #2 머지 후 `.venv/bin/python cli.py --decide --weights tests/fixtures/sweet_spot.yml --top-n 5` 가 RR 가중치 반영된 ranking 출력.
- [ ] PR #3·4·5 머지 후 `.venv/bin/python -m backtest_engine.demo` 가 디폴트 설정에서 변경 전과 동일한 PF/승률 (backward compatible).
- [ ] PR #3·4·5 활성화 시 (`use_rr_filter=True, use_atr_stops=True, use_conditional_time_stop=True`) 백테스트 demo PF 가 베이스라인 대비 ≥0% (실험적, 사용자 검증).
- [ ] 모든 PR 머지 후 `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` 388개 이상 통과 (370 + 신규 18).
- [ ] `.venv/bin/python -m ruff check . --exclude .venv` clean.

## 테스트 전략

### 단위 테스트 (신규 18개)

| PR | 파일 | 테스트 수 | 검증 내용 |
|----|------|----------|----------|
| #1 | `tests/test_output_formatters.py`, `tests/test_strategy_one_unit.py` | 4 | metadata 채움 + CSV 컬럼 노출 + 회귀 가드 |
| #2 | `tests/test_decision_config.py`, `tests/test_decision_aggregator.py` | 5 | must_have DSL 확장 + numeric metric 통합 |
| #3 | `backtest_engine/tests/test_strategy.py` | 4 | RR 필터 sweet/over/below + 디폴트 회귀 |
| #4 | `backtest_engine/tests/test_strategy.py` | 5 | ATR max() + NaN/threshold fallback + target 비례 |
| #5 | `backtest_engine/tests/test_strategy.py` | 5 | 조건부 시간 손절 + 우선순위 + alias 회귀 |

### 회귀 보호

- 모든 신규 옵션 디폴트 OFF/None. `StrategyDConfig()` 무인자 호출 시 변경 전 동작.
- `python -m backtest_engine.demo` 출력을 PR 시작 전 `/tmp/demo_baseline.txt` 로 저장하고 매 PR 후 diff.
- 기존 370개 테스트 모두 변경 없이 통과.

### 통합 테스트

- PR #1 후: `cli.py --strategy strategy_one_d_v2` E2E (mock 네이버) 출력에 신규 컬럼.
- PR #2 후: `cli.py --decide --weights <fixture>` E2E (manifest.json fixture) 출력에 신규 priority 반영.
- PR #5 후: `backtest_engine.demo` 활성화 옵션으로 PF 비교 산출.

## Progress

- [x] 2026-05-02 1차 초안 작성 (`/Users/user/.claude/plans/validated-wondering-porcupine.md`, 백테스트 한정)
- [x] 2026-05-02 plan-review-loop 1회차 → **refactor** (의사결정 엔진 미인지)
- [x] 2026-05-02 의사결정 엔진 구조 탐색 (`core/decision/*` plug-in 아키텍처 확인)
- [x] 2026-05-02 2차 초안 작성 (본 파일, 두 레이어 분리 + 5 PR)
- [x] 2026-05-02 2차 자체 체크 게이트 통과 (7 도메인 섹션 + 모호 표현 0)
- [x] 2026-05-02 2차 리뷰 1회차 → **pass** (시니어 아키텍트 페르소나, 6 관점 모두 통과)
- [x] 2026-05-02 사용자 최종 승인 (PR #1 부터 구현 시작)
- [x] 2026-05-02 PR #1 구현 + commit `28e3c0c` (376 passed, +6)
- [x] 2026-05-02 PR #2 구현 (must_have DSL string/boolean + recipes, 383 passed, +7)
- [x] 2026-05-02 PR #3 구현 (백테스트 RR 필터, 387 passed, +4)
- [x] 2026-05-02 PR #4 구현 (백테스트 ATR 손절, 392 passed, +5)
- [ ] PR #5 구현 (백테스트 조건부 시간 손절)
- [ ] 통합 회귀 검증

## Decision Log

| Decision | Rationale | Date |
|----------|-----------|------|
| 1차 plan refactor | 의사결정 엔진(`core/decision/*`, 커밋 5072095) 의 존재를 누락하여 사용자 프롬프트의 "트리거 가중치/매매 일지/강제 검토" 를 잘못 매핑 (out of scope 처리). 백테스트 엔진 한정 plan 이라 사용자 의도의 절반 이상을 놓침. | 2026-05-02 |
| 두 레이어 분리 (Decision + Backtest) | 의사결정 엔진은 plug-in 아키텍처라 metadata 키 추가만으로 신규 metric 활용 가능. 백테스트 엔진 변경(ATR/시간 손절)은 진입 시뮬레이션 한정이라 의사결정 엔진과 독립. 두 영역을 같은 PR 에 묶으면 리뷰/롤백 어려움. | 2026-05-02 |
| PR #1 (metric bridge) 를 모든 후속 PR 의 전제로 | metadata 채움이 양 레이어의 공통 원자. 이를 분리하면 PR 간 의존성이 깔끔해짐. | 2026-05-02 |
| ATR 손절 = `max(fixed_pct, ATR×mult)` | 사용자 결정 (프롬프트 원본). 노이즈 청산 방지가 단일 손실 폭 제한보다 우선. | 2026-05-02 |
| 모든 신규 옵션 디폴트 OFF/None | 370개 기존 테스트 회귀 보호 + 점진적 활성화. | 2026-05-02 |
| 매매 일지 신설 = `output/decision_journal.py` 로 대체 | 이미 진입 결정/펀더멘털/R:R/메모 markdown 생성 기능 존재. 실매매 trade ledger 는 본 프로젝트 영역 외. | 2026-05-02 |
| 트레일링 스톱·강제 검토 큐 알림 = 본 작업 제외 | 트레일링 스톱은 사용자 프롬프트 5번에서도 명시 제외. 알림 인프라 부재 → must_have DSL + Minimax Regret 정렬로 출력 상단 노출만. | 2026-05-02 |
| `time_stop_bars` deprecated alias 유지 | 기존 사용자 코드 호환. `force_time_stop_bars: None` 디폴트로 무조건 시간 손절 비활성화하되 alias 로 폴백. | 2026-05-02 |

## Surprises & Discoveries

| Observation | Evidence |
|-------------|----------|
| 초기 `gitStatus` (system context) 가 stale snapshot 이라 의사결정 엔진 커밋(5072095) 누락. `git status` 실시간 조회 시 `nothing to commit, working tree clean` + recent commits 에 `feat(decision)` 발견. | `git log --oneline -15` 출력에 `5072095 feat(decision): 의사결정 프레임워크 통합 (Phase 1+2)` 와 `acc5ccf chore: 백로그 잔여 변경 일괄 정리`. |
| 의사결정 엔진은 plug-in 아키텍처 — metadata dict 에 키만 추가하면 자동 인식. interview/aggregator/ensemble 코드 변경 거의 불필요. | `core/decision/aggregator.py:35-39` `cand.metadata.get(key)`. interview.py 는 사용자 stdin 으로 priority key 받음, hardcoded 목록 없음. |
| Decision Journal 이 사용자 요구의 "매매 일지" 와 정확히 매핑됨 (펀더멘털 + 가중치 기여도 + R:R + 사용자 메모 6 섹션). | `output/decision_journal.py:35-160`. |
| 테스트 베이스라인이 268 → 370 (5072095 커밋이 +72 신규). 1차 plan 의 "268개 통과" 기준 무효. | 커밋 메시지 "회귀: 370 단위 테스트 통과 (Phase 1+2 신규 +72), ruff clean". |

## Outcomes & Retrospective

(pass 후 채울 것)
