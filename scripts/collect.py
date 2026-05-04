"""
scripts/collect.py — OHLCV 데이터 수집 Job.

사용:
    python scripts/collect.py --market KOSPI --max-universe 500 \\
        --cache-root .cache --timeframes 1D 1W 1h 30m

TF 매핑: 1D/1W → base_tf=1D, 1h/30m/2h/4h → base_tf=1m
수집된 데이터는 {cache_root}/{base_tf}/{ticker}.parquet 에 증분 저장.
"""
from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (scripts/ 하위에서 직접 실행 지원)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cache.ohlcv_disk import OhlcvDiskCache
from core.cache.universe_cache import UniverseCache
from core.data_fetch import DataClient, OhlcvCache
from core.data_sources.naver import naver_detail_url
from core.dates import latest_business_day
from core.universe import UniverseFilter, build_universe
from output.snapshot_builder import build_market_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# TF별 최소 재수집 주기 (--smart-skip 용)
_TF_MIN_INTERVAL: dict[str, timedelta] = {
    "1m":  timedelta(minutes=1),
    "30m": timedelta(minutes=30),
    "1h":  timedelta(hours=1),
    "2h":  timedelta(hours=2),
    "4h":  timedelta(hours=4),
    "1D":  timedelta(hours=20),
    "1W":  timedelta(days=6),
}

# 전략 TF → 수집 base TF 매핑
_TF_TO_BASE = {
    "1D": "1D", "1W": "1D",
    "1m": "1m",
    "30m": "1m", "1h": "1m", "2h": "1m", "4h": "1m",
}


@dataclass
class CollectConfig:
    market: str = "KOSPI"
    cache_root: Path = Path(".cache")
    max_universe_size: int = 500
    # 1D+1W는 base 1D로, 1h/30m는 base 1m으로 저장 후 리샘플링
    base_tfs: list[str] = field(default_factory=lambda: ["1D", "1m"])
    lookback_days: int = 90
    min_market_cap_bil: float = 0.0
    max_market_cap_bil: float = 9_999_999.0
    min_daily_volume: int = 50_000  # 거래량 중간 필터
    skip_collected: bool = False
    smart_skip: bool = True
    include_etf: bool = True
    force_refetch: bool = False  # True면 기존 parquet 무시하고 전 구간 재수집
    scan_root: Path = field(default_factory=lambda: Path("scan_results"))


def run_collect(cfg: CollectConfig, target_date: str | None = None) -> None:
    if target_date is None:
        target_date = latest_business_day()

    target_dt = datetime.strptime(target_date, "%Y%m%d")
    day_start = (target_dt - timedelta(days=cfg.lookback_days + 30)).strftime("%Y%m%d")
    # 분봉(1m) lookback. HMM 학습용 1h regime, 30m/1h RSI(14) 안정성을 위해 30일치.
    min_start = (target_dt - timedelta(days=30)).strftime("%Y%m%d")

    start_ts = time.monotonic()
    logger.info(f"수집 시작: {cfg.market} @ {target_date}")

    client = DataClient()

    uc = UniverseCache(cfg.cache_root)
    cached = uc.load(cfg.market, target_date)
    if cached and len(cached["tickers"]) >= cfg.max_universe_size:
        from core.universe import UniverseResult
        logger.info(
            f"유니버스 캐시 히트: {len(cached['tickers'])}종목 → "
            f"상위 {cfg.max_universe_size}개 사용 (크롤 skip)"
        )
        univ = UniverseResult(
            tickers=cached["tickers"][:cfg.max_universe_size],
            cap_lookup=cached["cap_lookup"],
            name_lookup=cached["name_lookup"],
        )
    else:
        univ = build_universe(
            client,
            target_date,
            UniverseFilter(
                min_market_cap_bil=cfg.min_market_cap_bil,
                max_market_cap_bil=cfg.max_market_cap_bil,
                min_daily_volume=cfg.min_daily_volume,
                market=cfg.market,
                max_universe_size=cfg.max_universe_size,
            ),
        )
        uc.save(
            market=cfg.market,
            date=target_date,
            tickers=univ.tickers,
            cap_lookup=univ.cap_lookup,
            name_lookup=univ.name_lookup,
        )
        logger.info(f"유니버스 캐시 저장: {len(univ.tickers)}종목")

    logger.info(f"주식 유니버스: {len(univ.tickers)}종목")

    # ETF 전종목 별도 fetch
    etf_tickers: list[str] = []
    if cfg.include_etf:
        try:
            etf_tickers = client.get_tickers("ETF", target_date)
            logger.info(f"ETF 유니버스: {len(etf_tickers)}개")
        except Exception as e:
            logger.warning(f"ETF 유니버스 수집 실패 (skip): {e}")

    # 주식 + ETF 합산 (중복 제거, 순서 유지)
    combined_tickers = list(dict.fromkeys(univ.tickers + etf_tickers))
    if etf_tickers:
        logger.info(
            f"합산 유니버스: 주식 {len(univ.tickers)} + ETF {len(etf_tickers)}"
            f" = {len(combined_tickers)}개"
        )

    disk = OhlcvDiskCache(cfg.cache_root)
    cache = OhlcvCache(client, disk=disk)
    timestamps = _load_timestamps(cfg.cache_root)

    # 오늘이면 미완료 봉이 갱신되어야 하므로 cooldown 무시 (사용자 의도: 매 주기 갱신)
    target_is_today = (target_date == datetime.now().strftime("%Y%m%d"))

    for tf in cfg.base_tfs:
        start = min_start if tf == "1m" else day_start
        to_collect = combined_tickers

        if cfg.smart_skip and not target_is_today:
            last = timestamps.get(tf)
            min_interval = _TF_MIN_INTERVAL.get(tf, timedelta(0))
            if last and (datetime.now() - last) < min_interval:
                # 주기 미달 — 캐시 없는 신규 종목만 수집, 기존 종목은 skip
                new_tickers = [t for t in combined_tickers if not disk.has_cache(t, tf)]
                if not new_tickers:
                    remaining = min_interval - (datetime.now() - last)
                    logger.info(
                        f"  {tf}: smart_skip (마지막 수집 {last.strftime('%H:%M:%S')}, "
                        f"{str(remaining).split('.')[0]} 남음)"
                    )
                    continue
                logger.info(
                    f"  {tf}: smart_skip 중 신규 종목 {len(new_tickers)}개 수집"
                )
                to_collect = new_tickers

        if cfg.skip_collected and to_collect is combined_tickers:
            to_collect = [t for t in combined_tickers if not disk.has_cache(t, tf)]
            skipped = len(combined_tickers) - len(to_collect)
            logger.info(f"  {tf}: {skipped}개 캐시 존재 skip, {len(to_collect)}개 수집 예정")
        if cfg.force_refetch:
            cleared = 0
            for ticker in to_collect:
                if disk.has_cache(ticker, tf):
                    disk.clear(ticker, tf)
                    cleared += 1
            logger.info(f"  {tf}: --force-refetch 로 {cleared}개 캐시 삭제")
        success, failed = 0, 0
        for ticker in to_collect:
            try:
                cache.get_or_fetch(ticker, start, target_date, timeframe=tf)
                success += 1
            except Exception as e:
                failed += 1
                logger.debug(f"  {ticker}/{tf} 실패: {e}")
        logger.info(f"  {tf}: 성공 {success}, 실패 {failed}")

        timestamps[tf] = datetime.now()
        _save_timestamps(cfg.cache_root, timestamps)

    # 펀더멘털 (PER/ROE/외인비율/naver_url) 1회 수집 — UI 인덱스용
    fundamentals = _collect_fundamentals(client, cfg.market, target_date, combined_tickers)
    fundamentals_collected_at = datetime.now().isoformat()

    # manifest 저장
    tickers_meta = _build_tickers_metadata(
        disk, combined_tickers, cfg.base_tfs, fundamentals=fundamentals,
    )
    duration_sec = int(time.monotonic() - start_ts)

    manifest = {
        "collected_at": datetime.now().isoformat(),
        "market": cfg.market,
        "include_etf": cfg.include_etf,
        "stock_count": len(univ.tickers),
        "etf_count": len(etf_tickers),
        "target_date": target_date,
        "tickers": combined_tickers,
        "etf_tickers": etf_tickers,
        "base_tfs": cfg.base_tfs,
        "tickers_meta": tickers_meta,
        "fundamentals_collected_at": fundamentals_collected_at,
        "summary": {
            "total_tickers": len(tickers_meta),
            "duration_sec": duration_sec,
        },
    }
    manifest_path = Path(cfg.cache_root) / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    logger.info(f"manifest 저장: {manifest_path}")

    # 시장 국면 저장 (weights.yml 불필요)
    try:
        from core.decision.market_regime import save_regime_analysis
        save_regime_analysis(Path(cfg.cache_root))
        _patch_manifest(manifest_path, {"regime_collected_at": datetime.now().isoformat()})
    except Exception as e:
        logger.warning(f"시장 국면 계산 실패 (skip): {e}")

    _update_dynamic_weights_status(cfg, manifest_path)

    # Job A: market_snapshot.json 저장 (선택 단계)
    try:
        ohlcv_latest = _extract_ohlcv_latest(str(cfg.cache_root), tickers_meta)
        market_indices = _fetch_market_indices(target_date)
        market_indices_collected_at = datetime.now().isoformat()

        # regime_analysis.json 이 있으면 snapshot 에도 함께 박아 signal-api join 으로 latest 응답
        regime_payload: dict | None = None
        regime_path = Path(cfg.cache_root) / "regime_analysis.json"
        if regime_path.exists():
            try:
                regime_data = json.loads(regime_path.read_text())
                regime_payload = regime_data.get("timeframe_scores")
            except Exception as e:
                logger.debug(f"regime_analysis.json 로드 실패 (skip): {e}")

        # breadth/axes 계산 (1D 기준)
        breadth_payload: dict | None = None
        axes_payload: dict | None = None
        try:
            from core.decision.market_breadth import compute_market_breadth
            from core.decision.market_axes import compute_trend_score, compute_volatility_regime
            from core.decision.market_regime import build_market_proxy

            breadth_1d = compute_market_breadth(cfg.cache_root, tf="1D")
            if breadth_1d:
                breadth_payload = {"1d": breadth_1d}

            proxy_1d = build_market_proxy(cfg.cache_root)
            if not proxy_1d.empty:
                trend_1d = compute_trend_score(proxy_1d["mean_return"])
                vol_1d = compute_volatility_regime(proxy_1d["rolling_std"])
                axes_payload = {"1d": {"trend_score": trend_1d, "volatility_regime": vol_1d}}
        except Exception as e:
            logger.warning(f"breadth/axes 계산 실패 (skip): {e}")

        snapshot = build_market_snapshot(
            universe={"tickers": tickers_meta},
            ohlcv_latest=ohlcv_latest,
            market_indices=market_indices,
            market_regime=regime_payload,
            market_breadth=breadth_payload,
            market_axes=axes_payload,
        )

        data_dir = pathlib.Path("data")
        data_dir.mkdir(exist_ok=True)
        snapshot_path = data_dir / "market_snapshot.json"
        snapshot_path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"[collect] market_snapshot.json 저장 → {snapshot_path}")
        _patch_manifest(manifest_path, {"market_indices_collected_at": market_indices_collected_at})
    except Exception as e:
        logger.warning(f"market_snapshot.json 저장 실패 (skip): {e}")


def _subprocess_run(cmd: list[str], **kw):
    """테스트 monkeypatch 포인트 — subprocess.run 래퍼."""
    import subprocess as _subprocess
    return _subprocess.run(cmd, **kw)


def _patch_manifest(path: Path, patch: dict) -> None:
    """manifest.json 부분 갱신. 성공 전환 시 error 키 제거."""
    if not path.exists():
        return
    data = json.loads(path.read_text())
    data.update(patch)
    if patch.get("dynamic_weights_computed") is True:
        data.pop("dynamic_weights_error", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _update_dynamic_weights_status(cfg: "CollectConfig", manifest_path: Path) -> None:
    """compute_weights.py subprocess 실행 후 manifest 에 결과 기록."""
    try:
        result = _subprocess_run(
            [sys.executable, str(Path(__file__).parent / "compute_weights.py"),
             "--cache-root", str(cfg.cache_root),
             "--scan-root", str(cfg.scan_root)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        logger.warning(f"동적 가중치 계산 실패 (skip): {e}")
        _patch_manifest(manifest_path, {
            "dynamic_weights_computed": False,
            "dynamic_weights_error": str(e),
        })
        return

    if result.returncode != 0:
        logger.warning(
            f"동적 가중치 계산 실패 (code {result.returncode}): {result.stderr.strip()}"
        )
        _patch_manifest(manifest_path, {
            "dynamic_weights_computed": False,
            "dynamic_weights_error": (result.stderr or "").strip()[:500],
        })
    else:
        logger.info("동적 가중치 계산 완료")
        _patch_manifest(manifest_path, {"dynamic_weights_computed": True})


def _load_timestamps(cache_root: Path) -> dict[str, datetime]:
    path = Path(cache_root) / "collect_timestamps.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {tf: datetime.fromisoformat(ts) for tf, ts in raw.items()}


def _save_timestamps(cache_root: Path, timestamps: dict[str, datetime]) -> None:
    path = Path(cache_root) / "collect_timestamps.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {tf: ts.isoformat() for tf, ts in timestamps.items()},
        indent=2,
    ))


def _collect_fundamentals(
    client: DataClient, market: str, target_date: str, tickers: list[str],
) -> dict[str, dict]:
    """펀더멘털 1회 fetch → ticker별 dict (per/roe/foreign_pct/naver_url).

    source 미지원/실패 시 모든 ticker를 None 으로 채우되 naver_url만 ticker 패턴으로
    항상 채워 UI 일관성을 보장한다. (NaN → None 정규화)
    """
    try:
        df = client.get_fundamentals(market, target_date)
    except Exception as e:
        logger.warning(f"펀더멘털 fetch 실패 (skip): {e}")
        df = None

    out: dict[str, dict] = {}
    for ticker in tickers:
        row = (df.loc[ticker].to_dict()
               if (df is not None and not df.empty and ticker in df.index)
               else {})
        out[ticker] = {
            "per": _none_if_nan(row.get("per")),
            "roe": _none_if_nan(row.get("roe")),
            "foreign_pct": _none_if_nan(row.get("foreign_pct")),
            "market_cap_bil": _none_if_nan(row.get("market_cap_bil")),
            "naver_url": row.get("naver_url") or naver_detail_url(ticker),
        }
    return out


def _none_if_nan(value):
    """pandas NaN/numpy.nan을 JSON 호환 None으로 정규화."""
    if value is None:
        return None
    try:
        import pandas as _pd
        if _pd.isna(value):
            return None
    except (TypeError, ValueError, ImportError):
        pass
    return value


def _build_tickers_metadata(
    disk_cache: OhlcvDiskCache,
    tickers: list[str],
    base_tfs: list[str],
    fundamentals: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """ticker별 base_tf마다 row_count와 last_date를 manifest용 dict로 빌드.

    각 (ticker, tf) 조합에서 데이터가 존재하면:
    - row_count_<tf>: 행 개수
    - last_date_<tf>: 마지막 날짜 (YYYY-MM-DD 문자열)
    - base_tfs: 해당 ticker에서 데이터가 있는 tf 목록

    데이터가 없으면 해당 ticker는 tickers_meta에서 제외.

    fundamentals (선택): ticker → {per, roe, foreign_pct, naver_url}.
    OHLCV 데이터가 있는 ticker에만 merge (UI는 OHLCV+펀더멘털 동시 보유 종목 표시).
    """
    tickers_meta: dict[str, dict] = {}

    for ticker in tickers:
        ticker_data: dict = {}
        found_tfs: list[str] = []

        for tf in base_tfs:
            try:
                df = disk_cache.read(ticker, tf)
                if df.empty:
                    continue

                row_count = len(df)
                last_date = df.index.max()
                if hasattr(last_date, "strftime"):
                    last_date_str = last_date.strftime("%Y-%m-%d")
                else:
                    last_date_str = str(last_date)

                ticker_data[f"row_count_{tf}"] = row_count
                ticker_data[f"last_date_{tf}"] = last_date_str
                found_tfs.append(tf)
            except Exception as e:
                logger.debug(f"메타 추출 실패 ({ticker}/{tf}): {e}")
                continue

        if found_tfs:
            ticker_data["base_tfs"] = found_tfs
            if fundamentals and ticker in fundamentals:
                ticker_data.update(fundamentals[ticker])
            tickers_meta[ticker] = ticker_data

    return tickers_meta


def _extract_ohlcv_latest(cache_root: str, tickers_meta: dict) -> dict[str, dict]:
    """parquet에서 각 ticker 최근 252행 OHLCV + 1m 마지막 분봉 + timeframe 별 RSI(14) 추출."""
    import pandas as pd
    from core.indicators import calc_rsi
    from core.cache.resampler import resample_to

    result = {}
    cache = pathlib.Path(cache_root) / "1D"
    minute_cache = pathlib.Path(cache_root) / "1m"

    def _rsi_last(close_series: pd.Series) -> float | None:
        if close_series is None or len(close_series) < 15:
            return None
        try:
            val = float(calc_rsi(close_series, period=14).iloc[-1])
            if val != val:  # NaN
                return None
            return round(val, 1)
        except Exception:
            return None

    for ticker in tickers_meta:
        pq = cache / f"{ticker}.parquet"
        if not pq.exists():
            continue
        df = pd.read_parquet(pq, columns=["close", "high", "low", "volume"])
        if df.empty:
            continue
        df = df.tail(252)  # 52주 = 약 252 거래일
        change_pct = df["close"].pct_change().fillna(0).mul(100).tolist()
        entry = {
            "close":      df["close"].tolist(),
            "high":       df["high"].tolist(),
            "low":        df["low"].tolist(),
            "volume":     df["volume"].tolist(),
            "change_pct": change_pct,
        }

        # 1D RSI — strategy 후보 여부와 무관하게 ticker 의 indicator
        rsi_by_tf: dict[str, float | None] = {"1D": _rsi_last(df["close"])}

        # 1m raw → 30m/1h 리샘플 + 마지막 분봉 close
        mpq = minute_cache / f"{ticker}.parquet"
        if mpq.exists():
            try:
                mdf_full = pd.read_parquet(mpq)
                if not mdf_full.empty:
                    last_idx = mdf_full.index.max()
                    today = pd.Timestamp.now().date()
                    if hasattr(last_idx, "hour") and (last_idx.hour or last_idx.minute):
                        if last_idx.date() == today:
                            entry["minute_close"] = float(mdf_full.loc[last_idx, "close"])
                            entry["minute_close_at"] = last_idx.isoformat()
                        for tf in ("30m", "1h"):
                            try:
                                resampled = resample_to(mdf_full, tf)
                                rsi_by_tf[tf] = _rsi_last(resampled["close"]) if not resampled.empty else None
                            except Exception:
                                rsi_by_tf[tf] = None
            except Exception as e:
                logger.debug(f"  {ticker}/1m 분봉 처리 실패: {e}")

        # 분봉 raw 가 없거나 리샘플 실패 시 1h/30m 키는 None 으로 명시
        rsi_by_tf.setdefault("1h", None)
        rsi_by_tf.setdefault("30m", None)
        entry["rsi_by_tf"] = rsi_by_tf

        result[ticker] = entry
    return result


def _fetch_vix() -> dict | None:
    """yfinance로 VIX 수집. 실패 시 None."""
    try:
        import yfinance as yf
        ticker = yf.Ticker("^VIX")
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        close = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else close
        change_pct = ((close - prev) / prev * 100) if prev else 0.0
        return {"value": close, "change_pct": round(change_pct, 2)}
    except Exception as e:
        logger.warning(f"VIX 수집 실패 (skip): {e}")
        return None


def _fetch_market_indices(target_date: str) -> dict[str, dict]:
    """KOSPI/KOSDAQ + 매크로 지수(USD/KRW, WTI, 국고채3Y, VIX) 수집."""
    try:
        from core.data_sources.naver import NaverSource
        src = NaverSource()
        result = {}
        for market, key in [("KOSPI", "kospi"), ("KOSDAQ", "kosdaq")]:
            data = src.get_market_index(market, target_date)
            if data:
                result[key] = data
        macro = src.get_macro_indices()
        result.update(macro)
        vix = _fetch_vix()
        if vix:
            result["vix"] = vix
        return result
    except Exception as e:
        logger.warning(f"시장 인덱스 수집 실패 (계속 진행): {e}")
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="OHLCV 수집 Job")
    parser.add_argument("--market", default="KOSPI", choices=["KOSPI", "KOSDAQ"])
    parser.add_argument("--cache-root", default=".cache")
    parser.add_argument("--max-universe", type=int, default=500)
    parser.add_argument(
        "--timeframes", nargs="+", default=["1D", "1W", "1h", "30m"],
        metavar="TF", help="1D 1W 1h 30m → 내부에서 base TF로 변환 (기본: 전 구간)",
    )
    parser.add_argument("--lookback-days", type=int, default=90, help="최근 N일 (기본: 3개월)")
    parser.add_argument("--min-volume", type=int, default=50_000, help="최소 거래량 (기본: 중간)")
    parser.add_argument("--date", help="기준일 YYYYMMDD")
    parser.add_argument(
        "--scan-root", default="scan_results",
        help="scan_results 디렉토리 경로 (compute_weights.py 전달용, 기본: scan_results)",
    )
    parser.add_argument(
        "--no-etf", action="store_true",
        help="ETF 전종목 합산 skip (기본: 포함)",
    )
    parser.add_argument(
        "--skip-collected", action="store_true",
        help="이미 캐시 파일이 있는 종목 skip (증분 수집용)",
    )
    parser.add_argument(
        "--no-smart-skip", action="store_true",
        help="smart-skip 비활성화 (기본: 활성화 — TF별 최소 주기 미달 시 기존 종목 skip)",
    )
    parser.add_argument(
        "--force-refetch", action="store_true",
        help="기존 parquet 캐시를 무시하고 전 구간 재수집 (schema migration 즉시 적용)",
    )
    args = parser.parse_args()

    base_tfs = sorted(set(
        _TF_TO_BASE[tf] for tf in args.timeframes if tf in _TF_TO_BASE
    ))
    cfg = CollectConfig(
        market=args.market,
        cache_root=Path(args.cache_root),
        max_universe_size=args.max_universe,
        base_tfs=base_tfs,
        lookback_days=args.lookback_days,
        min_daily_volume=args.min_volume,
        include_etf=not args.no_etf,
        skip_collected=args.skip_collected,
        smart_skip=not args.no_smart_skip,
        force_refetch=args.force_refetch,
        scan_root=Path(args.scan_root),
    )
    run_collect(cfg, target_date=args.date)


if __name__ == "__main__":
    main()
