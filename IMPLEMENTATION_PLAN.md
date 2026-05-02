# 5-변경사항 구현 계획: kospi-swing-scanner

**계획 작성일**: 2026-05-02  
**대상 프로젝트**: `/Users/user/PycharmProjects/kospi-swing-scanner`  
**테스트 기준선**: 268개 테스트 통과 (현재 baseline)

---

## 1. 변경별 영향 파일/함수 매핑 (라인 단위)

### 변경 1: 손익비(RR) 진입 필터 + 스캐너 출력
**우선순위**: P1 (minimum viable change)

#### 구현 파일:
- `backtest_engine/strategy.py:49-76` (StrategyDConfig)
  - 신규 필드:
    - `min_rr_ratio: float = 2.0`
    - `sweet_spot_rr_low: float = 2.0`
    - `sweet_spot_rr_high: float = 2.5`
    - `use_rr_filter: bool = False` (기본값, backward compat)

- `backtest_engine/strategy.py:113-231` (StrategyD.check_entry)
  - 라인 188-220: RR 필터 + confidence 부스트 로직 추가
  - RR = reward_pct_target_2 / risk_pct
  - sweet spot (2.0~2.5): confidence +0.15
  - over-reward (≥2.5): confidence +0.10

- `output/formatters.py:20-45` (CSV 헤더 + 행 생성)
  - 라인 20-24: `_CSV_FIELDS` 에 `"atr_14"`, `"rr_ratio"`, `"rr_band"` 추가
  - 라인 27-45: `_candidate_to_row()` 에서 metadata 추출

---

### 변경 2: ATR 기반 동적 손절·목표가
**우선순위**: P2 (독립 PR)

#### 구현 파일:
- `backtest_engine/core.py:223-231` (calc_atr)
  - 이미 구현됨 ✓

- `backtest_engine/core.py:31-47` (TradeSignal)
  - 신규 필드: `atr_at_entry: float = 0.0`

- `backtest_engine/core.py:49-65` (Position)
  - 신규 필드: `atr_at_entry: float = 0.0`

- `backtest_engine/strategy.py:49-76` (StrategyDConfig)
  - 신규 필드:
    - `use_atr_stops: bool = False`
    - `atr_stop_mult: float = 1.5`
    - `atr_target_mult: float = 3.0`

- `backtest_engine/strategy.py:89-108` (StrategyD.prepare)
  - df["atr"] 계산 추가 (calc_atr 호출)

- `backtest_engine/strategy.py:113-231` (StrategyD.check_entry)
  - 라인 216-220: 진입가/손절/목표 계산 시 ATR 스냅샷 적용
  - `stop_loss = min(atr_stop_distance, fixed_pct)` (더 좁은 쪽, 추천)
  - `target_2 = entry_price + atr * atr_target_mult`

- `backtest_engine/engine.py:200-250` (BacktestEngine.run_multi)
  - Position 생성 시 signal.atr_at_entry 복사

#### 선택지: ATR 손절 기본값
- **Option A** (추천): `min(atr_stop, fixed_pct)` = 더 좁은 쪽
  - 이유: 변동성 기반 + 고정% 이중 안전장치
- **Option B**: `max(atr_stop, fixed_pct)` = 더 넓은 쪽

---

### 변경 3: 조건부 시간 손절
**우선순위**: P3 (독립 PR)

#### 구현 파일:
- `backtest_engine/strategy.py:49-76` (StrategyDConfig)
  - 신규 필드:
    - `use_conditional_time_stop: bool = False`
    - `min_progress_pct: float = 0.01` (1%)

- `backtest_engine/strategy.py:236-272` (StrategyD.check_exit)
  - 라인 268-270: 기존 time_stop 로직 수정
  - N봉 경과 후 `current_pnl_pct < min_progress_pct` 시에만 청산

#### 선택지: 청산 가격
- **Option A**: 다음 봉 시가
- **Option B** (추천): 현재 봉 종가
  - 이유: 기존 코드 일관성, 현재 check_exit → execute_exit 구조

---

### 변경 4: 스캐너 출력 ATR·RR 노출
**우선순위**: P1 (변경 1과 함께)

#### 구현 파일:
- `output/formatters.py:20-45`
  - `_CSV_FIELDS`, `_candidate_to_row()`, `format_table()`, `format_markdown()` 업데이트
  - Candidate.metadata에서 `atr_14`, `rr_ratio`, `rr_band` 추출

---

### 변경 5: Multi-strategy 가중 통합 랭킹
**우선순위**: P5 (별도 단계, Phase 1은 인프라만)

#### 구현 파일:
- **신규**: `backtest_engine/weighting.py`
  - `load_strategy_weights()` → YAML 로드
  - `apply_strategy_weights()` → score × weight

- **신규**: `config/strategy_weights.yaml` (template)

---

## 2. Config 마이그레이션 전략

**핵심**: 모든 신규 필드의 기본값이 기존 동작을 유지해야 함

### StrategyDConfig 신규 필드 (기본값):
```python
# 변경 1
use_rr_filter: bool = False
min_rr_ratio: float = 2.0
sweet_spot_rr_low: float = 2.0
sweet_spot_rr_high: float = 2.5

# 변경 2
use_atr_stops: bool = False
atr_stop_mult: float = 1.5
atr_target_mult: float = 3.0

# 변경 3
use_conditional_time_stop: bool = False
min_progress_pct: float = 0.01
```

**검증**: 268개 baseline 테스트 모두 통과해야 함 (신규 필드 off 상태)

---

## 3. 테스트 추가 계획

### Phase 1: 변경 1 + 변경 4 (RR 필터)

**신규 테스트**: `backtest_engine/tests/test_rr_filter.py`
- `test_rr_filter_sweet_spot_entry()` — sweet spot 진입 우대
- `test_rr_filter_blocks_below_min()` — RR < 2.0 배제
- `test_rr_filter_off_backward_compat()` — use_rr_filter=False 기존 동작

**신규 테스트**: `output/tests/test_formatters_atr_rr.py` (또는 backtest_engine/tests/)
- `test_csv_fields_include_atr_rr()` — 헤더 포함
- `test_candidate_to_row_extracts_metadata()` — metadata 추출

**기대**: 268개 → 276개 통과

---

### Phase 2: 변경 2 (ATR 기반)

**신규 테스트**: `backtest_engine/tests/test_atr_stops.py`
- `test_atr_snapshot_at_entry()` — 스냅샷 저장
- `test_atr_stop_calculation_sweet_variant()` — min() 로직
- `test_atr_target_2_calculation()` — target 계산

**기대**: 276개 → 283개 통과

---

### Phase 3: 변경 3 (조건부 시간 손절)

**신규 테스트**: `backtest_engine/tests/test_conditional_time_stop.py`
- `test_conditional_time_stop_blocks_loss()` — 수익 < 1% 청산
- `test_conditional_time_stop_allows_win()` — 수익 ≥ 1% 보유
- `test_conditional_time_stop_off_backward_compat()` — off 상태 기존 동작

**기대**: 283개 → 290개 통과

---

## 4. 선택지 제시

### (a) ATR 손절: "더 넓은 쪽" vs "더 좁은 쪽"

**Option A (추천): min (더 좁은 쪽)**
```python
stop_loss = min(atr_stop_distance, fixed_pct_stop_distance)
```
- 장점: 이중 안전장치, 보수적 리스크 관리
- 단점: 손절 빈번, 위험 회피 성향

**Option B: max (더 넓은 쪽)**
- 장점: 관대한 손절, 장기 포지션 유지
- 단점: 손실 폭 증가 가능

---

### (b) 조건부 시간 손절 청산 가격: "시가" vs "종가"

**Option A: 다음 봉 시가**
- 장점: gap down 손실 회피
- 단점: 구조 복잡, 다음 봉 정보 필요

**Option B (추천): 현재 봉 종가**
```python
elif reason == ExitReason.TIME_STOP:
    return float(bar["close"])  # 기존 로직
```
- 장점: 코드 일관성, 간단함
- 단점: gap down 가능성

---

## 5. 엣지 케이스 및 안전장치

### Case 1: 저유동성 종목 ATR 왜곡
**대책**: `atr_min_threshold` config 추가, 거래량 필터링

### Case 2: Sweet spot RR 후보 부족
**대책**: `allow_rr_above_sweet_spot=True` (기본), 범위 조정 옵션

### Case 3: ATR 14일 미만 (신규 상장)
**대책**: `min_periods=10` 옵션, NaN fallback

### Case 4: Gap down + 조건부 시간 손절 충돌
**대책**: check_exit 순서 보장 (GAP_DOWN > ... > TIME_STOP)

---

## 6. 단계별 PR 분할 제안

### PR #1: RR 필터 + 스캐너 출력 (Minimum Viable)
**포함**: 변경 1 + 변경 4
- `backtest_engine/strategy.py` (RR 로직)
- `output/formatters.py` (출력)
- **테스트**: test_rr_filter.py, test_formatters_atr_rr.py
- **기대**: 268 → 276개 통과 ✓

---

### PR #2: ATR 기반 동적 손절
**포함**: 변경 2
- `backtest_engine/core.py`, `strategy.py`, `engine.py`
- **테스트**: test_atr_stops.py (7개)
- **기대**: 276 → 283개 통과

---

### PR #3: 조건부 시간 손절
**포함**: 변경 3
- `backtest_engine/strategy.py` (check_exit 수정)
- **테스트**: test_conditional_time_stop.py (5개)
- **기대**: 283 → 290개 통과

---

### PR #4: Multi-strategy 가중 (Phase 2)
**포함**: 변경 5
- `backtest_engine/weighting.py` (신규)
- `config/strategy_weights.yaml` (template)
- **테스트**: test_strategy_weighting.py
- **기대**: 290 → 294개 통과

---

## 7. 회귀 검증 절차

### Demo 실행 (변경 전/후 비교)

**변경 전**:
```bash
cd /Users/user/PycharmProjects/kospi-swing-scanner
.venv/bin/python -m backtest_engine.demo > results_before.txt 2>&1
```

**변경 후**:
```bash
.venv/bin/python -m backtest_engine.demo > results_after.txt 2>&1

# 비교
diff -u <(grep -A 20 "최종 자본" results_before.txt) \
         <(grep -A 20 "최종 자본" results_after.txt)
```

**기대**: use_rr_filter=False (기본) → PF/승률 ≈ 동일

---

### 전체 회귀 테스트

```bash
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q --tb=short

# 예상: 290개 이상 통과 (Phase 1-3 포함)
```

---

### 스크리너 출력 검증

```bash
.venv/bin/python -m core.runner --date 2026-05-02 --strategy all --format csv > candidates.csv

# CSV 헤더 확인 (atr_14, rr_ratio, rr_band 포함)
head -1 candidates.csv
```

---

## 최종 체크리스트

- [ ] 변경 1: RR 필터 (check_entry, StrategyDConfig)
- [ ] 변경 2: ATR 동적 손절 (core, strategy, engine)
- [ ] 변경 3: 조건부 시간 손절 (check_exit)
- [ ] 변경 4: 스캐너 출력 (formatters)
- [ ] 변경 5: Multi-strategy 가중 (weighting.py, YAML)
- [ ] 테스트 추가 (5개 test_*.py 파일)
- [ ] 기존 268개 테스트 보호
- [ ] PR #1-4 분할
- [ ] Demo 회귀 확인

---

**계획 버전**: v1.0  
**다음 단계**: User 승인 후 구현 시작 (PR #1부터)
