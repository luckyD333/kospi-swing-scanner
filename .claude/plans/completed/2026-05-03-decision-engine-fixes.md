---
slug: decision-engine-fixes
status: completed
created: 2026-05-03
updated: 2026-05-03
---

# 결정 엔진·동적 가중치 파이프라인 결함 수정 계획

## Purpose / Big Picture

`50720956..b08ddf1` 변경 분석(`/Users/user/.claude/plans/analyze-50720956-zesty-swan.md`)에서
식별된 6개 결함 중 **silent 실패**·**dead option**·**관측 불가능성**을 야기하는 P0/P1 항목 4개를 수정한다.
완료 시 사용자는 다음을 확인할 수 있다:

1. `python scripts/collect.py` 실행 후 `scan_results/<date>/manifest.json` 의
   `dynamic_weights_computed: true|false` 필드로 동적 가중치 계산 성공 여부 즉시 확인
2. `weights.yml` 부재 시 collect.py 가 `WARNING [dynamic_weights] weights.yml not found at ...` 명시 출력
3. `weights.yml.example` 을 복사·수정만으로 `ensemble_score` priority 가 즉시 반영
4. `strategy_one_d_v2` config 의 dead option (`use_conditional_time_stop`) 제거 — 옵션 표면 단순화

## Context and Orientation

### 현재 상태

- 분석 보고서: `/Users/user/.claude/plans/analyze-50720956-zesty-swan.md`
  - 결함 1: `strategies/strategy_one_d_v2.py:53` — `use_conditional_time_stop` dead-load
  - 결함 3: `core/decision/aggregator.py:68-115` — `ensemble_score` priority 미등록 시 ranking 영향 0
  - 결함 5: `scripts/compute_weights.py:148` — `weights.yml` 부재 시 `sys.exit(0)` silent 실패
  - 결함 6: `scripts/compute_weights.py:79-81` — HMM 실패 모두 `regime_score=50` 로 흡수 (BULL/BEAR 판별 불가)
- 본 plan 범위 외:
  - 결함 2 (backtest OFF / 실전 ON): 의도된 결정 (Decision Log 참조). 본 plan 은 docstring 만 보강
  - 결함 4 (regime priority 직접 노출): 디자인 변경 영향도 큼 → 별도 plan 으로 분리

### 핵심 파일 (전체 경로)

- `/Users/user/PycharmProjects/kospi-swing-scanner/scripts/collect.py`
- `/Users/user/PycharmProjects/kospi-swing-scanner/scripts/compute_weights.py`
- `/Users/user/PycharmProjects/kospi-swing-scanner/strategies/strategy_one_d_v2.py`
- `/Users/user/PycharmProjects/kospi-swing-scanner/docs/decision_engine_recipes.md`
- `/Users/user/PycharmProjects/kospi-swing-scanner/weights.yml.example` (신규)
- `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_compute_weights_cli.py` (신규)
- `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_collect_pipeline.py` (신규)

### 전문용어 정의

- **dynamic_weights**: HMM 시장 국면 + Factor Momentum 기반으로 매일 재산출되는 priority weight
  + strategy_weights. `.cache/dynamic_weights.json` 에 직렬화.
- **regime_score**: HMM 2-state Bull/Bear 모델의 BULL state 확률 × 100 (1~100). 50 미만 BEAR, 70 이상 BULL.
- **silent failure**: 실패가 발생했지만 returncode/manifest/로그에 명시되지 않아 사용자가 인지 불가능한 상태.
- **dead-load 옵션**: 설정 객체에는 존재하나 코드 경로에서 참조되지 않는 옵션 (예: live scan 에서 청산 룰).

## Architecture Overview (Top-Down)

### 1. System Context

```
┌───────────────────┐  cron / manual           ┌──────────────────────┐
│ scripts/collect.py├────────────────────────► │ 네이버 금융 API      │
│ (entry point)     │  OHLCV crawl             │ (sise_market_sum,    │
│                   │                          │  siseJson)           │
│                   │  subprocess              └──────────────────────┘
│                   ├──────► compute_weights.py
└────────┬──────────┘                          ┌──────────────────────┐
         │ 산출                                 │ hmmlearn (lib)       │
         ▼                                     │ — HMM 2-state        │
.cache/{                                       └──────────────────────┘
  manifest.json,
  regime_analysis.json,
  dynamic_weights.json,    ◄── 본 plan 의 관측성 강화 대상
}
scan_results/<date>/{
  candidates_*.json,
  manifest.json            ◄── dynamic_weights_computed 필드 추가
}
```

### 2. Layer 구조

```
┌────────────────────────────────────────────────────┐
│ CLI Entry: scripts/collect.py                      │
│  - OHLCV 크롤링 → manifest 저장                     │
│  - subprocess 호출 → compute_weights.py            │
│  - returncode 분기 → manifest 갱신 (NEW)           │
└──────────────────────┬─────────────────────────────┘
                       │ subprocess
                       ▼
┌────────────────────────────────────────────────────┐
│ Job: scripts/compute_weights.py                    │
│  - weights.yml 로드 → 부재 시 exit 1 (CHANGED)     │
│  - HMM regime → 실패 사유별 분리 로깅 (CHANGED)    │
│  - factor momentum → strategy_weights              │
│  - apply_regime_overlay + correlations_to_weights  │
└──────────────────────┬─────────────────────────────┘
                       │ JSON
                       ▼
┌────────────────────────────────────────────────────┐
│ Decision Engine: core/decision/*                   │
│  (본 plan 변경 없음 — 호출 인터페이스 유지)         │
└────────────────────────────────────────────────────┘

별도 trace:
┌────────────────────────────────────────────────────┐
│ strategies/strategy_one_d_v2.py                    │
│  - use_conditional_time_stop 옵션 제거 (CHANGED)   │
└────────────────────────────────────────────────────┘
```

### 3. 요청 처리 흐름 (happy path: collect.py 1회 실행)

```
User
  │ python scripts/collect.py --market KOSPI
  ▼
collect.py:_run_collect
  │ 1. OHLCV crawl (네이버) → .cache/{tf}/*.parquet
  │ 2. manifest.json 저장 (collect.py:192-210)
  │ 3. save_regime_analysis(.cache) → regime_analysis.json
  │ 4. subprocess.run(compute_weights.py, ..., timeout=120)
  │
  ├─► compute_weights.py:main
  │     │ 4a. WeightConfig.load(weights.yml)
  │     │     ├── 부재 → logger.error + sys.exit(1)  [CHANGED]
  │     │     └── 정상 → base_config
  │     │ 4b. load_regime_analysis(.cache)
  │     │     ├── ImportError(hmmlearn) → log + score=50  [CHANGED 분리]
  │     │     ├── ValueError(데이터 부족) → log + score=50  [CHANGED 분리]
  │     │     └── 정상 → score = regime_data.current_score
  │     │ 4c. update_factor_records → correlations
  │     │ 4d. apply_regime_overlay + correlations_to_weights
  │     │ 4e. dynamic_weights.json 직렬화
  │     └── exit 0 (성공) | exit 1 (weights.yml 부재)  [CHANGED]
  │
  │ 5. subprocess returncode 분기:                          [CHANGED]
  │      0 → manifest_update(dynamic_weights_computed=True)
  │      else → manifest_update(dynamic_weights_computed=False, error=stderr)
  ▼
.cache/dynamic_weights.json (성공 시) +
scan_results/<date>/manifest.json (dynamic_weights_computed 필드)
```

### 4. 저장소 구조

| 경로 | 키/필드 | TTL/정책 | 본 plan 변경 |
|------|---------|----------|-------------|
| `.cache/regime_analysis.json` | `current_score`, `current_regime`, `windows{3d,7d,30d,90d}` | 매 collect 실행 시 갱신 | 없음 |
| `.cache/dynamic_weights.json` | `weight_config{priorities, must_have, strategy_weights}`, `meta` | 매 collect 실행 시 갱신 | 없음 |
| `scan_results/<date>/manifest.json` | `tickers_meta`, `candidates_*`, **`dynamic_weights_computed: bool`** (NEW) | 일자별 immutable | **신규 필드** |
| `weights.yml` | `priorities[]`, `must_have[]`, `strategy_weights{}` | 사용자 편집 | 변경 없음 |
| `weights.yml.example` (NEW) | 위와 동일 + `ensemble_score` priority 포함 | git tracked | **신규 파일** |

### 5. 장애 시나리오

| 시나리오 | 현재 (문제) | 수정 후 |
|----------|------------|--------|
| `weights.yml` 부재 | compute_weights.py 가 logger.error 후 exit 0 → collect.py 정상 인식 | exit 1 → collect.py 가 manifest 에 `dynamic_weights_computed: false` 기록 + `WARNING [dynamic_weights] weights.yml not found` 로그 |
| `hmmlearn` 미설치 | `Exception` 캐치 → `regime_score=50` (NEUTRAL) | `ImportError` 분리 캐치 → `WARNING [regime] hmmlearn not installed; install with 'pip install hmmlearn>=0.3.0'` 후 `regime_score=50` |
| HMM 학습 데이터 부족 | 동상 — `regime_score=50` 흡수 | `ValueError` 분리 캐치 → `WARNING [regime] insufficient data: <message>` 후 `regime_score=50` |
| compute_weights.py 타임아웃 (120s) | subprocess `TimeoutExpired` → logger.warning → manifest 미갱신 | 동일하나 manifest 에 `dynamic_weights_computed: false` 기록 |

### 6. 컴포넌트 책임 요약

| Component | Task | 책임 1줄 |
|-----------|------|---------|
| `weights.yml.example` (신규) | Task 1 | `ensemble_score` priority 포함한 권장 weights 템플릿 제공 |
| `compute_weights.py` | Task 2 | weights.yml 부재 시 exit 1 + HMM 실패 사유별 분리 로깅 |
| `collect.py` | Task 3 | compute_weights subprocess returncode 를 manifest `dynamic_weights_computed` 필드에 기록 |
| `strategy_one_d_v2.py` | Task 4 | `use_conditional_time_stop` dead-load 옵션 제거 (실전 청산 미호출) |
| `docs/decision_engine_recipes.md` | Task 5 | `ensemble_score` priority 사용 시 동적 strategy_weights 효과 발현 안내 |

## Progress

- [x] Task 1: weights.yml.example 작성 (2026-05-03, commit 368546c)
- [x] Task 2: compute_weights.py 실패 모드 명확화 (2026-05-03, commit 40d47bb)
- [x] Task 3: collect.py manifest 동적 가중치 상태 기록 (2026-05-03, commit b644345)
- [x] Task 4: strategy_one_d_v2 dead option 제거 (2026-05-03, commit ac83442)
- [x] Task 5: docs/decision_engine_recipes.md 업데이트 (2026-05-03, commit 09db1b8)
- [x] Task 6: 통합 회귀 — **450 passed** + ruff clean (2026-05-03)

## Plan of Work (Bite-sized TDD)

### Task 1: weights.yml.example 신규 파일

**TDD 면제 케이스**: yml 설정 파일 (Decision Log 1 기록).

**Files:**
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/weights.yml.example`

- [ ] **Step 1.3: 작성 (Step 1·2·4 면제)**

```yaml
# 권장 weights.yml — 동적 가중치 (ensemble_score) 포함.
# 사용: cp weights.yml.example weights.yml 후 priorities/must_have 조정.
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
must_have:
  - "ensemble_count>=1"
  - "rr_ratio>=2.0"
strategy_weights:
  strategy_one_d_v2: 1.0
  strategy_two_cross_sectional_momentum: 1.0
  strategy_three_trend_following: 1.0
```

- [ ] **Step 1.5: 커밋**

```bash
git add weights.yml.example
git commit -m "docs(decision): weights.yml.example 추가 — ensemble_score priority 포함"
```

---

### Task 2: compute_weights.py 실패 모드 명확화

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/scripts/compute_weights.py:54-81,142-148`
- Test: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_compute_weights_cli.py` (신규)

- [ ] **Step 2.1: 실패 테스트 작성**

```python
"""tests/test_compute_weights_cli.py — compute_weights.py CLI 실패 모드 회귀."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_weights_yml_missing_exits_1(tmp_path: Path) -> None:
    """weights.yml 부재 시 exit 1 + stderr 에 명시 메시지."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    missing_yml = tmp_path / "missing_weights.yml"

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "scripts" / "compute_weights.py"),
            "--cache-root", str(cache_root),
            "--scan-root", str(scan_root),
            "--weights-yml", str(missing_yml),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "weights.yml not found" in (result.stderr + result.stdout)
    assert not (cache_root / "dynamic_weights.json").exists()


def test_hmm_import_failure_logs_explicit_message(tmp_path: Path, monkeypatch) -> None:
    """hmmlearn ImportError 시 분리된 경고 메시지 (regime_score=50 fallback)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import compute_weights as cw

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    weights_yml = tmp_path / "weights.yml"
    weights_yml.write_text(
        "priorities:\n"
        "  - key: rr_ratio\n    weight: 100.0\n    direction: higher_better\n    label: RR\n"
        "must_have: []\n"
        "strategy_weights: {}\n"
    )

    def _raise_import_error(_path: Path) -> None:
        raise ImportError("No module named 'hmmlearn'")

    monkeypatch.setattr(cw, "load_regime_analysis", lambda _p: None)
    monkeypatch.setattr(cw, "analyze_regime", _raise_import_error)

    result = cw.compute_dynamic_weights(cache_root, scan_root, weights_yml)
    assert result["regime_score"] == 50
    assert result["meta"]["regime_failure"] == "hmmlearn_not_installed"
```

- [ ] **Step 2.2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_compute_weights_cli.py -q --tb=short
```
Expected: FAIL — `weights.yml not found` 메시지 부재 + `regime_failure` 키 없음

- [ ] **Step 2.3: 최소 구현**

`scripts/compute_weights.py` 에 다음 변경 (전체 패치, 발췌):

**중요 변경**: `load_regime_analysis` 를 module-level import 로 이동.
이유: 기존 try 블록 내부 import 는 monkeypatch 적용 불가 (테스트 검증성 보장).

```python
# 모듈 상단 import 변경:
from core.decision.market_regime import (
    RegimeAnalysis,
    analyze_regime,
    apply_regime_overlay,
    load_regime_analysis,  # 신규 — module-level import (monkeypatch 가능)
)

def compute_dynamic_weights(...) -> dict:
    base_config = WeightConfig.load(weights_yml)  # FileNotFoundError 시 main 에서 처리

    regime_score = 50
    hmm_meta: dict = {}
    regime_failure: str | None = None
    try:
        # try 블록 내부 import 제거 — 모듈 상단으로 이동
        cached = load_regime_analysis(cache_root)
        if cached:
            regime_score = cached.get("current_score", 50)
            hmm_meta = {...}  # 기존 동일
        else:
            analysis = analyze_regime(cache_root)
            regime_score = analysis.current_score
            hmm_meta = {...}
    except ImportError as e:
        regime_failure = "hmmlearn_not_installed"
        logger.warning(
            f"[regime] hmmlearn not installed; install with 'pip install hmmlearn>=0.3.0' ({e})"
        )
    except ValueError as e:
        regime_failure = "insufficient_data"
        logger.warning(f"[regime] insufficient data, regime_score=50 fallback: {e}")
    except Exception as e:
        regime_failure = "unknown"
        logger.warning(f"[regime] unexpected failure, regime_score=50 fallback: {e}")

    # (factor momentum 동일)

    result = {
        "computed_at": datetime.now().isoformat(),
        "regime_score": regime_score,
        ...
        "meta": {
            ...
            "regime_failure": regime_failure,  # 신규
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args()
    ...
    weights_yml = Path(args.weights_yml)
    if not weights_yml.exists():
        logger.error(f"[dynamic_weights] weights.yml not found at {weights_yml}; "
                     f"copy weights.yml.example and edit.")
        sys.exit(1)  # 변경: 0 → 1

    try:
        result = compute_dynamic_weights(cache_root, scan_root, weights_yml)
    except Exception as e:
        logger.error(f"동적 가중치 계산 실패: {e}")
        sys.exit(1)  # 변경: 0 → 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    logger.info(f"dynamic_weights 저장: {output_path} (regime_score={result['regime_score']})")
```

- [ ] **Step 2.4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_compute_weights_cli.py -q --tb=short
```
Expected: PASS (2 passed)

- [ ] **Step 2.5: 커밋**

```bash
git add scripts/compute_weights.py tests/test_compute_weights_cli.py
git commit -m "fix(decision): weights.yml 부재 시 exit 1 + HMM 실패 사유 분리 로깅"
```

---

### Task 3: collect.py manifest 동적 가중치 상태 기록

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/scripts/collect.py:192-236`
- Test: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_collect_pipeline.py` (신규)

- [ ] **Step 3.1: 실패 테스트 작성**

```python
"""tests/test_collect_pipeline.py — collect.py manifest 동적 가중치 상태 회귀."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_manifest_records_dynamic_weights_failure(tmp_path: Path, monkeypatch) -> None:
    """compute_weights.py exit 1 시 manifest 에 dynamic_weights_computed=False 기록."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import collect as col

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    manifest_path = cache_root / "manifest.json"
    manifest_path.write_text(json.dumps({"tickers_meta": {}, "timeframes": {}}))

    fake_result = MagicMock(returncode=1, stderr="weights.yml not found", stdout="")

    cfg = col.CollectConfig(
        market="KOSPI",
        cache_root=cache_root,
        scan_root=scan_root,
        timeframes=["1D"],
    )
    with patch.object(col, "_subprocess_run", return_value=fake_result):
        col._update_dynamic_weights_status(cfg, manifest_path)

    updated = json.loads(manifest_path.read_text())
    assert updated["dynamic_weights_computed"] is False
    assert "weights.yml not found" in updated.get("dynamic_weights_error", "")


def test_manifest_records_dynamic_weights_success(tmp_path: Path) -> None:
    """compute_weights.py exit 0 시 manifest 에 dynamic_weights_computed=True 기록."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import collect as col

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    manifest_path = cache_root / "manifest.json"
    manifest_path.write_text(json.dumps({"tickers_meta": {}, "timeframes": {}}))

    fake_result = MagicMock(returncode=0, stderr="", stdout="dynamic_weights 저장")

    cfg = col.CollectConfig(
        market="KOSPI",
        cache_root=cache_root,
        scan_root=scan_root,
        timeframes=["1D"],
    )
    with patch.object(col, "_subprocess_run", return_value=fake_result):
        col._update_dynamic_weights_status(cfg, manifest_path)

    updated = json.loads(manifest_path.read_text())
    assert updated["dynamic_weights_computed"] is True
    assert "dynamic_weights_error" not in updated
```

- [ ] **Step 3.2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_collect_pipeline.py -q --tb=short
```
Expected: FAIL — `_update_dynamic_weights_status` 함수 부재, `_subprocess_run` 미정의

- [ ] **Step 3.3: 최소 구현**

`scripts/collect.py:222-236` 의 인라인 subprocess 블록을 함수로 추출 + manifest 갱신:

```python
import subprocess as _subprocess

def _subprocess_run(cmd: list[str], **kw):  # 테스트 monkeypatch 포인트
    return _subprocess.run(cmd, **kw)


def _update_dynamic_weights_status(cfg: CollectConfig, manifest_path: Path) -> None:
    """compute_weights.py 실행 후 manifest 에 결과 기록."""
    try:
        result = _subprocess_run(
            [sys.executable, str(Path(__file__).parent / "compute_weights.py"),
             "--cache-root", str(cfg.cache_root),
             "--scan-root", str(cfg.scan_root)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        logger.warning(f"동적 가중치 계산 실패 (skip): {e}")
        _patch_manifest(manifest_path, {
            "dynamic_weights_computed": False,
            "dynamic_weights_error": str(e),
        })
        return

    if result.returncode != 0:
        logger.warning(
            f"동적 가중치 계산 실패 (code {result.returncode}): {result.stderr.strip()}"
        )
        _patch_manifest(manifest_path, {
            "dynamic_weights_computed": False,
            "dynamic_weights_error": result.stderr.strip()[:500],
        })
    else:
        logger.info("동적 가중치 계산 완료")
        _patch_manifest(manifest_path, {"dynamic_weights_computed": True})


def _patch_manifest(path: Path, patch: dict) -> None:
    if not path.exists():
        return
    data = json.loads(path.read_text())
    data.update(patch)
    # dynamic_weights_error 가 빈 dict 면 키 제거 (성공 시 False→True 전환 케이스)
    if patch.get("dynamic_weights_computed") is True:
        data.pop("dynamic_weights_error", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# 기존 inline 블록 (collect.py:222-236) 을 다음 한 줄로 교체:
_update_dynamic_weights_status(cfg, manifest_path)
```

- [ ] **Step 3.4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_collect_pipeline.py -q --tb=short
```
Expected: PASS (2 passed)

- [ ] **Step 3.5: 커밋**

```bash
git add scripts/collect.py tests/test_collect_pipeline.py
git commit -m "feat(collect): manifest 에 dynamic_weights_computed 상태 기록"
```

---

### Task 4: strategy_one_d_v2 dead option 제거

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/strategies/strategy_one_d_v2.py:53,109`
- Test: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_strategy_one_unit.py` (기존, +1)

- [ ] **Step 4.1: 실패 테스트 작성**

`tests/test_strategy_one_unit.py` 에 추가:

```python
def test_config_does_not_expose_dead_conditional_time_stop_option():
    """live scan 에 영향 없는 use_conditional_time_stop 옵션은 노출하지 않는다.

    Why: backtest_engine.StrategyD.check_exit 만 사용 — strategy_one_d_v2.scan() 은
    check_entry 만 호출. 옵션 노출 시 사용자 혼란.
    """
    from strategies.strategy_one_d_v2 import StrategyOneDv2Config

    cfg = StrategyOneDv2Config()
    assert not hasattr(cfg, "use_conditional_time_stop"), (
        "use_conditional_time_stop 은 live scan 에 영향이 없으므로 제거되어야 함"
    )
```

- [ ] **Step 4.2: 실패 확인**

```bash
.venv/bin/python -m pytest tests/test_strategy_one_unit.py::test_config_does_not_expose_dead_conditional_time_stop_option -q
```
Expected: FAIL — 현재 옵션 존재

- [ ] **Step 4.3: 최소 구현**

```python
# strategies/strategy_one_d_v2.py:42-53
@dataclass(frozen=True)
class StrategyOneDv2Config:
    min_daily_volume: int = 100_000
    detector_name: str = "simple"
    min_lookback_bars: int = 25
    prominence_pct: float = 0.015
    engulf_strict: bool = True
    db_freshness: int = 2
    db_price_tolerance: float = 0.03
    use_rr_filter: bool = True
    use_atr_stops: bool = True
    # use_conditional_time_stop 제거 — live scan 은 check_exit 미호출

# strategies/strategy_one_d_v2.py:103-110
self._engine = StrategyD(
    config=StrategyDConfig(
        min_lookback_bars=self.config.min_lookback_bars,
        engulf_strict=self.config.engulf_strict,
        use_rr_filter=self.config.use_rr_filter,
        use_atr_stops=self.config.use_atr_stops,
        # use_conditional_time_stop 미전달 — backtest 디폴트 False 사용
    ),
    ...
)
```

- [ ] **Step 4.4: 통과 확인**

```bash
.venv/bin/python -m pytest tests/test_strategy_one_unit.py tests/test_daily_scanner_mock.py -q --tb=short
```
Expected: PASS (전체 단위 테스트 + 기존 mock 회귀)

- [ ] **Step 4.5: 커밋**

```bash
git add strategies/strategy_one_d_v2.py tests/test_strategy_one_unit.py
git commit -m "refactor(strategy): use_conditional_time_stop dead-load 옵션 제거 (live scan 무영향)"
```

---

### Task 5: docs/decision_engine_recipes.md 업데이트

**TDD 면제 케이스**: docs-only (Decision Log 2 기록).

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/docs/decision_engine_recipes.md`

- [ ] **Step 5.3: 작성 (Step 1·2·4 면제)**

기존 문서 끝에 다음 섹션 추가:

```markdown
## 동적 가중치 효과 발현 — `ensemble_score` priority 등록 필수

`scripts/compute_weights.py` 가 산출하는 `strategy_weights` 는 `_build_unique_pool` 에서
ticker 의 `ensemble_score` (= 등장 전략의 가중 합) 로 변환되어 metadata 에 주입된다.
그러나 `aggregator.aggregate_candidates` 의 가중합은 `weights.yml` 의
`priorities[].key` 에 등재된 키만 반영하므로, 다음을 명시해야 효과가 ranking 에 발현된다:

```yaml
priorities:
  - key: ensemble_score    # 이 항목이 없으면 strategy_weights 변경이 ranking 에 영향 0
    weight: 30.0
    direction: higher_better
    label: 다중 전략 합의도
```

`weights.yml.example` 을 참고해 시작하라.

## 시장 국면 (regime_score) 효과 범위

`apply_regime_overlay` 는 priority weight 자체를 1.3×/1.2×/0.7× 조정 후 합=100 정규화한다
(BULL/BEAR 시 momentum/quality priority 의 영향력 변경). 후보별 `regime_score` 는
ranking 점수에 직접 더해지지 않는다. 직접 가산이 필요하면 별도 priority 추가가 필요한데,
이는 본 시점에서는 미지원 (별도 plan 필요).
```

- [ ] **Step 5.5: 커밋**

```bash
git add docs/decision_engine_recipes.md
git commit -m "docs(decision): ensemble_score priority 등록·regime_score 효과 범위 안내"
```

---

### Task 6: 통합 회귀 검증

**TDD 면제 케이스**: 빌드/통합 검증 (Decision Log 3 기록).

**Files:**
- 변경 없음 (검증만)

- [ ] **Step 6.3: 통합 회귀 (Step 1·2 면제)**

```bash
.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q --tb=line 2>&1 | tail -10
```
Expected: 444+ passed (기존 444 + Task2 +2 + Task3 +2 + Task4 +1 = **449 passed**)

```bash
.venv/bin/ruff check . --exclude .venv
```
Expected: All checks passed

```bash
# 실 시나리오: weights.yml 없는 상태에서 collect.py 1회
.venv/bin/python scripts/collect.py --market KOSPI --cache-root /tmp/test_cache \
    --timeframes 1D --limit 5 2>&1 | grep -i "dynamic_weights\|weights.yml"
```
Expected: `WARNING ... weights.yml not found at weights.yml; copy weights.yml.example and edit.`
+ `dynamic_weights_computed: false` 가 `/tmp/test_cache/manifest.json` 에 기록

- [ ] **Step 6.5: 최종 커밋 (Optional — 회귀만 한 경우 스킵)**

각 Task 가 자체 커밋을 가지므로 별도 커밋 불요. plan 파일을 `completed/` 로 이동:

```bash
git mv .claude/plans/active/2026-05-03-decision-engine-fixes.md \
       .claude/plans/completed/
git commit -m "docs(plan): decision-engine-fixes 완료 이동"
```

## Validation and Acceptance

수용 기준 (행동 기반):

1. **`weights.yml` 부재 재현**: `rm -f weights.yml && python scripts/collect.py --market KOSPI --limit 5`
   실행 시:
   - stderr/stdout 에 `weights.yml not found at weights.yml; copy weights.yml.example and edit.` 출력
   - `.cache/manifest.json` 에 `"dynamic_weights_computed": false` 필드 존재
   - `.cache/dynamic_weights.json` 미생성
2. **`weights.yml` 정상 시**: `cp weights.yml.example weights.yml && python scripts/collect.py --market KOSPI --limit 5`
   실행 시:
   - `.cache/manifest.json` 에 `"dynamic_weights_computed": true`
   - `.cache/dynamic_weights.json` 생성
   - `dynamic_weights_error` 키 없음
3. **`hmmlearn` 미설치 시뮬**: `pytest tests/test_compute_weights_cli.py::test_hmm_import_failure_logs_explicit_message`
   PASS — `meta.regime_failure == "hmmlearn_not_installed"` 확인
4. **dead option 제거**: `python -c "from strategies.strategy_one_d_v2 import StrategyOneDv2Config; \
   print(hasattr(StrategyOneDv2Config(), 'use_conditional_time_stop'))"` → `False`
5. **통합 회귀**: `.venv/bin/python -m pytest backtest_engine/tests/ tests/ -q` → **449 passed** (444 + 5 신규)
6. **ruff clean**: `.venv/bin/ruff check . --exclude .venv` → All checks passed

## Decision Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| 1 | Task 1 (weights.yml.example) Step 1·2·4 TDD 면제 | yml 설정 파일 — 면제 표 "yml/properties 설정" 적용. 검증은 Task 6 의 collect.py 시나리오 통합 테스트로 수행 | 2026-05-03 |
| 2 | Task 5 (docs) Step 1·2·4 TDD 면제 | docs-only 변경 — 면제 표 "docs-only 변경" 적용 | 2026-05-03 |
| 3 | Task 6 (통합 회귀) Step 1·2 면제 | 빌드/통합 검증 — 면제 표 "자동 생성 코드 / 빌드 스크립트" 응용. 신규 테스트는 Task 2/3/4 에서 작성 | 2026-05-03 |
| 4 | 결함 2 (backtest OFF/실전 ON) 본 plan 제외 | 의도된 결정 — `b08ddf1` 커밋 메시지 + tests/test_daily_scanner_mock.py:4 의 허용 범위 조정에서 명시적으로 채택. 정책 변경은 별도 plan 필요 | 2026-05-03 |
| 5 | 결함 4 (regime priority 직접 노출) 본 plan 제외 | priorities 키 추가는 weights.yml 스키마·aggregator 정규화·HMM 점수 분포 검증 필요 — 본 plan 의 silent failure 수정과 결합 시 위험 | 2026-05-03 |
| 6 | manifest 갱신 위치를 `_update_dynamic_weights_status` 함수 분리 | inline 시 단위 테스트 어려움 — 함수 분리 + `_subprocess_run` monkeypatch 포인트 노출로 테스트 용이 | 2026-05-03 |
| 7 | `compute_weights.py` exit 0→1 변경의 backward compatibility | 기존 cron 스크립트가 returncode 무시하므로 영향 제한적. collect.py 는 returncode 분기 처리하므로 안전 | 2026-05-03 |

## Surprises & Discoveries

| # | Observation | Evidence |
|---|-------------|----------|
| 1 | `tests/test_strategy_one_unit.py` 의 기존 mock 회귀 테스트는 `use_conditional_time_stop` 옵션 노출 여부와 무관 — Task 4 제거 시 추가 영향 없음 | `pytest tests/test_strategy_one_unit.py tests/test_daily_scanner_mock.py` 10 passed (2026-05-03) |
| 2 | `compute_weights.py` 의 `WeightConfig.load` 가 `priorities.weight` 합 != 100 시 ValueError 발생 — `weights.yml.example` 의 30+25+20+15+10=100 정확 일치 필요 | docs/decision_engine_recipes.md:125 의 "가중치 합 100% 검증" 주의사항 |
| 3 | 신규 5 테스트 + 기존 444 = **450 passed** (+6, plan 추정 +5 보다 1개 더) — Task 2 에서 `test_hmm_value_error_logs_insufficient_data` 추가로 +1 | `pytest backtest_engine/tests/ tests/ -q` 16.24s (2026-05-03) |

## Outcomes & Retrospective

### 성과

- 결함 1·3·5·6 모두 해결, 6 commit (Task 1~5 + plan 이동)
- 회귀: 444 → 450 passed (+6 단위 테스트), ruff clean
- silent failure → 명시적 manifest 필드 + 분리 로깅 + exit 1 로 관측성 확보
- dead option 제거 → 옵션 표면 단순화

### 격차 (Plan 외)

- 결함 2 (backtest 디폴트 OFF / 실전 ON) — 의도된 결정으로 결론, 본 plan 미처리
- 결함 4 (regime priority 직접 노출) — 별도 plan 필요, 본 plan 미처리

### 교훈

- module-level import 가 monkeypatch 검증성에 직결 — try 블록 내부 import 는 테스트 적대적
- subprocess returncode 처리는 manifest 필드 + 단위 테스트 가능 함수 분리로 회귀 가능
- dead option 은 docstring 으로 인정하기보다 제거가 명확

## Interfaces and Dependencies

- **외부 라이브러리**: `hmmlearn>=0.3.0` (이미 requirements.txt 등재). 본 plan 은 미설치 시 분리 로깅만 추가.
- **subprocess 호출 인터페이스**: `compute_weights.py` 의 returncode 가 0→1 변경. cron 등 외부 호출자는 returncode 무시 가정 (검증 불요).
- **manifest.json 스키마**: 기존 키 유지, `dynamic_weights_computed: bool` + `dynamic_weights_error: str` (실패 시) 추가. 기존 소비자 (output/formatters.py 등) 는 신규 키 무시 (backward compatible).
