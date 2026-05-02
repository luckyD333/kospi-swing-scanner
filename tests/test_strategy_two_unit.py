"""
test_strategy_two_unit.py — Cross-sectional Momentum (Jegadeesh-Titman 1993) 단위 테스트.

검증:
  - 15일 상대 수익률 ranking 상위 percentile 만 후보 진입
  - volume filter (당일 거래량 ≥ 20일 평균) 작동
  - lookback 부족 ticker 배제
  - score = percentile rank (0.75~1.0 범위)
  - top_n cut, 빈 universe 처리
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from core.strategy_base import ScanContext
from strategies.strategy_two_cross_sectional_momentum import (
    StrategyTwoConfig,
    StrategyTwoCrossSectionalMomentum,
)

# ============================================================================
# fixtures
# ============================================================================

def _trend_df(start_price: float, daily_return: float, n: int = 30, volume: int = 1_000_000) -> pd.DataFrame:
    """일정 일간 수익률로 상승/하락하는 결정론적 OHLCV."""
    closes = [start_price * ((1 + daily_return) ** i) for i in range(n)]
    return pd.DataFrame({
        "open": closes,
        "high": [c * 1.005 for c in closes],
        "low": [c * 0.995 for c in closes],
        "close": closes,
        "volume": [volume] * n,
    }, index=pd.date_range("2026-01-01", periods=n, freq="D"))


def _make_ctx(ticker_dfs: dict[str, pd.DataFrame]) -> ScanContext:
    return ScanContext(
        target_date="20260418",
        universe=tuple(ticker_dfs.keys()),
        ohlcv=ticker_dfs,
        names={t: f"name_{t}" for t in ticker_dfs},
        market_caps={t: 5_000 * 1e8 for t in ticker_dfs},
        market="KOSPI",
    )


# ============================================================================
# tests
# ============================================================================

def test_winners_only_above_percentile_threshold():
    """5종목 강세 + 5종목 약세 universe — 상위 25% 만 후보."""
    universe = {}
    # 5 winners: +1%/일
    for i in range(5):
        universe[f"WIN{i}"] = _trend_df(100, 0.01)
    # 5 losers: -1%/일
    for i in range(5):
        universe[f"LOS{i}"] = _trend_df(100, -0.01)

    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=15, entry_percentile=0.75)
    )
    candidates = strat.scan(ctx, top_n=10)

    # 상위 25% (10종목 중 ~2-3개) 만 진입
    assert 1 <= len(candidates) <= 4
    # 모두 winner 여야
    assert all(c.ticker.startswith("WIN") for c in candidates)


def test_score_is_percentile_rank_high_winners_first():
    """가장 강한 winner 가 가장 높은 score."""
    universe = {
        "FAST": _trend_df(100, 0.02),    # +2%/일 — 최고
        "MID": _trend_df(100, 0.01),     # +1%/일
        "SLOW": _trend_df(100, 0.005),   # +0.5%/일
        "FLAT": _trend_df(100, 0.0),     # 횡보
        "DOWN": _trend_df(100, -0.01),   # 하락
    }
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=10, entry_percentile=0.6)
    )
    candidates = strat.scan(ctx, top_n=5)

    assert len(candidates) >= 1
    # 첫 후보가 가장 높은 score
    assert candidates[0].ticker == "FAST"
    # score 내림차순
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_volume_filter_excludes_low_volume_tickers():
    """당일 거래량 < 20일 평균 종목은 후보에서 제외."""
    universe = {
        # 강한 상승이지만 마지막 봉 거래량 매우 낮음
        "WIN_LOW_VOL": _trend_df(100, 0.02, volume=1_000_000).copy(),
        "WIN_OK_VOL": _trend_df(100, 0.018, volume=1_000_000),
        "FLAT": _trend_df(100, 0.0),
        "DOWN": _trend_df(100, -0.01),
    }
    # WIN_LOW_VOL 의 마지막 봉 거래량을 평균보다 낮춤
    universe["WIN_LOW_VOL"] = universe["WIN_LOW_VOL"].copy()
    universe["WIN_LOW_VOL"].loc[universe["WIN_LOW_VOL"].index[-1], "volume"] = 100

    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=10, entry_percentile=0.5),
    )
    candidates = strat.scan(ctx, top_n=5)
    tickers = {c.ticker for c in candidates}

    assert "WIN_LOW_VOL" not in tickers, "거래량 필터에서 제외되어야"
    assert "WIN_OK_VOL" in tickers


def test_short_history_ticker_skipped():
    """lookback+1 봉 미만 ticker 는 스킵."""
    universe = {
        "FULL": _trend_df(100, 0.01, n=30),
        "SHORT": _trend_df(100, 0.01, n=10),  # lookback 15 미달
    }
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=15, entry_percentile=0.5),
    )
    candidates = strat.scan(ctx, top_n=5)
    assert all(c.ticker != "SHORT" for c in candidates)


def test_empty_universe_returns_empty():
    ctx = _make_ctx({})
    strat = StrategyTwoCrossSectionalMomentum()
    assert strat.scan(ctx, top_n=10) == []


def test_top_n_cut():
    universe = {f"T{i}": _trend_df(100, 0.01 + i * 0.001) for i in range(10)}
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=10, entry_percentile=0.0)  # 모두 통과
    )
    candidates = strat.scan(ctx, top_n=3)
    assert len(candidates) == 3


def test_strategy_name_constant():
    assert StrategyTwoCrossSectionalMomentum.name == "strategy_two_cross_sectional_momentum"


def test_pricing_invariants_hold():
    """모든 후보의 가격 순서 sl < entry < t1 < t2."""
    universe = {f"T{i}": _trend_df(100, 0.01 + i * 0.002) for i in range(8)}
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=10, entry_percentile=0.5)
    )
    candidates = strat.scan(ctx, top_n=10)
    for c in candidates:
        assert c.stop_loss < c.entry_price < c.target_1 <= c.target_2
        assert 0.0 <= c.score <= 1000.0
        assert "momentum_pct" in c.metadata


def test_metadata_records_momentum_value():
    universe = {f"T{i}": _trend_df(100, 0.01 + i * 0.002) for i in range(5)}
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=10, entry_percentile=0.0)
    )
    candidates = strat.scan(ctx, top_n=10)
    for c in candidates:
        mom = c.metadata["momentum_pct"]
        assert mom > 0  # 모두 상승 추세이므로


def test_metadata_uses_percentile_rank_not_rank():
    """metadata 키는 'percentile_rank' (top-level Candidate.rank 와 충돌 회피)."""
    universe = {f"T{i}": _trend_df(100, 0.01 + i * 0.002) for i in range(5)}
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=10, entry_percentile=0.0)
    )
    candidates = strat.scan(ctx, top_n=10)
    for c in candidates:
        assert "percentile_rank" in c.metadata
        assert "rank" not in c.metadata, "충돌 위험 키 'rank'는 metadata에 없어야"
        assert 0.0 <= c.metadata["percentile_rank"] <= 1.0


def test_invalid_lookback_raises():
    with pytest.raises(ValueError):
        StrategyTwoCrossSectionalMomentum(StrategyTwoConfig(lookback=0))
    with pytest.raises(ValueError):
        StrategyTwoCrossSectionalMomentum(StrategyTwoConfig(lookback=-5))


def test_registry_has_strategy_two():
    """strategies/__init__.py 에 등록되어 cli.py 에서 자동 노출."""
    from strategies import REGISTRY, available
    assert StrategyTwoCrossSectionalMomentum.name in REGISTRY
    assert StrategyTwoCrossSectionalMomentum.name in available()


# ============================================================================
# 추가 엣지 — 동률 momentum + 데이터 품질
# ============================================================================

def test_tied_momentum_resolves_deterministically():
    """동률 모멘텀 (정확히 같은 close 흐름) 도 결정론적으로 분리 rank 부여.

    np.argsort(np.argsort) 는 unique rank 를 할당하므로 동률은 stable sort 순서로
    나뉜다. 같은 입력 → 같은 출력 (재현성) 만 검증.
    """
    # 5종목 모두 정확히 동일 시계열 (동률 momentum)
    universe = {f"T{i}": _trend_df(100, 0.01) for i in range(5)}
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=10, entry_percentile=0.6),
    )
    cands1 = strat.scan(ctx, top_n=5)
    cands2 = strat.scan(ctx, top_n=5)
    # 결정론: 두 번 호출해도 동일 ticker 순서
    assert [c.ticker for c in cands1] == [c.ticker for c in cands2]
    # 모두 동률이지만 entry_percentile=0.6 통과 ticker 만 진입 (상위 40%)
    assert 1 <= len(cands1) <= 5


def test_zero_past_price_skipped():
    """과거 가격이 0 이하면 division-by-zero 회피로 스킵."""
    df_zero = _trend_df(100, 0.01)
    df_zero = df_zero.copy()
    df_zero.iloc[-16, df_zero.columns.get_loc("close")] = 0.0  # lookback 봉 close=0

    df_ok = _trend_df(100, 0.015)
    universe = {"ZERO": df_zero, "OK": df_ok}
    ctx = _make_ctx(universe)
    strat = StrategyTwoCrossSectionalMomentum(
        StrategyTwoConfig(lookback=15, entry_percentile=0.0),
    )
    cands = strat.scan(ctx, top_n=5)
    # 0 가격 ticker 는 후보에서 제외, 다른 ticker 는 통과
    assert all(c.ticker != "ZERO" for c in cands)


def test_invalid_entry_percentile_raises():
    with pytest.raises(ValueError):
        StrategyTwoCrossSectionalMomentum(StrategyTwoConfig(entry_percentile=1.5))
    with pytest.raises(ValueError):
        StrategyTwoCrossSectionalMomentum(StrategyTwoConfig(entry_percentile=-0.1))
