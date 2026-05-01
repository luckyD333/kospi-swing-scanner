"""
cli.py — 멀티 전략 KOSPI 스윙 스캐너 진입점.

사용:
    python cli.py --strategy strategy_one_d_v2 --market KOSPI --top 20
    python cli.py --strategy all --top 10 --format markdown
    python cli.py --strategy strategy_one_d_v2 --format json --output-dir scan_results

플래그는 README 참조.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from core.data_fetch import DataClient
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import Candidate, Strategy
from output import comparison, formatters
from strategies import REGISTRY, available

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# CLI 인자 파싱
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="멀티 전략 KOSPI/KOSDAQ 스윙 스캐너 (일봉 기반)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--strategy", default="strategy_one_d_v2",
        help=(
            f"실행할 전략 이름. 'all' 입력 시 등록된 모든 전략 실행. "
            f"등록된 전략: {', '.join(available())}"
        ),
    )
    parser.add_argument(
        "--market", default="KOSPI", choices=["KOSPI", "KOSDAQ", "KRX", "ETF"],
    )
    parser.add_argument("--date", help="기준일 YYYYMMDD. 미지정 시 최근 영업일")
    parser.add_argument("--top", type=int, default=20, help="상위 N개")
    parser.add_argument(
        "--format", default="table",
        choices=["table", "json", "csv", "markdown"],
        help="출력 포맷 (단일 전략) / 비교 모드 (--strategy all) 시 markdown/csv/json 권장",
    )
    parser.add_argument(
        "--min-cap", type=float, default=2000.0,
        help="최소 시총 (억)",
    )
    parser.add_argument(
        "--max-cap", type=float, default=30000.0,
        help="최대 시총 (억)",
    )
    parser.add_argument(
        "--min-volume", type=int, default=100_000,
        help="최소 20일 평균 거래량",
    )
    parser.add_argument(
        "--lookback-days", type=int, default=90,
        help="지표 계산용 과거 일수",
    )
    parser.add_argument("--output-dir", help="JSON/CSV 저장 디렉토리. 미지정 시 stdout만")
    parser.add_argument(
        "--no-krx", action="store_true",
        help="KRX 공식 Proxy 비활성화 (네이버/pykrx만)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="KRX Proxy 데이터 불완전 시 즉시 중단",
    )
    return parser


# ============================================================================
# 전략 선택
# ============================================================================

def resolve_strategies(name: str) -> List[Strategy]:
    if name == "all":
        return [cls() for cls in REGISTRY.values()]
    if name not in REGISTRY:
        raise SystemExit(
            f"알 수 없는 전략 '{name}'. 사용 가능: {', '.join(available())} 또는 'all'"
        )
    return [REGISTRY[name]()]


# ============================================================================
# 출력
# ============================================================================

def render_single(
    candidates: List[Candidate],
    target_date: str,
    fmt: str,
) -> str:
    formatter = formatters.FORMATTERS.get(fmt)
    if formatter is None:
        raise ValueError(f"unsupported format: {fmt}")
    return formatter(candidates, target_date)


def render_multi(
    results: Dict[str, List[Candidate]],
    target_date: str,
    fmt: str,
    top_n: int,
) -> str:
    if fmt == "table":
        # table 은 단일 전략용. 멀티는 markdown 으로 fallback.
        logger.info("멀티 전략은 markdown 비교 테이블로 출력합니다 (--format table → markdown)")
        fmt = "markdown"
    if fmt == "markdown":
        return comparison.format_markdown_comparison(results, target_date, top_n=top_n)
    if fmt == "csv":
        return comparison.format_csv_comparison(results, target_date)
    if fmt == "json":
        return comparison.format_json_comparison(results, target_date)
    raise ValueError(f"unsupported multi format: {fmt}")


def save_output(
    body: str, fmt: str, target_date: str, strategy_name: str, output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = {"json": "json", "csv": "csv", "markdown": "md", "table": "txt"}[fmt]
    timestamp = datetime.now().strftime("%H%M")
    filename = f"scan_{target_date}_{strategy_name}_{timestamp}.{ext}"
    path = output_dir / filename
    path.write_text(body, encoding="utf-8")
    logger.info(f"💾 결과 저장: {path}")
    return path


# ============================================================================
# main
# ============================================================================

def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.date:
        try:
            datetime.strptime(args.date, "%Y%m%d")
        except ValueError:
            parser.error(f"--date 형식 오류: '{args.date}' (YYYYMMDD)")

    strategies = resolve_strategies(args.strategy)
    logger.info(f"실행 전략: {[s.name for s in strategies]}")

    client = DataClient(
        use_krx_for_universe=not args.no_krx,
        strict_mode=args.strict,
    )
    runner = ScanRunner(
        client,
        RunnerConfig(
            market=args.market,
            min_market_cap_bil=args.min_cap,
            max_market_cap_bil=args.max_cap,
            min_daily_volume=args.min_volume,
            lookback_days=args.lookback_days,
            top_n=args.top,
        ),
    )
    result = runner.run(strategies, target_date=args.date)
    target = result.target_date

    if result.errors:
        for strat, err in result.errors.items():
            logger.error(f"❌ {strat}: {err}")

    # 단일 전략 vs 멀티
    if len(strategies) == 1 and not result.errors:
        strat_name = strategies[0].name
        candidates = result.candidates_by_strategy.get(strat_name, [])
        body = render_single(candidates, target, args.format)
    else:
        body = render_multi(
            result.candidates_by_strategy, target, args.format, top_n=args.top,
        )
        strat_name = "multi"

    print(body)

    if args.output_dir:
        save_output(body, args.format, target, strat_name, Path(args.output_dir))

    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
