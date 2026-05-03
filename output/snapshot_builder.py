# output/snapshot_builder.py
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from output.models import (
    MarketSnapshot, TickerSnapshot, Fundamentals, Flow, MarketIndexRaw
)

KST = ZoneInfo("Asia/Seoul")
_LOOKBACK = 252  # 52주 = 약 252 거래일


def build_market_snapshot(
    universe: dict,
    ohlcv_latest: dict[str, dict],
    market_indices: dict[str, dict],
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

        current_price = int(closes[-1]) if closes else 0
        volume        = int(vols[-1])   if vols   else 0
        change_list   = ohlcv.get("change_pct", [0])
        last_chg      = float(change_list[-1]) if isinstance(change_list, list) else float(change_list)

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
                pbr=meta.get("pbr"),
                eps=meta.get("eps"),
                dividend_yield_pct=meta.get("dividend_yield_pct"),
                high_52w=high_52w,
                low_52w=low_52w,
            ),
            flow=Flow(
                foreign_ratio_pct=meta.get("foreign_pct"),
                institutional_net_krw=None,
            ),
            external_links={"naver_finance": meta.get("naver_url", "")},
        )

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
    )
