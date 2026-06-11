"""collect 의 VIX → axes CRISIS 배선 헬퍼 검증."""
import pandas as pd

from scripts.collect import _vix_last_from_history


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
