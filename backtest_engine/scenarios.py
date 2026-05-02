"""
scenarios.py — 가상 OHLCV 시나리오 빌더

TDD를 위해 알려진 결과가 있는 합성 시장 데이터를 프로그래매틱하게 생성한다.
실제 종목 데이터 없이도 각 엔진 컴포넌트를 정확히 검증할 수 있다.

각 시나리오는:
  - 명확한 예상 동작 (어디서 진입/청산 해야 하는가)
  - 재현 가능 (시드 고정 옵션)
  - 파라미터화 가능 (강도, 노이즈 등 조절)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd


def _make_ohlcv_from_closes(
    closes: list[float],
    start_time: datetime,
    freq: str,
    volume_base: int = 100_000,
    noise_pct: float = 0.005,
    seed: int = 42,
) -> pd.DataFrame:
    """종가 시리즈로부터 OHLCV DataFrame 생성 (현실적인 시가/고가/저가 추정)"""
    rng = np.random.default_rng(seed)
    n = len(closes)
    times = pd.date_range(start=start_time, periods=n, freq=freq)

    opens = []
    highs = []
    lows = []
    volumes = []

    prev_close = closes[0]
    for i, close in enumerate(closes):
        # 시가 = 전봉 종가 근처 (작은 갭)
        if i == 0:
            open_ = close * (1 + rng.normal(0, noise_pct))
        else:
            open_ = prev_close * (1 + rng.normal(0, noise_pct * 0.5))

        # 고가/저가: 시가와 종가의 max/min에 약간 여유
        high = max(open_, close) * (1 + abs(rng.normal(0, noise_pct)))
        low = min(open_, close) * (1 - abs(rng.normal(0, noise_pct)))

        opens.append(open_)
        highs.append(high)
        lows.append(low)

        # 거래량: 큰 변동 시 증가
        vol_multiplier = 1 + abs(close - open_) / open_ * 10
        volumes.append(int(volume_base * vol_multiplier * rng.uniform(0.8, 1.3)))

        prev_close = close

    return pd.DataFrame(
        {
            "open": [float(x) for x in opens],
            "high": [float(x) for x in highs],
            "low": [float(x) for x in lows],
            "close": [float(x) for x in closes],
            "volume": volumes,
        },
        index=times,
    )


# ============================================================================
# 시나리오 빌더
# ============================================================================

@dataclass
class Scenario:
    """백테스트용 시나리오"""
    name: str
    df: pd.DataFrame
    expected_entry_idx: int | None       # 예상 진입 봉 (없으면 None)
    expected_exit_idx: int | None        # 예상 청산 봉
    expected_outcome: str                   # "win" / "loss" / "no_trade"
    notes: str = ""


class ScenarioBuilder:
    """재사용 가능한 시나리오 생성기"""

    START_TIME = datetime(2026, 1, 5, 9, 0)
    BASE_PRICE = 10_000.0

    @staticmethod
    def perfect_double_bottom(
        freq: str = "1D",
        base: float = 10_000.0,
        seed: int = 42,
    ) -> Scenario:
        """
        완벽한 쌍바닥 + 장악형 양봉 → 3일 내 +5% 상승

        구조 (총 43봉, BB/RSI 지표 warmup 포함):
          [0..19]   지표 warmup 구간 (횡보 10000 근처)
          [20..24]  연속 음봉 하락 → 1차 바닥 9050 (idx=24)
          [25..28]  반등 9350
          [29..31]  재하락 → 2차 바닥 9070 (idx=31)
          [32]      장악형 양봉 (진입 예정)
          [33..42]  상승 (익절 도달)
        """
        # 20봉 warmup: 10000 근처 횡보
        rng = np.random.default_rng(seed)
        warmup = [10000.0 + float(rng.normal(0, 30)) for _ in range(20)]

        closes = (
            warmup                                           # 0~19 warmup
            + [9800.0, 9600.0, 9400.0, 9200.0, 9050.0]       # 20~24 하락, 1차 바닥
            + [9150.0, 9250.0, 9300.0, 9350.0]                # 25~28 반등
            + [9250.0, 9150.0, 9070.0]                        # 29~31 재하락, 2차 바닥
            + [9500.0]                                         # 32 장악형 양봉
            + [9700.0, 9900.0, 10100.0, 10300.0, 10500.0]    # 33~37 상승
            + [10500.0, 10450.0, 10400.0, 10420.0, 10400.0]  # 38~42 유지
        )
        df = _make_ohlcv_from_closes(
            closes, ScenarioBuilder.START_TIME, freq=freq, seed=seed
        )

        # idx 29~31: 음봉 강제 (open > close)
        for i in [29, 30, 31]:
            open_price = closes[i - 1] * 1.002
            close_price = closes[i]
            df.iloc[i, df.columns.get_loc("open")] = open_price
            df.iloc[i, df.columns.get_loc("close")] = close_price
            df.iloc[i, df.columns.get_loc("high")] = open_price * 1.005
            df.iloc[i, df.columns.get_loc("low")] = close_price * 0.998

        # idx 32: 장악형 양봉
        prev_open = df.iloc[31]["open"]
        prev_close = df.iloc[31]["close"]
        df.iloc[32, df.columns.get_loc("open")] = prev_close * 0.998
        df.iloc[32, df.columns.get_loc("close")] = prev_open * 1.02
        df.iloc[32, df.columns.get_loc("high")] = df.iloc[32]["close"] * 1.008
        df.iloc[32, df.columns.get_loc("low")] = df.iloc[32]["open"] * 0.997

        return Scenario(
            name="perfect_double_bottom",
            df=df,
            expected_entry_idx=32,
            expected_exit_idx=35,   # +5% 달성 예상 시점
            expected_outcome="win",
            notes="이상적 쌍바닥(9050, 9070) + 장악형 양봉(idx 32) + 빠른 반등",
        )

    @staticmethod
    def fake_double_bottom_loss(freq: str = "1D", seed: int = 42) -> Scenario:
        """
        쌍바닥처럼 보이지만 2차 바닥 이후 추가 하락 → 손절.
        """
        rng = np.random.default_rng(seed)
        warmup = [10000.0 + float(rng.normal(0, 30)) for _ in range(20)]

        closes = (
            warmup                                           # 0~19
            + [9800.0, 9600.0, 9400.0, 9200.0, 9050.0]       # 20~24 하락
            + [9150.0, 9250.0, 9300.0, 9350.0]                # 25~28 반등
            + [9250.0, 9150.0, 9070.0]                        # 29~31 재하락
            + [9500.0]                                         # 32 장악형 (진입)
            + [9400.0, 9200.0, 9000.0, 8700.0, 8400.0]        # 33~37 추가 하락
            + [8300.0, 8200.0, 8100.0, 8050.0, 8000.0]        # 38~42
        )
        df = _make_ohlcv_from_closes(
            closes, ScenarioBuilder.START_TIME, freq=freq, seed=seed
        )

        for i in [29, 30, 31]:
            open_price = closes[i - 1] * 1.002
            df.iloc[i, df.columns.get_loc("open")] = open_price
            df.iloc[i, df.columns.get_loc("close")] = closes[i]
            df.iloc[i, df.columns.get_loc("high")] = open_price * 1.005
            df.iloc[i, df.columns.get_loc("low")] = closes[i] * 0.998

        prev_open = df.iloc[31]["open"]
        prev_close = df.iloc[31]["close"]
        df.iloc[32, df.columns.get_loc("open")] = prev_close * 0.998
        df.iloc[32, df.columns.get_loc("close")] = prev_open * 1.02
        df.iloc[32, df.columns.get_loc("high")] = df.iloc[32]["close"] * 1.008
        df.iloc[32, df.columns.get_loc("low")] = df.iloc[32]["open"] * 0.997

        return Scenario(
            name="fake_double_bottom_loss",
            df=df,
            expected_entry_idx=32,
            expected_exit_idx=None,
            expected_outcome="loss",
            notes="진입 후 추가 하락, 고정 손절(-2.5%) 도달",
        )

    @staticmethod
    def gap_down_loss(freq: str = "1D", seed: int = 42) -> Scenario:
        """진입 후 다음 봉 큰 갭다운 → 갭다운 손절"""
        rng = np.random.default_rng(seed)
        warmup = [10000.0 + float(rng.normal(0, 30)) for _ in range(20)]

        closes = (
            warmup
            + [9800.0, 9600.0, 9400.0, 9200.0, 9050.0]
            + [9150.0, 9250.0, 9300.0, 9350.0]
            + [9250.0, 9150.0, 9070.0]
            + [9500.0]                     # 32 진입
            + [9000.0]                      # 33: 갭다운
            + [8900.0, 8800.0, 8700.0, 8600.0]
            + [8500.0, 8400.0, 8300.0, 8200.0, 8100.0]
        )
        df = _make_ohlcv_from_closes(
            closes, ScenarioBuilder.START_TIME, freq=freq, seed=seed
        )

        for i in [29, 30, 31]:
            open_price = closes[i - 1] * 1.002
            df.iloc[i, df.columns.get_loc("open")] = open_price
            df.iloc[i, df.columns.get_loc("close")] = closes[i]
            df.iloc[i, df.columns.get_loc("high")] = open_price * 1.005
            df.iloc[i, df.columns.get_loc("low")] = closes[i] * 0.998

        prev_open = df.iloc[31]["open"]
        prev_close = df.iloc[31]["close"]
        df.iloc[32, df.columns.get_loc("open")] = prev_close * 0.998
        df.iloc[32, df.columns.get_loc("close")] = prev_open * 1.02
        df.iloc[32, df.columns.get_loc("high")] = df.iloc[32]["close"] * 1.008
        df.iloc[32, df.columns.get_loc("low")] = df.iloc[32]["open"] * 0.997

        # idx 33: -4% 갭다운
        entry_close = df.iloc[32]["close"]
        df.iloc[33, df.columns.get_loc("open")] = entry_close * 0.96
        df.iloc[33, df.columns.get_loc("high")] = entry_close * 0.962
        df.iloc[33, df.columns.get_loc("low")] = entry_close * 0.945
        df.iloc[33, df.columns.get_loc("close")] = entry_close * 0.955

        return Scenario(
            name="gap_down_loss",
            df=df,
            expected_entry_idx=32,
            expected_exit_idx=33,
            expected_outcome="loss",
            notes="진입 다음 봉 -4% 갭다운, 갭다운 손절 규칙",
        )

    @staticmethod
    def time_stop_breakeven(freq: str = "1D", seed: int = 42) -> Scenario:
        """진입 후 횡보 → 3봉 경과 시간 손절 (약한 손실 상태 마감)"""
        rng = np.random.default_rng(seed)
        warmup = [10000.0 + float(rng.normal(0, 30)) for _ in range(20)]

        closes = (
            warmup
            + [9800.0, 9600.0, 9400.0, 9200.0, 9050.0]
            + [9150.0, 9250.0, 9300.0, 9350.0]
            + [9250.0, 9150.0, 9070.0]
            + [9500.0]                     # 32 진입가
            + [9450.0, 9400.0, 9350.0]     # 33~35 약한 하락 (목표/손절 모두 미도달)
            + [9350.0]                     # 36 시간 손절 (진입가 대비 -1.6%, 거래비용 포함 시 loss)
            + [9350.0, 9340.0, 9360.0, 9350.0, 9340.0, 9360.0]
        )
        df = _make_ohlcv_from_closes(
            closes, ScenarioBuilder.START_TIME, freq=freq, seed=seed
        )

        for i in [29, 30, 31]:
            open_price = closes[i - 1] * 1.002
            df.iloc[i, df.columns.get_loc("open")] = open_price
            df.iloc[i, df.columns.get_loc("close")] = closes[i]
            df.iloc[i, df.columns.get_loc("high")] = open_price * 1.005
            df.iloc[i, df.columns.get_loc("low")] = closes[i] * 0.998

        prev_open = df.iloc[31]["open"]
        prev_close = df.iloc[31]["close"]
        df.iloc[32, df.columns.get_loc("open")] = prev_close * 0.998
        df.iloc[32, df.columns.get_loc("close")] = prev_open * 1.02
        df.iloc[32, df.columns.get_loc("high")] = df.iloc[32]["close"] * 1.008
        df.iloc[32, df.columns.get_loc("low")] = df.iloc[32]["open"] * 0.997

        # idx 33~35: 고가가 target_1(+3%) 미만, 저가가 stop_loss(-2.5%) 초과 유지
        entry_close = float(df.iloc[32]["close"])
        for i, close in [(33, 9450.0), (34, 9400.0), (35, 9350.0)]:
            df.iloc[i, df.columns.get_loc("open")] = entry_close * 0.995
            df.iloc[i, df.columns.get_loc("close")] = close
            df.iloc[i, df.columns.get_loc("high")] = entry_close * 1.005  # +0.5%, target_1 미도달
            df.iloc[i, df.columns.get_loc("low")] = close * 0.995

        return Scenario(
            name="time_stop_breakeven",
            df=df,
            expected_entry_idx=32,
            expected_exit_idx=35,   # 3봉 경과
            expected_outcome="loss",
            notes="진입 후 3봉 내 목표 미달, 시간 손절 (약한 -1.6% 손실)",
        )

    @staticmethod
    def no_signal_uptrend(freq: str = "1D", seed: int = 42) -> Scenario:
        """상승 추세 — 진입 시그널 없어야 함"""
        closes = list(np.linspace(10000, 13000, 43))
        df = _make_ohlcv_from_closes(
            closes, ScenarioBuilder.START_TIME, freq=freq, seed=seed
        )
        return Scenario(
            name="no_signal_uptrend",
            df=df,
            expected_entry_idx=None,
            expected_exit_idx=None,
            expected_outcome="no_trade",
            notes="지속 상승, RSI 과매도 조건 충족 안 됨",
        )

    @staticmethod
    def choppy_no_signal(freq: str = "1D", seed: int = 42) -> Scenario:
        """횡보 장 — RSI가 50 근처 머물러 시그널 없음"""
        rng = np.random.default_rng(seed)
        closes = [10000.0 + float(rng.normal(0, 80)) for _ in range(43)]
        df = _make_ohlcv_from_closes(
            closes, ScenarioBuilder.START_TIME, freq=freq, seed=seed
        )
        return Scenario(
            name="choppy_no_signal",
            df=df,
            expected_entry_idx=None,
            expected_exit_idx=None,
            expected_outcome="no_trade",
            notes="횡보장, 진입 조건 미충족",
        )

    @staticmethod
    def all() -> list[Scenario]:
        """전체 시나리오 목록"""
        return [
            ScenarioBuilder.perfect_double_bottom(),
            ScenarioBuilder.fake_double_bottom_loss(),
            ScenarioBuilder.gap_down_loss(),
            ScenarioBuilder.time_stop_breakeven(),
            ScenarioBuilder.no_signal_uptrend(),
            ScenarioBuilder.choppy_no_signal(),
        ]
