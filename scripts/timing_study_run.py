#!/usr/bin/env python3
"""전략별 최적 진입/청산 타이밍 백테스트 실행기."""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

from backtest_engine.historical_signals import HistoricalSignalGenerator
from backtest_engine.timing_study import (
    MetricsAggregator,
    ReportFormatter,
    TimingStudyConfig,
    TimingStudyEngine,
)

CACHE_DIR = pathlib.Path(".cache/1D")
STRATEGIES = [
    "strategy_one",
    "strategy_two",
    "strategy_three",
    "strategy_four",
    "strategy_five",
]


def load_ohlcv(cache_dir: pathlib.Path, top_n: int) -> dict[str, pd.DataFrame]:
    """유동성 상위 N개 종목의 1D 캐시 로드 (파일명 순)."""
    files = sorted(cache_dir.glob("*.parquet"))
    result: dict[str, pd.DataFrame] = {}
    for f in files[:top_n]:
        try:
            df = pd.read_parquet(f)
            if len(df) >= 30:
                result[f.stem] = df
        except Exception as e:
            print(f"[skip] {f.stem}: {e}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="전략별 타이밍 백테스트")
    parser.add_argument("--top-n", type=int, default=500, help="분석 종목 수")
    parser.add_argument("--output", default="timing_study_report.md", help="리포트 저장 경로")
    parser.add_argument("--cache-dir", default=str(CACHE_DIR), help="1D 캐시 디렉토리")
    args = parser.parse_args()

    cache_dir = pathlib.Path(args.cache_dir)
    if not cache_dir.exists():
        print(f"[error] 캐시 디렉토리 없음: {cache_dir}")
        return

    print(f"캐시 로드 중 (상위 {args.top_n}개 종목)...")
    ohlcv_map = load_ohlcv(cache_dir, args.top_n)
    print(f"{len(ohlcv_map)}개 종목 로드 완료")

    config = TimingStudyConfig()
    gen = HistoricalSignalGenerator(min_lookback=config.min_lookback_bars)
    engine = TimingStudyEngine()
    all_trades = []

    for strategy_name in STRATEGIES:
        print(f"신호 추출 중: {strategy_name} ...", end=" ", flush=True)
        signals = gen.extract(strategy_name, ohlcv_map)
        print(f"{len(signals)}개 신호")
        trades = engine.compute_trades(signals, ohlcv_map, config)
        all_trades.extend(trades)

    if not all_trades:
        print("[error] 생성된 거래 없음 — 캐시 데이터를 확인하세요.")
        return

    print(f"\n총 {len(all_trades)}개 거래 집계 중...")
    agg = MetricsAggregator()
    summary = agg.aggregate(all_trades)

    report = ReportFormatter().format(summary, config)
    pathlib.Path(args.output).write_text(report, encoding="utf-8")
    print(f"리포트 저장: {args.output}")

    print("\n─── 최적 조합 미리보기 (rank_bucket=1, Top 5) ───")
    top5 = summary[summary["rank_bucket"] == 1].nlargest(5, "avg_return")[
        ["strategy", "entry_window", "hold_days", "avg_return", "win_rate", "sample_n"]
    ].copy()
    top5["entry_window"] = top5["entry_window"].apply(lambda x: x.value if hasattr(x, "value") else x)
    print(top5.to_string(index=False))


if __name__ == "__main__":
    main()
