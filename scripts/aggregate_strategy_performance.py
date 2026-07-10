"""운영 signal archive의 최근 6개월 1D 성과 집계.

사용:
    python scripts/aggregate_strategy_performance.py \
        --data-dir data --cache-root .cache \
        --output data/strategy_performance.json
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cache.ohlcv_disk import OhlcvDiskCache  # noqa: E402
from core.strategy_performance import (  # noqa: E402
    build_performance_payload,
    canonical_strategy_key,
)

logger = logging.getLogger(__name__)


def load_signal_snapshots(data_dir: Path) -> list[dict[str, Any]]:
    """archive의 JSON snapshot을 최신 파일 순서로 읽는다."""
    archive_dir = data_dir / "archive"
    snapshots: list[dict[str, Any]] = []
    for path in sorted(archive_dir.glob("signals_*.json")):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("signal archive 로드 실패 (%s): %s", path, exc)
            continue
        snapshot["source_file"] = path.name
        snapshots.append(snapshot)
    return snapshots


def _tickers_from_snapshots(snapshots: list[dict[str, Any]]) -> set[str]:
    tickers: set[str] = set()
    for snapshot in snapshots:
        for signal in snapshot.get("signals", []) or []:
            strategy = signal.get("strategy") or {}
            if canonical_strategy_key(strategy.get("id"), strategy.get("timeframe")):
                ticker = signal.get("ticker")
                if ticker:
                    tickers.add(str(ticker))
    return tickers


def _load_ohlcv(cache_root: Path, snapshots: list[dict[str, Any]]):
    cache = OhlcvDiskCache(cache_root)
    frames = {}
    for ticker in sorted(_tickers_from_snapshots(snapshots)):
        frame = cache.read(ticker, "1D")
        if not frame.empty:
            frames[ticker] = frame
    return frames


@contextmanager
def _exclusive_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update_performance_file(
    data_dir: Path | str,
    cache_root: Path | str,
    output_path: Path | str,
) -> dict[str, Any]:
    """성과 파일을 lock + atomic replace 방식으로 재생성한다."""
    data_dir = Path(data_dir)
    cache_root = Path(cache_root)
    output_path = Path(output_path)
    lock_path = output_path.with_suffix(output_path.suffix + ".lock")

    with _exclusive_lock(lock_path):
        snapshots = load_signal_snapshots(data_dir)
        frames = _load_ohlcv(cache_root, snapshots)
        payload = build_performance_payload(
            snapshots,
            frames,
            generated_at=datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        )
        _write_atomic(output_path, payload)
        logger.info(
            "전략 성과 저장: %s (status=%s, daily=%d)",
            output_path,
            payload["status"],
            len(payload["daily"]),
        )
        return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="최근 6개월 1D 전략 성과 집계")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cache-root", default=".cache")
    parser.add_argument("--output", default="data/strategy_performance.json")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    update_performance_file(args.data_dir, args.cache_root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
