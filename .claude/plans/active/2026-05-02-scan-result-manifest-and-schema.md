---
slug: scan-result-manifest-and-schema
status: active
created: 2026-05-02
---

# 수집기·전략 분리 실행 + UI 친화적 결과 저장

## Context

KOSPI Swing Scanner는 수집기(`scripts/collect.py`)·전략 plug-in(`strategies/`)·스캔 entry(`cli.py`)이 이미 분리된 구조라, 별도 schedule job으로 돌리는 것은 **현재 코드만으로 가능**해요. 신규 전략 추가도 `strategies/__init__.py`에 import + REGISTRY 등록 2줄이면 끝나고 기존 전략에 영향이 없어요.

다만 최종 목적이 **수집결과·전략결과를 UI에 노출**하는 것이라면 두 가지 gap이 있어요:

1. 스캔 결과 파일명에 `HHMM` timestamp가 들어가서 UI가 "최신 결과"를 디렉토리 listing + sort로 추정해야 해요 (`cli.py:170-171`).
2. 수집 manifest(`.cache/manifest.json`)에 ticker별 메타가 부족해서 UI가 ticker 카드를 그리려면 parquet을 직접 열어야 해요.

이 plan은 **YAGNI 원칙**으로, UI가 안전하게 로드할 수 있는 manifest와 표준 JSON schema를 더하고, 운영용 cron 예시를 문서화해요. 코드 재구조화는 안 해요. 이미 잘 분리된 부분은 그대로 둬요.

## Architecture Overview

### 데이터 흐름 (현재 + 추가)

```
Cron 23:00 → scripts/collect.py
              → DataClient (네이버 API)
              → OhlcvDiskCache (.cache/{tf}/{ticker}.parquet)
              → .cache/manifest.json  ← [C] tickers_meta 보강

Cron 16:00 → cli.py --strategy strategy_one_d_v2 --output-dir scan_results
              → ScanRunner (core/runner.py, RunResult 생성)
              → output/formatters.py format_json  ← [D] schema 표준화
              → scan_results/{date}/{tf}/scan_{date}_{strategy}_{HHMM}.json (history)
              → scan_results/manifest.json  ← [A] latest 갱신

UI (별도)    → scan_results/manifest.json 읽기 → latest_file 따라 결과 로드
              → .cache/manifest.json 읽기 → 수집 현황 표시
```

### 비-목표 (Non-goals)

- `cli.py`/`runner.py`/`strategies/` 의 구조 변경은 안 해요. 이미 OCP를 만족해요.
- 별도 wrapper script(`scripts/run_strategy_one.py`)는 안 만들어요. `cli.py --strategy <name>`이 이미 단독 실행이라 wrapper는 중복 layer예요.
- 수집 manifest에 parquet 자체 데이터(OHLCV row)는 안 넣어요. 메타만요.
- UI 자체는 이 plan 범위 밖이에요. 데이터 contract만 정의해요.

## Plan of Work

### [D] JSON 결과 schema 표준화 (가장 먼저)

**왜 먼저**: A의 manifest와 UI가 이 schema에 의존해요. 다른 작업의 기반이에요.

**대상 파일**:
- `output/formatters.py` — `format_json()` (현재 line 102-116) 확장
- `cli.py` — `render_single()` (line 125-133) 시그니처에 `strategy_name`, `timeframe`, `filters` 추가, JSON 포맷 호출 시 전달

**변경 내용**:
- `format_json()` 시그니처를 `(candidates, target_date, strategy_name=None, timeframe="1D", filters=None, indent=2) -> str`로 확장.
- Payload 구조:
  ```json
  {
    "strategy": "strategy_one_d_v2",
    "date": "2026-05-01",
    "timeframe": "1D",
    "generated_at": "2026-05-01T16:30:45+09:00",
    "candidates": [
      {"rank": 1, "ticker": "000660", "name": "SK하이닉스", "score": 0.82,
       "metrics": {"entry_price": 140500, "stop_loss": 130000, "target_1": 155000, ...}}
    ],
    "summary": {"count": 20, "filters": {"min_cap_bil": 2000, ...}}
  }
  ```
- 기존 `_candidate_to_row()`(line 25-42)의 dict는 `metrics` 안으로 래핑해요. 기존 필드 이름은 보존(backward compat).
- `format_csv`, `format_table`, `format_markdown`은 변경 안 해요 (필요 시 후속 작업).

**테스트**: `tests/test_output_formatters.py`에 `test_format_json_includes_schema_fields()` 추가.

### [A] 스캔 결과 manifest.json 갱신

**왜**: UI가 `scan_results/manifest.json`만 읽어서 모든 전략의 latest를 한 번에 알 수 있게 해요. timestamp 파일은 history로 유지해요.

**대상 파일**: `cli.py` — `save_output()`(line 155-195) 직후 manifest 갱신 헬퍼 호출.

**새 함수**: `_update_scan_manifest(output_dir: Path, strategy_name: str, target_date: str, timeframe: str, saved_path: Path, fmt: str) -> None`
- `{output_dir}/manifest.json` 읽기 (없으면 `{}`).
- 키: `f"{strategy_name}__{timeframe}"`. 값: `{"date": target_date, "latest_file": "<output_dir 기준 상대경로>", "formats": [...], "generated_at": <iso>}`.
- 같은 strategy + timeframe 키에 다른 포맷 저장 시 `formats` 배열에 추가(중복 제거).
- Atomic write: temp file에 쓰고 `os.replace()` 로 rename. JSON decode 실패 시 warning log + 새 manifest로 시작.

**대상 호출 지점**:
- `cli.py` 의 결과 저장 루프 (line 155-195) — 각 포맷 저장이 끝날 때마다 manifest 갱신.

**테스트**: `tests/test_cli.py`에 `test_save_output_updates_manifest()` 추가. tmp_path fixture로 manifest 생성, 두 번 실행 시 history 유지 + manifest는 latest 가리킴 검증.

### [C] 수집 manifest UI 친화 보강

**왜**: UI가 ticker 카드(이름·마지막 수집일·timeframe별 row count)를 그릴 때 parquet을 일일이 열지 않게 해요.

**대상 파일**: `scripts/collect.py` — manifest 생성 부분 (line 172-186).

**새 함수**: `_build_tickers_metadata(disk_cache: OhlcvDiskCache, tickers: list[str], base_tfs: list[str]) -> dict`
- 각 ticker × base_tf 에 대해 `disk_cache.read(ticker, tf)`로 DataFrame 로드.
- `row_count_<tf>`, `last_date_<tf>`, ticker별 `base_tfs` 리스트 산출.
- 빈 DataFrame은 키 생략. parquet 미존재는 try/except로 흡수.

**Manifest 구조 (확장 후)**:
```json
{
  "collected_at": "2026-05-01T23:05:12+09:00",
  "market": "KOSPI",
  "base_tfs": ["1D", "1m"],
  "tickers": ["005930", "000660", ...],
  "tickers_meta": {
    "005930": {"last_date_1D": "2026-05-01", "row_count_1D": 500, "row_count_1m": 12000, "base_tfs": ["1D", "1m"]}
  },
  "summary": {"total_tickers": 500, "duration_sec": 1234}
}
```

**기존 코드 재사용**:
- `OhlcvDiskCache._path()` (`core/cache/ohlcv_disk.py:21-28`) — 파일 경로 규칙
- `OhlcvDiskCache.read()` (같은 파일) — DataFrame 로드

**성능 주의**: 500 ticker × 2 base_tf = 1000회 parquet read. 1회 수집 후 manifest 생성에서만 발생하므로 허용 가능. 시간이 문제면 `pyarrow.parquet.ParquetFile(path).metadata.num_rows`로 row만 빠르게 읽도록 후속 최적화.

**테스트**: `tests/test_collect.py`에 `test_manifest_includes_tickers_meta()` 추가 (mock disk cache).

### [B] Cron 운영 예시 문서

**왜**: wrapper script보다 사용 패턴 문서가 사용자 요구에 직결돼요. 신규 전략(3, 4)도 동일한 패턴으로 cron 한 줄만 추가하면 끝나요.

**대상 파일**: `docs/cron_examples.md` (신규)

**내용**:
```bash
# 매일 23:00 — 수집 (전략들이 의존하므로 먼저)
0 23 * * 1-5 cd /path/to/kospi-swing-scanner && \
  .venv/bin/python scripts/collect.py --market KOSPI \
  --cache-root .cache --timeframes 1D 1W 1h 30m \
  >> logs/collect.log 2>&1

# 매일 16:00 — 전략별 단독 스캔 (각 전략은 독립 process)
0 16 * * 1-5 cd /path/... && .venv/bin/python cli.py \
  --strategy strategy_one_d_v2 --output-dir scan_results \
  --format json --cache-root .cache >> logs/strategy_one.log 2>&1

5 16 * * 1-5 cd /path/... && .venv/bin/python cli.py \
  --strategy strategy_two_cross_sectional_momentum \
  --output-dir scan_results --format json --cache-root .cache \
  >> logs/strategy_two.log 2>&1

# 신규 전략 추가 시: strategies/__init__.py에 REGISTRY 등록 후 cron 한 줄 추가
```

신규 전략 추가 절차도 함께 기재 (REGISTRY 등록 → cron entry 추가 → 끝, 기존 전략 코드/cron entry 무수정).

## Critical Files

| 작업 | 파일 | 변경 종류 |
|------|------|----------|
| D | `output/formatters.py:102-116` (`format_json`) | 시그니처 확장 + payload 래핑 |
| D | `cli.py:125-133` (`render_single`) | 인자 전달 |
| A | `cli.py:155-195` (`save_output`) | manifest 헬퍼 호출 |
| A | `cli.py` 신규 함수 `_update_scan_manifest` | atomic write |
| C | `scripts/collect.py:172-186` | tickers_meta 추가 |
| C | `scripts/collect.py` 신규 `_build_tickers_metadata` | parquet meta 수집 |
| B | `docs/cron_examples.md` | 신규 문서 |

## Verification

```bash
# 1) 단위 테스트 — 71개 이상 통과 유지
.venv/bin/python -m pytest backtest_engine/tests/ -q
.venv/bin/python -m pytest tests/ -v

# 2) E2E — 수집 후 manifest 확인
python scripts/collect.py --market KOSPI --cache-root .cache --timeframes 1D --max-universe 5
cat .cache/manifest.json | jq '.tickers_meta | keys | length'  # >= 1
cat .cache/manifest.json | jq '.tickers_meta | to_entries[0].value'  # row_count_1D, last_date_1D 포함

# 3) E2E — 전략 단독 실행 후 manifest 확인
python cli.py --strategy strategy_one_d_v2 --output-dir scan_results --format json \
  --cache-root .cache --target-date 2026-05-01
cat scan_results/manifest.json | jq '."strategy_one_d_v2__1D"'  # latest_file, generated_at 포함

# 4) E2E — 같은 전략 재실행 시 history 유지 + manifest는 최신 가리킴
python cli.py --strategy strategy_one_d_v2 --output-dir scan_results --format json \
  --cache-root .cache --target-date 2026-05-01
ls scan_results/2026-05-01/1D/scan_*.json | wc -l  # >= 2 (history)
cat scan_results/manifest.json | jq -r '."strategy_one_d_v2__1D".latest_file'  # 가장 최근 timestamp

# 5) JSON schema 검증
python cli.py --strategy strategy_one_d_v2 --output-dir scan_results --format json --cache-root .cache
cat scan_results/.../scan_*.json | jq 'has("strategy") and has("date") and has("timeframe") and has("generated_at") and has("candidates") and has("summary")'  # true

# 6) 신규 전략 격리성 검증 — 가짜 strategy_four 추가 후 strategy_one_d_v2 결과 동일성
diff <(이전 결과) <(추가 후 결과)  # 동일

# 7) ruff lint
ruff check . --exclude .venv
```

## Decision Log

- **wrapper script 안 만들기**: `cli.py --strategy <name>`로 충분, wrapper는 중복 layer. cron 한 줄로 동일 효과.
- **manifest 키를 `<strategy>__<timeframe>`로**: 같은 전략의 1D/1h 결과를 동시에 가져갈 때 키 충돌 방지.
- **atomic write**: manifest 손상 시 UI가 전체 데이터 로드 실패하므로 temp file + `os.replace()` 필수.
- **CSV/Markdown formatter는 미변경**: 사용자 요구는 UI 로드(JSON)에 직결, 다른 포맷은 인간 가독성용으로 그대로 둬요. YAGNI.
- **C에서 row_count 계산 방식**: 일단 `disk_cache.read()` 사용. 성능 문제 발생 시 `pyarrow` metadata 읽기로 후속 최적화.

## Surprises / Risks

- 기존 결과 JSON 파서가 새 `metrics` 래핑을 기대하지 않으면 깨질 수 있어요. 현재 production에서 결과 JSON을 소비하는 코드가 있는지 점검 필요해요(없을 가능성이 큼 — UI 자체가 미구현).
- 멀티 프로세스 동시 manifest 갱신은 atomic rename으로 lost update가 발생할 수 있어요(전략 cron이 동시 실행되면 한 전략의 갱신이 사라질 수 있음). cron 시간을 5분 간격으로 띄우거나, 추후 fcntl lock 추가를 고려해요. 첫 단계에서는 간격 분리(예시 cron에 명시)로 회피.
- 수집 manifest의 `tickers_meta`는 base_tfs 기준만 포함해요. 1D 리샘플링된 30m/1h/4h는 manifest에 안 들어가요(파생 데이터이므로). UI가 필요하면 별도 API/계산으로.
