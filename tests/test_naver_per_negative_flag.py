"""test_naver_per_negative_flag.py — PER raw text 분기 검증 (PR-A Step 1).

네이버 PER 값이 적자 sentinel('—', '-', 음수)인지
단순 누락(NaN, 빈 문자열)인지 구분 가능해야 PR-A 의 결측 정책 분기가 작동.
"""
from __future__ import annotations

import pandas as pd

from core.data_sources.naver import _classify_per, _classify_per_raw


def test_em_dash_is_negative():
    """raw 가 '—' (em dash) → 적자 sentinel."""
    value, negative = _classify_per_raw("—")
    assert value is None
    assert negative is True


def test_hyphen_is_negative():
    """raw 가 '-' (hyphen) → 적자 sentinel."""
    value, negative = _classify_per_raw("-")
    assert value is None
    assert negative is True


def test_negative_string_is_negative():
    """음수 PER string → 적자."""
    value, negative = _classify_per_raw("-12.3")
    assert value is None
    assert negative is True


def test_negative_float_is_negative():
    """음수 PER float → 적자."""
    value, negative = _classify_per_raw(-5.0)
    assert value is None
    assert negative is True


def test_nan_is_data_missing():
    """raw 가 NaN → 단순 누락."""
    value, negative = _classify_per_raw(float("nan"))
    assert value is None
    assert negative is False


def test_none_is_data_missing():
    """raw 가 None → 단순 누락."""
    value, negative = _classify_per_raw(None)
    assert value is None
    assert negative is False


def test_empty_string_is_data_missing():
    """빈 문자열 → 단순 누락 (적자 아님)."""
    value, negative = _classify_per_raw("")
    assert value is None
    assert negative is False


def test_normal_positive_string():
    """정상 양수 string → value 보존."""
    value, negative = _classify_per_raw("10.5")
    assert value == 10.5
    assert negative is False


def test_normal_positive_float():
    """정상 양수 float → value 보존."""
    value, negative = _classify_per_raw(15.0)
    assert value == 15.0
    assert negative is False


def test_unparseable_string_is_data_missing():
    """파싱 불가 string → 단순 누락 (적자 아님)."""
    value, negative = _classify_per_raw("invalid")
    assert value is None
    assert negative is False


def test_pd_isna_handling():
    """pd.NA 도 NaN 과 동일 처리."""
    value, negative = _classify_per_raw(pd.NA)
    assert value is None
    assert negative is False


# ---------------------------------------------------------------------------
# _classify_per: JSON API 의 per/eps 조합 분기 (구형 페이지 폐쇄 대응)
# ---------------------------------------------------------------------------

def test_classify_per_null_with_negative_eps_is_negative():
    """per null + eps 음수 → 적자 (새 JSON API 의 적자 표현)."""
    assert _classify_per(None, "-7193.0") == (None, True)


def test_classify_per_null_without_eps_is_missing():
    """per null + eps 없음/양수 → 단순 누락."""
    assert _classify_per(None, None) == (None, False)
    assert _classify_per(None, "100.0") == (None, False)


def test_classify_per_positive_string():
    """정상 양수 문자열 → 값."""
    assert _classify_per("11.34", "22292.0") == (11.34, False)


def test_classify_per_negative_string_is_negative():
    """음수 PER 문자열 → 적자 (기존 규칙 유지)."""
    assert _classify_per("-3.2", "22292.0") == (None, True)
