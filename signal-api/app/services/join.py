"""signals.json + market_snapshot.json 응답 시점 조인 헬퍼.

옵션 B 디자인: cli.py 가 만든 signals.json 의 fundamentals/flow/external_links 는
*매핑 시점 freeze* 라 collect.py 가 갱신해도 stale. 응답 시 latest market_snapshot 의
ticker 정보로 override 해서 항상 fresh 한 참고 지표를 UI 에 노출.

live_quote/trade_plan/signal_date 는 cli.py 가 *동일 시점*으로 묶어 박은 거라
override 안 함 (사용자 의도: 현재가·trade_plan 일관성).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


# UI catalog 카드용 timeframe 라벨 (signal-web/src/types/signal.ts 와 매칭)
_TIMEFRAME_KEYS = {"1D": "rsi_1d", "1h": "rsi_1h", "30m": "rsi_30m"}


def apply_snapshot_overlay(
    signal: dict[str, Any], snapshot_ticker: dict[str, Any] | None
) -> dict[str, Any]:
    """signal entry 를 deepcopy 해서 fundamentals/flow/external_links 만 latest 로 override.

    snapshot_ticker 가 None 이면 signal 그대로 반환 (deepcopy).
    """
    out = deepcopy(signal)
    if snapshot_ticker is None:
        return out
    if "fundamentals" in snapshot_ticker:
        out["fundamentals"] = snapshot_ticker["fundamentals"]
    if "flow" in snapshot_ticker:
        out["flow"] = snapshot_ticker["flow"]
    if "external_links" in snapshot_ticker:
        out["external_links"] = snapshot_ticker["external_links"]
    return out


def merge_rsi_by_timeframe(
    entries: list[dict[str, Any]],
    snapshot_rsi: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    """timeframe 별 rsi_14 를 분배.

    우선순위: snapshot.tickers[ticker].rsi_by_tf (ticker 의 indicator, strategy 후보 여부와 무관) →
    signals 의 strategy entries 의 rsi_14 (fallback).

    반환: {"rsi_1d": ..., "rsi_1h": ..., "rsi_30m": ...}.
    """
    out: dict[str, float | None] = {"rsi_1d": None, "rsi_1h": None, "rsi_30m": None}
    # 1) snapshot 의 ticker 단위 RSI 우선
    if snapshot_rsi:
        for tf, key in _TIMEFRAME_KEYS.items():
            val = snapshot_rsi.get(tf)
            if val is not None:
                out[key] = val
    # 2) signals entries 로 빈 자리 채움
    for entry in entries:
        strategy = entry.get("strategy") or {}
        tf = strategy.get("timeframe")
        key = _TIMEFRAME_KEYS.get(tf)
        if key is None:
            continue
        if out[key] is not None:
            continue
        rsi_14 = (entry.get("trade_plan") or {}).get("rsi_14")
        if rsi_14 is not None:
            out[key] = rsi_14
    return out


def pick_base_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """ticker 의 entries 중 highest score 를 base 로 선택. score 없으면 첫 번째."""
    if not entries:
        raise ValueError("empty entries")

    def _score(e: dict[str, Any]) -> float:
        ranking = e.get("ranking") or {}
        s = ranking.get("score")
        return float(s) if s is not None else float("-inf")

    return max(entries, key=_score)


def build_aggregated_signal(
    entries: list[dict[str, Any]],
    snapshot_ticker: dict[str, Any] | None,
) -> dict[str, Any]:
    """ticker 의 모든 entries 를 합쳐 단일 응답 dict 생성.

    - base = highest score entry (deepcopy + snapshot overlay).
    - trade_plan 에 rsi_1d/rsi_1h/rsi_30m merge: snapshot.rsi_by_tf 우선, entries fallback.
    """
    base = pick_base_entry(entries)
    out = apply_snapshot_overlay(base, snapshot_ticker)
    snapshot_rsi = (snapshot_ticker or {}).get("rsi_by_tf")
    rsi_merged = merge_rsi_by_timeframe(entries, snapshot_rsi)
    trade_plan = out.setdefault("trade_plan", {})
    for key, val in rsi_merged.items():
        trade_plan[key] = val
    return out


def overlay_signals_list(
    raw: dict[str, Any],
    tickers: dict[str, Any],
) -> dict[str, Any]:
    """signals.json 의 raw dict 전체를 deepcopy 후 각 signal 에 overlay 적용.

    tickers 는 LoadedMarket.tickers (ticker_id → TickerSnapshot dict).
    """
    out = deepcopy(raw)
    new_signals = []
    for s in out.get("signals", []):
        ticker = s.get("ticker")
        new_signals.append(apply_snapshot_overlay(s, tickers.get(ticker)))
    out["signals"] = new_signals
    return out
