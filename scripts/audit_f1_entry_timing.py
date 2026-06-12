"""
audit_f1_entry_timing.py — 감사 F1 후속: S1 same-bar vs next-bar 진입 delta 측정.

BacktestEngine 을 동일 데이터·동일 StrategyDConfig(운영 기본값)로 두 번 실행
(next_bar_entry=False/True), 포트폴리오 수준 delta 를 공표한다.

데이터: .cache_wf/1D/*.parquet (scripts/collect_wf_history.py 로 수집한 1년치).

실행:
    .venv/bin/python scripts/audit_f1_entry_timing.py --cache-root .cache_wf
"""
import argparse
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backtest_engine.engine import BacktestConfig, BacktestEngine  # noqa: E402
from backtest_engine.strategy import StrategyD, StrategyDConfig  # noqa: E402
from backtest_engine.walk_forward import compute_sharpe  # noqa: E402
from wf_validate_2026_05_14 import load_history  # noqa: E402

logger = logging.getLogger(__name__)


def run_mode(data, next_bar_entry: bool) -> dict:
    strategy = StrategyD(config=StrategyDConfig())
    config = BacktestConfig(next_bar_entry=next_bar_entry)
    result = BacktestEngine(strategy=strategy, config=config).run_multi(data)
    return {
        "trades": result.total_trades,
        "win_rate": result.win_rate * 100,
        "total_return_pct": result.total_return_pct,
        "avg_pnl_pct": result.avg_pnl_pct,
        "mdd_pct": result.max_drawdown_pct,
        "sharpe": compute_sharpe(result.equity_curve),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="S1 same-bar vs next-bar 진입 delta")
    parser.add_argument("--cache-root", default=".cache_wf")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    data = load_history(Path(args.cache_root))
    if not data:
        logger.error("데이터 없음: %s/1D", args.cache_root)
        sys.exit(1)

    spans = [(df.index.min(), df.index.max()) for df in data.values()]
    logger.info("종목 %d개, 기간 %s ~ %s", len(data),
                min(s for s, _ in spans).date(), max(e for _, e in spans).date())

    same = run_mode(data, next_bar_entry=False)
    nxt = run_mode(data, next_bar_entry=True)

    header = f"{'metric':<18}{'same-bar':>12}{'next-bar':>12}{'delta':>12}"
    print(header)
    print("-" * len(header))
    for key in same:
        delta = nxt[key] - same[key]
        print(f"{key:<18}{same[key]:>12.3f}{nxt[key]:>12.3f}{delta:>+12.3f}")


if __name__ == "__main__":
    main()
