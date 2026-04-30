"""
_capture_snapshot.py — daily_only_scanner.py 출력 박제 (회귀 baseline)

Sub-0에서 1회 실행. 결과는 `tests/fixtures/legacy_scanner_snapshot.json`에 저장되며,
Sub-1·2·3 진행 중 신규 모듈/CLI 결과와 비교해 회귀 검증에 사용한다.

실행:
    python -m tests._capture_snapshot

전제:
  - 기존 daily_only_scanner.py 가 정상 동작
  - tests.test_daily_scanner_mock.MockKOSPIDataSource 가 결정론적 (seed 고정)
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

# tests/ 를 import path 에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daily_only_scanner import DailyOnlyScanner, DataClient, ScanConfig
from tests.test_daily_scanner_mock import MockKOSPIDataSource


SNAPSHOT_PATH = Path(__file__).resolve().parent / "fixtures" / "legacy_scanner_snapshot.json"
TARGET_DATE = "20260418"
TOP_N = 20


def capture() -> dict:
    """Mock 데이터로 daily_only_scanner.py 실행 후 후보 직렬화"""
    mock = MockKOSPIDataSource()
    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=False,  # 네트워크 의존 제거
    )
    config = ScanConfig(
        market="KOSPI",
        min_market_cap_bil=2000.0,
        max_market_cap_bil=30000.0,
        top_n=TOP_N,
        detector_name="simple",
    )
    scanner = DailyOnlyScanner(client=client, config=config)
    candidates = scanner.scan(target_date=TARGET_DATE)

    serialized = []
    for c in candidates:
        d = asdict(c)
        # conditions_met 의 bool 값만 정렬해 결정론 보장
        d["conditions_met"] = {k: bool(v) for k, v in sorted(d["conditions_met"].items())}
        serialized.append(d)

    return {
        "version": 1,
        "target_date": TARGET_DATE,
        "top_n": TOP_N,
        "scanner": "daily_only_scanner.py",
        "candidate_count": len(serialized),
        "candidates": serialized,
    }


def main():
    snapshot = capture()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"✓ snapshot 저장: {SNAPSHOT_PATH}")
    print(f"  후보 {snapshot['candidate_count']}개 (target_date={TARGET_DATE}, top_n={TOP_N})")
    if snapshot["candidates"]:
        top = snapshot["candidates"][0]
        print(f"  Top 1: {top['ticker']} {top['name']} (confidence={top['confidence']})")


if __name__ == "__main__":
    main()
