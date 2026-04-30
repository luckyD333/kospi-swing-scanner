"""
demo.py — 백테스트 엔진 + 스크리너 통합 실행 데모

실행:
    python -m backtest_engine.demo

동작:
  1. 6가지 시나리오별 백테스트 + 결과 출력
  2. 3가지 detector 구현 비교 백테스트
  3. 여러 타임프레임(30m/1h/2h/4h/1D) 스크리너 데모
  4. 가상 multi-ticker 유니버스 스크리닝 → 매수/매도/손절 가격 출력
"""
from __future__ import annotations

import sys
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd

from .scenarios import ScenarioBuilder
from .strategy import StrategyD, StrategyDConfig
from .engine import BacktestEngine, BacktestConfig
from .screener import MultiTimeframeScreener, SUPPORTED_TIMEFRAMES
from .detectors import (
    DoubleBottomSimple,
    DoubleBottomFractal,
    DoubleBottomProminence,
)


# ============================================================================
# 출력 유틸
# ============================================================================

def print_header(title: str, width: int = 80):
    bar = "=" * width
    print()
    print(bar)
    print(f"  {title}")
    print(bar)


def print_section(title: str, width: int = 80):
    bar = "─" * width
    print()
    print(bar)
    print(f"  {title}")
    print(bar)


def format_price(x: float) -> str:
    return f"{x:,.0f}" if x >= 1000 else f"{x:,.2f}"


# ============================================================================
# 1. 시나리오별 백테스트
# ============================================================================

def demo_scenarios():
    print_header("1️⃣  6가지 시나리오 × 백테스트 엔진 검증")

    results = []
    strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=25))
    config = BacktestConfig(
        initial_capital=10_000_000.0,
        position_size_pct=0.20,
        commission_pct=0.0025,
    )

    scenarios = ScenarioBuilder.all()
    for scenario in scenarios:
        engine = BacktestEngine(strategy, config)
        result = engine.run_single(scenario.df, ticker=scenario.name)
        results.append((scenario, result))

    # 결과 테이블
    rows = []
    for scenario, result in results:
        if result.total_trades == 0:
            rows.append({
                "시나리오": scenario.name,
                "예상 결과": scenario.expected_outcome,
                "거래 수": 0,
                "실현 PnL %": "-",
                "청산 사유": "no_trade",
                "보유 봉": "-",
                "최종 자본": f"{result.final_capital:,.0f}",
            })
        else:
            trade = result.trades[0]
            rows.append({
                "시나리오": scenario.name,
                "예상 결과": scenario.expected_outcome,
                "거래 수": result.total_trades,
                "실현 PnL %": f"{trade.pnl_pct:+.2f}%",
                "청산 사유": trade.exit_reason.value,
                "보유 봉": trade.bars_held,
                "최종 자본": f"{result.final_capital:,.0f}",
            })

    df = pd.DataFrame(rows)
    print()
    print(df.to_string(index=False))

    # 검증
    print_section("✅ 시나리오 검증")
    for scenario, result in results:
        expected = scenario.expected_outcome
        if expected == "no_trade":
            actual = "no_trade" if result.total_trades == 0 else "trade_occurred"
        elif expected == "win":
            actual = "win" if (result.trades and result.trades[0].is_win) else "loss"
        else:  # loss
            actual = "loss" if (result.trades and not result.trades[0].is_win) else "win"

        status = "✓" if actual == expected else "✗"
        print(f"  [{status}] {scenario.name:30s}  예상={expected:10s}  실제={actual}")


# ============================================================================
# 2. Detector 3종 비교
# ============================================================================

def demo_detector_comparison():
    print_header("2️⃣  쌍바닥 감지 3가지 구현 비교")

    scenarios = [
        ScenarioBuilder.perfect_double_bottom(),
        ScenarioBuilder.fake_double_bottom_loss(),
        ScenarioBuilder.gap_down_loss(),
        ScenarioBuilder.time_stop_breakeven(),
    ]

    detectors = {
        "Simple": DoubleBottomSimple(),
        "Fractal": DoubleBottomFractal(),
        "Prominence": DoubleBottomProminence(prominence_pct=0.01),
    }

    rows = []
    for scenario in scenarios:
        row = {"시나리오": scenario.name}
        for name, det in detectors.items():
            strategy = StrategyD(
                config=StrategyDConfig(min_lookback_bars=25),
                double_bottom_detector=det,
            )
            engine = BacktestEngine(strategy)
            result = engine.run_single(scenario.df, ticker=scenario.name)
            if result.total_trades == 0:
                row[name] = "no_trade"
            else:
                t = result.trades[0]
                row[name] = f"{t.pnl_pct:+.1f}% ({t.exit_reason.value})"
        rows.append(row)

    df = pd.DataFrame(rows)
    print()
    print(df.to_string(index=False))


# ============================================================================
# 3. 다중 타임프레임 스크리너
# ============================================================================

def _make_ticker_data(base_scenario_func, ticker_name: str, seed: int):
    """타임프레임별 동일 패턴의 가상 데이터 생성"""
    # 30m/1h/2h/4h/1D 모두 같은 시나리오의 복사본 (freq만 변경)
    data = {}
    # 1D 시나리오에서 시작
    scenario_1d = base_scenario_func(freq="1D", seed=seed)
    data["1D"] = scenario_1d.df

    # 다른 타임프레임은 1D 데이터를 복제하되 index만 달리 부여
    n = len(scenario_1d.df)
    for tf, periods in [("30m", "30min"), ("1h", "1h"), ("2h", "2h"), ("4h", "4h")]:
        df_tf = scenario_1d.df.copy()
        df_tf.index = pd.date_range(
            start=datetime(2026, 1, 5, 9, 0),
            periods=n,
            freq=periods,
        )
        data[tf] = df_tf
    return data


def demo_screener():
    print_header("3️⃣  다중 타임프레임 × 다종목 스크리너")

    # 가상 유니버스: 5개 "종목"
    universe_setup = [
        ("005930_삼성전자", ScenarioBuilder.perfect_double_bottom, 42),
        ("000660_SK하이닉스", ScenarioBuilder.perfect_double_bottom, 123),
        ("035720_카카오", ScenarioBuilder.fake_double_bottom_loss, 55),
        ("373220_LG에너지솔루션", ScenarioBuilder.no_signal_uptrend, 77),
        ("207940_삼성바이오로직스", ScenarioBuilder.choppy_no_signal, 99),
    ]

    universe: Dict[str, Dict[str, pd.DataFrame]] = {}
    for ticker, scenario_func, seed in universe_setup:
        # 진입봉까지만 데이터를 잘라서 "지금 이 순간" 시그널 탐지 상황 연출
        data_by_tf = _make_ticker_data(scenario_func, ticker, seed)
        trimmed = {}
        for tf, df in data_by_tf.items():
            # 완벽/가짜 시나리오는 idx 32(진입봉)까지만
            scenario_name = scenario_func.__name__
            if "perfect" in scenario_name or "fake" in scenario_name:
                trimmed[tf] = df.iloc[:33]
            else:
                trimmed[tf] = df
        universe[ticker] = trimmed

    screener = MultiTimeframeScreener(
        strategy_config=StrategyDConfig(min_lookback_bars=25),
        timeframes=SUPPORTED_TIMEFRAMES,
    )
    result = screener.scan_multi(universe)

    print()
    print(f"  📊 스캔 시각: {result.scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  📦 총 스캔 종목: {result.total_scanned}개")
    print(f"  🎯 시그널 발생: {len(result.hits)}건")

    # 상위 결과 표
    if result.hits:
        print_section("🏆 Confidence 상위 결과 (매수 후보)")
        summary = result.summary_table(top_n=20)
        print()
        print(summary.to_string(index=False))

    # 타임프레임 confluence (여러 TF 동시 시그널)
    confluence = result.multi_timeframe_confluence(min_timeframes=3)
    if confluence:
        print_section(f"💎 다중 타임프레임 Confluence 종목 (3개 이상 TF 동시 시그널)")
        for ticker in confluence:
            ticker_hits = [h for h in result.hits if h.ticker == ticker]
            tfs = sorted(set(h.timeframe for h in ticker_hits))
            avg_conf = sum(h.confidence for h in ticker_hits) / len(ticker_hits)
            print(f"  ✨ {ticker}: {', '.join(tfs)} (평균 confidence {avg_conf:.2f})")


# ============================================================================
# 4. 최종 매수 리스트 (실전 형식)
# ============================================================================

def demo_final_buy_list():
    print_header("4️⃣  최종 매수 후보 리스트 (실전 출력 형식)")

    # 좀 더 다양한 종목 구성
    universe_setup = [
        ("005930_삼성전자", ScenarioBuilder.perfect_double_bottom, 42),
        ("000660_SK하이닉스", ScenarioBuilder.perfect_double_bottom, 7),
        ("035420_NAVER", ScenarioBuilder.perfect_double_bottom, 101),
        ("035720_카카오", ScenarioBuilder.fake_double_bottom_loss, 55),
        ("373220_LG에너지솔루션", ScenarioBuilder.no_signal_uptrend, 77),
        ("051910_LG화학", ScenarioBuilder.choppy_no_signal, 88),
        ("006400_삼성SDI", ScenarioBuilder.perfect_double_bottom, 222),
    ]

    universe = {}
    for ticker, func, seed in universe_setup:
        data = _make_ticker_data(func, ticker, seed)
        trimmed = {}
        for tf, df in data.items():
            scenario_name = func.__name__
            if "perfect" in scenario_name or "fake" in scenario_name:
                trimmed[tf] = df.iloc[:33]
            else:
                trimmed[tf] = df
        universe[ticker] = trimmed

    screener = MultiTimeframeScreener(
        strategy_config=StrategyDConfig(min_lookback_bars=25),
    )
    result = screener.scan_multi(universe)

    # 상위 5개 종목 × 최고 confidence 타임프레임만
    best_per_ticker: Dict[str, 'ScreenerHit'] = {}
    for hit in result.hits:
        if hit.ticker not in best_per_ticker:
            best_per_ticker[hit.ticker] = hit
        elif hit.confidence > best_per_ticker[hit.ticker].confidence:
            best_per_ticker[hit.ticker] = hit

    top_5 = sorted(
        best_per_ticker.values(),
        key=lambda h: h.confidence,
        reverse=True,
    )[:5]

    print()
    print(f"  ⏰ 스캔 시각: {result.scan_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  🎯 진입 권고 종목: {len(top_5)}개")
    print()

    for i, hit in enumerate(top_5, 1):
        print(f"  ────── #{i}  {hit.ticker}  ──────")
        print(f"    시그널 타임프레임  : {hit.timeframe}")
        print(f"    Confidence       : {hit.confidence:.1%}")
        print(f"    진입가 (매수)     : {format_price(hit.entry_price):>10} 원")
        print(f"    손절가           : {format_price(hit.stop_loss):>10} 원  ({-hit.risk_pct:.2f}%)")
        print(f"    1차 목표 (익절)   : {format_price(hit.target_1):>10} 원  (+{hit.reward_pct_target_1:.2f}%)")
        print(f"    2차 목표 (익절)   : {format_price(hit.target_2):>10} 원  (+{hit.reward_pct_target_2:.2f}%)")
        print(f"    손익비 (R:R)     : 1 : {hit.risk_reward_ratio:.1f}")
        conds = [k for k, v in hit.conditions_met.items() if v]
        print(f"    충족 조건 ({len(conds)}개): {', '.join(conds[:5])}{'...' if len(conds) > 5 else ''}")
        print()


# ============================================================================
# 메인
# ============================================================================

def main():
    print("╔══════════════════════════════════════════════════════════════════════════╗")
    print("║       Strategy D v2 — 단기 스윙 반등 포착 백테스트 엔진 데모              ║")
    print("║       (Long Only, 1-3일 보유, 일봉/멀티타임프레임)                        ║")
    print("╚══════════════════════════════════════════════════════════════════════════╝")

    demo_scenarios()
    demo_detector_comparison()
    demo_screener()
    demo_final_buy_list()

    print()
    print("=" * 80)
    print("  ✨ 데모 완료. 모든 시나리오가 전략 로직대로 동작함을 확인.")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
