"""runner 후처리에서 MAX 가드가 후보를 제외/페널티하는지 검증."""
import pandas as pd

from core.decision.max_filter import MaxFilterConfig
from core.strategy_base import Candidate


def _surge_df(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-06-01", periods=len(closes), freq="D")
    return pd.DataFrame({
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1_000_000] * len(closes),
    }, index=idx)


def test_apply_max_guard_가_EXCLUDE_후보를_제거한다():
    from core.runner import _apply_max_guard

    cand = Candidate(
        ticker="000001", name="급등주", strategy="strategy_three_trend_following",
        signal_date=pd.Timestamp("2026-06-07"), score=500.0,
        entry_price=126.0, stop_loss=120.0, target_1=130.0, target_2=135.0,
    )
    df = _surge_df([100, 100, 100, 100, 109, 118, 126])  # 3일 +26%
    keep = _apply_max_guard(cand, df, MaxFilterConfig())
    assert keep is False
    assert cand.metadata["max_guard"] == "EXCLUDE"


def test_apply_max_guard_가_PENALTY_시_score_절반():
    from core.runner import _apply_max_guard

    cand = Candidate(
        ticker="000002", name="준급등주", strategy="strategy_four_pullback_ma",
        signal_date=pd.Timestamp("2026-06-07"), score=500.0,
        entry_price=120.0, stop_loss=115.0, target_1=124.0, target_2=128.0,
    )
    df = _surge_df([100, 100, 100, 100, 106, 112, 120])  # 3일 +20%
    keep = _apply_max_guard(cand, df, MaxFilterConfig())
    assert keep is True
    assert cand.score == 250.0
    assert cand.metadata["max_guard"] == "PENALTY"


def test_apply_max_guard_가_데이터_없으면_SKIPPED_로_통과():
    from core.runner import _apply_max_guard

    cand = Candidate(
        ticker="000003", name="데이터부족", strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-06-07"), score=500.0,
        entry_price=100.0, stop_loss=95.0, target_1=105.0, target_2=110.0,
    )
    keep = _apply_max_guard(cand, None, MaxFilterConfig())
    assert keep is True
    assert cand.score == 500.0
    assert cand.metadata["max_guard"] == "SKIPPED"
