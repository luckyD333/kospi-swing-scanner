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
    """VIX 가 시계열 최고치면 volatility score 는 0 근처 (fear)."""
    from core.decision.fear_greed import compute_components

    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    momentum = pd.Series(np.linspace(20, 80, 90), index=idx)
    breadth = pd.Series(np.full(90, 0.5), index=idx)
    vix = pd.Series(np.linspace(15, 35, 89).tolist() + [40.0], index=idx)  # 마지막이 최고

    comps = compute_components(momentum, breadth, vix, lookback=89)

    assert comps["momentum"] >= 95  # 시계열 최고 근처
    assert comps["volatility"] <= 5  # VIX 최고 → invert 후 0 근처


def test_compute_components_constant_breadth_returns_top():
    """breadth 가 동일값으로 평탄 → percentile rank 100 (≤ 비율 = 1.0)."""
    from core.decision.fear_greed import compute_components

    idx = pd.date_range("2026-01-01", periods=90, freq="B")
    momentum = pd.Series(np.full(90, 50.0), index=idx)
    breadth = pd.Series(np.full(90, 0.6), index=idx)
    vix = pd.Series(np.full(90, 20.0), index=idx)

    comps = compute_components(momentum, breadth, vix, lookback=89)
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
    vix = pd.Series(rng.uniform(12, 30, 120), index=idx)

    snap = compute_with_history(
        momentum, breadth, vix, lookback=90, history_window=30
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
    vix = pd.Series(np.linspace(30, 15, 100), index=idx)

    snap = compute_with_history(
        momentum, breadth, vix, lookback=60, history_window=10
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


def test_build_fear_greed_payload_with_fixtures(tmp_path):
    """regime_analysis.json + vix.parquet + 1D parquet → payload dict 생성."""
    import json as _json
    from core.decision.fear_greed import build_fear_greed_payload

    cache_root = tmp_path / ".cache"
    cache_root.mkdir()
    idx = pd.date_range("2026-01-01", periods=100, freq="B")

    # regime_analysis.json fixture
    history = [
        {"date": d.strftime("%Y-%m-%d"), "score": 50 + (i % 30)}
        for i, d in enumerate(idx)
    ]
    (cache_root / "regime_analysis.json").write_text(_json.dumps({"history": history}))

    # vix.parquet fixture
    macro_dir = cache_root / "macro"
    macro_dir.mkdir()
    pd.DataFrame(
        {"close": [15 + (i % 10) for i in range(100)]},
        index=idx,
    ).to_parquet(macro_dir / "vix.parquet")

    # 1D ticker parquet fixtures
    one_d_dir = cache_root / "1D"
    one_d_dir.mkdir()
    rng = np.random.default_rng(0)
    tickers = ["005930", "000660", "035420"]
    for t in tickers:
        closes = 50_000 + np.cumsum(rng.normal(0, 500, 100))
        pd.DataFrame(
            {"open": closes, "high": closes + 100, "low": closes - 100,
             "close": closes, "volume": [1_000] * 100},
            index=idx,
        ).to_parquet(one_d_dir / f"{t}.parquet")

    payload = build_fear_greed_payload(cache_root, tickers, history_window=20)

    assert payload is not None
    assert 0 <= payload["score"] <= 100
    assert payload["label"] in (
        "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    )
    assert set(payload["components"]) == {"momentum", "breadth", "volatility"}
    assert len(payload["history"]) == 20
    assert payload["score"] == payload["history"][-1]["score"]


def test_build_fear_greed_payload_missing_inputs_returns_none(tmp_path):
    """필수 입력 (regime/vix/breadth) 중 하나라도 부재 → None."""
    from core.decision.fear_greed import build_fear_greed_payload

    cache_root = tmp_path / ".cache"
    cache_root.mkdir()

    payload = build_fear_greed_payload(cache_root, ["005930"])
    assert payload is None
