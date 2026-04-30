"""
test_daily_scanner_mock.py — 일봉 스크리너 end-to-end 검증

실제 pykrx/네이버 없이 Mock 데이터 소스로 스크리너 전체 흐름을 검증한다.
합성 시나리오(perfect_double_bottom 등)를 다양한 "가상 종목"에 주입하여
진입 조건 만족 종목을 정확히 탐지하는지 확인.
"""
import sys
from pathlib import Path
from typing import List

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from daily_only_scanner import (
    DataClient,
    DailyDataSource,
    DailyOnlyScanner,
    ScanConfig,
    print_results,
)
from backtest_engine.scenarios import ScenarioBuilder


# ============================================================================
# Mock 데이터 소스
# ============================================================================

class MockKOSPIDataSource(DailyDataSource):
    """가상 KOSPI 유니버스를 반환하는 Mock 소스"""
    name = "mock_kospi"

    # 가상 종목: (종목코드, 종목명, 시총(억), 사용할 시나리오 빌더)
    MOCK_UNIVERSE = [
        ("005930", "삼성전자",         3500_00, "perfect"),      # 350조 (제외: 너무 큼)
        ("000660", "SK하이닉스",        1200_00, "perfect"),      # 120조 (제외: 너무 큼)
        ("035720", "카카오",            19_000,  "perfect"),       # 1.9조 (포함)
        ("005380", "현대차",            45_000,  "uptrend"),       # 4.5조 (제외: 큼)
        ("068270", "셀트리온",          24_000,  "perfect"),       # 2.4조 (포함)
        ("207940", "삼성바이오로직스",   28_000,  "choppy"),        # 2.8조 (포함)
        ("051910", "LG화학",            40_000,  "fake"),          # 4조 (제외: 큼)
        ("035420", "NAVER",             25_000,  "perfect"),       # 2.5조 (포함)
        ("066570", "LG전자",            12_000,  "perfect"),       # 1.2조 (포함)
        ("034730", "SK",                15_000,  "fake"),          # 1.5조 (포함)
        ("015760", "한국전력",          25_000,  "perfect"),       # 2.5조 (포함)
        ("003490", "대한항공",          12_000,  "uptrend"),       # 1.2조 (포함)
        ("009540", "HD한국조선해양",    22_000,  "perfect"),       # 2.2조 (포함)
        ("028260", "삼성물산",          25_000,  "choppy"),        # 2.5조 (포함)
        ("105560", "KB금융",            28_000,  "perfect"),       # 2.8조 (포함)
        ("017670", "SK텔레콤",          10_000,  "perfect"),       # 1조 (제외: 경계)
        ("012450", "한화에어로스페이스", 18_000,  "perfect"),       # 1.8조 (제외: 경계)
        ("086790", "하나금융지주",      16_000,  "fake"),          # 1.6조 (포함)
        ("316140", "우리금융지주",      11_000,  "perfect"),       # 1.1조 (제외)
        ("055550", "신한지주",          22_000,  "choppy"),        # 2.2조 (포함)
    ]

    def __init__(self):
        self._scenarios = {
            "perfect": ScenarioBuilder.perfect_double_bottom,
            "fake": ScenarioBuilder.fake_double_bottom_loss,
            "uptrend": ScenarioBuilder.no_signal_uptrend,
            "choppy": ScenarioBuilder.choppy_no_signal,
        }
        self._lookup = {t: (n, c, s) for t, n, c, s in self.MOCK_UNIVERSE}

    def get_tickers(self, market: str, target_date: str) -> List[str]:
        return [t for t, _, _, _ in self.MOCK_UNIVERSE]

    def get_ticker_name(self, ticker: str) -> str:
        info = self._lookup.get(ticker)
        return info[0] if info else ticker

    def get_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        info = self._lookup.get(ticker)
        if info is None:
            return pd.DataFrame()
        _, _, scenario_key = info
        scenario_func = self._scenarios[scenario_key]
        # 각 종목별 다른 seed로 약간 다른 데이터 생성
        seed = int(ticker) % 1000
        scenario = scenario_func(seed=seed)
        df = scenario.df
        # 실전 재현: "오늘"이 진입봉이 되도록 잘라서 반환
        # perfect/fake 시나리오의 진입봉은 idx 32이므로 0~32까지만
        if scenario_key in ("perfect", "fake"):
            df = df.iloc[:33]
        return df

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """Mock 시가총액 DataFrame 반환 (pykrx 형식 모방)"""
        data = {
            ticker: {"시가총액": cap * 100_000_000, "종목명": name}
            for ticker, name, cap, _ in self.MOCK_UNIVERSE
        }
        return pd.DataFrame(data).T


# ============================================================================
# 테스트 실행
# ============================================================================

def test_scanner_end_to_end():
    """
    Mock 데이터로 전체 스크리너 파이프라인 검증.

    기대 결과:
      - 시총 필터 (2천억~3조) 통과 종목만 분석
      - perfect_double_bottom 시나리오 가진 종목만 시그널 발생
      - confidence 순 정렬된 결과 반환
      - 매수/손절/익절 가격 합리적
    """
    print("\n" + "=" * 90)
    print("  🧪 스크리너 end-to-end 검증 (Mock 데이터)")
    print("=" * 90 + "\n")

    # Mock 소스만 사용하도록 구성 (KRX Proxy 비활성화)
    mock = MockKOSPIDataSource()
    client = DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=False,  # Mock 테스트에선 실제 네트워크 접근 안 함
    )

    # 시총 2천억~3조 필터 적용
    config = ScanConfig(
        market="KOSPI",
        min_market_cap_bil=2000.0,
        max_market_cap_bil=30000.0,
        top_n=10,
        detector_name="simple",
    )
    scanner = DailyOnlyScanner(client=client, config=config)

    candidates = scanner.scan(target_date="20260418")

    print_results(candidates, "20260418")

    # 검증 항목
    print("  🔎 검증 결과")
    print("  " + "─" * 86)

    # 1) 시총 필터 제대로 작동? (삼성전자 350조, SK하이닉스 120조는 제외되어야)
    tickers_found = [c.ticker for c in candidates]
    assert "005930" not in tickers_found, "삼성전자(350조)는 시총 필터로 제외되어야"
    assert "000660" not in tickers_found, "SK하이닉스(120조)는 시총 필터로 제외되어야"
    print("  ✓ 시총 필터 정상 (초대형주 제외)")

    # 2) 진입 시그널이 나올 수 있는 시나리오는 perfect/fake (진입 시점 동일)
    # uptrend/choppy는 시그널 안 나와야 함
    for c in candidates:
        info = mock._lookup[c.ticker]
        scenario_key = info[2]
        assert scenario_key in ("perfect", "fake"), (
            f"{c.ticker}({info[0]})는 {scenario_key} 시나리오인데 시그널 발생!"
        )
    print(f"  ✓ perfect/fake 시나리오 종목만 시그널 ({len(candidates)}개)")
    print(f"     (진입 시점엔 동일, 이후 가격 흐름으로 승패 결정)")

    # 3) confidence 내림차순 정렬 확인
    confs = [c.confidence for c in candidates]
    assert confs == sorted(confs, reverse=True), "confidence 정렬 오류"
    print("  ✓ confidence 내림차순 정렬")

    # 4) 가격 로직 검증
    for c in candidates:
        assert c.stop_loss < c.entry_price < c.target_1 < c.target_2, (
            f"{c.ticker} 가격 순서 오류: sl={c.stop_loss}, e={c.entry_price}, "
            f"t1={c.target_1}, t2={c.target_2}"
        )
        assert 2.0 < c.risk_pct < 3.0, f"{c.ticker} 손절 폭 이상: {c.risk_pct:.2f}%"
        assert 2.5 < c.reward_pct_t1 < 3.5, f"{c.ticker} 1차 목표 이상"
        assert 4.5 < c.reward_pct_t2 < 5.5, f"{c.ticker} 2차 목표 이상"
    print("  ✓ 진입가/손절/목표가 로직 정상 (-2.5% / +3% / +5%)")

    # 5) 모든 후보에 conditions_met 기록 존재
    for c in candidates:
        assert len(c.conditions_met) > 0, f"{c.ticker} 조건 기록 없음"
        assert c.conditions_met.get("double_bottom", False), f"{c.ticker} 쌍바닥 미기록"
    print("  ✓ 진입 조건 기록 정상")

    print("\n  🎉 모든 검증 통과!\n")
    return candidates


if __name__ == "__main__":
    # ScanConfig 한글 필드명 이슈 임시 패치
    from dataclasses import fields
    candidates = test_scanner_end_to_end()
