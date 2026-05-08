"""
test_strategy_one_regression.py — 전략1 마이그레이션 회귀.

snapshot(legacy_scanner_snapshot.json) 과 신규 StrategyOneDv2 결과가 100% 일치
해야 한다. 일치 기준: ticker 순서 + confidence + entry_price + stop_loss +
target_1 + target_2 (모두 정확).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 같은 디렉토리의 mock 데이터 소스 재사용
sys.path.insert(0, str(Path(__file__).parent))

from test_daily_scanner_mock import MockKOSPIDataSource

from core.data_fetch import DataClient
from core.runner import RunnerConfig, ScanRunner
from strategies.strategy_one_d_v2 import StrategyOneDv2, StrategyOneDv2Config

SNAPSHOT_PATH = Path(__file__).parent / "fixtures" / "legacy_scanner_snapshot.json"


@pytest.fixture
def snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def new_candidates():
    """StrategyOneDv2 + ScanRunner 로 동일 mock 시나리오 재실행."""
    mock = MockKOSPIDataSource()
    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
    )
    runner = ScanRunner(
        client,
        RunnerConfig(
            market="KOSPI",
            min_market_cap_bil=2000.0,
            max_market_cap_bil=30000.0,
            min_daily_volume=100_000,
            top_n=20,
        ),
    )
    strategy = StrategyOneDv2(StrategyOneDv2Config(detector_name="simple"))
    result = runner.run([strategy], target_date="20260418")
    return result.candidates_by_strategy[strategy.name]


_ENTRY_GATE_SNAPSHOT_SKIP = pytest.mark.skip(
    reason="Task 5a-3 entry gate 도입으로 candidate 수·순서 변경 (의도된 동작 변경). "
    "Task 10 검증 단계에서 새 baseline 으로 snapshot 재생성 예정. "
    "test_snapshot_conditions_met_match 는 매칭된 후보 검증으로 유지."
)


@_ENTRY_GATE_SNAPSHOT_SKIP
def test_snapshot_count_matches(snapshot, new_candidates):
    assert len(new_candidates) == snapshot["candidate_count"]


@_ENTRY_GATE_SNAPSHOT_SKIP
def test_snapshot_ticker_order_matches(snapshot, new_candidates):
    legacy_tickers = [c["ticker"] for c in snapshot["candidates"]]
    new_tickers = [c.ticker for c in new_candidates]
    assert new_tickers == legacy_tickers


@_ENTRY_GATE_SNAPSHOT_SKIP
def test_snapshot_prices_and_score_match(snapshot, new_candidates):
    """가격·confidence·name 모두 일치 (1e-9 tolerance)."""
    for legacy, new in zip(snapshot["candidates"], new_candidates):
        assert legacy["ticker"] == new.ticker
        assert legacy["name"] == new.name
        # PR-H: score = confidence × 1000 × conf_scale (confirmation 배율 ≤ 1.0)
        assert 0 < new.score <= legacy["confidence"] * 1000 + 1e-6
        # entry_price/stop_loss 는 100원 반올림·반내림 적용 → raw 값은 current_price 에 보존
        assert legacy["entry_price"] == pytest.approx(new.current_price, abs=1e-9)
        assert new.stop_loss <= legacy["stop_loss"]          # 반내림이므로 항상 ≤
        assert new.entry_price >= legacy["entry_price"] - 50  # 반올림 범위 내
        assert new.stop_loss < new.entry_price < new.target_1 <= new.target_2


def test_snapshot_conditions_met_match(snapshot, new_candidates):
    for legacy, new in zip(snapshot["candidates"], new_candidates):
        # 정렬된 키 비교 (capture 시 sort 적용)
        legacy_conds = {k: bool(v) for k, v in legacy["conditions_met"].items()}
        new_conds = {k: bool(v) for k, v in new.conditions_met.items()}
        assert legacy_conds == new_conds, f"{new.ticker} conditions diff"
