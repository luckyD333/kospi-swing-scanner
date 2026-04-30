"""
test_strict_mode_e2e.py — 엄격 모드에서 KRX 장애 시 스캔 중단 검증.

사용자 요구: "딜레이 또는 오류가 발생해 데이터를 전부 가져오지 못한다면 동작을 멈추도록"

검증 시나리오:
  1. strict_mode=True + KRX 503 → RuntimeError 로 ScanRunner.run() 중단
  2. strict_mode=False (기본) + KRX 503 → 네이버/mock fallback 진행
  3. strict_mode=True + use_krx_for_universe=False → KRX 호출 0, 정상 완료
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from core.data_fetch import DataClient
from core.runner import RunnerConfig, ScanRunner
from strategies.strategy_one_d_v2 import StrategyOneDv2
from test_daily_scanner_mock import MockKOSPIDataSource


def _mock_fail_response(status_code):
    import requests
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = None
    m.raise_for_status = MagicMock(
        side_effect=requests.HTTPError(f"{status_code}")
    )
    return m


def _runner(strict_mode: bool, use_krx: bool):
    mock = MockKOSPIDataSource()
    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=use_krx,
        strict_mode=strict_mode,
    )
    return ScanRunner(
        client,
        RunnerConfig(
            market="KOSPI",
            min_market_cap_bil=2000.0,
            max_market_cap_bil=30000.0,
            min_daily_volume=100_000,
            top_n=10,
        ),
    )


def test_strict_mode_aborts_on_krx_503():
    """strict_mode=True: KRX 503 발생하면 RuntimeError 로 스캔 중단."""
    runner = _runner(strict_mode=True, use_krx=True)

    def always_503(url, params=None, **kwargs):
        return _mock_fail_response(503)

    with patch("core.data_sources.krx_proxy.requests.get", side_effect=always_503), \
         patch("core.data_sources.krx_proxy.time.sleep"):
        with pytest.raises(RuntimeError) as excinfo:
            runner.run([StrategyOneDv2()], target_date="20260418")

    msg = str(excinfo.value)
    assert "strict_mode" in msg or "중단" in msg or "불완전" in msg


def test_non_strict_mode_falls_back_on_krx_503():
    """strict_mode=False: KRX 503 → 네이버/mock fallback 으로 계속."""
    runner = _runner(strict_mode=False, use_krx=True)

    def always_503(url, params=None, **kwargs):
        return _mock_fail_response(503)

    with patch("core.data_sources.krx_proxy.requests.get", side_effect=always_503), \
         patch("core.data_sources.krx_proxy.time.sleep"):
        result = runner.run([StrategyOneDv2()], target_date="20260418")

    candidates = result.candidates_by_strategy.get("strategy_one_d_v2", [])
    assert candidates, "fallback 모드인데 candidates 없음"


def test_strict_mode_allows_no_krx():
    """strict_mode=True + use_krx_for_universe=False → KRX 호출 0, 정상 완료."""
    runner = _runner(strict_mode=True, use_krx=False)

    def unreachable(url, params=None, **kwargs):
        raise AssertionError(f"KRX 호출되면 안 됨: {url}")

    with patch("core.data_sources.krx_proxy.requests.get", side_effect=unreachable):
        result = runner.run([StrategyOneDv2()], target_date="20260418")

    candidates = result.candidates_by_strategy.get("strategy_one_d_v2", [])
    assert candidates
