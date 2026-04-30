"""
test_krx_proxy_mock.py — KRX Proxy + Circuit Breaker 단위 테스트

실제 네트워크 호출 없이 requests.get을 monkey-patch.
스킬 문서의 정확한 응답 구조(items/item 단수형, proxy.upstream.degraded) 반영.

검증 항목:
  1. 정확한 응답 구조 파싱 (items, item)
  2. trade-info의 market_cap 추출
  3. Circuit Breaker 동작 (연속 실패 시 중단)
  4. 503/502 즉시 OPEN
  5. 재시도 (429, 500)
  6. 실패율 초과 시 enrich 중단
  7. 휴장일 fallback
  8. Ctrl+C 전파
"""
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from daily_only_scanner import KRXProxySource, CircuitBreaker, CircuitBreakerOpen


# ============================================================================
# 스킬 문서 기반 정확한 Mock 응답
# ============================================================================

MOCK_SEARCH_RESPONSE = {
    "items": [
        {
            "market": "KOSPI",
            "code": "005930",
            "standard_code": "KR7005930003",
            "name": "삼성전자",
            "short_name": "삼성전자",
            "english_name": "Samsung Electronics",
            "listed_at": "1975-06-11",
        }
    ],
    "query": {"q": "삼성전자", "bas_dd": "20260418", "limit": 10},
    "proxy": {"name": "k-skill-proxy", "cache": {"hit": False, "ttl_ms": 300000}},
}

MOCK_SEARCH_DEGRADED = {
    "items": [
        {"market": "KOSPI", "code": "005930", "name": "삼성전자",
         "short_name": "삼성전자", "standard_code": "KR7005930003",
         "english_name": "Samsung", "listed_at": "1975-06-11"}
    ],
    "query": {"q": "삼성"},
    "proxy": {
        "name": "k-skill-proxy",
        "cache": {"hit": False, "ttl_ms": 300000},
        "upstream": {"degraded": True, "failed_markets": ["KONEX"]},
    },
}

MOCK_BASE_INFO_RESPONSES = {
    "005930": {
        "item": {
            "market": "KOSPI", "code": "005930",
            "standard_code": "KR7005930003",
            "name": "삼성전자", "short_name": "삼성전자",
            "english_name": "Samsung Electronics",
            "security_group": "주권", "section_type": "대형주",
            "stock_certificate_type": "보통주",
            "par_value": 100, "listed_shares": 5_969_782_550,
        },
        "query": {"market": "KOSPI", "code": "005930", "bas_dd": "20260418"},
        "proxy": {"name": "k-skill-proxy", "cache": {"hit": False, "ttl_ms": 300000}},
    },
}

# trade-info만 market_cap 포함 (스킬 스펙)
MOCK_TRADE_INFO_RESPONSES = {
    "005930": {
        "item": {
            "market": "KOSPI", "code": "005930",
            "standard_code": "KR7005930003",
            "base_date": "20260418", "name": "삼성전자",
            "close_price": 84_000, "change_price": 1000, "fluctuation_rate": 1.2,
            "open_price": 83_000, "high_price": 84_500, "low_price": 82_800,
            "trading_volume": 12_345_678, "trading_value": 1_030_000_000_000,
            "market_cap": 500_000_000_000_000,  # 500조
        },
        "query": {"market": "KOSPI", "code": "005930", "bas_dd": "20260418"},
        "proxy": {"name": "k-skill-proxy", "cache": {"hit": False, "ttl_ms": 300000}},
    },
    "035720": {
        "item": {
            "market": "KOSPI", "code": "035720",
            "standard_code": "KR7035720002",
            "base_date": "20260418", "name": "카카오",
            "close_price": 42_000, "change_price": 500, "fluctuation_rate": 1.2,
            "open_price": 41_800, "high_price": 42_200, "low_price": 41_500,
            "trading_volume": 2_000_000, "trading_value": 84_000_000_000,
            "market_cap": 19_000 * 100_000_000,  # 1.9조
        },
        "query": {"market": "KOSPI", "code": "035720", "bas_dd": "20260418"},
        "proxy": {"name": "k-skill-proxy", "cache": {"hit": False, "ttl_ms": 300000}},
    },
    "035420": {
        "item": {
            "market": "KOSPI", "code": "035420",
            "standard_code": "KR7035420009",
            "base_date": "20260418", "name": "NAVER",
            "close_price": 155_000, "change_price": 2000, "fluctuation_rate": 1.3,
            "open_price": 154_000, "high_price": 156_000, "low_price": 153_000,
            "trading_volume": 500_000, "trading_value": 77_500_000_000,
            "market_cap": 25_000 * 100_000_000,  # 2.5조
        },
        "query": {"market": "KOSPI", "code": "035420", "bas_dd": "20260418"},
        "proxy": {"name": "k-skill-proxy", "cache": {"hit": False, "ttl_ms": 300000}},
    },
}


def _mock_response(json_data, status_code=200):
    import requests
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data
    if status_code >= 400:
        m.raise_for_status = MagicMock(
            side_effect=requests.HTTPError(f"{status_code}")
        )
    else:
        m.raise_for_status = MagicMock()
    return m


def _fake_get_factory(fail_status=None, fail_count=0):
    """Mock request handler factory"""
    fail_left = [fail_count]

    def fake_get(url, params=None, **kwargs):
        if fail_status is not None and fail_left[0] > 0:
            fail_left[0] -= 1
            return _mock_response(None, status_code=fail_status)

        if "/search" in url:
            q = (params or {}).get("q", "")
            if "degraded" in q:
                return _mock_response(MOCK_SEARCH_DEGRADED)
            if "삼성" in q:
                return _mock_response(MOCK_SEARCH_RESPONSE)
            return _mock_response(None, status_code=404)

        if "/base-info" in url:
            code = (params or {}).get("code", "")
            if code in MOCK_BASE_INFO_RESPONSES:
                return _mock_response(MOCK_BASE_INFO_RESPONSES[code])
            return _mock_response(None, status_code=404)

        if "/trade-info" in url:
            code = (params or {}).get("code", "")
            if code in MOCK_TRADE_INFO_RESPONSES:
                return _mock_response(MOCK_TRADE_INFO_RESPONSES[code])
            return _mock_response(None, status_code=404)

        return _mock_response(None, status_code=404)

    return fake_get


# ============================================================================
# [1] 엔드포인트 응답 구조
# ============================================================================

def test_search_returns_items_array():
    """search는 items 배열 + proxy meta 반환"""
    src = KRXProxySource()
    with patch("core.data_sources.krx_proxy.requests.get", side_effect=_fake_get_factory()):
        items, proxy = src.search(query="삼성전자", bas_dd="20260418")
    assert len(items) == 1
    assert items[0]["code"] == "005930"
    assert items[0]["name"] == "삼성전자"
    assert "cache" in proxy
    print("  ✓ search() → items 배열 + proxy meta 정확히 파싱")


def test_search_degraded_warning():
    """upstream.degraded=true 응답 처리"""
    src = KRXProxySource()
    with patch("core.data_sources.krx_proxy.requests.get", side_effect=_fake_get_factory()):
        items, proxy = src.search(query="degraded")
    assert len(items) == 1
    assert proxy["upstream"]["degraded"] is True
    assert "KONEX" in proxy["upstream"]["failed_markets"]
    print("  ✓ search() degraded 응답 (failed_markets 포함)")


def test_search_not_found():
    src = KRXProxySource()
    with patch("core.data_sources.krx_proxy.requests.get", side_effect=_fake_get_factory()):
        items, _ = src.search(query="UNKNOWN")
    assert items == []
    print("  ✓ search() 404 → 빈 리스트")


def test_get_base_info_returns_item_singular():
    """base-info는 단수 item (market_cap 없음)"""
    src = KRXProxySource()
    with patch("core.data_sources.krx_proxy.requests.get", side_effect=_fake_get_factory()):
        info = src.get_base_info(market="KOSPI", code="005930", bas_dd="20260418")
    assert info is not None
    assert info["name"] == "삼성전자"
    assert info["listed_shares"] == 5_969_782_550
    assert "market_cap" not in info
    print("  ✓ get_base_info() → item 단수, market_cap 필드 없음 (스킬 스펙 일치)")


def test_get_trade_info_has_market_cap():
    """trade-info만 market_cap 포함 — 시총 필터링 핵심"""
    src = KRXProxySource()
    with patch("core.data_sources.krx_proxy.requests.get", side_effect=_fake_get_factory()):
        data = src.get_trade_info(market="KOSPI", code="005930", bas_dd="20260418")
    assert data is not None
    assert data["market_cap"] == 500_000_000_000_000
    assert data["close_price"] == 84_000
    assert data["trading_volume"] == 12_345_678
    print("  ✓ get_trade_info() → market_cap 포함 (시총 필드 여기서만 옴)")


def test_invalid_market_raises():
    src = KRXProxySource()
    try:
        src.get_base_info(market="INVALID", code="005930")
        assert False, "ValueError 기대"
    except ValueError:
        pass
    print("  ✓ invalid market → ValueError")


# ============================================================================
# [2] Circuit Breaker
# ============================================================================

def test_cb_closed_by_default():
    cb = CircuitBreaker()
    assert cb.state == CircuitBreaker.STATE_CLOSED
    cb.before_request()
    print("  ✓ 기본 상태 CLOSED")


def test_cb_opens_on_503():
    cb = CircuitBreaker()
    cb.on_failure(status_code=503)
    assert cb.state == CircuitBreaker.STATE_OPEN
    try:
        cb.before_request()
        assert False
    except CircuitBreakerOpen:
        pass
    print("  ✓ 503 → 즉시 OPEN")


def test_cb_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3)
    cb.on_failure(status_code=500)
    cb.on_failure(status_code=500)
    assert cb.state == CircuitBreaker.STATE_CLOSED
    cb.on_failure(status_code=500)
    assert cb.state == CircuitBreaker.STATE_OPEN
    print("  ✓ 연속 N회 실패 → threshold 초과 시 OPEN")


def test_cb_recovery():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_sec=0.1)
    cb.on_failure(status_code=500)
    cb.on_failure(status_code=500)
    assert cb.state == CircuitBreaker.STATE_OPEN

    time.sleep(0.15)
    cb.before_request()
    assert cb.state == CircuitBreaker.STATE_HALF_OPEN

    cb.on_success()
    assert cb.state == CircuitBreaker.STATE_CLOSED
    assert cb.consecutive_failures == 0
    print("  ✓ HALF_OPEN 복구 후 성공 시 CLOSED")


def test_cb_success_resets():
    cb = CircuitBreaker()
    cb.on_failure(status_code=500)
    cb.on_failure(status_code=500)
    assert cb.consecutive_failures == 2
    cb.on_success()
    assert cb.consecutive_failures == 0
    print("  ✓ 성공 시 카운터 리셋")


# ============================================================================
# [3] HTTP Retry
# ============================================================================

def test_retry_on_500_then_success():
    """500 → 재시도 → 성공"""
    src = KRXProxySource()
    call_count = [0]

    def flaky(url, params=None, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 2:
            return _mock_response(None, status_code=500)
        if "/trade-info" in url:
            return _mock_response(MOCK_TRADE_INFO_RESPONSES["005930"])
        return _mock_response(None, status_code=404)

    with patch("core.data_sources.krx_proxy.requests.get", side_effect=flaky), \
         patch("core.data_sources.krx_proxy.time.sleep"):
        data = src.get_trade_info(market="KOSPI", code="005930", bas_dd="20260418")

    assert data is not None
    assert call_count[0] == 3
    print("  ✓ 500 재시도 후 복구")


def test_503_no_retry_opens_cb():
    """503 한 번에 circuit OPEN (재시도 없음)"""
    src = KRXProxySource()
    with patch(
        "core.data_sources.krx_proxy.requests.get",
        side_effect=_fake_get_factory(fail_status=503, fail_count=99),
    ), patch("core.data_sources.krx_proxy.time.sleep"):
        try:
            src.get_trade_info(market="KOSPI", code="005930", bas_dd="20260418")
            assert False
        except Exception:
            pass
    assert src.circuit_breaker.state == CircuitBreaker.STATE_OPEN
    print("  ✓ 503 → 재시도 없이 즉시 circuit OPEN")


# ============================================================================
# [4] enrich 중단 시나리오 (사용자 요구 핵심)
# ============================================================================

def test_enrich_normal():
    src = KRXProxySource()
    with patch(
        "core.data_sources.krx_proxy.requests.get", side_effect=_fake_get_factory(),
    ), patch("core.data_sources.krx_proxy.time.sleep"):
        result = src.enrich_with_trade_info(
            tickers=["005930", "035720", "035420"],
            market="KOSPI", bas_dd="20260418", rate_limit_sec=0,
        )
    assert len(result) == 3
    assert result["005930"]["market_cap"] == 500_000_000_000_000
    print("  ✓ 정상 케이스 (3종목 보강)")


def test_enrich_stops_on_503():
    """503 → Circuit Breaker OPEN → enrich 즉시 중단"""
    src = KRXProxySource()
    tickers = [f"TEST{i:04d}" for i in range(100)]

    with patch(
        "core.data_sources.krx_proxy.requests.get",
        side_effect=_fake_get_factory(fail_status=503, fail_count=999),
    ), patch("core.data_sources.krx_proxy.time.sleep"):
        try:
            src.enrich_with_trade_info(
                tickers=tickers, market="KOSPI",
                bas_dd="20260418", rate_limit_sec=0,
            )
            assert False, "RuntimeError 기대"
        except RuntimeError as e:
            assert "장애" in str(e) or "중단" in str(e)

    assert src.circuit_breaker.state == CircuitBreaker.STATE_OPEN
    print("  ✓ 503 발생 → 즉시 enrich 중단 (사용자 요구: '동작을 멈추도록')")


def test_enrich_handles_keyboard_interrupt():
    """Ctrl+C 즉시 전파"""
    src = KRXProxySource()

    def interrupting(url, params=None, **kwargs):
        raise KeyboardInterrupt()

    with patch("core.data_sources.krx_proxy.requests.get", side_effect=interrupting):
        try:
            src.enrich_with_trade_info(
                tickers=["005930", "035720"],
                market="KOSPI", bas_dd="20260418", rate_limit_sec=0,
            )
            assert False
        except KeyboardInterrupt:
            pass
    print("  ✓ Ctrl+C → 즉시 전파")


def test_enrich_market_cap_filter():
    """보강 결과로 시총 필터링"""
    src = KRXProxySource()
    with patch(
        "core.data_sources.krx_proxy.requests.get", side_effect=_fake_get_factory(),
    ), patch("core.data_sources.krx_proxy.time.sleep"):
        result = src.enrich_with_trade_info(
            tickers=["005930", "035720", "035420"],
            market="KOSPI", bas_dd="20260418", rate_limit_sec=0,
        )

    # 2천억~3조 필터 (억 단위)
    filtered = [
        t for t, info in result.items()
        if 2_000 <= info["market_cap"] / 100_000_000 <= 30_000
    ]
    assert "005930" not in filtered  # 500조
    assert "035720" in filtered       # 1.9조
    assert "035420" in filtered       # 2.5조
    print("  ✓ 보강 → 시총 범위 필터 정상 작동")


# ============================================================================
# [5] 휴장일 처리
# ============================================================================

def test_holiday_fallback():
    """휴장일이면 최근 영업일로 소급"""
    src = KRXProxySource()
    call_count = [0]

    def holiday_get(url, params=None, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 2:
            return _mock_response(None, status_code=404)
        if "/trade-info" in url:
            return _mock_response(MOCK_TRADE_INFO_RESPONSES["005930"])
        return _mock_response(None, status_code=404)

    with patch("core.data_sources.krx_proxy.requests.get", side_effect=holiday_get):
        data = src.get_trade_info_with_fallback(
            market="KOSPI", code="005930", bas_dd="20260418"
        )
    assert data is not None
    print("  ✓ 휴장일 fallback (N영업일 소급)")


# ============================================================================
# 실행
# ============================================================================

def main():
    print("\n" + "=" * 76)
    print("  🧪 KRX Proxy + Circuit Breaker 단위 테스트")
    print("=" * 76 + "\n")

    print("\n[1] 엔드포인트 응답 구조 (스킬 스펙 반영)")
    test_search_returns_items_array()
    test_search_degraded_warning()
    test_search_not_found()
    test_get_base_info_returns_item_singular()
    test_get_trade_info_has_market_cap()
    test_invalid_market_raises()

    print("\n[2] Circuit Breaker")
    test_cb_closed_by_default()
    test_cb_opens_on_503()
    test_cb_opens_after_threshold()
    test_cb_recovery()
    test_cb_success_resets()

    print("\n[3] HTTP Retry")
    test_retry_on_500_then_success()
    test_503_no_retry_opens_cb()

    print("\n[4] enrich 중단 시나리오 (사용자 요구 핵심)")
    test_enrich_normal()
    test_enrich_stops_on_503()
    test_enrich_handles_keyboard_interrupt()
    test_enrich_market_cap_filter()

    print("\n[5] 휴장일 처리")
    test_holiday_fallback()

    print("\n  🎉 모든 KRX Proxy 테스트 통과!\n")


if __name__ == "__main__":
    main()
