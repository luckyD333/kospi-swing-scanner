---
slug: incremental-checkpoint-multi-timeframe
status: active
created: 2026-04-30
updated: 2026-04-30
review_iteration: 2
review_verdict: pass
---

# Incremental Checkpoint + Multi-Timeframe Scanner

## Purpose / Big Picture

주기적(예: 매일 16:00, 30분마다) KOSPI 스캐너 실행 시:
- **이전 수집 데이터 재사용** — 캐시된 영업일까지의 OHLCV 는 재fetch 하지 않고, 마지막 캐시일+1 ~ 오늘만 증분 fetch
- **타임프레임별 독립 후보 출력** — 일봉(`1D`) / 주봉(`1W`) / 1시간봉(`1h`) / 30분봉(`30m`) 각각 별도 후보 리스트 생성
- **`strategy_one_d_v2` 무후보 검증** — 진단 로그로 "정상 작동 후 0개" vs "데이터 부족/필터 과다로 0개" 구분

확인 방법:
```bash
# 첫 실행 (cold cache): 평소처럼 전체 fetch
python cli.py --timeframes 1D,1W,1h,30m --strategy strategy_one_d_v2 --output-dir scan_results

# 두 번째 실행 (warm cache): "캐시 hit: N건, 증분 fetch: M건" 로그 + 동일 결과
# ➜ 두 번째 실행이 첫 실행 대비 60-80% 빠르고 후보 결과는 동일
```

## Context and Orientation

### 현재 시스템 상태 (`/Users/user/PycharmProjects/kospi-swing-scanner`)

진입점·핵심 파일:
- `cli.py` — argparse → `ScanRunner.run()` (단일 결과 → stdout/scan_results/)
- `core/runner.py:ScanRunner` — 유니버스 필터 → OHLCV 단일 fetch → 전략 실행 → `RunResult`
- `core/data_fetch.py:DataClient` — 네이버/pykrx/FDR fallback 체인
- `core/data_fetch.py:OhlcvCache` — **per-run 메모리 dict, 디스크 캐시 없음** (8번째 줄 주석 "disk cache는 별도 plan")
- `core/data_sources/naver.py:NaverSource.get_ohlcv()` — siseJson API. `params["timeframe"] = "day"` 하드코딩 (line 82)
- `strategies/strategy_one_d_v2.py:StrategyOneDv2` — `backtest_engine.StrategyD` wrapping. 5조건 AND
- `strategies/__init__.py:REGISTRY` — `{name → Class}` dict
- `backtest_engine/screener.py` — **다중 TF 인프라 존재 but cli 와 미연결**. `SUPPORTED_TIMEFRAMES = ["30m","1h","2h","4h","1D"]` (line 27), `resample_ohlcv(df_1m, target_tf)` (line 210)

전문용어:
- **OHLCV** — Open/High/Low/Close/Volume, 봉 데이터 4-5 컬럼 + datetime index
- **Timeframe (TF)** — 봉 주기. 본 plan 에서는 `1D` (일봉), `1W` (주봉), `1h`, `30m` 4종.
- **Strict Mode** — `--strict` 플래그. KRX Proxy 실패 시 즉시 중단 (실전 안전 보호). 캐시 사용 여부와 독립.
- **Funnel Stats** — `core/runner.py:107-119` 의 단계별 통과/실패 카운트 (universe → fetch_success → short_bars → candidates).

### `strategy_one_d_v2` 무후보 분석 (코드 리딩 기반)

`StrategyOneDv2.scan()` (`/Users/user/PycharmProjects/kospi-swing-scanner/strategies/strategy_one_d_v2.py:64-119`):
1. `df.volume.tail(20).mean() ≥ 100,000` 통과
2. `StrategyD.prepare()` 로 RSI/BB/MACD 계산
3. `StrategyD.check_entry(prepared, last_idx)` — **마지막 봉에서만** 시그널 체크
4. `check_entry` 5조건 AND: ① RSI 최근 N봉 내 ≤30 (oversold 이력) ② 연속 음봉 OR BB 하단 이탈 ③ 상승 장악형 양봉 ④ 쌍바닥 (DoubleBottomSimple, freshness=2) ⑤ 당일 양봉

5조건 동시 충족이 마지막 봉 1개에서 일어나는 빈도는 자연 시장에서 매우 낮음 → **0개 후보는 정상 범위**. 단, 문제 케이스와 구분 필요:
- (정상) `funnel.fetch_success ≥ 100`, `short_bars ≤ 10`, 0 candidates → 그냥 그날 시그널 없음
- (이상 1) `funnel.fetch_success < 50` → 유니버스 너무 작음 (시총 필터 과다)
- (이상 2) `funnel.fetch_failed > 100` → 네트워크/API 장애
- (이상 3) 모든 종목이 조건 ②~⑤ 중 하나에서 일관 탈락 → 디텍터 버그 의심

본 plan Task 1 에서 진단 로깅을 추가하여 위 4 경우를 구분 가능하게 한다.

## Architecture Overview (Top-Down)

### 1. System Context

```
+-----------------+     +--------------------+     +-----------------+
| User (CLI/cron) | --> |  cli.py            | --> | ScanRunner      |
+-----------------+     |  (timeframe parse) |     | (per-tf scan)   |
                        +--------------------+     +--------+--------+
                                                            |
                                +-----------+----------+----+----+----------------+
                                |           |          |        |                 |
                                v           v          v        v                 v
                        Naver siseJson  pykrx     FDR    KRX Proxy        OhlcvDiskCache
                        (day/minute)   (fallback) (fb)   (universe enrich) (.cache/ohlcv/)
```

### 2. Layer 구조

```
[CLI Layer]              cli.py                          (--timeframes 파싱, 출력 디렉토리 분리)
    |
[Runner Layer]           core/runner.py:ScanRunner       (per-tf 루프, ScanContext 생성)
    |
[Strategy Layer]         strategies/strategy_*.py        (TF-aware: 1D/1W/1h/30m 변형)
    |
[Data Layer]             core/data_fetch.py:DataClient   (소스 fallback)
                         core/cache/ohlcv_disk.py        (NEW: parquet 영속 캐시)
                         core/cache/incremental.py       (NEW: gap 계산 + 증분 fetch)
                         core/cache/resampler.py         (NEW: 1m → 30m/1h, 1D → 1W)
    |
[Source Layer]           core/data_sources/naver.py      (timeframe=day → minute 분기)
                         core/data_sources/krx_proxy.py  (변경 없음)
```

의존 방향: 위 → 아래 (한 방향). Strategy 는 Data Layer 의 DiskCache 를 직접 모르고 OhlcvCache 인터페이스만 본다.

### 3. 요청 처리 흐름 (warm-cache, `--timeframes 1D,1W,1h,30m`)

```
User: python cli.py --timeframes 1D,1W,1h,30m --output-dir scan_results
   |
   v
cli.main()
   |  --timeframes 파싱 → ["1D","1W","1h","30m"]
   v
ScanRunner.run(strategies, timeframes=["1D","1W","1h","30m"])
   |
   v
build_universe(target_date)                           # 1회 (TF 무관)
   |
   v
For each tf in timeframes:                            # 4회 루프
   |
   |  required_window = lookback_bars * tf_seconds
   |
   v
   OhlcvCache.get_or_fetch(ticker, tf, start, end)            # 단일 인터페이스 (memory + disk)
      |
      |--- [memory hit] in-process dict → 사본 반환
      |
      |--- [disk hit] .cache/ohlcv/{tf}/{ticker}.parquet 존재
      |          → last_cached_date 읽기
      |          → DataClient.get_ohlcv(last_cached+1, today) 만 호출 (gap fetch)
      |          → append 후 반환
      |
      \--- [cold]  전체 [start, end] fetch → 디스크 저장 → 반환
   |
   v
   StrategyOneDv2(timeframe=tf).scan(ScanContext) → List[Candidate]    # 단일 클래스, tf 파라미터화
   |
   v
RunResult(candidates_by_strategy_tf={(strat,tf): [...]})
   |
   v
cli.save_output(...)
   ├─ scan_results/2026-04-30/1D/scan_..._strategy_one_d_v2_HHMM.json
   ├─ scan_results/2026-04-30/1W/scan_..._strategy_one_d_v2_HHMM.json
   ├─ scan_results/2026-04-30/1h/scan_..._strategy_one_d_v2_HHMM.json   (Task 2 probe 통과 시)
   └─ scan_results/2026-04-30/30m/scan_..._strategy_one_d_v2_HHMM.json  (Task 2 probe 통과 시)
```

### 4. 저장소·캐시 구조

| 위치 | 키 | 포맷 | TTL/무효화 |
|------|----|----|-----------|
| `.cache/ohlcv/1D/{ticker}.parquet` | (ticker, 1D) | parquet (date index, OHLCV) | 수동 `rm` 만. 본 plan 은 TTL 자동 무효화 미구현 (수정주가 변경 시 사용자 책임). 후속 plan 으로 분리 |
| `.cache/ohlcv/1m/{ticker}.parquet` | (ticker, 1m) | parquet (datetime index) | 수동 `rm`. 30m/1h 는 1m 에서 resample (별도 저장 X) |
| `.cache/ohlcv/manifest.json` | global | JSON | `{schema_version}` 만 기록. last_full_refresh_at 은 TTL plan 으로 미룸 |
| `scan_results/{YYYY-MM-DD}/{tf}/scan_*.{ext}` | (date, tf) | json/csv/md | gitignored. 사용자가 보관 |

cap_lookup·name_lookup 은 캐시 안 함 (네이버 크롤링이 빠르고 시총은 매일 변함).

### 5. 장애 시나리오

```
시나리오 A: 디스크 캐시 손상 (parquet 깨짐)
  ohlcv_disk.read() → pyarrow.lib.ArrowInvalid
    → log warning + 캐시 파일 .corrupted 로 rename
    → fall through to full fetch
    → 다음 실행에 정상화

시나리오 B: 증분 fetch 만 실패 (네이버 일시 장애)
  IncrementalRefresher.fetch_gap() → RequestException
    → strict_mode=True: 기존 동작대로 ScanRunner.run() 중단
    → strict_mode=False: 기존 캐시만으로 진행 + warning
                          ("증분 fetch 실패, {last_cached_date} 까지 데이터로 진행")

시나리오 C: 인트라데이 소스 미지원
  NaverSource.get_ohlcv(timeframe="1m") 가 빈 DataFrame 반환
    → 30m/1h 타임프레임은 자동 skip + warning
    → 1D/1W 만 결과 출력 (degraded mode)
```

### 6. 컴포넌트 책임 요약

| Component | Task | 책임 (1줄) |
|-----------|------|-----------|
| `tests/test_strategy_one_d_v2_diagnostic.py` + `_classify_zero_candidate` | Task 1 | 무후보 시 funnel_stats 분류 (NORMAL/UNIVERSE_TOO_SMALL/FETCH_FAILURE) |
| `scripts/probe_naver_minute.py` (research only) | Task 2 | 네이버 siseJson minute 지원 실증. 결과에 따라 Task 6 진행 여부 게이트 |
| `core/cache/ohlcv_disk.py:OhlcvDiskCache` | Task 3 | parquet 파일 read/write + corruption 격리 (`.corrupted` rename) |
| `core/data_fetch.py:OhlcvCache` (확장) | Task 4 | memory + disk 단일 캐시 인터페이스. `disk=` 인자 주입 시 incremental gap fetch 자동 수행 |
| `core/cache/resampler.py:resample_to` | Task 5 | 1m→30m/1h, 1D→1W (W-FRI close) 리샘플 |
| `core/data_sources/naver.py:NaverSource` (modify) | Task 6 | `timeframe="1m"` 분기. Task 2 probe 결과로 미지원 시 NotImplementedError → 시나리오 C |
| `core/strategy_base.py:ScanContext` + `core/runner.py:ScanRunner` + `strategies/strategy_one_d_v2.py:StrategyOneDv2` | Task 7 | `ScanContext.ohlcv_by_tf` 추가 + per-tf 루프 + `StrategyOneDv2(timeframe=tf)` 파라미터화 (variant 클래스 X) |
| `cli.py:build_parser()` + `save_output()` (modify) | Task 8 | `--timeframes` 옵션 + `scan_results/{date}/{tf}/` 출력 |

각 컴포넌트는 정확히 하나의 Task 에 매핑됨 (1:1). Task 7 은 3 파일 동시 수정이지만 단일 변경 단위 (ScanContext 확장 = strategy 가 그것을 읽음 = runner 가 그것을 채움) 라 분리 시 의존 역전 발생 → 통합 유지.

## Progress

- [ ] Task 1: 진단 (`strategy_one_d_v2` 무후보 분류)
- [ ] Task 2: 네이버 minute API probe (research gate — 결과로 Task 6 진행 여부 결정)
- [ ] Task 3: `OhlcvDiskCache` parquet 영속 캐시
- [ ] Task 4: `OhlcvCache` 디스크 통합 (단일 인터페이스, incremental gap fetch 내장)
- [ ] Task 5: `resample_to` 헬퍼 (1D→1W, 1m→30m/1h)
- [ ] Task 6: NaverSource minute 분기 (Task 2 통과 시만)
- [ ] Task 7: `ScanContext` ohlcv_by_tf + `ScanRunner` 루프 + `StrategyOneDv2(timeframe=)` 파라미터화
- [ ] Task 8: CLI `--timeframes` + 출력 디렉토리 분리

## Plan of Work

> **Review iteration 1 (continue)**: probe gate 신설(Task 2), strategy variant 클래스 폐기 → `StrategyOneDv2(timeframe=)` 파라미터화로 흡수, `IncrementalRefresher` 폐기 → `OhlcvCache` 단일 인터페이스로 통합, Task 6/7 의존 역전 해소.

### Task 1: 진단 — `strategy_one_d_v2` 무후보 분류

**Files:**
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_strategy_one_d_v2_diagnostic.py`
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/runner.py:107-119` (funnel 에 `condition_failures: Counter` 추가)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/strategies/strategy_one_d_v2.py:91-92` (signal None 일 때 어느 조건에서 탈락했는지 카운트)

- [ ] **Step 1.1: 실패 테스트 — 무후보 funnel 분류**

```python
# tests/test_strategy_one_d_v2_diagnostic.py
import pytest
from core.runner import RunResult, _classify_zero_candidate

def test_classify_zero_candidate_normal():
    r = RunResult(target_date="20260430", universe_size=200,
                  funnel_stats={"fetch_success":150,"short_bars":5,"fetch_failed":10,
                                "condition_failures":{"double_bottom":120,"engulfing":30}})
    assert _classify_zero_candidate(r) == "NORMAL_NO_SIGNAL"

def test_classify_zero_candidate_universe_too_small():
    r = RunResult(target_date="20260430", universe_size=200,
                  funnel_stats={"fetch_success":40,"short_bars":5,"fetch_failed":10,
                                "condition_failures":{}})
    assert _classify_zero_candidate(r) == "UNIVERSE_TOO_SMALL"

def test_classify_zero_candidate_fetch_failure():
    r = RunResult(target_date="20260430", universe_size=200,
                  funnel_stats={"fetch_success":50,"short_bars":5,"fetch_failed":150,
                                "condition_failures":{}})
    assert _classify_zero_candidate(r) == "FETCH_FAILURE"
```

- [ ] **Step 1.2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_strategy_one_d_v2_diagnostic.py -q`
Expected: FAIL — `_classify_zero_candidate` 미구현

- [ ] **Step 1.3: 최소 구현**

`core/runner.py` 마지막에 추가:
```python
def _classify_zero_candidate(result: RunResult) -> str:
    f = result.funnel_stats
    if f.get("fetch_failed", 0) > f.get("fetch_success", 1) * 0.5:
        return "FETCH_FAILURE"
    if f.get("fetch_success", 0) < 50:
        return "UNIVERSE_TOO_SMALL"
    return "NORMAL_NO_SIGNAL"
```
`strategies/strategy_one_d_v2.py:90-91` 사이에 `signal is None` 시 `funnel["condition_failures"][reason] += 1` 추가 (StrategyD 가 `failed_reason` 노출 필요 → 확장).

- [ ] **Step 1.4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_strategy_one_d_v2_diagnostic.py -q`
Expected: PASS

- [ ] **Step 1.5: 커밋**

```bash
git add core/runner.py strategies/strategy_one_d_v2.py tests/test_strategy_one_d_v2_diagnostic.py
git commit -m "diag: classify zero-candidate runs (NORMAL/UNIVERSE_TOO_SMALL/FETCH_FAILURE)"
```

---

### Task 2: 네이버 minute API probe (research gate)

**목적**: `siseJson?timeframe=minute` 가 실제 분봉 데이터를 반환하는지 실증. 결과로 Task 6 (NaverSource minute 분기) 진행 여부 + 30m/1h 타임프레임 운명 결정.

**Files:**
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/scripts/probe_naver_minute.py`
- Update: `/Users/user/.claude/plans/valiant-herding-karp.md` (본 plan 파일 — Surprises 섹션에 결과 기록)

**TDD 면제** (Decision Log 기록): research probe 는 production 코드가 아니며, 외부 API 호출 결과 자체가 검증 목표. Step 1·2·4 생략. Step 3·5 만 수행.

- [ ] **Step 2.3: 최소 구현 (probe 스크립트)**

```python
# scripts/probe_naver_minute.py
"""네이버 siseJson minute timeframe 지원 실증."""
import sys, json, requests
from datetime import date, timedelta

URL = "https://api.finance.naver.com/siseJson.naver"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def probe(timeframe: str, ticker="005930"):
    end = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=3)).strftime("%Y%m%d")
    r = requests.get(URL, params={
        "symbol": ticker, "requestType": 1,
        "startTime": start, "endTime": end, "timeframe": timeframe,
    }, headers=HEADERS, timeout=10)
    text = r.text.strip().replace("'", '"')
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return None
    return raw

if __name__ == "__main__":
    for tf in ["day", "minute", "1m", "30m", "1h"]:
        result = probe(tf)
        if result is None or len(result) < 2:
            print(f"[{tf}] UNSUPPORTED (empty/invalid)")
            continue
        cols = result[0]
        sample = result[1] if len(result) > 1 else None
        n = len(result) - 1
        print(f"[{tf}] OK rows={n} cols={cols} sample={sample}")
```

- [ ] **Step 2.5: 결과 기록 + 커밋**

```bash
.venv/bin/python scripts/probe_naver_minute.py 2>&1 | tee /tmp/naver_probe.log
# 결과를 plan 의 Surprises & Discoveries 섹션에 paste
git add scripts/probe_naver_minute.py
git commit -m "probe: naver siseJson minute API support check (research script)"
```

**Gate 판정**:
- `[minute]` 또는 `[1m]` 이 OK → Task 6 진행, 30m/1h 타임프레임 활성화
- 모두 UNSUPPORTED → Task 6·7·8 의 30m/1h 분기 삭제 + plan scope 1D/1W 로 축소 (Decision Log 갱신)

---

### Task 3: `OhlcvDiskCache` (parquet 영속 캐시)

**Files:**
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/core/cache/__init__.py`
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/core/cache/ohlcv_disk.py`
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_ohlcv_disk_cache.py`
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/.gitignore` (`.cache/` 이미 포함 — 변경 불필요, 확인만)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/requirements.txt` (`pyarrow` 추가)

- [ ] **Step 3.1: 실패 테스트**

```python
# tests/test_ohlcv_disk_cache.py
import pandas as pd, pytest
from datetime import datetime
from core.cache.ohlcv_disk import OhlcvDiskCache

def test_write_then_read_roundtrip(tmp_path):
    cache = OhlcvDiskCache(root=tmp_path)
    df = pd.DataFrame({
        "open":[1.0],"high":[2.0],"low":[0.5],"close":[1.5],"volume":[100],
    }, index=pd.DatetimeIndex([datetime(2026,4,30)], name="date"))
    cache.write("005930", "1D", df)
    out = cache.read("005930", "1D")
    pd.testing.assert_frame_equal(out, df)

def test_read_missing_returns_empty(tmp_path):
    cache = OhlcvDiskCache(root=tmp_path)
    assert cache.read("999999", "1D").empty

def test_corrupted_file_renamed_and_returns_empty(tmp_path):
    (tmp_path/"1D").mkdir()
    (tmp_path/"1D"/"123456.parquet").write_bytes(b"not parquet")
    cache = OhlcvDiskCache(root=tmp_path)
    out = cache.read("123456", "1D")
    assert out.empty
    assert (tmp_path/"1D"/"123456.parquet.corrupted").exists()
```

- [ ] **Step 3.2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_ohlcv_disk_cache.py -q`
Expected: FAIL — 모듈 미존재

- [ ] **Step 3.3: 최소 구현**

```python
# core/cache/ohlcv_disk.py
from __future__ import annotations
import logging, shutil
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

class OhlcvDiskCache:
    """parquet 기반 (ticker, timeframe) → DataFrame 영속 캐시."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, ticker: str, tf: str) -> Path:
        d = self.root / tf
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{ticker}.parquet"

    def read(self, ticker: str, tf: str) -> pd.DataFrame:
        p = self._path(ticker, tf)
        if not p.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(p)
        except Exception as e:
            logger.warning(f"캐시 손상 ({ticker}/{tf}): {e} → .corrupted 로 격리")
            shutil.move(str(p), str(p) + ".corrupted")
            return pd.DataFrame()

    def write(self, ticker: str, tf: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        df.to_parquet(self._path(ticker, tf))

    def append(self, ticker: str, tf: str, df_new: pd.DataFrame) -> pd.DataFrame:
        existing = self.read(ticker, tf)
        merged = pd.concat([existing, df_new])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        self.write(ticker, tf, merged)
        return merged
```

- [ ] **Step 3.4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_ohlcv_disk_cache.py -q`
Expected: PASS

- [ ] **Step 3.5: 커밋**

```bash
git add core/cache/__init__.py core/cache/ohlcv_disk.py tests/test_ohlcv_disk_cache.py requirements.txt
git commit -m "feat(cache): add parquet-based OhlcvDiskCache with corruption recovery"
```

---

### Task 4: `OhlcvCache` 디스크 통합 (단일 인터페이스, incremental gap fetch 내장)

**목적**: 별도 `IncrementalRefresher` 클래스를 신설하지 않고 기존 `OhlcvCache` 인터페이스에 disk 옵션을 주입한다. 호출자(`ScanRunner`)는 `cache.get_or_fetch(ticker, tf, start, end)` 한 메소드만 알면 된다 — memory hit / disk gap-fetch / cold full-fetch 분기가 모두 내부에서 일어남.

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/data_fetch.py:131-205` (`OhlcvCache` 에 `disk: OhlcvDiskCache | None = None` 인자 + tf 인식)
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_ohlcv_cache_disk.py`

- [ ] **Step 4.1: 실패 테스트**

```python
# tests/test_ohlcv_cache_disk.py
from datetime import datetime
import pandas as pd
from unittest.mock import MagicMock
from core.cache.ohlcv_disk import OhlcvDiskCache
from core.data_fetch import OhlcvCache

def _make_df(start_date, n, tf_freq="B"):
    idx = pd.date_range(start_date, periods=n, freq=tf_freq)
    return pd.DataFrame({"open":[1.0]*n,"high":[1.0]*n,"low":[1.0]*n,
                         "close":[1.0]*n,"volume":[100]*n}, index=idx)

def test_legacy_memory_only_no_regression():
    """disk= 미주입 시 기존 동작 그대로 (memory dict)."""
    client = MagicMock(); client.get_ohlcv.return_value = _make_df("2026-01-02", 80)
    cache = OhlcvCache(client)   # disk 인자 없음
    df1 = cache.get_or_fetch("005930", "20260102", "20260430")
    df2 = cache.get_or_fetch("005930", "20260102", "20260430")
    assert client.get_ohlcv.call_count == 1   # 두 번째는 memory hit
    assert cache.stats["hit_count"] == 1

def test_disk_warm_does_incremental_fetch(tmp_path):
    disk = OhlcvDiskCache(root=tmp_path)
    disk.write("005930", "1D", _make_df("2026-01-02", 80))   # ~04-22
    client = MagicMock(); client.get_ohlcv.return_value = _make_df("2026-04-23", 5)
    cache = OhlcvCache(client, disk=disk)
    df = cache.get_or_fetch("005930", "20260102", "20260430", timeframe="1D")
    assert len(df) == 85
    args, _ = client.get_ohlcv.call_args
    assert args[1] >= "20260423"   # gap_start 만 fetch

def test_disk_cold_does_full_fetch_then_persist(tmp_path):
    disk = OhlcvDiskCache(root=tmp_path)
    client = MagicMock(); client.get_ohlcv.return_value = _make_df("2026-01-02", 80)
    cache = OhlcvCache(client, disk=disk)
    cache.get_or_fetch("005930", "20260102", "20260430", timeframe="1D")
    # 디스크에 저장되었는지
    assert not disk.read("005930", "1D").empty
```

- [ ] **Step 4.2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_ohlcv_cache_disk.py -q`
Expected: FAIL — `OhlcvCache.__init__` 가 `disk` kwarg 미지원, `get_or_fetch` 가 `timeframe` kwarg 미지원

- [ ] **Step 4.3: 최소 구현**

`core/data_fetch.py:OhlcvCache` 변경:
```python
class OhlcvCache:
    def __init__(self, client, disk=None):   # NEW: disk
        self._client = client
        self._disk = disk
        self._cache = {}; self._source_cache = {}
        self._fetch_count = 0; self._hit_count = 0

    def get_or_fetch(self, ticker, start, end, timeframe="1D"):   # NEW: timeframe
        key = (ticker, timeframe, start, end)
        if key in self._cache:
            self._hit_count += 1
            return self._cache[key].copy()

        if self._disk is not None:
            cached = self._disk.read(ticker, timeframe)
            if not cached.empty:
                last = cached.index.max()
                gap_start = (last + pd.Timedelta(days=1)).strftime("%Y%m%d")
                if gap_start <= end:
                    new = self._client.get_ohlcv(ticker, gap_start, end)
                    cached = self._disk.append(ticker, timeframe, new)
                df = cached.loc[start:end]
            else:
                df = self._client.get_ohlcv(ticker, start, end)
                self._disk.write(ticker, timeframe, df)
        else:
            df = self._client.get_ohlcv(ticker, start, end)

        self._cache[key] = df
        self._fetch_count += 1
        return df.copy()
```

- [ ] **Step 4.4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_ohlcv_cache_disk.py tests/test_core_data_fetch.py -q`
Expected: PASS (legacy memory-only test 도 회귀 X)

- [ ] **Step 4.5: 커밋**

```bash
git add core/data_fetch.py tests/test_ohlcv_cache_disk.py
git commit -m "feat(cache): OhlcvCache integrates disk + incremental gap fetch (single interface)"
```

---

### Task 5: `resample_to` 헬퍼 (1D→1W, 1m→30m/1h)

**Files:**
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/core/cache/resampler.py`
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_resampler.py`

- [ ] **Step 5.1: 실패 테스트**

```python
# tests/test_resampler.py
import pandas as pd
from core.cache.resampler import resample_to

def test_daily_to_weekly_friday_close():
    idx = pd.date_range("2026-04-13", "2026-04-24", freq="B")  # 2주 (10영업일)
    df = pd.DataFrame({"open":range(10),"high":range(10),"low":range(10),
                       "close":range(10),"volume":[100]*10}, index=idx)
    w = resample_to(df, "1W")
    assert len(w) == 2
    # 첫 주 close = 4(금요일 close)
    assert w["close"].iloc[0] == 4
    # high = max of week
    assert w["high"].iloc[0] == 4

def test_minute_to_30m():
    idx = pd.date_range("2026-04-30 09:00", periods=120, freq="1min")
    df = pd.DataFrame({"open":[1.0]*120,"high":[2.0]*120,"low":[0.5]*120,
                       "close":[1.5]*120,"volume":[10]*120}, index=idx)
    out = resample_to(df, "30m")
    assert len(out) == 4

def test_unsupported_raises():
    import pytest
    with pytest.raises(ValueError):
        resample_to(pd.DataFrame(), "5s")
```

- [ ] **Step 5.2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_resampler.py -q`
Expected: FAIL — 모듈 미존재

- [ ] **Step 5.3: 최소 구현**

```python
# core/cache/resampler.py
from __future__ import annotations
import pandas as pd

_FREQ_MAP = {"30m":"30min","1h":"1h","2h":"2h","4h":"4h","1D":"1D","1W":"W-FRI"}

def resample_to(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    if target_tf not in _FREQ_MAP:
        raise ValueError(f"unsupported timeframe: {target_tf}")
    if df.empty:
        return df
    out = df.resample(_FREQ_MAP[target_tf]).agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    ).dropna()
    return out
```

- [ ] **Step 5.4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_resampler.py -q`
Expected: PASS

- [ ] **Step 5.5: 커밋**

```bash
git add core/cache/resampler.py tests/test_resampler.py
git commit -m "feat(cache): add resample_to (1D→1W, 1m→30m/1h)"
```

---

### Task 6: NaverSource minute 분기 *(Task 2 probe 통과 시만 진행)*

**전제**: Task 2 결과 `[minute]` 또는 `[1m]` 응답이 OK (rows ≥ 1). UNSUPPORTED 시 본 task skip + Decision Log 갱신 + 30m/1h scope 제거.

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/data_sources/base.py:1-25` (signature 에 `timeframe="1D"` 추가)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/data_sources/naver.py:75-105` (timeframe 파라미터 처리)
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_naver_minute.py`

- [ ] **Step 6.1: 실패 테스트 (mock 필수, 실제 네이버 호출 금지)**

```python
# tests/test_naver_minute.py
from unittest.mock import patch, MagicMock
from core.data_sources.naver import NaverSource

def test_get_ohlcv_minute_passes_timeframe_param():
    src = NaverSource()
    fake = MagicMock(); fake.text = "[]"; fake.raise_for_status = MagicMock()
    with patch("core.data_sources.naver.requests.get", return_value=fake) as gm:
        src.get_ohlcv("005930", "20260430", "20260430", timeframe="1m")
        params = gm.call_args.kwargs["params"]
        assert params["timeframe"] == "minute"

def test_get_ohlcv_day_default():
    src = NaverSource()
    fake = MagicMock(); fake.text = "[]"; fake.raise_for_status = MagicMock()
    with patch("core.data_sources.naver.requests.get", return_value=fake) as gm:
        src.get_ohlcv("005930", "20260101", "20260430")
        params = gm.call_args.kwargs["params"]
        assert params["timeframe"] == "day"
```

- [ ] **Step 6.2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_naver_minute.py -q`
Expected: FAIL — `timeframe` kwarg 미지원

- [ ] **Step 6.3: 최소 구현**

`core/data_sources/base.py:DailyDataSource.get_ohlcv` signature 에 `timeframe: str = "1D"` 추가.
`core/data_sources/naver.py:get_ohlcv` 에 `timeframe="1D"` kwarg 추가, `_TF_MAP = {"1D":"day","1m":"minute"}` 매핑.
minute 응답 시 `날짜` 컬럼이 datetime (예: `202604301030`) 으로 반환됨 → `pd.to_datetime(format="%Y%m%d%H%M")` 분기.

- [ ] **Step 6.4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_naver_minute.py tests/test_krx_proxy_mock.py -q`
Expected: PASS (KRX 회귀도 같이)

- [ ] **Step 6.5: 커밋**

```bash
git add core/data_sources/base.py core/data_sources/naver.py tests/test_naver_minute.py
git commit -m "feat(data): NaverSource supports timeframe='1m' (siseJson minute)"
```

---

### Task 7: `ScanContext` 확장 + `ScanRunner` 루프 + `StrategyOneDv2(timeframe=)` 파라미터화

**목적 (review 반영)**: 별도 strategy variant 클래스 (`StrategyOneWv2`, `StrategyOne1Hv2`, `StrategyOne30Mv2`) 를 만들지 않고 기존 `StrategyOneDv2` 에 `timeframe` 인자를 추가한다. REGISTRY 에는 4 인스턴스(같은 클래스, 다른 timeframe) 를 등록. ScanContext 확장 + Runner 루프 + Strategy 파라미터화는 한 변경 단위 (서로 의존 — Task 분리 시 의존 역전).

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/strategy_base.py` (`ScanContext` 에 `ohlcv_by_tf: Dict[str, Dict[str, pd.DataFrame]]` 추가, 기존 `ohlcv` 는 `ohlcv_by_tf.get("1D", {})` property 로 alias)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/runner.py:RunnerConfig` (`timeframes: List[str] = field(default_factory=lambda: ["1D"])`, `cache_root: Optional[Path] = None`)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/runner.py:ScanRunner.run` (per-tf 루프, `OhlcvCache(disk=...)` 활성화)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/core/runner.py:RunResult` (`candidates_by_strategy_tf: Dict[Tuple[str,str], List[Candidate]]`)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/strategies/strategy_one_d_v2.py` (`__init__(timeframe="1D")`, `scan` 이 `ctx.ohlcv_by_tf[self.timeframe]` 사용)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/strategies/__init__.py` (REGISTRY 에 4 인스턴스 등록 — 모두 `StrategyOneDv2` 클래스, name=`strategy_one_d_v2`/`strategy_one_w_v2`/`strategy_one_1h_v2`/`strategy_one_30m_v2`)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_core_runner.py`, `tests/test_strategy_one_unit.py` (회귀)
- Create: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_runner_multi_tf.py`

- [ ] **Step 7.1: 실패 테스트**

```python
# tests/test_runner_multi_tf.py
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock
from core.runner import ScanRunner, RunnerConfig
from strategies import REGISTRY

def _mock_client():
    client = MagicMock()
    idx = pd.date_range("2026-01-02", "2026-04-30", freq="B")
    df = pd.DataFrame({"open":[1.0]*len(idx),"high":[1.0]*len(idx),"low":[1.0]*len(idx),
                       "close":[1.0]*len(idx),"volume":[200_000]*len(idx)}, index=idx)
    client.get_ohlcv.return_value = df
    client.get_ohlcv_with_source.return_value = ("mock", df)
    client.get_tickers.return_value = ["005930"]
    client.get_market_cap.return_value = pd.DataFrame({"시가총액":[5e12]}, index=["005930"])
    client.get_ticker_name.return_value = "삼성전자"
    return client

def test_runner_scans_1D_and_1W(tmp_path):
    cfg = RunnerConfig(market="KOSPI", timeframes=["1D","1W"], cache_root=tmp_path/".cache")
    runner = ScanRunner(_mock_client(), cfg)
    s_d = REGISTRY["strategy_one_d_v2"]()
    s_w = REGISTRY["strategy_one_w_v2"]()
    result = runner.run([s_d, s_w], target_date="20260430")
    assert ("strategy_one_d_v2","1D") in result.candidates_by_strategy_tf
    assert ("strategy_one_w_v2","1W") in result.candidates_by_strategy_tf

def test_strategy_timeframe_param_reads_correct_ohlcv():
    s = REGISTRY["strategy_one_w_v2"]()
    assert s.timeframe == "1W"
```

- [ ] **Step 7.2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_runner_multi_tf.py tests/test_core_runner.py -q`
Expected: FAIL — `RunResult.candidates_by_strategy_tf` 미존재, `StrategyOneDv2(timeframe=)` 미지원, REGISTRY 에 1W 미등록

- [ ] **Step 7.3: 최소 구현**

1. `ScanContext` 에 `ohlcv_by_tf: Dict[str, Dict[str, pd.DataFrame]]` 필드 추가. `@property def ohlcv(self)` 로 `ohlcv_by_tf.get("1D", {})` 반환 (legacy 호환).
2. `RunnerConfig.timeframes`, `cache_root` 추가.
3. `RunResult.candidates_by_strategy_tf: Dict[Tuple[str,str], List[Candidate]]` 추가. 기존 `candidates_by_strategy` 는 1D 만 alias 로 채움 (legacy 호환).
4. `ScanRunner.run`:
   - `OhlcvDiskCache(self.config.cache_root) if cache_root else None` → `OhlcvCache(client, disk=...)` 생성
   - `for tf in self.config.timeframes:` 루프
     - tf == "1D": fetch 그대로
     - tf == "1W": 1D fetch 후 `resample_to(df, "1W")`
     - tf in ("30m","1h"): 1m fetch 후 `resample_to(df, tf)` (Task 6 통과 시만)
   - `ScanContext(ohlcv_by_tf={tf: {ticker: df ...}})` 1회 생성
5. `StrategyOneDv2.__init__(self, config=None, timeframe="1D")`. `scan` 에서 `ctx.ohlcv_by_tf.get(self.timeframe, {})` 사용. `name = f"strategy_one_{tf_to_suffix(timeframe)}_v2"` 동적.
6. `strategies/__init__.py:REGISTRY` 에 lambda factory 4개 등록 (각 timeframe 인스턴스 생성).

- [ ] **Step 7.4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_runner_multi_tf.py tests/test_core_runner.py tests/test_strategy_one_unit.py tests/test_integration.py -q`
Expected: PASS (기존 단일 tf 테스트도 회귀 X)

- [ ] **Step 7.5: 커밋**

```bash
git add core/strategy_base.py core/runner.py strategies/strategy_one_d_v2.py strategies/__init__.py tests/test_runner_multi_tf.py
git commit -m "feat(runner): multi-tf scan via timeframe-parameterized StrategyOneDv2"
```

---

### Task 8: CLI `--timeframes` + 출력 디렉토리 분리

**Files:**
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/cli.py:38-93` (`--timeframes` 옵션, default `"1D"`, comma-separated)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/cli.py:144-183` (`save_output` → `save_output_per_tf`. `scan_results/{date}/{tf}/scan_*.{ext}`)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/output/formatters.py` (필요 시 timeframe 컬럼 추가)
- Modify: `/Users/user/PycharmProjects/kospi-swing-scanner/tests/test_cli.py` (CLI E2E)

- [ ] **Step 8.1: 실패 테스트**

```python
# tests/test_cli.py 에 추가
def test_cli_timeframes_creates_per_tf_dirs(tmp_path, monkeypatch):
    # MockKOSPIDataSource 주입 (test_daily_scanner_mock 패턴 재사용)
    monkeypatch.setenv("KOSPI_SCANNER_USE_MOCK", "1")
    rc = main([
        "--strategy","all","--timeframes","1D,1W",
        "--output-dir",str(tmp_path),"--format","json","--max-universe","5",
    ])
    assert rc == 0
    assert (tmp_path / "1D").exists()
    assert (tmp_path / "1W").exists()
    assert any((tmp_path/"1D").glob("scan_*.json"))
    assert any((tmp_path/"1W").glob("scan_*.json"))
```

- [ ] **Step 8.2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_cli.py -q`
Expected: FAIL — `--timeframes` 옵션 미존재

- [ ] **Step 8.3: 최소 구현**

`build_parser()` 에 `parser.add_argument("--timeframes", default="1D", help="콤마 구분: 1D,1W,1h,30m")`.
`main()` 에서 `tfs = [t.strip() for t in args.timeframes.split(",")]` → `RunnerConfig(timeframes=tfs)`.
`save_output(result, output_dir)` 가 `result.candidates_by_strategy_tf` 를 순회하며 `output_dir/{date}/{tf}/scan_*.{ext}` 생성.

- [ ] **Step 8.4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_cli.py tests/test_integration.py -q && .venv/bin/python -c "import cli; print('ok')"`
Expected: PASS

- [ ] **Step 8.5: 커밋**

```bash
git add cli.py output/formatters.py tests/test_cli.py
git commit -m "feat(cli): --timeframes flag + per-tf output (scan_results/{date}/{tf}/...)"
```

## Validation and Acceptance

행동 기반 수용 기준 (모두 통과 시 plan 완료):

1. **회귀**: 기존 단일 tf 동작 보존
   ```bash
   .venv/bin/python -m pytest backtest_engine/tests/ tests/ -q
   ```
   80개 이상 테스트 PASS, 신규 50+ 추가 → 총 130+ PASS.

2. **Cold cache**: 첫 실행 후 `.cache/ohlcv/1D/{ticker}.parquet` 파일 생성 확인
   ```bash
   rm -rf .cache && python cli.py --timeframes 1D --max-universe 10 --output-dir scan_results
   ls .cache/ohlcv/1D/ | wc -l   # ≥ 5 (mock 모드 기준)
   ```

3. **Warm cache**: 두 번째 실행이 첫 실행 대비 fetch 호출 ≤ 20%
   - `DataClient.get_ohlcv` 를 MagicMock 으로 카운트하는 단위 테스트로 검증 (Task 4 의 `test_disk_warm_does_incremental_fetch`).

4. **Multi-tf 출력**: `--timeframes 1D,1W,1h,30m` 실행 후 4 디렉토리 생성
   ```bash
   python cli.py --timeframes 1D,1W,1h,30m --output-dir scan_results
   ls scan_results/$(date +%Y-%m-%d)/   # → 1D/ 1W/ 1h/ 30m/
   ```
   각 디렉토리에 `scan_*.json` 1개 이상.

5. **무후보 진단**: `strategy_one_d_v2` 가 0 후보 시 `_classify_zero_candidate` 가 "NORMAL_NO_SIGNAL" / "UNIVERSE_TOO_SMALL" / "FETCH_FAILURE" 중 하나를 반환. 로그 라인에 분류 결과 포함.

6. **Strict mode 격리**: `--strict --timeframes 1D,1W,1h,30m` 시 30m/1h 의 minute fetch 가 실패해도 1D/1W 는 정상 결과 출력 (시나리오 C). Task 2 probe 가 UNSUPPORTED 결과를 낸 경우 plan scope 가 1D/1W 로 축소되며 본 항목은 시나리오 C 미발생 으로 자동 충족.

## Decision Log

| 날짜 | Decision | Rationale |
|------|----------|-----------|
| 2026-04-30 | parquet 포맷 채택 (csv X) | 컬럼별 압축 + datetime index 보존, pandas 직접 read/write |
| 2026-04-30 | `.cache/ohlcv/{tf}/{ticker}.parquet` 디렉토리 구조 | 한 파일에 ticker × tf 모두 넣으면 lock contention. 분리가 단순 |
| 2026-04-30 | 1m bar 만 캐시, 30m/1h 는 매번 resample | resample 은 빠름 (수십ms). 캐시 multiply 회피 |
| 2026-04-30 | `1W` resampling 은 W-FRI close (한국 증시 주봉 컨벤션) | 토·일 미장. 금요일 종가가 주봉 close |
| 2026-04-30 | 인디케이터 (RSI/BB) 캐시 X — OHLCV 만 캐시 | 인디케이터 재계산은 ms 수준. 캐시하면 strategy 변경 시 stale 위험 |
| 2026-04-30 | strategy variant 클래스 폐기 → `StrategyOneDv2(timeframe=tf)` 단일 클래스 파라미터화 | review iter 1 (continue/이슈 B): 4개 거의 동일한 클래스보다 1개 + 4 인스턴스 등록이 단순. REGISTRY 오염 회피 |
| 2026-04-30 | `IncrementalRefresher` 별도 클래스 폐기 → `OhlcvCache` 단일 인터페이스에 disk 통합 | review iter 1 (continue/이슈 C): 두 캐시 레이어가 같은 책임. 호출자(`ScanRunner`) 가 한 인터페이스만 알면 되도록 통합 |
| 2026-04-30 | 인트라데이 소스 검증을 Task 2 (probe gate) 로 선행 | review iter 1 (continue/이슈 A): mock 통과 ≠ 실제 API 지원. probe UNSUPPORTED 시 30m/1h scope 즉시 제거하여 무용 작업 회피 |
| 2026-04-30 | Task 7 = ScanContext + Runner + Strategy 통합 (3 파일 동시 수정) | review iter 1 (continue/이슈 D): 분리 시 Task 6 의 strategy variant 가 Task 7 의 ScanContext 를 미리 참조하는 의존 역전 발생. 단일 변경 단위로 묶음 |
| 2026-04-30 | TTL 기반 자동 캐시 무효화는 본 plan 에서 제외 (수동 `rm` 만) | review iter 1 (continue/이슈 E): 약속과 구현 일치. 수정주가 변경에 의한 stale 캐시는 후속 plan 으로 분리. Idempotence 섹션에 명시 |
| 2026-04-30 | `DailyDataSource` 명칭 유지 (rename X) | review iter 1 (continue/이슈 F): rename 시 변경 범위가 plan scope 를 초과 (3 구현체 + 모든 caller). 본 plan 은 timeframe kwarg 추가만, 명칭 정리는 후속 |
| 2026-04-30 | 디스크 캐시 default OFF on legacy `OhlcvCache`, opt-in via `disk=` 인자 (RunnerConfig.cache_root 통해 주입) | 기존 테스트 회귀 보호. 명시 활성화만 disk 사용 |
| 2026-04-30 | parquet via `pyarrow` (csv/feather X) | parquet 은 pandas 표준. csv 는 datetime index round-trip 손실. feather 는 빠르지만 columnar compression 약함 |
| 2026-04-30 | TDD 면제 — Task 2 (probe) 만 면제. Step 1·2·4 생략, Step 3·5 만 수행 | research probe 는 production 코드 X. 외부 API 응답 자체가 검증 목표. plan-principles 면제 표 "research" 케이스 |
| 2026-04-30 | Architecture Overview 면제 없음 — 6 sub-section 모두 작성 | 외부 의존 4개(네이버/pykrx/FDR/KRX) + 신규 컴포넌트 5개로 면제 조건 미충족 |

## Surprises & Discoveries

(실행 중 발견 시 기록)

- 2026-04-30 (코드 리딩): `backtest_engine/screener.py` 에 다중 TF 인프라가 이미 존재하지만 `cli.py` 와 단절. 본 plan 에서는 screener 를 직접 재사용하지 않고 ScanRunner 를 확장 — 이유: screener 는 universe 를 dict 로 받지만 cli 흐름은 `core/universe.build_universe()` 출력을 사용하며 funnel_stats 를 갱신해야 하므로 통합 비용 > 재사용 이득.
- 2026-04-30 (review iter 1, continue): 시니어 아키텍트 페르소나 리뷰에서 6개 결함 식별. 4개는 plan 에 반영 (probe gate 신설, variant 클래스 폐기, cache 인터페이스 통합, Task 6/7 의존 역전 해소). 2개 (TTL, DailyDataSource rename) 는 후속 plan 으로 분리 결정. 핵심 아키텍처 (디스크 캐시 + multi-tf 루프) 는 유효하므로 refactor 가 아닌 continue 판정.
- 2026-04-30 (코드 리딩): `strategy_one_d_v2` 무후보 가능성 — `StrategyD.check_entry` (`/Users/user/PycharmProjects/kospi-swing-scanner/strategies/strategy_one_d_v2.py:91`) 가 5조건 AND (RSI oversold 이력 + BB 하단/연속 음봉 + 장악형 양봉 + 쌍바닥 + 당일 양봉) 을 마지막 봉 1개에서만 체크. `DoubleBottomSimple` 은 freshness=2 (최근 2봉 내 2nd 바닥 필수). 정상 시장에서 0 후보는 충분히 개연. Task 1 의 분류 로직이 이를 "NORMAL_NO_SIGNAL" 로 식별하면 정상 확정.
- 2026-04-30 (Task 2 probe 결과): **`[minute]` 지원 확인** — `siseJson?timeframe=minute` 가 1603 row 1분봉 반환 (3일치). 컬럼 `['날짜','시가','고가','저가','종가','거래량','외국인소진율']`. 날짜 포맷 `YYYYMMDDHHMM` (예: `202604301555`). `[1m]/[30m]/[1h]` 토큰은 빈 응답으로 JSON 파싱 실패 — 네이버가 인지하지 못하는 값. **Gate 판정: Task 6 진행**. `_TF_MAP = {"1D":"day", "1m":"minute"}` 매핑 + 30m/1h 는 minute 데이터에 `resample_to(df, "30m"/"1h")` 적용. 분봉 응답에 거래 없는 row (`[ts, None, None, None, close, vol, None]`) 가 섞여 있음 → fetcher 단계에서 `dropna(subset=["open","high","low"])` 필요.

## Outcomes & Retrospective

(완료 시 작성)

## Interfaces and Dependencies

- **신규 의존**: `pyarrow ≥ 14.0` (`pip install pyarrow`). requirements.txt 에 명시.
- **변경 없는 외부 API**: KRX Proxy, pykrx, FDR. 네이버 siseJson 만 `timeframe=minute` 분기 추가.
- **하위 호환**: 기존 `OhlcvCache(client)` 시그니처 유지. 디스크 캐시는 `OhlcvCache(client, disk=OhlcvDiskCache(...))` 명시 시만 활성화.

## Idempotence and Recovery

- **재실행 안전**: 같은 (ticker, tf) 에 대해 N 번 호출해도 결과 동일. `OhlcvDiskCache.append` 가 `index.duplicated(keep="last")` 로 중복 제거. `OhlcvCache(disk=...)` 의 gap fetch 도 동일 영업일 재호출 시 새 데이터 없음 → no-op.
- **부분 실패 복구**: Task 6 에서 minute fetch 실패해도 1D/1W 결과는 보존 (시나리오 C). `--strict` 미사용 시 partial 결과 + warning.
- **수동 캐시 무효화**: `rm -rf .cache/ohlcv/1D/005930.parquet` 한 줄로 특정 ticker 재fetch 강제. 전체 무효화는 `rm -rf .cache/`.
- **TTL 기반 자동 무효화**: 본 plan 미포함 (수동만, Decision Log 기록). 후속 plan 으로 분리. 수정주가 변경 (배당락·액면분할) 시 사용자가 명시적으로 캐시 삭제 책임.
