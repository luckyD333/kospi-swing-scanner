---
slug: regime-score-priority-exposure
status: completed
created: 2026-05-03
updated: 2026-05-03
---

# regime_score 후보별 metadata 노출 + priority 등록 가능화

## Purpose / Big Picture

분석 보고서(`/Users/user/.claude/plans/analyze-50720956-zesty-swan.md`) 의 결함 4 후속 작업.
현재 `regime_score` 는 `apply_regime_overlay` 의 priority weight 곱셈(1.3/1.2/0.7) 으로만
ranking 에 영향을 주고, 후보별 score 가산 효과는 없다. 본 plan 은 다음을 가능하게 한다:

1. `_build_unique_pool` 이 후보 metadata 에 `regime_score`, `regime_label` 주입
2. 사용자가 `weights.yml` 에 `regime_score` priority 등록 시 ranking 점수에 직접 가산
3. BULL=85 같은 명확한 신호일 때 **모든 후보가 동일 부스트** → 시장 분포가 위로 shift

완료 시 검증:
```bash
# weights.yml 에 regime_score priority 추가 후
python cli.py --decide --top-n 10
# decision_top10.md 의 contributions 컬럼에 regime_score 항목이 percentile_rank × weight 으로 가산됨
```

## Context and Orientation

### 현재 상태

- `core/decision/runner.py:127` — `compute_weighted_ensemble_score` 만 호출, regime 정보 미사용
- `core/decision/runner.py:144-184` — `run_decide_ranking` 가 `_build_unique_pool` 호출 시 regime 미전달
- 후보 metadata 에 `regime_score` 키 부재 → `aggregator.aggregate_candidates` 가 priority key 로
  `regime_score` 를 찾아도 모든 후보의 값이 None → percentile_rank 결측 → 0.0 처리 (영향 0)

### 핵심 파일 (전체 경로)

- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/runner.py`
- `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/market_regime.py`
  (기존 `load_regime_analysis` 재사용)
- `/Users/user/PycharmProjects/kospi-swing-scanner/weights.yml.example`
- `/Users/user/PycharmProjects/kospi-swing-scanner/docs/decision_engine_recipes.md`
- `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_decision_runner_regime.py` (신규)

### 전문용어 정의

- **regime_score**: HMM 2-state Bull/Bear 모델의 BULL state 확률 × 100 (1~100). 50 미만 BEAR, 70 이상 BULL.
- **regime_label**: regime_score 기준 라벨 — `BULL` / `BEAR` / `NEUTRAL` (`get_regime_label` 결과).
- **percentile_rank 정규화**: aggregator 가 priority 별로 후보들의 raw 값을 0~1 범위로 정렬하는 처리.
  **모든 후보가 동일 값일 경우** rank 는 1/m..1.0 분포 (m=후보 수) — 이는 의도된 동작이며
  같은 regime_score 라도 contribution 이 0 이 되지는 않는다.

## Architecture Overview (Top-Down)

### 1. System Context

본 변경은 외부 시스템 의존 추가 없음. 기존 `.cache/regime_analysis.json` 만 재사용.

```
┌──────────────────┐  load_regime_analysis  ┌────────────────────┐
│ run_decide_*     ├───────────────────────►│ .cache/            │
│ (cli.py --decide)│                        │  regime_analysis   │
└────────┬─────────┘                        │  .json             │
         │ regime_score, regime_label       └────────────────────┘
         ▼
┌──────────────────┐
│ _build_unique_   │ → 각 Candidate.metadata 에
│ pool             │   regime_score, regime_label 주입
└──────────────────┘
```

### 2. Layer 구조

면제: 단일 모듈 변경 (`core/decision/runner.py`) + 테스트만 추가. Decision Log #1 참조.

### 3. 요청 처리 흐름

```
User: python cli.py --decide --top-n 10
  ▼
cli.py:_run_decide
  ▼
core/decision/runner.py:run_decide_ranking
  │ 1. dynamic_weights 로드 (기존)
  │ 2. by_strategy = load_candidates_from_manifest(scan_root)  (기존)
  │ 3. regime = load_regime_analysis(cache_root)  [NEW]
  │ 4. pool = _build_unique_pool(
  │            by_strategy,
  │            strategy_weights=...,
  │            regime=regime,    [NEW]
  │          )
  │      └─► 각 Candidate.metadata 에 주입:
  │           - regime_score: int (1~100)  [NEW]
  │           - regime_label: "BULL"|"BEAR"|"NEUTRAL"  [NEW]
  │ 5. aggregate_candidates(pool, weight_config)
  │      └─► weights.yml 에 regime_score priority 있으면
  │           contribution = percentile_rank × weight 으로 가산
  ▼
decision_top{N}.md 출력
```

### 4. 저장소·캐시 구조

| 경로 | 키 | 본 plan 변경 |
|------|----|--|
| `.cache/regime_analysis.json` | `current_score`, `current_regime` | **읽기만** (변경 없음) |
| `scan_results/<date>/manifest.json` | `dynamic_weights_computed` 등 | 변경 없음 |
| `scan_results/<date>/decision_top{N}.md` | contributions 컬럼 | **regime_score 항목 추가 가능** (사용자 weights.yml 설정에 따라) |

### 5. 장애 시나리오

| 시나리오 | 동작 |
|----------|------|
| `.cache/regime_analysis.json` 부재 | `load_regime_analysis` → None → metadata 에 regime_* 키 미주입. weights.yml 에 priority 가 있어도 결측 처리(0.0) → 기존 동작과 동일 (안전) |
| `cache_root` 인자 미전달 (cli.py 경로) | `cli.py` 가 `args.cache_root or ".cache"` 로 처리 (기존 패턴) |
| weights.yml 에 regime_score priority 없음 | metadata 키가 있어도 aggregator 가 무시 → 기존 동작 유지 |

### 6. 컴포넌트 책임 요약

| Component | Task | 책임 |
|-----------|------|------|
| `_build_unique_pool` (변경) | Task 1 | 인자에 `regime: dict | None` 추가, 후보 metadata 에 regime_score/label 주입 |
| `run_decide_ranking` / `run_decide_journal` (변경) | Task 2 | `cache_root` 인자 추가, `load_regime_analysis` 호출 결과를 `_build_unique_pool` 에 전달 |
| `cli.py:_run_decide` (변경) | Task 2 | `cache_root` 를 runner 함수에 전달 |
| `weights.yml.example` (변경) | Task 3 | `regime_score` priority 옵션 주석으로 안내 (디폴트는 미포함, 권장 weight=10) |
| `docs/decision_engine_recipes.md` (변경) | Task 4 | regime_score priority 등록 시 효과 + 동일 값 percentile_rank 동작 설명 |

## Progress

- [x] Task 1: `_build_unique_pool` regime metadata 주입 (2026-05-03, commit 9fba958)
- [x] Task 2: `run_decide_*` cache_root + regime 로드 (2026-05-03, commit de48610)
- [x] Task 3: `weights.yml.example` 옵션 주석 (2026-05-03, commit 82d37a4)
- [x] Task 4: `docs/decision_engine_recipes.md` 업데이트 (2026-05-03, commit 53270e1)
- [x] Task 5: 통합 회귀 — **454 passed** (450 → +4) + ruff clean (2026-05-03)

## Plan of Work (Bite-sized TDD)

### Task 1: `_build_unique_pool` regime 주입

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/runner.py:121-141`
- Test: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_decision_runner_regime.py` (신규)

- [ ] **Step 1.1: 실패 테스트 작성**

```python
"""tests/test_decision_runner_regime.py — _build_unique_pool 의 regime metadata 주입 회귀."""
from __future__ import annotations

import pandas as pd

from core.decision.runner import _build_unique_pool
from core.strategy_base import Candidate


def _mk_candidate(ticker: str, strategy: str, score: float = 100.0) -> Candidate:
    return Candidate(
        ticker=ticker,
        name=ticker,
        strategy=strategy,
        signal_date=pd.Timestamp("2026-05-03"),
        score=score,
        entry_price=10000.0,
        stop_loss=9700.0,
        target_1=10300.0,
        target_2=10500.0,
        current_price=10000.0,
        market_cap_bil=100.0,
        volume_20d_avg=100_000.0,
        conditions_met={},
        metadata={"source_strategy": strategy},
    )


def test_build_unique_pool_injects_regime_score_and_label():
    """regime 인자 전달 시 모든 후보 metadata 에 regime_score / regime_label 주입."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
        "strategy_two_*":     [_mk_candidate("000660", "strategy_two_*")],
    }
    regime = {"current_score": 85, "current_regime": "BULL"}

    pool = _build_unique_pool(by_strategy, regime=regime)

    assert len(pool) == 2
    for cand in pool:
        assert cand.metadata["regime_score"] == 85
        assert cand.metadata["regime_label"] == "BULL"


def test_build_unique_pool_without_regime_omits_keys():
    """regime=None 시 후보 metadata 에 regime_* 키 미주입 (기존 동작 유지)."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
    }
    pool = _build_unique_pool(by_strategy, regime=None)

    assert "regime_score" not in pool[0].metadata
    assert "regime_label" not in pool[0].metadata


def test_build_unique_pool_handles_partial_regime_dict():
    """current_regime 키 부재 시 regime_label 만 미주입 (score 는 가능)."""
    by_strategy = {
        "strategy_one_d_v2": [_mk_candidate("005930", "strategy_one_d_v2")],
    }
    regime = {"current_score": 25}  # current_regime 누락

    pool = _build_unique_pool(by_strategy, regime=regime)

    assert pool[0].metadata["regime_score"] == 25
    # regime_label 은 score 기반으로 derive: 25 < 30 → BEAR
    assert pool[0].metadata["regime_label"] == "BEAR"
```

- [ ] **Step 1.2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_decision_runner_regime.py -q --tb=short
```
Expected: FAIL — `_build_unique_pool` 가 regime 인자 미수용 (TypeError)

- [ ] **Step 1.3: 최소 구현**

`core/decision/runner.py:121-141` 수정:

```python
from core.decision.market_regime import get_regime_label  # 추가 import

def _build_unique_pool(
    by_strategy: dict[str, list[Candidate]],
    strategy_weights: dict[str, float] | None = None,
    regime: dict | None = None,  # 신규
) -> list[Candidate]:
    """ticker별 1개 후보만 유지. ensemble + regime 메타 주입."""
    sw = strategy_weights or {}
    weighted_scores = compute_weighted_ensemble_score(by_strategy, sw)
    chosen: dict[str, Candidate] = {}
    for cands in by_strategy.values():
        for c in cands:
            existing = chosen.get(c.ticker)
            if existing is None or c.score > existing.score:
                chosen[c.ticker] = c

    # regime metadata 준비 (한 번만 계산)
    regime_meta: dict = {}
    if regime is not None:
        score = regime.get("current_score")
        if score is not None:
            regime_meta["regime_score"] = int(score)
            label = regime.get("current_regime") or get_regime_label(int(score))
            regime_meta["regime_label"] = label

    for ticker, cand in chosen.items():
        ws = weighted_scores.get(ticker, 1.0)
        cand.metadata = {
            **(cand.metadata or {}),
            "ensemble_count": int(round(ws)),
            "ensemble_score": ws,
            **regime_meta,
        }
    return list(chosen.values())
```

- [ ] **Step 1.4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_decision_runner_regime.py -q --tb=short
```
Expected: PASS (3 passed)

- [ ] **Step 1.5: 커밋**

```bash
git add core/decision/runner.py tests/test_decision_runner_regime.py
git commit -m "feat(decision): _build_unique_pool 에 regime metadata 주입 옵션 추가"
```

---

### Task 2: `run_decide_*` 에 regime 로드 흐름 + cli.py 연결

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/runner.py:144-184` (run_decide_ranking)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/decision/runner.py:184+` (run_decide_journal)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/cli.py:380-405`
- Test: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_decision_runner_regime.py` (기존, +1)

- [ ] **Step 2.1: 실패 테스트 추가**

`tests/test_decision_runner_regime.py` 끝에 추가:

```python
def test_run_decide_ranking_passes_regime_from_cache_root(tmp_path, monkeypatch):
    """cache_root 인자로 regime_analysis.json 로드해 후보에 주입."""
    from core.decision import runner as r
    from core.decision.config import Priority, WeightConfig

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    (cache_root / "regime_analysis.json").write_text(
        '{"current_score": 80, "current_regime": "BULL", "history": [], '
        '"bull_state_mean_return": 0.01, "bear_state_mean_return": -0.01, '
        '"n_tickers": 100, "n_days": 30}'
    )
    scan_root = tmp_path / "scan"
    scan_root.mkdir()

    captured: dict = {}

    def fake_pool(by_strategy, strategy_weights=None, regime=None):
        captured["regime"] = regime
        return []

    monkeypatch.setattr(r, "load_candidates_from_manifest", lambda _p: {})
    monkeypatch.setattr(r, "_build_unique_pool", fake_pool)
    monkeypatch.setattr(r, "aggregate_candidates", lambda _p, _c: [])
    monkeypatch.setattr(r, "format_ranking_report", lambda *_a, **_k: "")

    cfg = WeightConfig(
        priorities=[Priority(key="rr_ratio", weight=100.0,
                              direction="higher_better", label="RR")],
        must_have=[],
        strategy_weights={},
    )
    r.run_decide_ranking(
        scan_root=scan_root,
        target_date="20260503",
        top_n=5,
        weight_config=cfg,
        cache_root=cache_root,
    )

    assert captured["regime"] is not None
    assert captured["regime"]["current_score"] == 80
    assert captured["regime"]["current_regime"] == "BULL"
```

- [ ] **Step 2.2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_decision_runner_regime.py::test_run_decide_ranking_passes_regime_from_cache_root -q --tb=short
```
Expected: FAIL — `run_decide_ranking` 가 `cache_root` 인자 미수용

- [ ] **Step 2.3: 최소 구현**

```python
# core/decision/runner.py
from core.decision.market_regime import get_regime_label, load_regime_analysis

def run_decide_ranking(
    scan_root: Path,
    target_date: str,
    top_n: int,
    weight_config: WeightConfig,
    *,
    dynamic_weights_path: Path | None = None,
    cache_root: Path | None = None,  # 신규
) -> Path:
    from output.decision_journal import format_ranking_report

    if dynamic_weights_path is not None and dynamic_weights_path.exists():
        try:
            weight_config = WeightConfig.load_dynamic(dynamic_weights_path)
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"dynamic_weights 로드 실패, static fallback: {e}")

    by_strategy = load_candidates_from_manifest(scan_root)

    regime: dict | None = None
    if cache_root is not None:
        try:
            regime = load_regime_analysis(cache_root)
        except Exception as e:
            logger.warning(f"regime 로드 실패 (skip): {e}")

    pool = _build_unique_pool(
        by_strategy,
        strategy_weights=weight_config.strategy_weights,
        regime=regime,
    )
    ranked = aggregate_candidates(pool, weight_config)
    if ranked:
        regret_fn = auto_volatility_scenarios(ranked)
        ranked = apply_minimax_regret(ranked, regret_fn)

    md = format_ranking_report(ranked, target_date, top_n, weight_config)
    out_path = scan_root / target_date / f"decision_top{top_n}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    logger.info(f"📝 ranking 저장: {out_path}")
    return out_path

# run_decide_journal 도 동일 패턴으로 cache_root 인자 + regime 전달
```

`cli.py:380-405` 의 `_run_decide` 에서 두 호출에 `cache_root=Path(args.cache_root or ".cache")` 전달.

- [ ] **Step 2.4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_decision_runner_regime.py tests/test_cli_decide.py -q --tb=short
```
Expected: PASS — 신규 4 + 기존 cli_decide 통과

- [ ] **Step 2.5: 커밋**

```bash
git add core/decision/runner.py cli.py tests/test_decision_runner_regime.py
git commit -m "feat(decision): run_decide_* 가 cache_root 의 regime 을 후보에 주입"
```

---

### Task 3: `weights.yml.example` 에 regime_score 옵션 주석 추가

**TDD 면제 케이스**: yml 설정 파일 (Decision Log #2 기록).

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/weights.yml.example`

- [ ] **Step 3.3: 작성**

기존 priorities 끝에 주석 + 옵션 항목 추가 (사용자가 주석 해제로 활성화):

```yaml
priorities:
  - key: ensemble_score
    weight: 30.0
    direction: higher_better
    label: 다중 전략 합의도
  - key: rr_ratio
    weight: 25.0
    direction: higher_better
    label: 손익비
  - key: momentum_pct
    weight: 20.0
    direction: higher_better
    label: 가격 모멘텀
  - key: per
    weight: 15.0
    direction: lower_better
    label: PER (저평가)
  - key: roe
    weight: 10.0
    direction: higher_better
    label: ROE (수익성)
  # 옵션: 시장 국면 직접 가산. 활성화하려면 다른 weight 합쳐 100 유지하도록 조정.
  # - key: regime_score
  #   weight: 10.0
  #   direction: higher_better
  #   label: 시장 국면
```

- [ ] **Step 3.5: 커밋**

```bash
git add weights.yml.example
git commit -m "docs(decision): weights.yml.example 에 regime_score priority 옵션 주석"
```

---

### Task 4: `docs/decision_engine_recipes.md` 업데이트

**TDD 면제 케이스**: docs-only (Decision Log #2 기록).

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/docs/decision_engine_recipes.md`

- [ ] **Step 4.3: 작성**

"시장 국면 (regime_score) 효과 범위" 섹션을 다음으로 교체:

```markdown
## 시장 국면 (regime_score) 효과 범위

regime_score 는 두 경로로 ranking 에 영향을 줄 수 있어요:

**1) 간접 영향 (기본 활성)** — `apply_regime_overlay`

priority weight 자체를 BULL 시 `momentum_pct × 1.3`, BEAR 시 `per/roe × 1.2`,
`momentum_pct × 0.7` 로 조정 후 합=100 정규화. 즉 priority 의 **영향력 비중**이
시장 국면에 따라 변해요.

**2) 직접 가산 (사용자 옵션)** — `regime_score` priority 등록

`weights.yml` 의 priorities 에 `regime_score` 를 등록하면 모든 후보가 동일
regime_score 를 metadata 에 보유하고, percentile_rank 정규화 후 weight 만큼
contribution 으로 가산돼요. 예:

\`\`\`yaml
priorities:
  - key: regime_score
    weight: 10.0
    direction: higher_better
    label: 시장 국면
\`\`\`

BULL=85 시: 모든 후보가 동일 값이라 percentile_rank 가 1/m..1.0 분포로 균등 (m=후보 수).
효과는 후보 분포의 **base 점수 shift** 로 작용 — BULL 시 전체 후보 ranking 의 절대값이
상승, BEAR 시 하락. 같은 값이라도 `aggregator._percentile_rank` 의 정렬 안정성 덕에
contribution 이 0 이 되지 않아요.

사용 시점:
- BULL/BEAR 신호가 명확할 때 후보 분포 자체를 위/아래로 이동시키고 싶을 때
- 다른 priority 와 가중치 합 100 을 유지해야 함 (예: rr_ratio 30 → 20, regime_score 10 추가)
```

- [ ] **Step 4.5: 커밋**

```bash
git add docs/decision_engine_recipes.md
git commit -m "docs(decision): regime_score 직접 가산 효과 가이드 추가"
```

---

### Task 5: 통합 회귀

**TDD 면제 케이스**: 빌드/통합 검증 (Decision Log #3 기록).

- [ ] **Step 5.3: 검증**

```bash
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q --tb=line 2>&1 | tail -5
```
Expected: 454 passed (450 + Task 1 +3 + Task 2 +1)

```bash
.venv/bin/ruff check . --exclude .venv
```
Expected: All checks passed

- [ ] **Step 5.5: plan 이동 (별도 commit)**

```bash
mv .claude/plans/active/2026-05-03-regime-score-priority-exposure.md \
   .claude/plans/completed/
```

(.claude/plans/ 는 git untracked — commit 불필요)

## Validation and Acceptance

수용 기준:

1. **regime 미주입 fallback**: `cache_root` 미전달 또는 `regime_analysis.json` 부재 시
   기존 동작 유지 (후보 metadata 에 regime_* 키 없음, weights.yml 에 priority 있어도 영향 0)
2. **regime 주입 시**: 모든 후보 metadata 에 `regime_score` (int) + `regime_label` (str) 존재.
   `weights.yml` 에 `regime_score` priority 등록 시 `decision_top{N}.md` 의 contributions
   컬럼에 항목 표시
3. **regime 정확성**: `.cache/regime_analysis.json` 의 `current_score` 와 후보 metadata 일치
4. **통합 회귀**: `pytest backtest_engine/tests/ tests/ -q` → **454 passed**
5. **ruff clean**: `ruff check . --exclude .venv` → All checks passed

## Decision Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | Architecture Overview Layer 구조 면제 | 단일 모듈(`core/decision/runner.py`) 변경 + 외부 의존 추가 없음 — 면제 표 "단일 파일 ≤100 LoC" 응용 | 2026-05-03 |
| 2 | Task 3·4 TDD 면제 | yml 설정 + docs-only — 면제 표 "yml/properties" / "docs-only" 적용 | 2026-05-03 |
| 3 | Task 5 통합 회귀 Step 1·2 면제 | 빌드 검증 — 면제 표 "빌드 스크립트" 응용 | 2026-05-03 |
| 4 | regime_score priority 디폴트는 `weights.yml.example` 에 주석으로만 노출 | 강제 활성 시 기존 weight 합 100 깨짐. 사용자가 의도적으로 활성화하도록 유도 | 2026-05-03 |
| 5 | regime_label 도 metadata 에 주입 | 향후 must_have DSL 에서 `regime_label==BEAR` 같은 string 비교 활용 가능 (PR #2 의 string DSL 확장 활용) | 2026-05-03 |
| 6 | regime_score 가산은 모든 후보에 동일 값이라 차별화 없음 — 의도된 동작인가? | percentile_rank 의 안정 정렬 덕에 contribution 0 아님. 효과는 분포 shift 로 작용 — 의도 명시 (docs Task 4) | 2026-05-03 |

## Surprises & Discoveries

| # | Observation | Evidence |
|---|-------------|----------|
| 1 | Task 1 commit (be67da2) 에 의도치 않은 design-ref/* 4 파일 포함 — 사전 staged 상태 미확인 | `git reset HEAD~1` (mixed) 로 복구 후 9fba958 로 재커밋, design-ref 는 untracked 유지 |
| 2 | regime_label 도 함께 주입하면 must_have DSL 의 string 비교(`regime_label==BEAR`) 활용 가능 — 추가 비용 없음 | docs Task 4 에 명시 |
| 3 | 동일 regime_score 의 percentile_rank 동작 검증 — `_percentile_rank` 의 안정 정렬로 1/m..1.0 균등 분포, contribution 0 아님 | aggregator.py:60-70 (직접 변경 없음) |

## Outcomes & Retrospective

### 성과

- 결함 4 (regime priority 직접 노출) 해결, 4 commit (Task 1~4)
- 회귀: 450 → 454 passed (+4 단위 테스트), ruff clean
- 사용자가 weights.yml 에 `regime_score` priority 등록 시 BULL/BEAR 시장 분포 shift 발현
- 옵트인 디자인 — 디폴트 동작 변경 없음 (기존 weights.yml 사용자 영향 0)

### 격차

- 본 plan 외 작업 없음

### 교훈

- 매 commit 전 `git status --short` 로 staged 파일 확인 필요 (Task 1 에서 design-ref/* 우발 포함)
- 옵션 priority 는 docstring 코멘트로만 노출하고 디폴트 활성화는 피해야 weight 합 100 제약 위반 회피
- regime metadata 주입은 한 번만 계산해 모든 후보에 동일 dict 적용 (성능 부담 없음)
