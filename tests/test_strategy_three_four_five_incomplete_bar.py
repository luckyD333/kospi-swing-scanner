"""strategy_three/four/five: scan() 이 close_resolver helper 를 호출하고
incomplete-bar 가드 path 가 작동하는지 검증.

가드의 출력 (entry_price 변동) 은 strategy 별 entry gate 다양성 때문에
fixture 로 끼우기 어렵다. 본 테스트는 helper 호출 + df slice 동작 검증.
helper 자체의 단위 검증은 tests/test_incomplete_bar_guard.py 가 담당.
"""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from core.strategy_base import ScanContext

KST = ZoneInfo("Asia/Seoul")


def _build_uptrend_df(n: int = 80) -> pd.DataFrame:
    today = datetime.now(KST).date()
    dates = [today - timedelta(days=n - 1 - i) for i in range(n)]
    closes_arr = np.linspace(800.0, 1000.0, n)
    return pd.DataFrame(
        {"open": closes_arr, "high": closes_arr * 1.005, "low": closes_arr * 0.995,
         "close": closes_arr, "volume": [1_000_000] * n},
        index=pd.to_datetime(dates),
    )


def _make_ctx(ticker: str, df: pd.DataFrame, fetched_at: str | None) -> ScanContext:
    meta = {"manifest_collected_at": fetched_at} if fetched_at else {}
    return ScanContext(
        target_date=datetime.now(KST).strftime("%Y%m%d"),
        universe=(ticker,),
        ohlcv={ticker: df},
        names={ticker: f"name_{ticker}"},
        market_caps={ticker: 5_000 * 1e8},
        market="KOSPI",
        meta=meta,
    )


def _assert_helper_called_with_fetched(strategy_module, ctx, fetched_expected: str):
    """strategy module 의 resolve_close_index 가 fetched_expected 인자로 호출됐는지 검증."""
    with patch.object(strategy_module, "resolve_close_index", wraps=strategy_module.resolve_close_index) as spy:
        strat_cls = next(
            v for k, v in vars(strategy_module).items()
            if k.startswith("Strategy") and isinstance(v, type) and hasattr(v, "scan")
        )
        strat = strat_cls(timeframe="1D")
        strat.scan(ctx, top_n=10)
    assert spy.called, f"{strategy_module.__name__}.scan() 이 resolve_close_index 를 호출하지 않음"
    # 첫 호출의 두 번째 positional 또는 kwarg 가 fetched_expected
    call_args = spy.call_args_list[0]
    fetched_arg = call_args.args[1] if len(call_args.args) >= 2 else call_args.kwargs.get("fetched_at_iso")
    assert fetched_arg == fetched_expected, \
        f"resolve_close_index 가 manifest_collected_at 을 받지 않음: got {fetched_arg!r}"


def test_strategy_three_calls_close_resolver():
    from strategies import strategy_three_trend_following as mod
    df = _build_uptrend_df()
    fetched = datetime.now(KST).replace(hour=11, minute=44).isoformat()
    ctx = _make_ctx("TST3", df, fetched)
    _assert_helper_called_with_fetched(mod, ctx, fetched)


def test_strategy_four_calls_close_resolver():
    from strategies import strategy_four_pullback_ma as mod
    df = _build_uptrend_df()
    fetched = datetime.now(KST).replace(hour=11, minute=44).isoformat()
    ctx = _make_ctx("TST4", df, fetched)
    _assert_helper_called_with_fetched(mod, ctx, fetched)


def test_strategy_five_calls_close_resolver():
    from strategies import strategy_five_bull_flag as mod
    df = _build_uptrend_df()
    fetched = datetime.now(KST).replace(hour=11, minute=44).isoformat()
    ctx = _make_ctx("TST5", df, fetched)
    _assert_helper_called_with_fetched(mod, ctx, fetched)


def test_strategy_three_handles_no_meta_legacy():
    """ctx.meta 가 비어 있어도 scan() 이 예외 없이 진행 (legacy 호환)."""
    from strategies.strategy_three_trend_following import StrategyThreeTrendFollowing
    df = _build_uptrend_df()
    ctx = _make_ctx("TST3L", df, fetched_at=None)
    strat = StrategyThreeTrendFollowing(timeframe="1D")
    # 예외 없이 동작해야 함 (가드 비활성)
    strat.scan(ctx, top_n=10)
