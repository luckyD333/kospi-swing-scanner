"""tests/test_signals_builder_market_dispatch.py — 시장별 ranking 분기 단위 테스트.

검증:
  - _market_config(market) → MarketRankingConfig 정확성 (KOSPI vs KOSDAQ)
  - market=None/unknown → DEFAULT_MARKET("KOSPI") fallback
  - 시장별 RegretWeights 합 = 1.0
  - 시장별 composite weights 합 = 1.0
  - 시장별 factor_label_weights 합 = 100
  - _base_strategy() prefix 매핑
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from output.signals_builder import (
    DEFAULT_MARKET,
    MarketRankingConfig,
    REGRET_FACTOR_LABELS,
    _base_strategy,
    _market_config,
)


def test_default_market_is_kospi():
    """기본 시장은 KOSPI (사용자 명시 요청)."""
    assert DEFAULT_MARKET == "KOSPI"


def test_market_config_kospi_returns_rank2_values():
    """KOSPI Rank 2 (OOS PF 4.62, DSR 7.75) 값 확인."""
    cfg = _market_config("KOSPI")
    assert isinstance(cfg, MarketRankingConfig)
    assert cfg.regret_weights.bull_reward == 0.22
    assert cfg.regret_weights.max_drawdown == 0.13
    assert cfg.regret_weights.dist_to_stop == 0.32
    assert cfg.regret_weights.signal_freshness == 0.33
    assert cfg.composite_weights == (0.24, 0.61, 0.15)
    assert cfg.confluence_penalty == 1.0
    assert cfg.strategy_score_weights == {
        "strategy_one":   0.88, "strategy_two":   0.46,
        "strategy_three": 1.03, "strategy_four":  0.56,
        "strategy_five":  0.30,
    }


def test_market_config_kosdaq_returns_rank1_values():
    """KOSDAQ Rank 1 (OOS PF 3.50, DSR 4.64, fresh OOS) 값 확인."""
    cfg = _market_config("KOSDAQ")
    assert cfg.regret_weights.bull_reward == 0.04
    assert cfg.regret_weights.max_drawdown == 0.61
    assert cfg.regret_weights.dist_to_stop == 0.31
    assert cfg.regret_weights.signal_freshness == 0.04
    assert cfg.composite_weights == (0.20, 0.23, 0.57)
    assert cfg.strategy_score_weights["strategy_three"] == 1.36   # S3 강조
    assert cfg.strategy_score_weights["strategy_two"] == 0.18     # S2 약화


def test_market_config_none_falls_back_to_default_kospi():
    """market=None → DEFAULT_MARKET=KOSPI fallback."""
    cfg_none = _market_config(None)
    cfg_kospi = _market_config("KOSPI")
    assert cfg_none == cfg_kospi


def test_market_config_unknown_falls_back_to_default():
    """unknown market 도 KOSPI fallback (예외 미발생)."""
    cfg_unknown = _market_config("ETF")
    assert cfg_unknown.regret_weights.bull_reward == 0.22  # KOSPI


def test_market_config_case_insensitive():
    """소문자 입력도 정상 처리."""
    cfg_lower = _market_config("kospi")
    cfg_upper = _market_config("KOSPI")
    assert cfg_lower == cfg_upper


def test_regret_weights_sum_to_one_for_each_market():
    """모든 시장의 RegretWeights 합 = 1.0."""
    for market in ("KOSPI", "KOSDAQ"):
        cfg = _market_config(market)
        w = cfg.regret_weights
        total = w.bull_reward + w.max_drawdown + w.dist_to_stop + w.signal_freshness
        assert abs(total - 1.0) < 0.001, f"{market}: sum={total}"


def test_composite_weights_sum_to_one_for_each_market():
    """모든 시장의 composite_weights 합 = 1.0."""
    for market in ("KOSPI", "KOSDAQ"):
        cfg = _market_config(market)
        opp, pot, sig = cfg.composite_weights
        total = opp + pot + sig
        assert abs(total - 1.0) < 0.001, f"{market}: sum={total}"


def test_factor_label_weights_sum_to_100_for_each_market():
    """모든 시장의 factor_label_weights 합 = 100 (× 100 scale)."""
    for market in ("KOSPI", "KOSDAQ"):
        cfg = _market_config(market)
        total = sum(cfg.factor_label_weights.values())
        assert abs(total - 100.0) < 0.1, f"{market}: sum={total}"


def test_base_strategy_prefix_mapping():
    """strategy id prefix → base name 매핑."""
    assert _base_strategy("strategy_one_d_v2") == "strategy_one"
    assert _base_strategy("strategy_one_1h_v2_r2") == "strategy_one"
    assert _base_strategy("strategy_two_cross_sectional_momentum") == "strategy_two"
    assert _base_strategy("strategy_two_30m") == "strategy_two"
    assert _base_strategy("strategy_three_trend_following") == "strategy_three"
    assert _base_strategy("strategy_four_pullback_ma_1h") == "strategy_four"
    assert _base_strategy("strategy_five_bull_flag_30m") == "strategy_five"
    # unknown → 그대로 반환
    assert _base_strategy("strategy_unknown") == "strategy_unknown"


def test_regret_factor_labels_simplified_to_str_only():
    """REGRET_FACTOR_LABELS 는 dict[str, str] (label only, weight 제거)."""
    assert all(isinstance(v, str) for v in REGRET_FACTOR_LABELS.values())
    assert set(REGRET_FACTOR_LABELS) == {
        "bull_reward", "max_drawdown", "dist_to_stop", "signal_freshness",
    }


def test_kospi_vs_kosdaq_strategy_weights_differ():
    """KOSPI vs KOSDAQ 의 strategy weights 가 서로 다름 (분기 의미 보장)."""
    kospi = _market_config("KOSPI").strategy_score_weights
    kosdaq = _market_config("KOSDAQ").strategy_score_weights
    # S3 weight 다름 (KOSPI 1.03 vs KOSDAQ 1.36)
    assert kospi["strategy_three"] != kosdaq["strategy_three"]
    # S2 weight 다름
    assert kospi["strategy_two"] != kosdaq["strategy_two"]
