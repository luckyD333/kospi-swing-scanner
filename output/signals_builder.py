# output/signals_builder.py
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
from output.models import (
    Fundamentals, Flow,
    SignalsPayload, Signal, TradePlan, Ranking, LiveQuote, LiveQuoteDisplay,
    StrategyContext, MarketSnapshot, MarketIndexDisplay,
)

KST = ZoneInfo("Asia/Seoul")

_STRATEGY_LABELS: dict[str, tuple[str, str]] = {
    "strategy_one_d_v2":   ("STRATEGY ONE", "MEAN REVERSION"),
    "strategy_one_1h_v2":  ("STRATEGY ONE", "MEAN REVERSION"),
    "strategy_two_cross_sectional_momentum": ("STRATEGY TWO", "MOMENTUM"),
    "strategy_three_trend_following": ("STRATEGY THREE", "TREND FOLLOWING"),
}

# strategy가 metadata에 저장하는 소문자 값 → Pydantic Literal 대문자 값
_BAND_MAP: dict[str, str] = {
    "below": "UNDER",
    "sweet": "SWEET",
    "over":  "OVER",
}


def _fmt_krw(val: int | None) -> str | None:
    if val is None:
        return None
    bil = val / 1e8
    if bil >= 10000:
        jo  = int(bil // 10000)
        rem = int(bil % 10000)
        return f"₩{jo}조 {rem:,}억" if rem else f"₩{jo}조"
    return f"₩{int(bil):,}억"


def _fmt_pct(val: float | None, positive_prefix: str = "") -> str | None:
    if val is None:
        return None
    prefix = positive_prefix if val > 0 else ""
    return f"{prefix}{val:.2f}%"


def _direction(change_pct: float) -> str:
    if change_pct > 0:
        return "up"
    elif change_pct < 0:
        return "down"
    return "flat"


def build_signals_payload(
    snapshot: MarketSnapshot,
    candidates_by_strategy: dict[str, list],
) -> SignalsPayload:
    # market_indices (display-ready)
    mi_display: dict[str, MarketIndexDisplay] = {}
    label_map = {
        "kospi": "코스피", "kosdaq": "코스닥",
        "usd_krw": "USD/KRW", "wti": "WTI",
        "vix": "VIX", "kr_treasury_3y": "국고채 3Y",
    }
    for key, idx in snapshot.market_indices.items():
        val = idx.value if hasattr(idx, "value") else idx["value"]
        chg = idx.change_pct if hasattr(idx, "change_pct") else idx["change_pct"]
        mi_display[key] = MarketIndexDisplay(
            label=label_map.get(key, key),
            value_display=f"{val:,.2f}",
            change_display=_fmt_pct(chg, positive_prefix="+") or "0.00%",
            direction=_direction(chg),
        )

    strategy_names = sorted({
        _STRATEGY_LABELS.get(s, (s.upper(), ""))[0]
        for s in candidates_by_strategy
    })

    # 전체 candidates 수집 → score 내림차순 정렬
    all_candidates: list[tuple[str, object]] = []
    for strategy_id, candidates in candidates_by_strategy.items():
        for c in candidates:
            all_candidates.append((strategy_id, c))
    all_candidates.sort(key=lambda x: x[1].score, reverse=True)
    total = len(all_candidates)

    signals: list[Signal] = []
    for rank_idx, (strategy_id, c) in enumerate(all_candidates, start=1):
        label, category = _STRATEGY_LABELS.get(strategy_id, (strategy_id.upper(), ""))
        tf = getattr(c, "timeframe", "1D")

        meta = getattr(c, "metadata", {}) or {}
        entry = int(getattr(c, "entry_price", 0))
        stop  = int(getattr(c, "stop_loss",   0))
        t1    = int(getattr(c, "target_1",    0))
        t2_raw = getattr(c, "target_2", None)
        t2    = int(t2_raw) if t2_raw else None

        rr_ratio = float(meta.get("rr_ratio", 0.0))
        rr_band_raw = str(meta.get("rr_band", "below")).lower()
        rr_band = _BAND_MAP.get(rr_band_raw, "UNDER")
        atr_14_raw = meta.get("atr_14")
        atr_14 = int(atr_14_raw) if atr_14_raw else None

        ticker_snap = snapshot.tickers.get(c.ticker)
        cp   = ticker_snap.current_price if ticker_snap else entry
        chg  = ticker_snap.change_pct    if ticker_snap else 0.0
        vol  = ticker_snap.volume        if ticker_snap else 0
        mcap = ticker_snap.market_cap_krw if ticker_snap else None
        fund = ticker_snap.fundamentals   if ticker_snap else Fundamentals()
        flow = ticker_snap.flow           if ticker_snap else Flow()

        naver_url = str(meta.get("naver_url", ""))

        signals.append(Signal(
            ticker=c.ticker,
            name=c.name,
            strategy=StrategyContext(
                id=strategy_id, label=label, category=category, timeframe=tf
            ),
            trade_plan=TradePlan(
                entry=entry, stop=stop, target_1=t1, target_2=t2,
                rr_ratio=rr_ratio, rr_band=rr_band, atr_14=atr_14,
            ),
            ranking=Ranking(
                score=round(c.score, 1),
                rank=rank_idx,
                percentile=round((1 - rank_idx / total) * 100, 1) if total > 1 else 100.0,
            ),
            live_quote=LiveQuote(
                current_price=cp, change_pct=chg, volume=vol, market_cap_krw=mcap,
                **{"_display": LiveQuoteDisplay(
                    current_price=f"₩{cp:,}",
                    change=_fmt_pct(chg, positive_prefix="+") or "0.00%",
                    direction=_direction(chg),
                    volume=f"{vol:,}",
                    market_cap=_fmt_krw(mcap),
                )}
            ),
            fundamentals=fund,
            flow=flow,
            external_links={"naver_finance": naver_url} if naver_url else {},
        ))

    by_strategy: dict[str, int] = {}
    by_rr_band: dict[str, int] = {}
    for s in signals:
        by_strategy[s.strategy.label] = by_strategy.get(s.strategy.label, 0) + 1
        by_rr_band[s.trade_plan.rr_band] = by_rr_band.get(s.trade_plan.rr_band, 0) + 1

    now_kst = datetime.now(KST)
    return SignalsPayload(
        generated_at=now_kst.isoformat(),
        generated_at_display=now_kst.strftime("%Y-%m-%d %H:%M KST"),
        market_indices=mi_display,
        filters={
            "strategies": ["ALL"] + strategy_names,
            "timeframes":  ["ALL", "1H", "4H", "1D"],
            "sort_options": ["score", "rr_ratio", "entry"],
        },
        signals=signals,
        stats={
            "total_signals": total,
            "by_strategy": by_strategy,
            "by_rr_band":  by_rr_band,
        },
    )
