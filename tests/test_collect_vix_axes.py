"""collect 의 VIX → axes CRISIS 배선 헬퍼 검증."""
from unittest.mock import MagicMock, patch

import pandas as pd

from scripts.collect import _fetch_v_kospi, _vix_last_from_history


def test_정상_히스토리에서_마지막_close_반환():
    df = pd.DataFrame({"close": [18.0, 22.5, 35.1]},
                      index=pd.date_range("2026-06-08", periods=3, freq="D"))
    assert _vix_last_from_history(df) == 35.1


def test_None_또는_빈_히스토리는_None():
    assert _vix_last_from_history(None) is None
    assert _vix_last_from_history(pd.DataFrame()) is None


def test_close_컬럼_없으면_None():
    df = pd.DataFrame({"open": [20.0]})
    assert _vix_last_from_history(df) is None


@patch("requests.get")
def test_stockplus_vkospi_현재값과_90일_백분위(mock_get):
    dates = pd.date_range(end="2026-07-15", periods=100, freq="B")
    rows = [
        {
            "date": date.strftime("%Y-%m-%dT00:00:00.000+00:00"),
            "tradePrice": float(i),
            "changePriceRate": 0.021674 if date == dates[-1] else 0.0,
        }
        for i, date in enumerate(dates, start=1)
    ][::-1]
    response = MagicMock()
    response.json.return_value = {"dayCandles": rows}
    mock_get.return_value = response

    result = _fetch_v_kospi("20260715")

    assert result == {
        "value": 100.0,
        "change_pct": 2.17,
        "asof": "2026-07-15",
        "percentile_90d": 100.0,
        "status": "informational",
    }
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["params"] == {
        "limit": 100,
        "to": "2026-07-16",
    }


@patch("requests.get")
def test_stockplus_vkospi_이력이_짧으면_생략(mock_get):
    response = MagicMock()
    response.json.return_value = {
        "dayCandles": [{
            "date": "2026-07-15T00:00:00.000+00:00",
            "tradePrice": 35.2,
            "changePriceRate": 0.02,
        }]
    }
    mock_get.return_value = response

    assert _fetch_v_kospi("20260715") is None
