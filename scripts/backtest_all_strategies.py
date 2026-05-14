"""
scripts/backtest_all_strategies.py — 전략 5개 Walk-forward 백테스트

각 전략을 역사적 날짜별로 ScanContext 를 구성해 실행하고,
신호 발생 후 T+1~T+5 실현 PnL 을 계산한다.

사용:
    python scripts/backtest_all_strategies.py
    python scripts/backtest_all_strategies.py --top-n 30 --step 3
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.strategy_base import Candidate, ScanContext
from strategies import REGISTRY

CACHE_ROOT = Path(".cache")

CORE_STRATEGIES = [
    "strategy_one_d_v2",
    "strategy_two_cross_sectional_momentum",
    "strategy_three_trend_following",
    "strategy_four_pullback_ma",
    "strategy_five_bull_flag",
]


# ─── 데이터 로딩 ──────────────────────────────────────────────────────────────

def load_manifest() -> dict:
    path = CACHE_ROOT / "manifest.json"
    if not path.exists():
        sys.exit("[ERROR] .cache/manifest.json 없음. collect.py 먼저 실행하세요.")
    return json.loads(path.read_text())


def load_all_1d(tickers: list[str]) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        path = CACHE_ROOT / "1D" / f"{ticker}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df = df[["open", "high", "low", "close", "volume"]]
        if len(df) >= 30:
            data[ticker] = df
    return data


# ─── Walk-forward 날짜 추출 ───────────────────────────────────────────────────

def get_scan_dates(all_data: dict[str, pd.DataFrame], step: int) -> list[pd.Timestamp]:
    """공통 거래일 중 step 간격으로 샘플링. 마지막 5일은 forward return 계산용으로 제외."""
    all_dates: set[pd.Timestamp] = set()
    for df in all_data.values():
        all_dates.update(df.index.tolist())
    dates = sorted(all_dates)
    # 마지막 5거래일 제외 (forward return 계산 불가)
    if len(dates) <= 5:
        return []
    dates = dates[:-5]
    # 최소 30봉 lookback 보장
    return dates[30::step]


# ─── 신호 시뮬레이션 ──────────────────────────────────────────────────────────

@dataclass
class SignalRecord:
    strategy: str
    ticker: str
    signal_date: pd.Timestamp
    entry_price: float
    stop_loss: float
    target_1: float
    score: float
    # 실현 결과
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    bars_held: int = 0


def simulate_exit(
    ticker: str,
    full_df: pd.DataFrame,
    signal_date: pd.Timestamp,
    entry: float,
    stop: float,
    target: float,
    max_bars: int = 5,
) -> tuple[float, str, int]:
    """T 이후 max_bars 동안 stop/target 도달 여부를 체크해 exit_price, reason, bars 반환."""
    future = full_df[full_df.index > signal_date].head(max_bars)
    if future.empty:
        return entry, "no_data", 0

    for i, (_, bar) in enumerate(future.iterrows(), start=1):
        # 갭다운 체크 (시가가 stop 이하)
        if float(bar["open"]) <= stop:
            return stop, "gap_stop", i
        # 손절 도달
        if float(bar["low"]) <= stop:
            return stop, "stop_loss", i
        # 1차 목표 도달
        if float(bar["high"]) >= target:
            return target, "target_1", i

    # 시간 손절
    last_close = float(future.iloc[-1]["close"])
    return last_close, "time_stop", len(future)


def run_walk_forward(
    all_data: dict[str, pd.DataFrame],
    manifest: dict,
    step: int,
    top_n: int,
) -> list[SignalRecord]:
    tickers = list(all_data.keys())
    meta = manifest.get("tickers_meta", {})
    names = {t: t for t in tickers}  # 종목명 없으면 코드로 대체
    market_caps = {t: meta.get(t, {}).get("market_cap_bil", 0.0) or 0.0 for t in tickers}

    scan_dates = get_scan_dates(all_data, step)
    print(f"  스캔 날짜: {len(scan_dates)}개 (step={step}일)")
    print(f"  종목: {len(tickers)}개, 전략: {len(CORE_STRATEGIES)}개")

    strategies = {key: REGISTRY[key]() for key in CORE_STRATEGIES if key in REGISTRY}
    records: list[SignalRecord] = []

    for date_idx, scan_date in enumerate(scan_dates):
        # 각 ticker 의 데이터를 scan_date 까지만 슬라이싱
        sliced: dict[str, pd.DataFrame] = {
            ticker: df[df.index <= scan_date]
            for ticker, df in all_data.items()
            if len(df[df.index <= scan_date]) >= 30
        }
        if not sliced:
            continue

        ctx = ScanContext(
            target_date=scan_date.strftime("%Y%m%d"),
            universe=tuple(sliced.keys()),
            ohlcv=sliced,
            names=names,
            market_caps=market_caps,
            market="KOSPI",
        )

        for strat_key, strategy in strategies.items():
            try:
                candidates: list[Candidate] = strategy.scan(ctx, top_n=top_n)
            except Exception as e:
                continue

            for cand in candidates:
                if cand.ticker not in all_data:
                    continue
                exit_price, reason, bars = simulate_exit(
                    cand.ticker,
                    all_data[cand.ticker],
                    scan_date,
                    cand.entry_price,
                    cand.stop_loss,
                    cand.target_1,
                )
                pnl = (exit_price - cand.entry_price) / cand.entry_price * 100
                records.append(SignalRecord(
                    strategy=strat_key,
                    ticker=cand.ticker,
                    signal_date=scan_date,
                    entry_price=cand.entry_price,
                    stop_loss=cand.stop_loss,
                    target_1=cand.target_1,
                    score=cand.score,
                    exit_price=exit_price,
                    exit_reason=reason,
                    pnl_pct=pnl,
                    bars_held=bars,
                ))

        if (date_idx + 1) % 5 == 0:
            print(f"    진행: {date_idx + 1}/{len(scan_dates)} ({scan_date.date()})")

    return records


# ─── 결과 출력 ────────────────────────────────────────────────────────────────

def print_strategy_summary(records: list[SignalRecord]) -> None:
    print(f"\n{'='*75}")
    print("  전략별 요약")
    print(f"{'='*75}")
    print(f"  {'전략':<40} {'신호':>5} {'승률':>7} {'평균PnL':>8} {'중앙PnL':>8} {'승PnL':>8} {'패PnL':>8}")
    print(f"  {'-'*73}")

    for strat in CORE_STRATEGIES:
        recs = [r for r in records if r.strategy == strat]
        if not recs:
            print(f"  {strat:<40} {'0':>5} {'—':>7} {'—':>8} {'—':>8} {'—':>8} {'—':>8}")
            continue
        pnls = [r.pnl_pct for r in recs]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = len(wins) / len(pnls) * 100
        avg_pnl = sum(pnls) / len(pnls)
        med_pnl = sorted(pnls)[len(pnls) // 2]
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        short_name = strat.replace("strategy_", "s").replace("_cross_sectional_momentum", "_2_momentum")
        print(
            f"  {short_name:<40} {len(recs):>5} {win_rate:>6.1f}% "
            f"{avg_pnl:>+7.2f}% {med_pnl:>+7.2f}% {avg_win:>+7.2f}% {avg_loss:>+7.2f}%"
        )


def print_ticker_detail(records: list[SignalRecord], top_n: int = 15) -> None:
    if not records:
        return
    print(f"\n{'='*75}")
    print(f"  종목별 상위 {top_n}개 (PnL 내림차순)")
    print(f"{'='*75}")
    print(f"  {'종목':<10} {'전략':<10} {'날짜':<12} {'진입가':>8} {'손절가':>8} {'목표가':>8} {'PnL%':>7} {'청산사유'}")
    print(f"  {'-'*75}")

    sorted_recs = sorted(records, key=lambda r: r.pnl_pct, reverse=True)
    for r in sorted_recs[:top_n]:
        short_strat = r.strategy.replace("strategy_", "s").split("_")[0] + "_" + r.strategy.split("_")[1]
        print(
            f"  {r.ticker:<10} {short_strat:<10} {str(r.signal_date.date()):<12} "
            f"{r.entry_price:>8,.0f} {r.stop_loss:>8,.0f} {r.target_1:>8,.0f} "
            f"{r.pnl_pct:>+6.2f}%  {r.exit_reason}"
        )

    print(f"\n  ── 하위 {top_n}개 ──")
    print(f"  {'종목':<10} {'전략':<10} {'날짜':<12} {'진입가':>8} {'손절가':>8} {'목표가':>8} {'PnL%':>7} {'청산사유'}")
    print(f"  {'-'*75}")
    for r in sorted_recs[-top_n:]:
        short_strat = r.strategy.replace("strategy_", "s").split("_")[0] + "_" + r.strategy.split("_")[1]
        print(
            f"  {r.ticker:<10} {short_strat:<10} {str(r.signal_date.date()):<12} "
            f"{r.entry_price:>8,.0f} {r.stop_loss:>8,.0f} {r.target_1:>8,.0f} "
            f"{r.pnl_pct:>+6.2f}%  {r.exit_reason}"
        )


def print_exit_breakdown(records: list[SignalRecord]) -> None:
    print(f"\n{'='*75}")
    print("  전략별 청산 사유 분포")
    print(f"{'='*75}")
    for strat in CORE_STRATEGIES:
        recs = [r for r in records if r.strategy == strat]
        if not recs:
            continue
        reasons: dict[str, int] = {}
        for r in recs:
            reasons[r.exit_reason] = reasons.get(r.exit_reason, 0) + 1
        short = strat.replace("strategy_", "s")
        reason_str = "  ".join(f"{k}:{v}" for k, v in sorted(reasons.items()))
        print(f"  {short:<35}  {reason_str}")


# ─── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="전략 5개 Walk-forward 백테스트")
    parser.add_argument("--step", type=int, default=5, help="스캔 날짜 간격 (기본: 5일)")
    parser.add_argument("--top-n", type=int, default=20, help="전략당 top-N 신호 (기본: 20)")
    parser.add_argument("--detail-n", type=int, default=15, help="상세 출력 종목 수 (기본: 15)")
    args = parser.parse_args()

    print("KOSPI Swing Scanner — 전략 5개 Walk-forward 백테스트")
    print(f"cache: {CACHE_ROOT.resolve()}")

    manifest = load_manifest()
    tickers: list[str] = manifest.get("tickers", [])
    print(f"전체 종목: {len(tickers)}개")

    all_data = load_all_1d(tickers)
    print(f"1D 데이터 로드: {len(all_data)}개 종목")

    print("\n[Walk-forward 실행 중...]")
    records = run_walk_forward(all_data, manifest, step=args.step, top_n=args.top_n)
    print(f"\n총 신호 수: {len(records)}건")

    if not records:
        print("[결과] 신호 없음. --step 줄이거나 데이터 재수집 필요.")
        return

    print_strategy_summary(records)
    print_exit_breakdown(records)
    print_ticker_detail(records, top_n=args.detail_n)

    print(f"\n{'='*75}")
    print("  완료.")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    main()
