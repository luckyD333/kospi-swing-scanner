"""
core/decision/market_breadth.py — 시장 Breadth 지표 계산.

시총 상위 N종목의 1D parquet을 읽어 상승 비율, MA20 상회 비율,
평균 변동성, 거래대금 상위 수익률을 반환한다. 추가 fetch 없음.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from core.cache.ohlcv_disk import OhlcvDiskCache

logger = logging.getLogger(__name__)


def compute_market_breadth(
    cache_root: Path,
    tf: str = "1D",
    max_tickers: int = 200,
) -> dict:
    """시총 상위 max_tickers 종목의 breadth 지표 계산.

    반환:
        {
          "up_ratio": float,            # 상승종목 비율 (0~1)
          "above_ma20_ratio": float,    # MA20 상회 종목 비율
          "avg_atr_pct": float,         # 평균 ATR% (14일 고저 평균 / 종가)
          "top_volume_return_avg": float,  # 거래대금 상위 50종목 평균 수익률
        }
    데이터 부족 시 빈 dict 반환.
    """
    root = Path(cache_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        tickers_meta = manifest.get("tickers_meta", {})
    except Exception:
        return {}

    sorted_tickers = sorted(
        tickers_meta.items(),
        key=lambda x: x[1].get("market_cap_bil", 0),
        reverse=True,
    )
    selected = sorted_tickers[:max_tickers]

    disk = OhlcvDiskCache(root)
    results = []

    for ticker, _ in selected:
        try:
            df = disk.read(ticker, tf)
            if df.empty or len(df) < 2:
                continue
            last_close = float(df["close"].iloc[-1])
            prev_close = float(df["close"].iloc[-2])
            ret = (last_close - prev_close) / prev_close if prev_close else 0.0

            ma20 = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else None
            above_ma20 = (last_close > ma20) if ma20 is not None and ma20 == ma20 else None

            atr_pct: float | None = None
            if len(df) >= 14 and "high" in df.columns and "low" in df.columns:
                atr_raw = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
                if atr_raw == atr_raw and last_close:  # NaN guard
                    atr_pct = float(atr_raw / last_close * 100)

            volume = float(df["volume"].iloc[-1]) if "volume" in df.columns else None

            results.append({
                "ret": ret,
                "above_ma20": above_ma20,
                "atr_pct": atr_pct,
                "volume": volume,
            })
        except Exception as e:
            logger.debug(f"breadth {ticker} 실패: {e}")
            continue

    if not results:
        return {}

    rets = [r["ret"] for r in results]
    up_ratio = sum(1 for r in rets if r > 0) / len(rets)

    above_list = [r["above_ma20"] for r in results if r["above_ma20"] is not None]
    above_ma20_ratio = float(np.mean(above_list)) if above_list else None

    atr_list = [r["atr_pct"] for r in results if r["atr_pct"] is not None]
    avg_atr_pct = float(np.mean(atr_list)) if atr_list else None

    vol_ret = [(r["volume"], r["ret"]) for r in results if r["volume"] is not None]
    vol_ret.sort(key=lambda x: x[0], reverse=True)
    top50 = vol_ret[:50]
    top_volume_return_avg = float(np.mean([r for _, r in top50])) if top50 else None

    return {
        "up_ratio": round(up_ratio, 4),
        "above_ma20_ratio": round(above_ma20_ratio, 4) if above_ma20_ratio is not None else None,
        "avg_atr_pct": round(avg_atr_pct, 4) if avg_atr_pct is not None else None,
        "top_volume_return_avg": round(top_volume_return_avg, 6) if top_volume_return_avg is not None else None,
    }
