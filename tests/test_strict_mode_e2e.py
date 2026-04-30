"""
test_strict_mode_e2e.py — 엄격 모드에서 KRX 장애 시 스캔 중단 검증

사용자 요구: "딜레이 또는 오류가 발생해 데이터를 전부 가져오지 못한다면 동작을 멈추도록"

검증 시나리오:
  1. strict_mode=True + KRX 503 → RuntimeError로 스캔 전체 중단
  2. strict_mode=False (기본) + KRX 503 → 네이버/pykrx fallback 진행
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from daily_only_scanner import (
    DataClient, DailyOnlyScanner, ScanConfig,
    KRXProxySource, CircuitBreaker, CircuitBreakerOpen,
)
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


def test_strict_mode_aborts_on_krx_503():
    """strict_mode=True: KRX 503 발생하면 RuntimeError로 스캔 중단"""
    print("\n[Scenario 1] strict_mode=True + KRX 503")
    print("  기대: RuntimeError로 스캔 전체 중단")

    mock = MockKOSPIDataSource()

    # KRX Proxy는 503만 반환
    def always_503(url, params=None, **kwargs):
        return _mock_fail_response(503)

    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=True,   # KRX 사용 강제
        strict_mode=True,             # 엄격 모드
    )

    config = ScanConfig(
        market="KOSPI",
        min_market_cap_bil=2000.0,
        max_market_cap_bil=30000.0,
        top_n=10,
    )
    scanner = DailyOnlyScanner(client=client, config=config)

    aborted = False
    err_msg = None
    with patch("daily_only_scanner.requests.get", side_effect=always_503), \
         patch("daily_only_scanner.time.sleep"):
        try:
            scanner.scan(target_date="20260418")
        except RuntimeError as e:
            aborted = True
            err_msg = str(e)

    assert aborted, "strict_mode=True에서 RuntimeError 발생 안 함"
    assert "strict_mode" in err_msg or "중단" in err_msg or "불완전" in err_msg
    print(f"  ✓ 스캔 중단됨: {err_msg[:80]}...")


def test_non_strict_mode_falls_back_on_krx_503():
    """strict_mode=False (기본): KRX 503이면 네이버/mock fallback으로 계속"""
    print("\n[Scenario 2] strict_mode=False + KRX 503")
    print("  기대: fallback으로 스캔 정상 완료")

    mock = MockKOSPIDataSource()

    def always_503(url, params=None, **kwargs):
        return _mock_fail_response(503)

    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=True,
        strict_mode=False,            # 기본 모드
    )

    config = ScanConfig(
        market="KOSPI",
        min_market_cap_bil=2000.0,
        max_market_cap_bil=30000.0,
        top_n=10,
    )
    scanner = DailyOnlyScanner(client=client, config=config)

    with patch("daily_only_scanner.requests.get", side_effect=always_503), \
         patch("daily_only_scanner.time.sleep"):
        candidates = scanner.scan(target_date="20260418")

    assert candidates is not None
    # Mock 시총으로 필터링되어 perfect/fake 후보 발견되어야
    assert len(candidates) > 0, "fallback 모드인데 candidates 없음"
    print(f"  ✓ fallback 성공: {len(candidates)}개 후보 발견")


def test_strict_mode_allows_no_krx():
    """strict_mode=True + use_krx_for_universe=False면 KRX 안 씀"""
    print("\n[Scenario 3] strict_mode=True + use_krx=False")
    print("  기대: KRX 호출 없이 mock만으로 완료")

    mock = MockKOSPIDataSource()

    def unreachable(url, params=None, **kwargs):
        raise AssertionError(f"KRX 호출되면 안 됨: {url}")

    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=False,   # KRX 끔
        strict_mode=True,              # strict이지만 KRX 안 쓰므로 OK
    )

    config = ScanConfig(
        market="KOSPI",
        min_market_cap_bil=2000.0,
        max_market_cap_bil=30000.0,
        top_n=10,
    )
    scanner = DailyOnlyScanner(client=client, config=config)

    # requests.get이 호출되지 않아야 하므로 예외 발생 시 테스트 실패
    with patch("daily_only_scanner.requests.get", side_effect=unreachable):
        candidates = scanner.scan(target_date="20260418")

    assert len(candidates) > 0
    print(f"  ✓ KRX 없이 {len(candidates)}개 후보 발견")


def main():
    print("\n" + "=" * 76)
    print("  🧪 엄격 모드 (strict_mode) 엔드투엔드 검증")
    print("  사용자 요구: '오류 발생 시 동작을 멈추도록'")
    print("=" * 76)

    test_strict_mode_aborts_on_krx_503()
    test_non_strict_mode_falls_back_on_krx_503()
    test_strict_mode_allows_no_krx()

    print("\n  🎉 엄격 모드 동작 검증 완료\n")
    print("  정리:")
    print("    --strict 없이: KRX 장애 시 네이버/pykrx로 자동 fallback (개발 편의)")
    print("    --strict 옵션: KRX 장애 시 RuntimeError로 즉시 중단 (실전 안전)")
    print()


if __name__ == "__main__":
    main()
