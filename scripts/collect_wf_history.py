"""scripts/collect_wf_history.py — Walk-Forward 검증용 1년치 일봉 수집.

기존 .cache/1D/ 는 manifest target_date 기준 단기(4~5개월) 데이터만 보유.
WF 검증(train=90 + test=30 = 120거래일 ≈ 6개월)은 충분한 데이터 필요 →
별도 .cache_wf/1D/ 에 1년치 일봉을 수집.

용도: Phase 4 (scripts/wf_validate_2026_05_14.py) 의 입력 데이터.

사용:
    python scripts/collect_wf_history.py
        # 기본: .cache/manifest.json universe → 1년치(2025-05-19 ~ 2026-05-19)
        # → .cache_wf/1D/{ticker}.parquet

    python scripts/collect_wf_history.py --years 2 --output-root .cache_wf
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path 에 추가 (scripts/ 하위에서 직접 실행 지원)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402, F401

from core.data_sources.naver import NaverSource  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="WF 검증용 장기 일봉 수집")
    parser.add_argument(
        "--cache-root", default=".cache",
        help="기존 manifest.json 위치 (universe 로드용)",
    )
    parser.add_argument(
        "--output-root", default=".cache_wf",
        help="장기 데이터 저장 위치 (.cache_wf/1D/)",
    )
    parser.add_argument(
        "--years", type=int, default=1,
        help="수집 기간 (년 단위)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="수집할 ticker 수 제한 (None=전체)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    cache_root = Path(args.cache_root)
    output_root = Path(args.output_root) / "1D"
    output_root.mkdir(parents=True, exist_ok=True)

    # 1) universe 로드
    manifest_path = cache_root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json 없음: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    tickers = manifest.get("tickers", [])
    if args.limit:
        tickers = tickers[: args.limit]
    logger.info(f"수집 대상: {len(tickers)}개 ticker")

    # 2) 날짜 범위 산출
    end_dt = datetime.now()
    start_dt = end_dt.replace(year=end_dt.year - args.years)
    start = start_dt.strftime("%Y%m%d")
    end = end_dt.strftime("%Y%m%d")
    logger.info(f"기간: {start} ~ {end} ({args.years}년)")

    # 3) 수집
    src = NaverSource()
    t0 = time.time()
    ok, empty, fail = 0, 0, 0
    for i, ticker in enumerate(tickers, 1):
        try:
            df = src.get_ohlcv(ticker, start, end, timeframe="1D")
        except Exception as exc:
            logger.warning(f"  [{i}/{len(tickers)}] {ticker} 실패: {exc}")
            fail += 1
            continue
        if df.empty:
            empty += 1
            continue
        out = output_root / f"{ticker}.parquet"
        df.to_parquet(out)
        ok += 1
        if i % 50 == 0:
            rate = i / (time.time() - t0)
            logger.info(f"  [{i}/{len(tickers)}] 진행 ({rate:.0f}/초)")

    elapsed = time.time() - t0
    logger.info(
        f"완료: 성공 {ok}, 빈 응답 {empty}, 실패 {fail} / "
        f"{elapsed:.1f}초 ({ok/elapsed:.0f}/초)"
    )
    logger.info(f"저장 위치: {output_root.absolute()}")

    # 4) 요약 메타데이터
    summary = {
        "collected_at": datetime.now().isoformat(),
        "start_date": start,
        "end_date": end,
        "years": args.years,
        "tickers_total": len(tickers),
        "tickers_ok": ok,
        "tickers_empty": empty,
        "tickers_fail": fail,
        "elapsed_seconds": round(elapsed, 1),
    }
    summary_path = output_root.parent / "wf_history_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info(f"요약 저장: {summary_path}")


if __name__ == "__main__":
    main()
