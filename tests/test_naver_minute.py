"""
Task 6: NaverSource minute 분기 (mock 필수, 실제 네이버 호출 금지).

검증:
  - timeframe="1D" → params["timeframe"] == "day"
  - timeframe="1m" → params["timeframe"] == "minute"
  - 미지원 timeframe → NotImplementedError
  - minute 응답에서 OHLC=None 행은 dropna 됨
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.data_sources.naver import NaverSource


def _fake_response(text: str) -> MagicMock:
    fake = MagicMock()
    fake.text = text
    fake.raise_for_status = MagicMock()
    return fake


def test_get_ohlcv_minute_passes_minute_param():
    src = NaverSource()
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_fake_response("[]"),
    ) as gm:
        src.get_ohlcv("005930", "20260430", "20260430", timeframe="1m")
        params = gm.call_args.kwargs["params"]
        assert params["timeframe"] == "minute"


def test_get_ohlcv_day_default():
    src = NaverSource()
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_fake_response("[]"),
    ) as gm:
        src.get_ohlcv("005930", "20260101", "20260430")
        params = gm.call_args.kwargs["params"]
        assert params["timeframe"] == "day"


def test_get_ohlcv_unsupported_timeframe_raises():
    src = NaverSource()
    with pytest.raises(NotImplementedError, match="미지원"):
        src.get_ohlcv("005930", "20260430", "20260430", timeframe="30m")


def test_minute_response_dropna_no_trade_rows():
    """probe 결과처럼 첫 row 가 [ts, None, None, None, close, vol, None] 일 때 dropna."""
    src = NaverSource()
    body = """[
['날짜','시가','고가','저가','종가','거래량','외국인소진율'],
['202604301555', null, null, null, 220500, 3262, null],
['202604301600', 220000, 226000, 218500, 224500, 22870374, 49.25]
]"""
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_fake_response(body),
    ):
        df = src.get_ohlcv("005930", "20260430", "20260430", timeframe="1m")
    assert len(df) == 1   # None 행 제거 후 1 row
    assert df.index[0] == pd.Timestamp("2026-04-30 16:00")
    assert df["close"].iloc[0] == 224500.0


def test_response_preserves_foreign_rate_column():
    """siseJson 응답의 외국인소진율 → df["foreign_rate"]로 보존."""
    src = NaverSource()
    body = """[
['날짜','시가','고가','저가','종가','거래량','외국인소진율'],
['20260430', 220000, 226000, 218500, 224500, 22870374, 49.25]
]"""
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_fake_response(body),
    ):
        df = src.get_ohlcv("005930", "20260430", "20260430", timeframe="1D")
    assert "foreign_rate" in df.columns
    assert df["foreign_rate"].iloc[0] == 49.25


def test_minute_dropna_only_on_ohlc_keeps_foreign_rate():
    """foreign_rate=null이지만 OHLC가 채워진 행은 보존되어야 (dropna 기준은 OHLC만)."""
    src = NaverSource()
    body = """[
['날짜','시가','고가','저가','종가','거래량','외국인소진율'],
['202604301600', 220000, 226000, 218500, 224500, 22870374, null]
]"""
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_fake_response(body),
    ):
        df = src.get_ohlcv("005930", "20260430", "20260430", timeframe="1m")
    assert len(df) == 1
    assert pd.isna(df["foreign_rate"].iloc[0])
    assert df["close"].iloc[0] == 224500.0


def test_response_without_foreign_rate_column_handled():
    """외국인소진율 컬럼이 없는 응답도 정상 처리 (conditional 컬럼)."""
    src = NaverSource()
    body = """[
['날짜','시가','고가','저가','종가','거래량'],
['20260430', 220000, 226000, 218500, 224500, 22870374]
]"""
    with patch(
        "core.data_sources.naver.requests.get",
        return_value=_fake_response(body),
    ):
        df = src.get_ohlcv("005930", "20260430", "20260430", timeframe="1D")
    # 응답에 컬럼이 없으면 결과 df 에도 없음 (KeyError 없이 정상 종료)
    assert "foreign_rate" not in df.columns
    assert df["close"].iloc[0] == 224500.0
