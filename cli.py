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
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.data_fetch import DataClient
from core.runner import RunnerConfig, ScanRunner
from core.strategy_base import Candidate, Strategy
from output import comparison, formatters
from strategies import FALLBACKS, REGISTRY, available

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
        "--market", default="KOSPI", choices=["KOSPI", "KOSDAQ"],
    )
    parser.add_argument("--date", help="기준일 YYYYMMDD. 미지정 시 최근 영업일")
    parser.add_argument("--top", type=int, default=20, help="상위 N개")
    parser.add_argument(
        "--format", default="table",
        choices=["table", "json", "csv", "markdown", "signals_ui"],
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
        "--timeframes", nargs="+", metavar="TF",
        help="스캔할 타임프레임 목록 (예: 1D 1W 1h 30m). 지정 시 해당 TF의 전략 자동 선택",
    )
    parser.add_argument(
        "--cache-root", metavar="DIR",
        help="collect.py가 저장한 캐시 루트. 지정 시 오프라인 스캔 (네트워크 OHLCV fetch 생략)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="DEBUG 로그 출력",
    )
    parser.add_argument(
        "--max-universe", type=int, default=500,
        help="시총 상위 N 종목으로 유니버스 제한. 0 또는 음수 입력 시 무제한",
    )
    # ----- Phase 2: 의사결정 모드 -----
    decision_grp = parser.add_argument_group("의사결정 모드 (Phase 2)")
    decision_grp.add_argument(
        "--interview", action="store_true",
        help="가중치 인터뷰 실행 → weights.yml 저장 후 종료",
    )
    decision_grp.add_argument(
        "--decide", action="store_true",
        help="scan_results 의 후보를 가중치 기반으로 ranking → decision_top{N}.md 생성",
    )
    decision_grp.add_argument(
        "--top-n", type=int, default=5,
        help="--decide 시 생성할 ranking 상위 개수",
    )
    decision_grp.add_argument(
        "--select", help="--decide 시 Decision Journal 생성할 ticker 목록 (콤마 구분)",
    )
    decision_grp.add_argument(
        "--notes", help="--decide --select 시 Journal 메모 영역에 추가할 텍스트",
    )
    decision_grp.add_argument(
        "--weights", help="가중치 yaml 경로 (기본: ~/.kospi-scanner/weights.yml)",
    )
    decision_grp.add_argument(
        "--scan-results-dir", default="scan_results",
        help="scan_results 루트 (manifest.json 위치)",
    )
    decision_grp.add_argument(
        "--dynamic-weights",
        action="store_true",
        help=".cache/dynamic_weights.json 로드 (없으면 --weights fallback)",
    )
    return parser


# ============================================================================
# 전략 선택
# ============================================================================

def resolve_strategies(name: str, timeframes: list[str] | None = None) -> list[Strategy]:
    if timeframes:
        return _resolve_by_timeframes(timeframes)
    if name == "all":
        return [factory() for factory in REGISTRY.values()]
    if name not in REGISTRY:
        raise SystemExit(
            f"알 수 없는 전략 '{name}'. 사용 가능: {', '.join(available())} 또는 'all'"
        )
    return [REGISTRY[name]()]


def _resolve_by_timeframes(timeframes: list[str]) -> list[Strategy]:
    """timeframes 목록에 해당하는 전략 인스턴스를 REGISTRY에서 선택."""
    result = []
    for factory in REGISTRY.values():
        inst = factory()
        if getattr(inst, "timeframe", "1D") in timeframes:
            result.append(inst)
    return result


# ============================================================================
# Manifest 관리
# ============================================================================

def _update_scan_manifest(
    output_dir: Path,
    strategy_name: str,
    target_date: str,
    timeframe: str,
    saved_path: Path,
    fmt: str,
) -> None:
    """output_dir/manifest.json 을 atomic 으로 갱신해서 strategy+tf 별 latest 결과를 가리켜요.

    키는 f"{strategy_name}__{timeframe}" 형태. 값은
    {"date": str, "latest_file": str(상대경로), "formats": list[str], "generated_at": iso}.
    """
    manifest_path = output_dir / "manifest.json"

    # 기존 manifest 읽기
    manifest = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"manifest.json 파싱 실패, 새로 시작: {e}")
            manifest = {}

    # 키 생성
    key = f"{strategy_name}__{timeframe}"

    # 상대경로 계산
    relative_path = saved_path.relative_to(output_dir).as_posix()

    # generated_at: timezone-aware ISO8601 (KST)
    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

    # entry 갱신
    if key in manifest:
        existing = manifest[key]
        # 같은 시점(latest_file)이면 formats 배열에 추가, 다르면 덮어씀
        if existing.get("latest_file") == relative_path:
            # 같은 파일: formats 배열에 fmt 추가 (dedup)
            formats_set = set(existing.get("formats", []))
            formats_set.add(fmt)
            existing["formats"] = sorted(formats_set)
            existing["generated_at"] = generated_at
        else:
            # 다른 파일: entry 전체 교체 (이전 formats 무시)
            manifest[key] = {
                "date": target_date,
                "latest_file": relative_path,
                "formats": [fmt],
                "generated_at": generated_at,
            }
    else:
        # 신규 entry
        manifest[key] = {
            "date": target_date,
            "latest_file": relative_path,
            "formats": [fmt],
            "generated_at": generated_at,
        }

    # Atomic write
    pid = os.getpid()
    ts = int(datetime.now().timestamp() * 1000)  # millisecond precision
    tmp_suffix = f".json.tmp.{pid}.{ts}"
    tmp_path = manifest_path.with_name(manifest_path.name + tmp_suffix)

    try:
        tmp_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, manifest_path)
        logger.info(f"📋 manifest 갱신: {key}")
    except OSError as e:
        logger.error(f"manifest 쓰기 실패: {e}")
        # tmp 파일 정리 시도
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


# ============================================================================
# 출력
# ============================================================================

def render_single(
    candidates: list[Candidate],
    target_date: str,
    fmt: str,
    strategy_name: str | None = None,
    timeframe: str = "1D",
    filters: dict | None = None,
    candidates_by_strategy: dict[str, list] | None = None,
) -> str:
    if fmt == "json":
        return formatters.format_json(
            candidates,
            target_date,
            strategy_name=strategy_name,
            timeframe=timeframe,
            filters=filters,
        )
    if fmt == "signals_ui":
        # signals_ui는 JSON 응답이 아니라 파일 저장 작업으로 처리
        # render_single 함수의 스코프 외이므로 None을 반환하고 main에서 처리
        return ""
    formatter = formatters.FORMATTERS.get(fmt)
    if formatter is None:
        raise ValueError(f"unsupported format: {fmt}")
    return formatter(candidates, target_date)


def render_multi(
    results: dict[str, list[Candidate]],
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
    summary_text: str | None = None, summary_dict: dict | None = None,
    tf: str | None = None,
) -> Path | None:
    """저장 처리. scan_results/YYYY-MM-DD/{tf}/ 또는 scan_results/YYYY-MM-DD/."""
    # 날짜·TF 디렉토리 생성
    date_dir = output_dir / target_date / tf if tf else output_dir / target_date
    try:
        date_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning(f"저장 디렉토리 생성 실패, stdout 만 출력: {e}")
        return None

    ext = {"json": "json", "csv": "csv", "markdown": "md", "table": "txt"}[fmt]
    timestamp = datetime.now().strftime("%H%M")
    filename = f"scan_{target_date}_{strategy_name}_{timestamp}.{ext}"
    path = date_dir / filename

    # 포맷별 처리
    if fmt == "json":
        # JSON: summary_dict 추가
        payload = json.loads(body)
        if summary_dict:
            payload["summary"] = summary_dict
        final_body = json.dumps(payload, ensure_ascii=False, indent=2)
    elif fmt == "csv":
        # CSV: summary 별도 파일
        final_body = body
        summary_filename = f"scan_{target_date}_{strategy_name}_{timestamp}_summary.txt"
        summary_path = date_dir / summary_filename
        if summary_text:
            summary_path.write_text(summary_text, encoding="utf-8")
            logger.info(f"💾 summary 저장: {summary_path}")
    else:
        # table/markdown: summary prepend
        final_body = (summary_text + "\n" + body) if summary_text else body

    path.write_text(final_body, encoding="utf-8")
    logger.info(f"💾 결과 저장: {path}")

    # manifest 갱신 (output_dir이 None이 아닐 때만)
    if tf:  # TF가 지정된 경우만 manifest 갱신
        try:
            _update_scan_manifest(
                output_dir,
                strategy_name=strategy_name,
                target_date=target_date,
                timeframe=tf,
                saved_path=path,
                fmt=fmt,
            )
        except OSError as e:
            logger.error(f"manifest 갱신 중 오류: {e}")

    return path


# ============================================================================
# main
# ============================================================================

def _run_interview(args) -> int:
    """가중치 인터뷰 모드. 사용자 stdin 입력 → weights.yml 저장."""
    from core.decision.interview import default_weights_path, interactive_interview

    save_path = Path(args.weights) if args.weights else default_weights_path()
    try:
        interactive_interview(save_path=save_path)
    except (OSError, ValueError) as e:
        logger.error(f"인터뷰 실패: {e}")
        return 1
    return 0


def _run_decide(args) -> int:
    """scan_results 의 후보를 ranking 또는 Decision Journal 로 변환."""
    from core.decision.config import WeightConfig
    from core.decision.interview import default_weights_path
    from core.decision.runner import run_decide_journal, run_decide_ranking

    weights_path = Path(args.weights) if args.weights else default_weights_path()
    if not weights_path.exists():
        logger.error(
            f"가중치 파일 없음: {weights_path}. 먼저 `cli.py --interview` 실행해주세요."
        )
        return 1
    weight_config = WeightConfig.load(weights_path)

    target_date = args.date or datetime.now().strftime("%Y%m%d")
    scan_root = Path(args.scan_results_dir)

    # dynamic_weights 경로 설정
    dynamic_weights_path = None
    if getattr(args, "dynamic_weights", False):
        dynamic_weights_path = Path(args.cache_root or ".cache") / "dynamic_weights.json"

    # regime 로드용 cache_root (regime_analysis.json 위치)
    cache_root_path = Path(args.cache_root or ".cache")

    if args.select:
        tickers = [t.strip() for t in args.select.split(",") if t.strip()]
        paths = run_decide_journal(
            scan_root=scan_root, target_date=target_date,
            tickers=tickers, weight_config=weight_config, notes=args.notes,
            dynamic_weights_path=dynamic_weights_path,
            cache_root=cache_root_path,
        )
        if not paths:
            logger.warning("생성된 Journal 없음 (선택한 ticker가 후보 풀에 없음)")
            return 1
        for p in paths:
            print(f"📝 {p}")
        return 0

    out_path = run_decide_ranking(
        scan_root=scan_root, target_date=target_date,
        top_n=args.top_n, weight_config=weight_config,
        dynamic_weights_path=dynamic_weights_path,
        cache_root=cache_root_path,
    )
    print(f"📝 {out_path}")
    return 0


def _handle_signals_ui_format(args, result) -> int:
    """signals_ui 포맷 처리 — MarketSnapshot 로드 → SignalsPayload → data/signals.json 저장."""
    from output.models import MarketSnapshot
    from output.signals_builder import build_signals_payload

    snap_path = Path("data") / "market_snapshot.json"
    if not snap_path.exists():
        logger.error("[ERROR] data/market_snapshot.json 없음. Job A (collect.py)를 먼저 실행하세요.")
        return 1

    snapshot = MarketSnapshot.model_validate_json(snap_path.read_text(encoding="utf-8"))

    regime = None
    regime_path = Path(".cache") / "regime_analysis.json"
    if regime_path.exists():
        import json as _json
        _r = _json.loads(regime_path.read_text(encoding="utf-8"))
        regime = _r.get("timeframe_scores")

    weight_config = None
    weights_path = Path("weights.yml")
    if weights_path.exists():
        try:
            from core.decision.config import WeightConfig
            weight_config = WeightConfig.load(weights_path)
        except Exception as e:
            logger.warning(f"weights.yml 로드 실패 (decision 데이터 생략): {e}")

    payload = build_signals_payload(
        snapshot, result.candidates_by_strategy,
        market_regime=regime, weight_config=weight_config,
    )

    data_dir = Path(args.output_dir or "data")
    data_dir.mkdir(exist_ok=True)

    # by_alias=True 필수 — _display alias가 JSON에 나타남
    json_str = payload.model_dump_json(by_alias=True, indent=2)

    out_path = data_dir / "signals.json"
    out_path.write_text(json_str, encoding="utf-8")

    archive_dir = data_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    archive_path = archive_dir / f"signals_{date.today().isoformat()}.json"
    archive_path.write_text(json_str, encoding="utf-8")

    logger.info(f"[cli] signals.json 저장 → {out_path} ({payload.stats['total_signals']}개 시그널)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # verbose 플래그 처리
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.date:
        try:
            datetime.strptime(args.date, "%Y%m%d")
        except ValueError:
            parser.error(f"--date 형식 오류: '{args.date}' (YYYYMMDD)")

    # Phase 2: 의사결정 모드 분기 (스캐너 실행과 별도)
    if args.interview:
        return _run_interview(args)
    if args.decide:
        return _run_decide(args)

    # max-universe: 음수 가드
    cap_limit = args.max_universe if args.max_universe and args.max_universe > 0 else None

    req_timeframes = args.timeframes or None
    strategies = resolve_strategies(args.strategy, req_timeframes)
    if not strategies:
        logger.error(f"선택된 전략 없음 (timeframes={req_timeframes})")
        return 1
    logger.info(f"실행 전략: {[s.name for s in strategies]}")

    # 전략 인스턴스에서 필요한 TF 목록 자동 추출
    runner_timeframes = sorted(set(getattr(s, "timeframe", "1D") for s in strategies))

    from core.cache.freshness import check_freshness

    cache_root = Path(args.cache_root) if args.cache_root else None
    if cache_root:
        freshness = check_freshness(cache_root)
        if not freshness.ok:
            logger.warning(f"⚠️  캐시 신선도: {freshness.message}")

    client = DataClient()
    runner = ScanRunner(
        client,
        RunnerConfig(
            market=args.market,
            min_market_cap_bil=args.min_cap,
            max_market_cap_bil=args.max_cap,
            min_daily_volume=args.min_volume,
            lookback_days=args.lookback_days,
            top_n=args.top,
            max_universe_size=cap_limit or 500,
            timeframes=runner_timeframes,
            cache_root=cache_root,
        ),
    )
    # --strategy all 은 strict/r1/r2 모두 독립 실행 → fallback 비활성화
    fallback_instances: dict | None = None
    if args.strategy != "all" and not args.timeframes:
        fallback_instances = {
            name: [REGISTRY[fb]() for fb in fb_names if fb in REGISTRY]
            for name, fb_names in FALLBACKS.items()
        }

    result = runner.run(strategies, target_date=args.date, fallbacks=fallback_instances)
    target = result.target_date

    if result.errors:
        for strat, err in result.errors.items():
            logger.error(f"❌ {strat}: {err}")

    # Summary 생성
    summary_text = formatters.format_run_summary(result, args.market)

    # JSON 포맷용 filters dict 구성
    filters_dict = {
        "min_cap_bil": args.min_cap,
        "max_cap_bil": args.max_cap,
        "min_volume": args.min_volume,
        "lookback_days": args.lookback_days,
        "market": args.market,
    }

    multi_tf = len(runner_timeframes) > 1

    if multi_tf:
        # 멀티 TF: TF별로 stdout 출력 + 파일 저장
        if args.format == "signals_ui":
            return _handle_signals_ui_format(args, result)
        else:
            if args.format != "json":
                print(summary_text)
            output_dir = Path(args.output_dir) if args.output_dir else None
            summary_dict = formatters.format_run_summary_json(result, args.market) if output_dir else None
            for (strat_name, tf), candidates in sorted(result.candidates_by_strategy_tf.items()):
                body = render_single(
                    candidates,
                    target,
                    args.format,
                    strategy_name=strat_name,
                    timeframe=tf,
                    filters=filters_dict,
                )
                print(f"\n--- {strat_name} / {tf} ---")
                print(body)
                if output_dir:
                    save_output(
                        body, args.format, target, strat_name, output_dir,
                        summary_text=summary_text, summary_dict=summary_dict, tf=tf,
                    )
    else:
        # 단일 TF: 기존 동작
        if args.format == "signals_ui":
            return _handle_signals_ui_format(args, result)
        elif len(strategies) == 1 and not result.errors:
            strat_name = strategies[0].name
            tf = getattr(strategies[0], "timeframe", "1D")
            candidates = result.candidates_by_strategy.get(strat_name, [])
            body = render_single(
                candidates,
                target,
                args.format,
                strategy_name=strat_name,
                timeframe=tf,
                filters=filters_dict,
            )
        else:
            body = render_multi(
                result.candidates_by_strategy, target, args.format, top_n=args.top,
            )
            strat_name = "multi"
            tf = runner_timeframes[0]

        if args.format != "json" and args.format != "signals_ui":
            print(summary_text)
        if args.format != "signals_ui":
            print(body)

        if args.output_dir and args.format != "signals_ui":
            summary_dict = formatters.format_run_summary_json(result, args.market)
            save_output(
                body, args.format, target, strat_name, Path(args.output_dir),
                summary_text=summary_text, summary_dict=summary_dict, tf=tf,
            )

    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
