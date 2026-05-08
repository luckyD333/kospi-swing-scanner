# output/snapshot_builder.py
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from output.models import (
    MarketSnapshot, TickerSnapshot, Fundamentals, Flow, MarketIndexRaw
)

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
_LOOKBACK = 252  # 52주 = 약 252 거래일


def build_market_snapshot(
    universe: dict,
    ohlcv_latest: dict[str, dict],
    market_indices: dict[str, dict],
    market_regime: dict | None = None,
    market_breadth: dict | None = None,
    market_axes: dict | None = None,
    fear_greed: dict | None = None,
    signal_tickers: list[str] | None = None,
    cache_root: str | Path | None = None,
) -> MarketSnapshot:
    tickers: dict[str, TickerSnapshot] = {}
    for ticker, meta in universe.get("tickers", {}).items():
        ohlcv = ohlcv_latest.get(ticker, {})
        closes = ohlcv.get("close", [])
        highs  = ohlcv.get("high", [])
        lows   = ohlcv.get("low", [])
        vols   = ohlcv.get("volume", [])

        # tail(252) — 전체 이력 대신 최근 252거래일만 사용
        highs_52w = highs[-_LOOKBACK:] if highs else []
        lows_52w  = lows[-_LOOKBACK:]  if lows  else []

        # 분봉 raw 가 있으면 분봉 close 가 더 최신 — 우선 사용.
        # 단, current_price 가 분봉 EOD 일 때 change_pct/volume 도 일관 source 로
        # 재계산해야 함. 그렇지 않으면 1D parquet 의 장중 stale row 와 mismatch.
        minute_close = ohlcv.get("minute_close")
        if minute_close is not None:
            current_price = int(minute_close)
            # prev_close 결정: 1D 의 마지막 row 가 오늘이면 closes[-2] 가 어제 종가,
            # 아니면 closes[-1] 자체가 어제 종가.
            today_kst = datetime.now(KST).strftime("%Y-%m-%d")
            today_row_present = ohlcv.get("last_date") == today_kst
            prev_close: float | None = None
            if today_row_present and len(closes) >= 2:
                prev_close = float(closes[-2])
            elif not today_row_present and len(closes) >= 1:
                prev_close = float(closes[-1])
            last_chg = (
                (current_price - prev_close) / prev_close * 100
                if prev_close
                else 0.0
            )
            # 분봉 누적 거래량 우선 (1D row 의 stale volume 회피)
            minute_volume = ohlcv.get("minute_volume_today")
            volume = int(minute_volume) if minute_volume is not None else (
                int(vols[-1]) if vols else 0
            )
        else:
            current_price = int(closes[-1]) if closes else 0
            volume = int(vols[-1]) if vols else 0
            change_list = ohlcv.get("change_pct", [0])
            last_chg = (
                float(change_list[-1])
                if isinstance(change_list, list)
                else float(change_list)
            )

        high_52w = int(max(highs_52w)) if highs_52w else None
        low_52w  = int(min(lows_52w))  if lows_52w  else None

        market_cap_bil = meta.get("market_cap_bil")
        market_cap_krw = int(round(market_cap_bil * 1e8)) if market_cap_bil else None

        tickers[ticker] = TickerSnapshot(
            ticker=ticker,
            name=meta.get("name", ""),
            current_price=current_price,
            change_pct=round(last_chg, 2),
            volume=volume,
            market_cap_krw=market_cap_krw,
            fundamentals=Fundamentals(
                per=meta.get("per"),
                per_negative=bool(meta.get("per_negative", False)),
                high_52w=high_52w,
                low_52w=low_52w,
            ),
            flow=Flow(
                foreign_ratio_pct=meta.get("foreign_pct"),
            ),
            external_links={"naver_finance": meta.get("naver_url", "")},
            rsi_by_tf=ohlcv.get("rsi_by_tf"),
        )

    # 안전망: universe 에 누락된 signal_tickers 를 disk 1D parquet 로 보강.
    # 호출 측 (collect.py) 의 universe 가 작게 들어가도 시그널 종목은 항상 포함.
    if signal_tickers and cache_root:
        cache_dir_1d = Path(cache_root) / "1D"
        for st in signal_tickers:
            if st in tickers:
                continue
            pq = cache_dir_1d / f"{st}.parquet"
            if not pq.exists():
                continue
            try:
                import pandas as pd
                df = pd.read_parquet(pq)
                if df.empty:
                    continue
                last_close = int(df["close"].iloc[-1])
                last_vol = int(df["volume"].iloc[-1]) if "volume" in df.columns else 0
                tickers[st] = TickerSnapshot(
                    ticker=st,
                    name="",
                    current_price=last_close,
                    change_pct=0.0,
                    volume=last_vol,
                    fundamentals=Fundamentals(),
                    flow=Flow(),
                )
            except Exception as e:
                logger.warning(f"snapshot 안전망 실패 ({st}): {e}")

    indices = {
        k: MarketIndexRaw(value=v["value"], change_pct=v["change_pct"])
        for k, v in market_indices.items()
        if isinstance(v, dict) and "value" in v
    }

    now_kst = datetime.now(KST).isoformat()
    return MarketSnapshot(
        generated_at=now_kst,
        source={"collected_at": now_kst},
        market_indices=indices,
        tickers=tickers,
        market_regime=market_regime,
        market_breadth=market_breadth,
        market_axes=market_axes,
        fear_greed=fear_greed,
    )
