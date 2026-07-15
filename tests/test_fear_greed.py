"""core/decision/fear_greed.py — Fear & Greed 컴포지트 단위 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def test_percentile_rank_uniform_distribution():
    from core.decision.fear_greed import percentile_rank

    history = np.arange(100, dtype=float)  # 0..99
    assert percentile_rank(history, target=50.0) == pytest.approx(51.0)
    assert percentile_rank(history, target=100.0) == 100.0
    assert percentile_rank(history, target=-1.0) == 0.0


def test_percentile_rank_empty_history_returns_neutral():
    from core.decision.fear_greed import percentile_rank

    assert percentile_rank([], target=10.0) == 50.0


def test_score_to_label_boundaries():
    from core.decision.fear_greed import score_to_label

    assert score_to_label(0) == "Extreme Fear"
    assert score_to_label(24.99) == "Extreme Fear"
    assert score_to_label(25) == "Fear"
    assert score_to_label(44.99) == "Fear"
    assert score_to_label(45) == "Neutral"
    assert score_to_label(55) == "Neutral"
    assert score_to_label(55.01) == "Greed"
    assert score_to_label(74) == "Greed"
    assert score_to_label(74.99) == "Greed"
    assert score_to_label(75) == "Extreme Greed"
    assert score_to_label(100) == "Extreme Greed"


def test_compute_components_volatility_inverted():
    """변동성이 시계열 최고치면 volatility score 는 0 근처 (fear)."""
    from core.decision.fear_greed import compute_components

    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    momentum = pd.Series(np.linspace(20, 80, 90), index=idx)
    breadth = pd.Series(np.full(90, 0.5), index=idx)
    volatility = pd.Series(
        np.linspace(0.01, 0.03, 89).tolist() + [0.04], index=idx
    )

    comps = compute_components(momentum, breadth, volatility, lookback=89)

    assert comps["momentum"] >= 95  # 시계열 최고 근처
    assert comps["volatility"] <= 5


def test_compute_components_constant_breadth_returns_top():
    """breadth 가 동일값으로 평탄 → percentile rank 100 (≤ 비율 = 1.0)."""
    from core.decision.fear_greed import compute_components

    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    momentum = pd.Series(np.full(90, 50.0), index=idx)
    breadth = pd.Series(np.full(90, 0.6), index=idx)
    volatility = pd.Series(np.full(90, 0.02), index=idx)

    comps = compute_components(momentum, breadth, volatility, lookback=89)
    assert comps["momentum"] == 100.0
    assert comps["breadth"] == 100.0
    assert comps["volatility"] == 0.0  # invert


def test_compute_with_history_returns_window_size():
    """history_window=30 → history 리스트 길이 30."""
    from core.decision.fear_greed import compute_with_history

    idx = pd.date_range("2026-01-01", periods=120, freq="B")
    rng = np.random.default_rng(42)
    momentum = pd.Series(rng.uniform(0, 100, 120), index=idx)
    breadth = pd.Series(rng.uniform(0.3, 0.7, 120), index=idx)
    volatility = pd.Series(rng.uniform(0.01, 0.03, 120), index=idx)

    snap = compute_with_history(
        momentum, breadth, volatility, lookback=90, history_window=30
    )

    assert len(snap.history) == 30
    assert all("date" in h and "score" in h for h in snap.history)
    assert snap.history[0]["date"] < snap.history[-1]["date"]
    assert 0 <= snap.score <= 100
    assert snap.label in (
        "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    )


def test_compute_with_history_score_matches_last_history_point():
    """snapshot.score == history[-1].score (current = sparkline 끝점)."""
    from core.decision.fear_greed import compute_with_history

    idx = pd.date_range("2026-01-01", periods=100, freq="B")
    momentum = pd.Series(np.linspace(20, 80, 100), index=idx)
    breadth = pd.Series(np.linspace(0.4, 0.6, 100), index=idx)
    volatility = pd.Series(np.linspace(0.03, 0.015, 100), index=idx)

    snap = compute_with_history(
        momentum, breadth, volatility, lookback=60, history_window=10
    )
    assert snap.score == snap.history[-1]["score"]


def test_compute_with_history_empty_input_returns_neutral():
    """빈 시계열 → score=50, Neutral, history=[]."""
    from core.decision.fear_greed import compute_with_history

    empty = pd.Series([], dtype=float, index=pd.DatetimeIndex([]))
    snap = compute_with_history(empty, empty, empty)

    assert snap.score == 50.0
    assert snap.label == "Neutral"
    assert snap.history == []


def test_composite_equal_weight():
    """3 component 동일가중 평균."""
    from core.decision.fear_greed import composite

    assert composite({"momentum": 60, "breadth": 30, "volatility": 90}) == 60.0
    assert composite({"momentum": 0, "breadth": 0, "volatility": 0}) == 0.0
    assert composite({"momentum": 100, "breadth": 100, "volatility": 100}) == 100.0


def test_load_universe_closes_and_breadth_golden(tmp_path):
    """1D close 로딩과 breadth 계산이 손계산 golden 값과 일치한다."""
    from core.decision.fear_greed import (
        _compute_breadth_from_closes,
        _load_universe_closes,
    )

    cache_root = tmp_path
    (cache_root / "1D").mkdir()
    idx = pd.date_range("2026-01-01", periods=25, freq="D")
    pd.DataFrame({"close": np.linspace(100, 148, 25)}, index=idx).to_parquet(
        cache_root / "1D" / "AAA.parquet"
    )
    pd.DataFrame({"close": np.linspace(200, 152, 25)}, index=idx).to_parquet(
        cache_root / "1D" / "BBB.parquet"
    )

    close_df = _load_universe_closes(cache_root, ["AAA", "BBB"])

    assert list(close_df.columns) == ["AAA", "BBB"]
    assert len(close_df) == 25
    breadth = _compute_breadth_from_closes(close_df)
    assert len(breadth) == 6  # MA20 이 유효해진 시점부터 계산
    assert breadth.iloc[0] == 0.5
    assert breadth.iloc[-1] == 0.5


def test_breadth_ignores_missing_constituent_instead_of_counting_zero_return():
    """당일 값이 없는 종목은 보합/하락으로 간주하지 않고 분모에서 제외한다."""
    from core.decision.fear_greed import _compute_breadth_from_closes

    idx = pd.date_range("2026-01-01", periods=21, freq="D")
    closes = pd.DataFrame(
        {
            **{f"active_{i}": np.linspace(100, 120, 21) for i in range(9)},
            "missing": [100.0] * 20 + [np.nan],
        },
        index=idx,
    )

    breadth = _compute_breadth_from_closes(closes)

    assert breadth.iloc[-1] == 1.0


def test_build_fear_greed_payload_no_vix_needed(tmp_path):
    """regime/breadth와 shared market volatility로 payload를 생성한다."""
    import json as _json
    from core.decision.fear_greed import build_fear_greed_payload

    cache_root = tmp_path
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    rng = np.random.default_rng(1)
    tickers = [f"stock_{i}" for i in range(10)]

    history = [
        {"date": d.strftime("%Y-%m-%d"), "score": float(score)}
        for d, score in zip(idx, rng.uniform(20, 80, 60))
    ]
    (cache_root / "regime_analysis.json").write_text(_json.dumps({"history": history}))

    one_d_dir = cache_root / "1D"
    one_d_dir.mkdir()
    for ticker in tickers:
        prices = 1000 * (1 + rng.normal(0, 0.012, 60)).cumprod()
        pd.DataFrame({"close": prices}, index=idx).to_parquet(
            one_d_dir / f"{ticker}.parquet"
        )

    volatility = pd.Series(rng.uniform(0.01, 0.03, 60), index=idx)
    payload = build_fear_greed_payload(
        cache_root,
        tickers,
        volatility_series=volatility,
        lookback=30,
        history_window=10,
    )

    assert payload is not None
    assert 0 <= payload["score"] <= 100
    assert set(payload["components"]) == {"momentum", "breadth", "volatility"}
    assert payload["status"] == "informational"


def test_build_fear_greed_payload_waits_for_full_lookback(tmp_path):
    """공통 이력이 lookback+1보다 짧으면 불완전 percentile을 표시하지 않는다."""
    import json as _json
    from core.decision.fear_greed import build_fear_greed_payload

    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    (tmp_path / "regime_analysis.json").write_text(_json.dumps({
        "history": [
            {"date": date.strftime("%Y-%m-%d"), "score": 50.0}
            for date in idx
        ]
    }))
    one_d_dir = tmp_path / "1D"
    one_d_dir.mkdir()
    tickers = [f"stock_{i}" for i in range(10)]
    for ticker in tickers:
        pd.DataFrame({"close": np.linspace(100, 130, 30)}, index=idx).to_parquet(
            one_d_dir / f"{ticker}.parquet"
        )

    payload = build_fear_greed_payload(
        tmp_path,
        tickers,
        volatility_series=pd.Series(np.linspace(0.01, 0.02, 30), index=idx),
        lookback=30,
    )

    assert payload is None


def test_build_fear_greed_payload_requires_ten_loaded_stocks(tmp_path):
    """breadth 구성 종목이 10개 미만이면 대표성이 부족해 표시하지 않는다."""
    import json as _json
    from core.decision.fear_greed import build_fear_greed_payload

    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    (tmp_path / "regime_analysis.json").write_text(_json.dumps({
        "history": [
            {"date": date.strftime("%Y-%m-%d"), "score": 50.0}
            for date in idx
        ]
    }))
    tickers = [f"stock_{i}" for i in range(9)]
    one_d_dir = tmp_path / "1D"
    one_d_dir.mkdir()
    for ticker in tickers:
        pd.DataFrame({"close": np.linspace(100, 130, 60)}, index=idx).to_parquet(
            one_d_dir / f"{ticker}.parquet"
        )

    payload = build_fear_greed_payload(
        tmp_path,
        tickers,
        volatility_series=pd.Series(np.linspace(0.01, 0.02, 60), index=idx),
        lookback=30,
    )

    assert payload is None


def test_build_fear_greed_payload_crash_moves_toward_fear(tmp_path):
    """마지막 3일 폭락은 volatility 와 composite score 를 Fear 방향으로 낮춘다."""
    import json as _json
    from core.decision.fear_greed import build_fear_greed_payload

    cache_root = tmp_path
    idx = pd.date_range("2026-01-01", periods=60, freq="D")
    rng = np.random.default_rng(7)
    tickers = [f"stock_{i}" for i in range(10)]

    one_d_dir = cache_root / "1D"
    one_d_dir.mkdir()
    for ticker in tickers:
        calm = 1000 * (1 + rng.normal(0.0005, 0.004, 57)).cumprod()
        crash = calm[-1] * np.array([0.95, 0.88, 0.82])
        pd.DataFrame({"close": np.concatenate([calm, crash])}, index=idx).to_parquet(
            one_d_dir / f"{ticker}.parquet"
        )

    history = [{"date": d.strftime("%Y-%m-%d"), "score": 50.0} for d in idx]
    (cache_root / "regime_analysis.json").write_text(_json.dumps({"history": history}))

    payload = build_fear_greed_payload(
        cache_root,
        tickers,
        volatility_series=pd.Series(
            np.concatenate([np.full(57, 0.01), [0.02, 0.04, 0.08]]),
            index=idx,
        ),
        lookback=30,
        history_window=10,
    )

    assert payload is not None
    assert payload["history"][-1]["score"] < payload["history"][-4]["score"] - 5.0
    assert payload["components"]["volatility"] < 50.0


def test_build_fear_greed_payload_missing_inputs_returns_none(tmp_path):
    """필수 입력 (regime/1D close) 중 하나라도 부재 → None."""
    from core.decision.fear_greed import build_fear_greed_payload

    cache_root = tmp_path / ".cache"
    cache_root.mkdir()

    payload = build_fear_greed_payload(
        cache_root,
        ["005930"],
        volatility_series=pd.Series(dtype=float),
    )
    assert payload is None
