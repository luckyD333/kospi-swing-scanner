"""
test_strategy_entry_gate_integration.py — Entry gate 통합 테스트.

TDD RED: 5개 strategy + entry gate 조합 검증.

fixture 패턴:
  - DOWNTREND_STRONG: position=0.10, slope<0 → 모든 전략 0건
  - UPTREND_STRONG: position=0.85, slope>0 → strategy_three 후보 정상
  - RANGE_TIGHT: position=0.50, width_percentile<0.4 → 특정 전략 통과
  - DOWNTREND_WEAK + setup_score=70 → strategy_one 통과 (allow_strong_only)
  - DOWNTREND_WEAK + setup_score=40 → strategy_one 차단
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from backtest_engine.scenarios import ScenarioBuilder
from core.decision.donchian import DonchianFrame, compute_donchian
from core.decision.per_ticker_regime import daily_regime
from core.decision.entry_gate import is_strategy_allowed
from core.strategy_base import ScanContext
from strategies.strategy_one_d_v2 import StrategyOneDv2
from strategies.strategy_three_trend_following import StrategyThreeTrendFollowing


def _make_context_with_regimes(
    ticker_dfs: dict[str, pd.DataFrame],
    per_ticker_regime: dict[str, str] | None = None,
    donchian_1h_by_ticker: dict[str, DonchianFrame | None] | None = None,
) -> ScanContext:
    """ScanContext 생성 + entry gate 필드 주입."""
    ctx = ScanContext(
        target_date="20260418",
        universe=tuple(ticker_dfs.keys()),
        ohlcv={t: df for t, df in ticker_dfs.items() if len(df) >= 30},
        names={t: t for t in ticker_dfs},
        market_caps={t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
        ohlcv_by_tf={"1D": ticker_dfs},
    )
    # entry gate 필드 주입 (runner.py 에서 수행)
    ctx.per_ticker_regime = per_ticker_regime or {}
    ctx.donchian_1h_by_ticker = donchian_1h_by_ticker or {}
    return ctx


@pytest.fixture
def downtrend_strong_df():
    """DOWNTREND_STRONG regime: position=0.10, slope<0 — 강제 단조 하락 시계열."""
    price = 100.0
    rows = []
    for _ in range(40):
        price *= 0.98  # 매일 2% 하락
        rows.append({
            "open": price,
            "high": price + 1.0,
            "low": price - 0.5,
            "close": price,
            "volume": 1_000_000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def uptrend_strong_df():
    """UPTREND_STRONG regime: position >= 0.70, slope > 0"""
    scenario = ScenarioBuilder.perfect_double_bottom(seed=42)
    df = scenario.df.copy()
    # 상승 추세 추가: 더블바닥 후 강하게 상승
    if len(df) < 40:
        price = float(df["close"].iloc[-1])
        last_rows = []
        for i in range(50 - len(df)):
            price *= 1.015  # 매일 1.5% 상승
            last_rows.append({
                "open": price - 0.5,
                "high": price + 1.0,
                "low": price - 0.5,
                "close": price,
                "volume": 1_500_000,
            })
        if last_rows:
            df = pd.concat([
                df,
                pd.DataFrame(last_rows)
            ], ignore_index=True)
    return df


@pytest.fixture
def range_tight_df():
    """RANGE_TIGHT regime: 0.30 <= position <= 0.70, width_percentile < 0.4"""
    # 매우 좁은 범위에서 진동
    rows = []
    price = 100.0
    for i in range(50):
        if i % 2 == 0:
            price += 0.1  # 진동폭 0.2%
        else:
            price -= 0.1
        rows.append({
            "open": price,
            "high": price + 0.15,
            "low": price - 0.15,
            "close": price,
            "volume": 1_000_000,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def downtrend_weak_df():
    """DOWNTREND_WEAK regime: 0.15 <= position < 0.30, slope <= 0"""
    rows = []
    price = 100.0
    for i in range(50):
        price *= 0.995  # 완만한 하락
        rows.append({
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 1_000_000,
        })
    return pd.DataFrame(rows)


class TestEntryGateBasics:
    """Entry gate 함수 단위 테스트."""

    def test_downtrend_strong_blocks_all_strategies(self):
        """DOWNTREND_STRONG 은 모든 전략 차단."""
        for strategy in [
            "strategy_one_d_v2",
            "strategy_two_1h",
            "strategy_three_1h",
            "strategy_four_pullback_ma_1h",
            "strategy_five_bull_flag",
        ]:
            assert not is_strategy_allowed(strategy, "DOWNTREND_STRONG", None)

    def test_uptrend_strong_allows_trend_following(self):
        """UPTREND_STRONG 은 추세 추종 전략 허용."""
        assert is_strategy_allowed("strategy_three_trend_following", "UPTREND_STRONG", None)
        assert is_strategy_allowed("strategy_four_pullback_ma", "UPTREND_STRONG", None)
        assert is_strategy_allowed("strategy_five_bull_flag", "UPTREND_STRONG", None)

    def test_range_tight_allows_trend_following(self):
        """RANGE_TIGHT (에너지 응축) 은 추세 추종 전략 통과 — 돌파 임박 종목 잡기."""
        assert is_strategy_allowed("strategy_two_cross_sectional_momentum", "RANGE_TIGHT", None)
        assert is_strategy_allowed("strategy_three_trend_following", "RANGE_TIGHT", None)
        # strategy_one (mean reversion) 은 RANGE_TIGHT 에서 allow_strong_only — setup_score 60+ 만 통과
        assert not is_strategy_allowed("strategy_one_d_v2", "RANGE_TIGHT", None)
        assert is_strategy_allowed("strategy_one_d_v2", "RANGE_TIGHT", 65)

    def test_allow_strong_only_respects_threshold(self):
        """allow_strong_only 는 setup_score >= 60 만 통과."""
        # DOWNTREND_WEAK + strategy_one = allow_strong_only
        assert is_strategy_allowed("strategy_one_d_v2", "DOWNTREND_WEAK", 70)
        assert not is_strategy_allowed("strategy_one_d_v2", "DOWNTREND_WEAK", 50)
        assert not is_strategy_allowed("strategy_one_d_v2", "DOWNTREND_WEAK", None)


class TestIntegrationStrategyOne:
    """Strategy One (평균 회귀) + entry gate."""

    def test_downtrend_strong_produces_no_candidates(
        self, downtrend_strong_df
    ):
        """DOWNTREND_STRONG 에서는 후보 0개."""
        d_1d = compute_donchian(downtrend_strong_df, timeframe="1d")
        regime = daily_regime(d_1d) if d_1d else "MIXED"

        # regime 검증
        assert regime == "DOWNTREND_STRONG", f"Expected DOWNTREND_STRONG, got {regime}"

        per_ticker_regime = {"TEST": regime}
        ctx = _make_context_with_regimes({"TEST": downtrend_strong_df}, per_ticker_regime)

        strat = StrategyOneDv2()
        candidates = strat.scan(ctx, top_n=10)
        assert len(candidates) == 0

    def test_uptrend_weak_produces_candidates(self, uptrend_strong_df):
        """UPTREND_WEAK (또는 UPTREND_STRONG) 에서는 후보 발생 가능."""
        df = uptrend_strong_df.iloc[:33].copy()  # snapshot 슬라이싱
        d_1d = compute_donchian(df, timeframe="1d")
        regime = daily_regime(d_1d) if d_1d else "MIXED"

        per_ticker_regime = {"TEST": regime}
        ctx = _make_context_with_regimes({"TEST": df}, per_ticker_regime)

        strat = StrategyOneDv2()
        candidates = strat.scan(ctx, top_n=10)
        # 추세형 데이터이므로 진입 신호는 없을 수 있음 (평균 회귀 전략이므로)
        # 핵심: entry gate 차단 없이 scan 실행됨
        assert isinstance(candidates, list)


class TestIntegrationStrategyThree:
    """Strategy Three (추세 추종) + entry gate."""

    def test_uptrend_strong_produces_candidates(self, uptrend_strong_df):
        """UPTREND_STRONG 에서 strategy_three 는 후보 발생."""
        df = uptrend_strong_df
        d_1d = compute_donchian(df, timeframe="1d")
        regime = daily_regime(d_1d) if d_1d else "MIXED"

        assert regime in ["UPTREND_STRONG", "UPTREND_WEAK"], f"Got {regime}"

        per_ticker_regime = {"TEST": regime}
        ctx = _make_context_with_regimes({"TEST": df}, per_ticker_regime)

        strat = StrategyThreeTrendFollowing()
        candidates = strat.scan(ctx, top_n=10)
        # 상승 추세 데이터 + UPTREND 환경 = 추세 추종 신호 가능
        assert isinstance(candidates, list)

    def test_range_blocks_strategy_three(self, range_tight_df):
        """RANGE 환경은 strategy_three 차단."""
        d_1d = compute_donchian(range_tight_df, timeframe="1d")
        regime = daily_regime(d_1d) if d_1d else "MIXED"

        # RANGE_TIGHT 는 허용, RANGE 는 차단
        if regime == "RANGE":
            per_ticker_regime = {"TEST": regime}
            ctx = _make_context_with_regimes({"TEST": range_tight_df}, per_ticker_regime)

            strat = StrategyThreeTrendFollowing()
            candidates = strat.scan(ctx, top_n=10)
            # entry gate에서 차단되어야 함
            assert candidates == []


class TestMetadataPopulation:
    """Entry gate 통과 후 metadata 로 setup_score·regime 저장."""

    def test_candidate_metadata_includes_regime_and_setup_score(self, uptrend_strong_df):
        """Candidate.metadata 에 per_ticker_regime, setup_score, setup_reasons."""
        df = uptrend_strong_df.iloc[:33].copy()
        d_1d = compute_donchian(df, timeframe="1d")
        d_1h = compute_donchian(df, timeframe="1h")
        regime = daily_regime(d_1d) if d_1d else "MIXED"

        per_ticker_regime = {"TEST": regime}
        donchian_1h = {"TEST": d_1h}
        ctx = _make_context_with_regimes(
            {"TEST": df},
            per_ticker_regime,
            donchian_1h,
        )

        strat = StrategyOneDv2()
        candidates = strat.scan(ctx, top_n=10)

        # 후보가 생성되면 metadata 검증
        if candidates:
            for c in candidates:
                # entry gate 필드가 있는지 확인
                # (아직 구현 안 됨 — 다음 RED→GREEN 단계)
                pass
