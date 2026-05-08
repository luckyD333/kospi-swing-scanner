"""signals.json + market_snapshot.json 응답 시점 조인 헬퍼.

옵션 B 디자인: cli.py 가 만든 signals.json 의 fundamentals/flow/external_links 는
*매핑 시점 freeze* 라 collect.py 가 갱신해도 stale. 응답 시 latest market_snapshot 의
ticker 정보로 override 해서 항상 fresh 한 참고 지표를 UI 에 노출.

live_quote/trade_plan/signal_date 는 cli.py 가 *동일 시점*으로 묶어 박은 거라
override 안 함 (사용자 의도: 현재가·trade_plan 일관성).
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

# signal-api/app/services/join.py → 레포 루트는 3단계 위
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.dates import is_same_trading_day, trading_days_since


# UI catalog 카드용 timeframe 라벨 (signal-web/src/types/signal.ts 와 매칭)
_TIMEFRAME_KEYS = {"1D": "rsi_1d", "1h": "rsi_1h", "30m": "rsi_30m"}

_KST = ZoneInfo("Asia/Seoul")


def compute_signal_status(
    current_price: float | None,
    stop: int | float | None,
    target_1: int | float | None,
    signal_date_str: str | None,
    now: datetime | None = None,
    timeframe: str | None = None,
) -> str:
    """API 응답 시점에 신호 상태 계산.

    우선순위:
      1. 장외 시간 (signal_date 거래일 ≠ 오늘 거래일) → STALE 또는 VALID
      2. 같은 거래일 + cp ≤ stop → STOPPED_OUT
      3. 같은 거래일 + cp ≥ target_1 → TARGET_REACHED
      4. 장중 TF 신호 만료 (1h: 2봉, 30m: 2봉) → STALE
      5. 그 외 → VALID

    stop 인자: 호출자가 limit_stop 우선, 없으면 stop 으로 결정해서 전달.
    timeframe: "1h" / "30m" 일 때 장중 신호 만료 감지 적용.
    """
    now = now or datetime.now(tz=_KST)
    today = now.date()

    sd_dt: datetime | None = None
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

    # STOPPED_OUT / TARGET_REACHED 는 신호 발생 시각과 무관하게 우선 적용
    if current_price is not None and stop is not None and current_price <= stop:
        return "STOPPED_OUT"
    if current_price is not None and target_1 is not None and current_price >= target_1:
        return "TARGET_REACHED"

    # 장중 TF 신호 만료: 가격 미발동(VALID 후보) 상태에서만 검사
    # 1h: 2봉(2h) 경과, 30m: 2봉(1h) 경과 → 재진입 기회 소멸로 간주
    if sd_dt is not None and timeframe in ("1h", "30m"):
        stale_hours = 2.0 if timeframe == "1h" else 1.0
        age_hours = (now - sd_dt.astimezone(_KST)).total_seconds() / 3600
        if age_hours > stale_hours:
            return "STALE"

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
    strategy_dict = out.get("strategy") or {}
    tf = strategy_dict.get("timeframe") if isinstance(strategy_dict, dict) else None
    out["signal_status"] = compute_signal_status(
        current_price=cp_for_compare,
        stop=stop_for_compare,
        target_1=target_for_compare,
        signal_date_str=out.get("signal_date"),
        timeframe=tf,
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


def aggregate_entries_for_ticker(
    entries: list[dict[str, Any]],
    ticker: str,
    snapshot_ticker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Multi-strategy aggregate response (schema_version 2.0).

    구조:
      {
        "schema_version": "2.0",
        "ticker": ...,
        "name": ...,
        "asset_class": ...,
        "fundamentals": ..., "live_quote": ..., "external_links": ...,
        "potential_score": float,        # ticker 단위 1개 (잠재력)
        "potential_factors": [ ... ],    # 잠재력 factor breakdown
        "matches": [                     # 매칭 strategy 별 N개 (all entry 제외)
          {
            "strategy": {...},
            "signal_strength": int,
            "opportunity_score": int,
            "opportunity_factors": [...],
            "trade_plan": {...},
            "setup_score": int | None,
            "setup_reasons": [...] | None,
          },
        ]
      }
    """
    if not entries:
        raise ValueError("empty entries")

    # base = "all" entry 우선 (potential_score 베이스), snapshot overlay 적용
    all_entry = next((e for e in entries if (e.get("strategy") or {}).get("id") == "all"), None)
    base_meta_raw = all_entry or entries[0]
    base_meta = apply_snapshot_overlay(base_meta_raw, snapshot_ticker)

    # RSI merge: snapshot.rsi_by_tf 우선, entries fallback
    snapshot_rsi = (snapshot_ticker or {}).get("rsi_by_tf")
    rsi_merged = merge_rsi_by_timeframe(entries, snapshot_rsi)

    # matches 배열 (all entry 는 제외, strategy entries 만 포함)
    matches = []
    for e in entries:
        strategy = e.get("strategy") or {}
        if strategy.get("id") == "all":
            continue  # all entry 는 matches 에서 제외

        ranking = e.get("ranking") or {}
        decision = ranking.get("decision") or {}

        # trade_plan 에 RSI merge 적용
        trade_plan = dict(e.get("trade_plan") or {})
        for k, v in rsi_merged.items():
            if v is not None or k not in trade_plan:
                trade_plan[k] = v

        match = {
            "strategy": strategy,
            "signal_strength": ranking.get("signal_strength", 0),
            "opportunity_score": decision.get("regret_score", 0),
            "opportunity_factors": decision.get("regret_factors", []),
            "trade_plan": trade_plan,
            "setup_score": e.get("setup_score"),
            "setup_reasons": e.get("setup_reasons"),
            "signal_components": e.get("signal_components") or [],
            "_score": ranking.get("score", 0),  # 정렬용
        }
        matches.append(match)

    # matches 정렬: highest ranking.score 순 (= base entry 가 matches[0])
    matches.sort(key=lambda m: m.pop("_score"), reverse=True)

    # 최상위 응답 구조
    base_ranking = base_meta.get("ranking") or {}
    base_decision = base_ranking.get("decision") or {}

    return {
        "schema_version": "2.0",
        "ticker": ticker,
        "name": base_meta.get("name"),
        "asset_class": base_meta.get("asset_class"),
        "fundamentals": base_meta.get("fundamentals"),
        "flow": base_meta.get("flow"),
        "live_quote": base_meta.get("live_quote"),
        "external_links": base_meta.get("external_links"),
        "potential_score": base_decision.get("final_score", 0),
        "potential_factors": base_decision.get("factors", []),
        "matches": matches,
        # 호환 필드 (signal_date, active_regime, signal_status, tradability_score 등)
        "signal_date": base_meta.get("signal_date"),
        "signal_status": base_meta.get("signal_status"),
        "active_regime": base_meta.get("active_regime"),
        "tradability_score": base_meta.get("tradability_score"),
        "product_type": base_meta.get("product_type"),
    }


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
