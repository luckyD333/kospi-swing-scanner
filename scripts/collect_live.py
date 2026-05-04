"""장중 경량 실시간 수집: 시장 지수 + 시그널 종목 현재가만 갱신.

2분 주기 cron용. collect.py 전체 실행 없이 market_snapshot.json의
market_indices + tickers[x].current_price 만 갱신한다.
"""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
_ROOT = Path(__file__).parent.parent
DATA_DIR = _ROOT / "data"
SIGNALS_PATH = DATA_DIR / "signals.json"
SNAPSHOT_PATH = DATA_DIR / "market_snapshot.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _load_signal_tickers() -> list[str]:
    data = _load_json(SIGNALS_PATH)
    return list({s["ticker"] for s in data.get("signals", [])})


def _fetch_market_indices(today: str) -> dict[str, dict]:
    """KOSPI/KOSDAQ + 매크로(USD/KRW, WTI, 국고채3Y) + VIX 수집."""
    from core.data_sources.naver import NaverSource

    try:
        src = NaverSource()
        result: dict[str, dict] = {}
        for market, key in [("KOSPI", "kospi"), ("KOSDAQ", "kosdaq")]:
            data = src.get_market_index(market, today)
            if data:
                result[key] = data
        macro = src.get_macro_indices()
        result.update(macro)
    except Exception as e:
        logger.warning(f"시장 지수 수집 실패: {e}")
        result = {}

    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="5d")
        if not hist.empty:
            close = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else close
            change_pct = round((close - prev) / prev * 100, 2) if prev else 0.0
            result["vix"] = {"value": close, "change_pct": change_pct}
    except Exception as e:
        logger.warning(f"VIX 수집 실패 (skip): {e}")

    return result


def _fetch_current_prices(tickers: list[str], now: datetime) -> dict[str, dict]:
    """siseJson 1m API로 각 ticker 현재가 수집.

    오늘 09:00 ~ 현재 범위로 조회해 마지막 bar close = 현재가,
    intraday change_pct = (last_close - first_open) / first_open * 100.
    장외 시간(빈 응답)이면 해당 ticker skip.
    """
    from core.data_sources.naver import NaverSource

    src = NaverSource()
    session_start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    start_str = session_start.strftime("%Y%m%d%H%M")
    end_str = now.strftime("%Y%m%d%H%M")

    result: dict[str, dict] = {}
    for ticker in tickers:
        try:
            df = src.get_ohlcv(ticker, start_str, end_str, timeframe="1m")
            if df.empty:
                continue
            last_close = float(df["close"].iloc[-1])
            first_open = float(df["open"].iloc[0])
            change_pct = (
                round((last_close - first_open) / first_open * 100, 2)
                if first_open else 0.0
            )
            volume = int(df["volume"].sum()) if "volume" in df.columns else None
            result[ticker] = {
                "current_price": last_close,
                "change_pct": change_pct,
                "volume": volume,
            }
        except Exception as e:
            logger.warning(f"  {ticker} 현재가 수집 실패 (skip): {e}")
    return result


def main() -> None:
    now = datetime.now(KST)
    today = now.strftime("%Y%m%d")
    logger.info(f"collect_live 시작 — {now.isoformat()}")

    snapshot = _load_json(SNAPSHOT_PATH)
    if not snapshot:
        snapshot = {"market_indices": {}, "tickers": {}, "source": {}}

    indices = _fetch_market_indices(today)
    if indices:
        snapshot.setdefault("market_indices", {}).update(indices)
        logger.info(f"  시장 지수 갱신: {list(indices.keys())}")

    tickers = _load_signal_tickers()
    logger.info(f"  시그널 종목 {len(tickers)}개 현재가 수집 중...")
    prices = _fetch_current_prices(tickers, now)
    for ticker, data in prices.items():
        snapshot.setdefault("tickers", {}).setdefault(ticker, {}).update(data)
    logger.info(f"  현재가 갱신: {len(prices)}/{len(tickers)}개")

    snapshot.setdefault("source", {})["collected_at"] = now.isoformat()

    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SNAPSHOT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    os.replace(tmp, SNAPSHOT_PATH)
    logger.info("  market_snapshot.json 갱신 완료")


if __name__ == "__main__":
    main()
