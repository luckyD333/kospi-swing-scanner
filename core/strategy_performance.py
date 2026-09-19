"""운영 signal의 1D 다음 거래일 성과를 계산하는 deep module.

이 모듈은 전략을 다시 실행하지 않는다. 이미 archive에 저장된 signal과
1D OHLCV를 입력으로 받아, 운영 시점에 실제로 노출된 후보의 성과만 계산한다.
"""
from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


PERFORMANCE_SCHEMA_VERSION = "1.1"
DEFAULT_COST_PCT = 0.30

# UI에 노출하는 canonical 전략 순서. strict base는 의도적으로 제외한다.
STRATEGY_DEFINITIONS: dict[str, dict[str, Any]] = {
    "strategy_one_original": {
        "label": "Strategy One · Original",
        "source_ids": ("strategy_one_d_v2_r1",),
    },
    "strategy_one_improved": {
        "label": "Strategy One · Improved",
        "source_ids": ("strategy_one_d_v2_r2",),
    },
    "strategy_two": {
        "label": "Strategy Two",
        "source_ids": ("strategy_two_cross_sectional_momentum",),
    },
    "strategy_three": {
        "label": "Strategy Three",
        "source_ids": ("strategy_three_trend_following",),
    },
    "strategy_four": {
        "label": "Strategy Four",
        "source_ids": ("strategy_four_pullback_ma",),
    },
    "strategy_five": {
        "label": "Strategy Five",
        "source_ids": ("strategy_five_bull_flag",),
    },
    "strategy_six": {
        "label": "Strategy Six",
        "source_ids": ("strategy_six_channel_grid",),
    },
    "strategy_seven": {
        "label": "Strategy Seven",
        "source_ids": ("strategy_seven_cfi",),
    },
}

_SOURCE_TO_CANONICAL = {
    source_id: key
    for key, definition in STRATEGY_DEFINITIONS.items()
    for source_id in definition["source_ids"]
}


def canonical_strategy_key(strategy_id: str | None, timeframe: str | None) -> str | None:
    """1D 운영 signal을 UI canonical 전략 키로 변환한다."""
    if not strategy_id or str(timeframe).upper() != "1D":
        return None
    return _SOURCE_TO_CANONICAL.get(strategy_id)


def _date_key(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        return timestamp.date().isoformat()
    except (TypeError, ValueError):
        return None


def _timestamp_for_sort(value: Any) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        return timestamp
    except (TypeError, ValueError):
        return pd.Timestamp.min


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _snapshot_as_of(snapshot: dict[str, Any]) -> str | None:
    """snapshot의 실제 노출일을 명시값 우선순위대로 결정한다."""
    target_date = _date_key(snapshot.get("target_date"))
    if target_date is not None:
        return target_date

    generated_date = _date_key(snapshot.get("generated_at"))
    if generated_date is not None:
        return generated_date

    filename = Path(str(snapshot.get("source_file") or "")).name
    match = re.fullmatch(r"signals_(\d{4}-\d{2}-\d{2})\.json", filename)
    return _date_key(match.group(1)) if match else None


def _normalised_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(pd.to_datetime(df.index))
    if index.tz is not None:
        index = index.tz_localize(None)
    return index.normalize()


def _lookup_close_pair(
    df: pd.DataFrame,
    exposure_date: str,
) -> tuple[float, float, str] | None:
    """최초 노출일 이하의 최근 close와 다음 거래일 close를 찾는다."""
    if df.empty or "close" not in df.columns:
        return None

    target = pd.Timestamp(exposure_date)
    dates = _normalised_index(df)
    anchor_positions = [i for i, value in enumerate(dates) if value <= target]
    if not anchor_positions:
        return None

    signal_position = max(anchor_positions, key=lambda i: dates[i])
    anchor_date = dates[signal_position]
    future_positions = [i for i, value in enumerate(dates) if value > anchor_date]
    if not future_positions:
        return None

    evaluation_position = min(future_positions, key=lambda i: dates[i])
    signal_close = _float_or_none(df.iloc[signal_position]["close"])
    evaluation_close = _float_or_none(df.iloc[evaluation_position]["close"])
    if (
        signal_close is None
        or evaluation_close is None
        or signal_close <= 0
        or evaluation_close <= 0
    ):
        return None

    evaluation_date = dates[evaluation_position].date().isoformat()
    return signal_close, evaluation_close, evaluation_date


def _empty_stats() -> dict[str, Any]:
    return {
        "signal_count": 0,
        "evaluated_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "flat_count": 0,
        "win_rate_pct": 0.0,
        "gross_sum_pct": 0.0,
        "net_sum_pct": 0.0,
        "avg_gross_return_pct": 0.0,
        "avg_net_return_pct": 0.0,
        "daily_return_pct": 0.0,
        "cumulative_return_pct": 0.0,
        "profit_factor": None,
    }


def _summarise_records(
    records: list[dict[str, Any]],
    cumulative_return_pct: float,
) -> dict[str, Any]:
    if not records:
        stats = _empty_stats()
        stats["cumulative_return_pct"] = round(cumulative_return_pct, 2)
        return stats

    gross = [float(record["gross_return_pct"]) for record in records]
    net = [float(record["net_return_pct"]) for record in records]
    wins = [value for value in net if value > 0]
    losses = [value for value in net if value < 0]
    flats = len(net) - len(wins) - len(losses)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "signal_count": len(records),
        "evaluated_count": len(records),
        "win_count": len(wins),
        "loss_count": len(losses),
        "flat_count": flats,
        "win_rate_pct": round(len(wins) / len(net) * 100, 2),
        "gross_sum_pct": round(sum(gross), 2),
        "net_sum_pct": round(sum(net), 2),
        "avg_gross_return_pct": round(sum(gross) / len(gross), 2),
        "avg_net_return_pct": round(sum(net) / len(net), 2),
        "daily_return_pct": round(sum(net) / len(net), 2),
        "cumulative_return_pct": round(cumulative_return_pct, 2),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else None,
    }


def _zero_totals() -> dict[str, dict[str, Any]]:
    return {key: _empty_stats() for key in STRATEGY_DEFINITIONS}


def build_performance_payload(
    snapshots: list[dict[str, Any]],
    ohlcv_by_ticker: dict[str, pd.DataFrame],
    *,
    retention_months: int = 6,
    cost_pct: float = DEFAULT_COST_PCT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """archive snapshot과 OHLCV로 rolling 성과 payload를 생성한다.

    같은 ``signal_date + canonical_strategy + ticker``가 여러 snapshot에 있으면
    최초 노출 snapshot을 한 번만 사용한다.
    """
    first_signals: dict[tuple[str, str, str], dict[str, Any]] = {}
    ordered_snapshots = sorted(
        snapshots,
        key=lambda snapshot: _timestamp_for_sort(snapshot.get("generated_at")),
    )

    for snapshot in ordered_snapshots:
        snapshot_date = _snapshot_as_of(snapshot)
        source_file = snapshot.get("source_file")
        for signal in snapshot.get("signals", []) or []:
            strategy = signal.get("strategy") or {}
            strategy_id = strategy.get("id")
            strategy_key = canonical_strategy_key(strategy_id, strategy.get("timeframe"))
            signal_date = _date_key(signal.get("signal_date")) or snapshot_date
            ticker = str(signal.get("ticker") or "")
            if strategy_key is None or signal_date is None or not ticker:
                continue
            first_signals.setdefault((signal_date, strategy_key, ticker), {
                "signal": signal,
                "strategy_key": strategy_key,
                "signal_date": signal_date,
                "exposure_date": snapshot_date,
                "source_strategy_id": strategy_id,
                "source_file": source_file,
                "snapshot_date": snapshot_date,
            })

    evaluated: list[dict[str, Any]] = []
    for item in first_signals.values():
        ticker = str(item["signal"].get("ticker"))
        frame = ohlcv_by_ticker.get(ticker)
        pair = (
            _lookup_close_pair(frame, item["exposure_date"])
            if frame is not None and item["exposure_date"] is not None
            else None
        )
        if pair is None:
            continue
        signal_close, evaluation_close, evaluation_date = pair
        gross_return = (evaluation_close / signal_close - 1.0) * 100
        net_return = gross_return - cost_pct
        if net_return > 0:
            outcome = "WIN"
        elif net_return < 0:
            outcome = "LOSS"
        else:
            outcome = "FLAT"

        signal = item["signal"]
        ranking = signal.get("ranking") or {}
        rank = ranking.get("rank", signal.get("rank"))
        try:
            rank = int(rank) if rank is not None else None
        except (TypeError, ValueError):
            rank = None

        evaluated.append({
            "evaluation_date": evaluation_date,
            "signal_date": item["signal_date"],
            "strategy_key": item["strategy_key"],
            "source_strategy_id": item["source_strategy_id"],
            "source_file": item["source_file"],
            "ticker": ticker,
            "name": signal.get("name") or ticker,
            "rank": rank,
            "signal_close": round(signal_close, 4),
            "evaluation_close": round(evaluation_close, 4),
            "gross_return_pct": round(gross_return, 4),
            "net_return_pct": round(net_return, 4),
            "outcome": outcome,
        })

    if not evaluated:
        return {
            "schema_version": PERFORMANCE_SCHEMA_VERSION,
            "status": "not_ready",
            "updated_at": generated_at or datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
            "window": {"from": None, "to": None},
            "evaluation": {
                "timeframe": "1D",
                "basis": "signal_close_to_next_close",
                "horizon_bars": 1,
                "cost_pct": cost_pct,
            },
            "strategies": STRATEGY_DEFINITIONS,
            "daily": [],
            "totals": _zero_totals(),
        }

    latest_evaluation = max(record["evaluation_date"] for record in evaluated)
    cutoff = (
        pd.Timestamp(latest_evaluation) - pd.DateOffset(months=retention_months)
    ).date().isoformat()
    retained = [
        record for record in evaluated
        if record["evaluation_date"] >= cutoff
    ]
    retained.sort(key=lambda record: (
        record["evaluation_date"],
        record["strategy_key"],
        record["rank"] if record["rank"] is not None else 10**9,
        record["ticker"],
    ))

    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for record in retained:
        grouped.setdefault(record["evaluation_date"], {}).setdefault(
            record["strategy_key"], [],
        ).append(record)

    cumulative_factors = {key: 1.0 for key in STRATEGY_DEFINITIONS}
    daily: list[dict[str, Any]] = []
    for evaluation_date in sorted(grouped):
        by_strategy: dict[str, dict[str, Any]] = {}
        for strategy_key in STRATEGY_DEFINITIONS:
            records = grouped[evaluation_date].get(strategy_key, [])
            daily_return = (
                sum(float(record["net_return_pct"]) for record in records) / len(records)
                if records else 0.0
            )
            cumulative_factors[strategy_key] *= 1.0 + daily_return / 100.0
            stats = _summarise_records(
                records,
                (cumulative_factors[strategy_key] - 1.0) * 100,
            )
            by_strategy[strategy_key] = stats
        daily.append({
            "evaluation_date": evaluation_date,
            "by_strategy": by_strategy,
        })

    totals: dict[str, dict[str, Any]] = {}
    for strategy_key in STRATEGY_DEFINITIONS:
        records = [record for record in retained if record["strategy_key"] == strategy_key]
        cumulative = cumulative_factors[strategy_key]
        totals[strategy_key] = _summarise_records(
            records,
            (cumulative - 1.0) * 100,
        )
    return {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "status": "ready",
        "updated_at": generated_at or datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "window": {
            "from": min(record["evaluation_date"] for record in retained),
            "to": latest_evaluation,
        },
        "evaluation": {
            "timeframe": "1D",
            "basis": "signal_close_to_next_close",
            "horizon_bars": 1,
            "cost_pct": cost_pct,
        },
        "strategies": STRATEGY_DEFINITIONS,
        "daily": daily,
        "totals": totals,
    }
