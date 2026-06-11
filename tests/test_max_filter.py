"""MAX effect 가드 — 1~3일 누적 급등·극단 일간 수익률 종목 차단."""
import pandas as pd
import pytest

from core.decision.max_filter import MaxFilterConfig, evaluate_surge


def _df(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-06-01", periods=len(closes), freq="D")
    return pd.DataFrame({
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1_000_000] * len(closes),
    }, index=idx)


def test_3일_누적_25퍼센트_이상은_EXCLUDE():
    # 100 → 109 → 118 → 126 (3일 누적 +26%)
    v = evaluate_surge(_df([100, 100, 100, 100, 109, 118, 126]), MaxFilterConfig())
    assert v.action == "EXCLUDE"
    assert v.surge_3d_pct == pytest.approx(26.0, abs=0.1)


def test_3일_누적_18에서_25퍼센트는_PENALTY():
    v = evaluate_surge(_df([100, 100, 100, 100, 106, 112, 120]), MaxFilterConfig())
    assert v.action == "PENALTY"
    assert v.score_mult == pytest.approx(0.5)


def test_5일내_일간_20퍼센트_급등은_EXCLUDE():
    # 4일 전 하루 +21% 후 보합 — 누적 3일은 평탄하지만 MAX 일간이 극단
    v = evaluate_surge(_df([100, 100, 121, 121, 121, 121, 121]), MaxFilterConfig())
    assert v.action == "EXCLUDE"
    assert v.max_daily_5d_pct == pytest.approx(21.0, abs=0.1)


def test_평탄한_종목은_PASS():
    v = evaluate_surge(_df([100, 101, 100, 102, 101, 103, 102]), MaxFilterConfig())
    assert v.action == "PASS"
    assert v.score_mult == 1.0


def test_봉_4개_미만은_SKIPPED():
    v = evaluate_surge(_df([100, 101, 102]), MaxFilterConfig())
    assert v.action == "SKIPPED"
