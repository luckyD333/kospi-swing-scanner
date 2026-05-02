"""
scripts/backtest_run.py — 수집된 OHLCV 데이터로 백테스트 실행.

사용:
    python scripts/backtest_run.py --cache-root .cache --timeframes 1D 1W
    python scripts/backtest_run.py --no-file  # stdout만
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest_engine.core import BacktestResult
from backtest_engine.engine import BacktestConfig, BacktestEngine
from backtest_engine.strategy import StrategyD, StrategyDConfig
from core.cache.ohlcv_disk import OhlcvDiskCache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MIN_BARS_1D = 40
MIN_BARS_1W = 10


@dataclass
class BacktestRunConfig:
    cache_root: Path = field(default_factory=lambda: Path(".cache"))
    timeframes: list[str] = field(default_factory=lambda: ["1D"])
    output_dir: Path = field(default_factory=lambda: Path("results"))
    date: str | None = None
    initial_capital: float = 10_000_000.0
    top_n: int = 20
    no_file: bool = False


def load_manifest(cache_root: Path) -> dict[str, Any]:
    path = cache_root / "manifest.json"
    if not path.exists():
        sys.exit("[ERROR] 캐시 데이터를 찾을 수 없습니다. 먼저 collect.py를 실행하세요.")
    manifest = json.loads(path.read_text())
    if not isinstance(manifest.get("tickers"), list):
        sys.exit("[ERROR] 캐시 구조가 올바르지 않습니다 (tickers 필드). collect.py를 다시 실행하세요.")
    return manifest


def load_ohlcv_1d(disk: OhlcvDiskCache, tickers: list[str]) -> dict[str, pd.DataFrame]:
    data: dict[str, pd.DataFrame] = {}
    skipped = 0
    for ticker in tickers:
        df = disk.read(ticker, "1D")
        if df.empty or len(df) < MIN_BARS_1D:
            skipped += 1
            continue
        data[ticker] = df
    if skipped:
        logger.warning(f"{skipped}개 종목 제외 (데이터 부족 또는 손상)")
    if not data:
        sys.exit("[ERROR] 로드 가능한 데이터 없음. collect.py를 먼저 실행하세요.")
    logger.info(f"로드 완료: {len(data)}개 종목")
    return data


def prepare_data_for_tf(data_1d: dict[str, pd.DataFrame], tf: str) -> dict[str, pd.DataFrame]:
    if tf == "1D":
        return data_1d
    if tf == "1W":
        result: dict[str, pd.DataFrame] = {}
        for ticker, df in data_1d.items():
            df_w = df.resample("W").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }).dropna()
            if len(df_w) >= MIN_BARS_1W:
                result[ticker] = df_w
        return result
    raise ValueError(f"지원하지 않는 TF: {tf}")


def calc_sharpe(equity_curve: pd.Series) -> float:
    if len(equity_curve) < 2:
        return float("nan")
    daily_ret = equity_curve.pct_change().dropna()
    std = daily_ret.std()
    if std == 0:
        return float("nan")
    return float(daily_ret.mean() / std * (252 ** 0.5))


def build_metrics(result: BacktestResult, tf: str) -> dict[str, str | int | float]:
    sharpe = calc_sharpe(result.equity_curve)
    s = result.summary()
    sharpe_display: float | str = round(sharpe, 3) if not math.isnan(sharpe) else "N/A"
    return {
        "TF": tf,
        "Trades": s["total_trades"],
        "Win%": s["win_rate"],
        "Return%": s["total_return_pct"],
        "AvgPnL%": s["avg_pnl_pct"],
        "MDD%": s["max_drawdown_pct"],
        "Sharpe": sharpe_display,
        "PF": s["profit_factor"],
        "AvgBars": s["avg_bars_held"],
    }


def print_table(metrics_list: list[dict]) -> None:
    try:
        from tabulate import tabulate
        print(tabulate(metrics_list, headers="keys", tablefmt="rounded_outline"))
    except ImportError:
        header = list(metrics_list[0].keys()) if metrics_list else []
        print(" | ".join(str(h) for h in header))
        print("-" * 80)
        for m in metrics_list:
            print(" | ".join(str(v) for v in m.values()))


def save_csv(result: BacktestResult, output_dir: Path, date: str, tf: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "ticker": t.ticker,
            "entry_time": str(t.entry_time),
            "exit_time": str(t.exit_time),
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "shares": t.shares,
            "pnl_pct": round(t.pnl_pct, 4),
            "exit_reason": t.exit_reason.value,
            "bars_held": t.bars_held,
        }
        for t in result.trades
    ]
    path = output_dir / f"backtest_{date}_{tf}.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    logger.info(f"CSV 저장: {path}")


def save_markdown(
    metrics_list: list[dict],
    results: dict[str, BacktestResult],
    output_dir: Path,
    date: str,
    top_n: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# 백테스트 리포트 — {date}",
        "",
        "## 요약",
        f"- 초기 자본: {results[next(iter(results))].initial_capital:,.0f}원",
        f"- 타임프레임: {', '.join(results.keys())}",
        "",
        "## 타임프레임별 성과",
        "",
    ]

    # 성과 테이블 (Markdown)
    if metrics_list:
        headers = list(metrics_list[0].keys())
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for m in metrics_list:
            lines.append("| " + " | ".join(str(v) for v in m.values()) + " |")
    lines.append("")

    # TF별 거래 목록
    for tf, result in results.items():
        lines.append(f"## 거래 목록 — {tf} (손익 내림차순 상위 {top_n}개)")
        lines.append("")
        trades_sorted = sorted(result.trades, key=lambda t: t.pnl_pct, reverse=True)[:top_n]
        if trades_sorted:
            lines.append("| ticker | 진입일 | 청산일 | 손익% | 청산사유 |")
            lines.append("| --- | --- | --- | --- | --- |")
            for t in trades_sorted:
                lines.append(
                    f"| {t.ticker} | {str(t.entry_time)[:10]} | "
                    f"{str(t.exit_time)[:10]} | {t.pnl_pct:.2f}% | {t.exit_reason.value} |"
                )
        else:
            lines.append("_(거래 없음)_")
        lines.append("")

    lines.extend([
        "## 주의사항",
        "",
        "- 이 결과는 과거 데이터 백테스트이며 미래 수익을 보장하지 않습니다.",
        "- 수수료: 왕복 0.25% (거래세 + 슬리피지 미포함)",
        "- 시뮬레이션은 당일 종가 진입을 가정합니다.",
    ])

    path = output_dir / f"backtest_{date}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Markdown 저장: {path}")


def run_backtest(cfg: BacktestRunConfig) -> None:
    manifest = load_manifest(cfg.cache_root)
    date = cfg.date or manifest.get("target_date", "unknown")
    tickers: list[str] = manifest.get("tickers", [])

    logger.info(f"백테스트 시작: {manifest.get('market')} @ {date}, {len(tickers)}종목")

    disk = OhlcvDiskCache(cfg.cache_root)
    data_1d = load_ohlcv_1d(disk, tickers)

    strategy = StrategyD(config=StrategyDConfig())
    engine_cfg = BacktestConfig(initial_capital=cfg.initial_capital)

    results: dict[str, BacktestResult] = {}
    for tf in cfg.timeframes:
        logger.info(f"백테스트 실행: {tf}")
        data = prepare_data_for_tf(data_1d, tf)
        if not data:
            logger.warning(f"{tf}: 유효한 데이터 없음, skip")
            continue
        engine = BacktestEngine(strategy=strategy, config=engine_cfg)
        results[tf] = engine.run_multi(data)
        logger.info(
            f"  {tf}: 거래 {results[tf].total_trades}개, "
            f"수익률 {results[tf].total_return_pct:.2f}%"
        )

    if not results:
        print("[결과] 실행 가능한 타임프레임이 없습니다.")
        return

    metrics_list = [build_metrics(r, tf) for tf, r in results.items()]
    print_table(metrics_list)

    if not cfg.no_file:
        for tf, result in results.items():
            save_csv(result, cfg.output_dir, date, tf)
        save_markdown(metrics_list, results, cfg.output_dir, date, cfg.top_n)


def main() -> None:
    parser = argparse.ArgumentParser(description="수집된 OHLCV 데이터로 백테스트 실행")
    parser.add_argument("--cache-root", default=".cache", help="parquet 캐시 루트 (기본: .cache)")
    parser.add_argument(
        "--timeframes", nargs="+", default=["1D"],
        metavar="TF", help="실행할 TF: 1D 1W (기본: 1D)",
    )
    parser.add_argument("--output-dir", default="results", help="결과 저장 디렉토리 (기본: results)")
    parser.add_argument("--date", default=None, help="기준일 YYYYMMDD (기본: manifest의 target_date)")
    parser.add_argument("--initial-capital", type=float, default=10_000_000.0)
    parser.add_argument("--top-n", type=int, default=20, help="리포트 상위 N개 거래")
    parser.add_argument("--no-file", action="store_true", help="파일 저장 없이 stdout만")
    args = parser.parse_args()

    if args.date and not re.match(r"^\d{8}$", args.date):
        sys.exit("[ERROR] --date는 YYYYMMDD 형식이어야 합니다.")

    cfg = BacktestRunConfig(
        cache_root=Path(args.cache_root),
        timeframes=args.timeframes,
        output_dir=Path(args.output_dir),
        date=args.date,
        initial_capital=args.initial_capital,
        top_n=args.top_n,
        no_file=args.no_file,
    )
    run_backtest(cfg)


if __name__ == "__main__":
    main()
