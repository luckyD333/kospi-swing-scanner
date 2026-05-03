"""
test_daily_scanner_mock.py — 스크리너 end-to-end 검증 + Mock 데이터 소스 fixture.

본 모듈은 두 역할을 겸한다:
  1. MockKOSPIDataSource — 다른 테스트(_strategy_one_regression, _strict_mode_e2e,
     _cli, _integration)가 import 해 사용하는 결정론적 KOSPI mock 소스
  2. test_scanner_end_to_end — ScanRunner + StrategyOneDv2 통합 시나리오 검증
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from backtest_engine.scenarios import ScenarioBuilder
from core.data_fetch import DataClient
from core.data_sources.base import DailyDataSource
from core.runner import RunnerConfig, ScanRunner
from output.formatters import format_table
from strategies.strategy_one_d_v2 import StrategyOneDv2

# ============================================================================
# Mock 데이터 소스 (다른 테스트의 fixture 로 import 됨)
# ============================================================================

class MockKOSPIDataSource(DailyDataSource):
    """가상 KOSPI 유니버스를 반환하는 결정론적 Mock 소스."""
    name = "mock_kospi"

    # (종목코드, 종목명, 시총(억), 시나리오 키)
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

    def get_tickers(self, market: str, target_date: str) -> list[str]:
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
        # 각 종목별 다른 seed 로 약간 다른 데이터
        seed = int(ticker) % 1000
        scenario = scenario_func(seed=seed)
        df = scenario.df
        # 진입봉 이후 cut: snapshot 캡처와 동일 슬라이싱
        if scenario_key in ("perfect", "fake"):
            df = df.iloc[:33]
        return df

    def get_market_cap(self, market: str, target_date: str) -> pd.DataFrame:
        """Mock 시가총액 DataFrame (네이버 형식: 시가총액, 종목명 컬럼)."""
        data = {
            ticker: {"시가총액": cap * 100_000_000, "종목명": name}
            for ticker, name, cap, _ in self.MOCK_UNIVERSE
        }
        return pd.DataFrame(data).T


# ============================================================================
# E2E 검증
# ============================================================================

def test_scanner_end_to_end():
    """ScanRunner + StrategyOneDv2 + Mock 데이터로 전체 파이프라인 검증."""
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
            top_n=10,
        ),
    )
    strategy = StrategyOneDv2()
    result = runner.run([strategy], target_date="20260418")
    candidates = result.candidates_by_strategy[strategy.name]

    # 시각 확인용 출력 (capsys 가 받음 — 실패 시 디버깅에 유용)
    print(format_table(candidates, "20260418"))

    # 1) 시총 필터 — 삼성전자(350조), SK하이닉스(120조)는 제외돼야
    tickers_found = [c.ticker for c in candidates]
    assert "005930" not in tickers_found, "삼성전자(350조)는 시총 필터로 제외되어야"
    assert "000660" not in tickers_found, "SK하이닉스(120조)는 시총 필터로 제외되어야"

    # 2) perfect/fake 시나리오만 시그널 발생
    for c in candidates:
        info = mock._lookup[c.ticker]
        scenario_key = info[2]
        assert scenario_key in ("perfect", "fake"), (
            f"{c.ticker}({info[0]})는 {scenario_key} 시나리오인데 시그널 발생!"
        )

    # 3) score 내림차순
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)

    # 4) 가격 순서 + 비율
    for c in candidates:
        assert c.stop_loss < c.entry_price < c.target_1 <= c.target_2
        assert 2.0 < c.risk_pct < 6.0  # ATR 손절 활성화 시 고정 2.5% 초과 가능
        assert 2.5 < c.reward_pct_t1 < 3.5
        assert 3.0 < c.reward_pct_t2 < 8.0  # ATR 목표가2: target_1(3%) 초과, 이상값 감지

    # 5) 진입 조건 기록
    for c in candidates:
        assert len(c.conditions_met) > 0
        assert c.conditions_met.get("double_bottom"), f"{c.ticker} 쌍바닥 미기록"
