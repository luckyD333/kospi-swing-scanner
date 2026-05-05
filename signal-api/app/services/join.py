"""signals.json + market_snapshot.json 응답 시점 조인 헬퍼.

옵션 B 디자인: cli.py 가 만든 signals.json 의 fundamentals/flow/external_links 는
*매핑 시점 freeze* 라 collect.py 가 갱신해도 stale. 응답 시 latest market_snapshot 의
ticker 정보로 override 해서 항상 fresh 한 참고 지표를 UI 에 노출.

live_quote/trade_plan/signal_date 는 cli.py 가 *동일 시점*으로 묶어 박은 거라
override 안 함 (사용자 의도: 현재가·trade_plan 일관성).
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


# UI catalog 카드용 timeframe 라벨 (signal-web/src/types/signal.ts 와 매칭)
_TIMEFRAME_KEYS = {"1D": "rsi_1d", "1h": "rsi_1h", "30m": "rsi_30m"}

_KST = ZoneInfo("Asia/Seoul")


def compute_signal_status(
    current_price: float | None,
    stop: int | float | None,
    target_1: int | float | None,
    signal_date_str: str | None,
    now: datetime | None = None,
) -> str:
    """API 응답 시점에 신호 상태 계산.

    우선순위:
      1. 장외 시간 (signal_date 거래일 ≠ 오늘 거래일) → STALE 또는 VALID
      2. 같은 거래일 + cp ≤ stop → STOPPED_OUT
      3. 같은 거래일 + cp ≥ target_1 → TARGET_REACHED
      4. 그 외 → VALID

    stop 인자: 호출자가 limit_stop 우선, 없으면 stop 으로 결정해서 전달.
    """
    from core.dates import is_same_trading_day, trading_days_since

    now = now or datetime.now(tz=_KST)
    today = now.date()

    if signal_date_str:
        try:
            sd_dt = datetime.fromisoformat(signal_date_str)
            # naive datetime 이면 KST 로 가정 (signals.json 은 KST 기반 생성)
            if sd_dt.tzinfo is None:
                sd_dt = sd_dt.replace(tzinfo=_KST)
            sd = sd_dt.astimezone(_KST).date()
        except ValueError:
            return "STALE"
        if not is_same_trading_day(sd, today):
            # current_price 가 전일 종가일 가능성 → cp 비교 의미 없음
            if trading_days_since(sd, today) > 3:
                return "STALE"
            return "VALID"

    if current_price is not None and stop is not None and current_price <= stop:
        return "STOPPED_OUT"
    if current_price is not None and target_1 is not None and current_price >= target_1:
        return "TARGET_REACHED"
    return "VALID"


def apply_snapshot_overlay(
    signal: dict[str, Any], snapshot_ticker: dict[str, Any] | None
) -> dict[str, Any]:
    """signal entry 를 deepcopy 해서 fundamentals/flow/external_links 와
    live_quote(current_price/change_pct/volume) 를 latest snapshot 으로 override.

    snapshot_ticker 가 None 이면 signal 그대로 반환 (deepcopy).
    trade_plan(entry/stop/target/rr_ratio) 과 signal_date 는 freeze 유지.
    """
    out = deepcopy(signal)
    if snapshot_ticker is not None:
        if "fundamentals" in snapshot_ticker:
            out["fundamentals"] = snapshot_ticker["fundamentals"]
        if "flow" in snapshot_ticker:
            out["flow"] = snapshot_ticker["flow"]
        if "external_links" in snapshot_ticker:
            out["external_links"] = snapshot_ticker["external_links"]
        # collect_live.py 가 갱신한 현재가 적용 (current_price 있을 때만)
        cp = snapshot_ticker.get("current_price")
        if cp:
            chg = snapshot_ticker.get("change_pct") or 0.0
            vol = snapshot_ticker.get("volume")
            direction = "up" if chg > 0 else ("down" if chg < 0 else "flat")
            existing_lq = out.get("live_quote") or {}
            existing_display = (existing_lq.get("_display") or {})
            out["live_quote"] = {
                **existing_lq,
                "current_price": cp,
                "change_pct": chg,
                "volume": vol,
                "_display": {
                    **existing_display,
                    "current_price": f"{int(cp):,}",
                    "change": f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%",
                    "direction": direction,
                    "volume": f"{int(vol):,}" if vol else existing_display.get("volume"),
                },
            }

    # signal_status 계산 — limit_stop 우선, 없으면 stop
    tp = out.get("trade_plan") or {}
    stop_for_compare = tp.get("limit_stop") or tp.get("stop")
    target_for_compare = tp.get("target_1")
    cp_for_compare = (out.get("live_quote") or {}).get("current_price")
    out["signal_status"] = compute_signal_status(
        current_price=cp_for_compare,
        stop=stop_for_compare,
        target_1=target_for_compare,
        signal_date_str=out.get("signal_date"),
    )
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
