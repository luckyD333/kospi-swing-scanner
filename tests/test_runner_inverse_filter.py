"""추세 추종 전략의 인버스 ETF 제외 — core/runner.py::_drop_inverse_for_trend."""
import pandas as pd

from core.runner import _drop_inverse_for_trend
from core.strategy_base import Candidate


def _cand(ticker: str, name: str) -> Candidate:
    return Candidate(
        ticker=ticker,
        name=name,
        strategy="test",
        signal_date=pd.Timestamp("2026-09-16"),
        score=100.0,
        entry_price=1000.0,
        stop_loss=950.0,
        target_1=1050.0,
        target_2=1100.0,
    )


_CANDIDATES = [
    _cand("251340", "KODEX 코스닥150선물인버스"),
    _cand("123310", "TIGER 인버스"),
    _cand("462330", "KODEX 2차전지산업레버리지"),
    _cand("005930", "삼성전자"),
]


def test_전략사는_인버스를_제외한다():
    """지수와 반대로 움직이는 상품은 눌림목 매수 논리와 충돌한다."""
    kept = _drop_inverse_for_trend("strategy_four_pullback_ma", list(_CANDIDATES))
    assert [c.ticker for c in kept] == ["462330", "005930"]


def test_전략삼과_오도_인버스를_제외한다():
    """돌파와 깃발형도 같은 추세 추종 논리를 쓴다."""
    for name in ("strategy_three_trend_following", "strategy_five_bull_flag_30m"):
        kept = _drop_inverse_for_trend(name, list(_CANDIDATES))
        assert all("인버스" not in c.name for c in kept)
        assert len(kept) == 2


def test_레버리지는_유지한다():
    """레버리지는 기초 지수와 방향이 같아 제외 대상이 아니다."""
    kept = _drop_inverse_for_trend("strategy_four_pullback_ma", list(_CANDIDATES))
    assert any("레버리지" in c.name for c in kept)


def test_전략일과_이는_영향받지_않는다():
    """평균 회귀와 상대 모멘텀은 이번 제외 대상이 아니다."""
    for name in ("strategy_one_d_v2_r1", "strategy_two_cross_sectional_momentum"):
        kept = _drop_inverse_for_trend(name, list(_CANDIDATES))
        assert len(kept) == 4
