"""strategy_two: 1D today row 가 미완료 봉이면 어제 종가로 entry 산출."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from core.cache.close_resolver import resolve_close_index

KST = ZoneInfo("Asia/Seoul")


def _df_two_days(today_close: float, yesterday_close: float, n_history: int = 60) -> pd.DataFrame:
    """ATR/RSI 계산을 위해 어제까지 n_history 일 + 어제 + 오늘 row 구성."""
    today = datetime.now(KST).date()
    dates = [today - timedelta(days=n_history + 1 - i) for i in range(n_history)]
    dates.append(today - timedelta(days=1))
    dates.append(today)
    closes = list(np.linspace(yesterday_close * 0.95, yesterday_close, n_history))
    closes.append(yesterday_close)
    closes.append(today_close)
    closes_arr = np.array(closes)
    return pd.DataFrame(
        {"open": closes_arr, "high": closes_arr * 1.01, "low": closes_arr * 0.99,
         "close": closes_arr, "volume": [1_000_000] * len(closes_arr)},
        index=pd.to_datetime(dates),
    )


def test_resolve_close_index_returns_minus_two_for_incomplete_today_bar():
    df = _df_two_days(today_close=30085.0, yesterday_close=30310.0)
    fetched = datetime.now(KST).replace(hour=11, minute=44).isoformat()
    assert resolve_close_index(df, fetched) == -2


def test_resolve_close_index_returns_minus_one_when_today_complete():
    df = _df_two_days(today_close=30085.0, yesterday_close=30310.0)
    fetched = datetime.now(KST).replace(hour=15, minute=35).isoformat()
    assert resolve_close_index(df, fetched) == -1


def test_resolve_close_index_returns_minus_one_when_last_row_is_past():
    """마지막 row 가 어제까지면 fetched 시각 무관 -1."""
    today = datetime.now(KST).date()
    n = 30
    dates = [today - timedelta(days=n - i) for i in range(n)]
    df = pd.DataFrame(
        {"close": np.linspace(10000, 12000, n)}, index=pd.to_datetime(dates),
    )
    fetched = datetime.now(KST).replace(hour=11, minute=44).isoformat()
    assert resolve_close_index(df, fetched) == -1


def test_resolve_close_index_returns_minus_one_when_history_too_short():
    """row 가 1개뿐이면 -2 fallback 불가 → -1."""
    today = datetime.now(KST).date()
    df = pd.DataFrame({"close": [10000.0]}, index=pd.to_datetime([today]))
    fetched = datetime.now(KST).replace(hour=11, minute=44).isoformat()
    assert resolve_close_index(df, fetched) == -1
