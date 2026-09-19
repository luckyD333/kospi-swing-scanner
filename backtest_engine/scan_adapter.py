"""scan_adapter.py — Strategy Protocol(scan) → WF scorer 변환.

기존 BacktestEngine 은 StrategyD 전용 (check_entry/check_exit/prepare 필수).
S2~S5 는 scan(ctx, top_n) → list[Candidate] 만 노출하므로 직접 호환 X.

두 어댑터 공존:
  1. `make_scan_pnl_scorer` — N봉 후 단순 종가 청산 (stop/target 무시).
     진입 파라미터 검증용. 기존 WF 결과 회귀 안전.
  2. `make_scan_bartracker_scorer` — Candidate.stop_loss/target_2 를 bar-by-bar 추적.
     청산 파라미터 (S3 atr_stop_mult 등) 검증 가능.

WF scorer 시그니처 (walk_forward.run_walk_forward 와 동일):
    scorer(ohlcv_data, params, start, end) -> (sharpe, n_trades)
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.decision.per_ticker_regime import build_regime_grid, regime_at
from core.strategy_base import ScanContext, Strategy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanPnlConfig:
    """N봉 PnL 평가 설정."""
    holding_bars: int = 5        # 진입 후 N봉 보유 (CLAUDE.md: 1~7일 spec, default 5 = S1 sweet spot)
    top_n: int = 5               # scan() 호출당 채택 후보 수 (max_positions=5 매칭)
    commission_pct: float = 0.0030  # 왕복 0.30% (BacktestConfig 기본과 일치)
    lookback_buffer_days: int = 60  # S3·S4 lookback 30 + 여유 (S1=45, S3·S4 더 필요)
    market: str = "KOSPI"
    max_entry_gap_pct: float | None = None  # T+1 open 갭상승 한도 — 초과 시 체결 skip (감사 F6). None=무제한
    # False 면 per_ticker_regime 을 안 채워 entry_gate 가 우회된다.
    # 게이트 적용 이전 기준선을 재현할 때만 쓴다.
    apply_entry_gate: bool = True


def _build_ctx(
    target_date: pd.Timestamp,
    ohlcv: dict[str, pd.DataFrame],
    market: str,
    regime_grid: dict[str, pd.Series] | None = None,
) -> ScanContext:
    """target_date 이하 봉만 포함한 ScanContext 생성. look-ahead 방지.

    lookback 부족 시 스킵은 각 전략이 책임 (S2~S5 의 min_bars 검사).

    regime_grid: build_regime_grid() 결과. 주면 per_ticker_regime 이 채워져
      entry gate 가 실제로 동작한다. None 이면 entry_gate 가 우회된다.
      donchian_1h_by_ticker 는 .cache_wf 에 1h 가 없어 항상 비어 있다.
    """
    sliced: dict[str, pd.DataFrame] = {}
    for ticker, df in ohlcv.items():
        sub = df[df.index <= target_date]
        if len(sub) > 0:
            sliced[ticker] = sub
    universe = tuple(sliced.keys())

    per_ticker_regime: dict[str, str] = {}
    if regime_grid is not None:
        for ticker in universe:
            label = regime_at(regime_grid, ticker, target_date)
            if label is not None:
                per_ticker_regime[ticker] = label

    return ScanContext(
        target_date=target_date.strftime("%Y%m%d"),
        universe=universe,
        ohlcv=sliced,
        names={t: t for t in universe},
        market_caps={t: 10_000.0 for t in universe},  # fragility 측정에는 무관
        market=market,
        per_ticker_regime=per_ticker_regime,
    )


def _gap_exceeds(
    full_df: pd.DataFrame,
    signal_date: pd.Timestamp,
    entry_price: float,
    max_gap_pct: float | None,
) -> bool:
    """T+1 open(entry_price) 이 시그널 시점 마지막 close 대비 한도 초과 갭상승인지.

    WF 검증 (2026-06-12, scripts/wf_validate_gap_filter.py): threshold 튜닝은
    unstable FAIL — 고정값(예: 0.03) 사용 전제. 갭하락은 제한하지 않음 (음수 갭 허용).
    """
    if max_gap_pct is None:
        return False
    prior = full_df[full_df.index <= signal_date]
    if prior.empty:
        return False
    signal_close = float(prior.iloc[-1]["close"])
    if signal_close <= 0:
        return False
    return entry_price / signal_close - 1.0 > max_gap_pct


# regime grid 는 파라미터와도, scorer 인스턴스와도 무관하다. ohlcv_data 객체당 1회만 만든다.
# 모듈 수준인 이유: scripts/aggregate_holding_recommendations.py 가 전략 × holdings
# 이중 루프 안에서 scorer factory 를 28번 부른다. 클로저 캐시면 grid 도 28번 만들어진다.
# clear() 로 1칸만 유지하고, 참조를 함께 들고 있어 id() 재사용으로 엉뚱한 grid 를 쓰지 않는다.
_REGIME_GRID_CACHE: dict[int, tuple[dict, dict]] = {}


def _regime_grid_for(
    ohlcv_data: dict[str, pd.DataFrame], apply_entry_gate: bool
) -> dict | None:
    if not apply_entry_gate:
        return None
    key = id(ohlcv_data)
    hit = _REGIME_GRID_CACHE.get(key)
    if hit is not None and hit[0] is ohlcv_data:
        return hit[1]
    grid = build_regime_grid(ohlcv_data)
    # .cache_wf 에 1h 가 없어 setup_score 가 항상 None 이다.
    # entry_gate 의 allow_strong_only 셀이 전부 block 되므로
    # S1(UPTREND_STRONG·RANGE_TIGHT·MIXED)과 S4(RANGE_TIGHT)는 실운영보다 엄격하다.
    # grid 를 새로 만들 때만 남긴다 — scorer 본문에 두면 파라미터 시도마다 찍힌다.
    logger.warning(
        "WF entry gate: 1h 데이터 없음 → setup_score=None, "
        "allow_strong_only 셀은 전부 block (S1·S4 편향 주의)"
    )
    _REGIME_GRID_CACHE.clear()
    _REGIME_GRID_CACHE[key] = (ohlcv_data, grid)
    return grid


def make_scan_pnl_scorer(
    strategy_factory: Callable[[dict], Strategy],
    scoring: ScanPnlConfig | None = None,
) -> Callable[
    [dict[str, pd.DataFrame], dict, pd.Timestamp, pd.Timestamp],
    tuple[float, int],
]:
    """WF scorer factory.

    Args:
        strategy_factory: params dict 받아 Strategy 인스턴스 반환하는 callable.
            예: lambda p: StrategyFiveBullFlag(config=StrategyFiveConfig(**p))
        scoring: PnL 평가 설정. None 이면 기본값 (3봉/5종목/0.30%).

    Returns:
        scorer(ohlcv_data, params, start, end) -> (sharpe, n_trades)
        WF run_walk_forward 의 evaluator 인자에 그대로 전달 가능.
    """
    cfg = scoring or ScanPnlConfig()

    def scorer(
        ohlcv_data: dict[str, pd.DataFrame],
        params: dict,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> tuple[float, int]:
        # 1) lookback buffer 포함 슬라이스 (전략 lookback 부족은 strategy 가 책임)
        buffered_start = start - pd.Timedelta(days=cfg.lookback_buffer_days)
        sliced: dict[str, pd.DataFrame] = {}
        for ticker, df in ohlcv_data.items():
            sub = df[(df.index >= buffered_start) & (df.index <= end)]
            if len(sub) > 0:
                sliced[ticker] = sub
        if not sliced:
            return float("nan"), 0

        # 2) signal 발생 가능 거래일 = [start, end] 내 모든 거래일
        all_dates = sorted(set().union(*[df.index for df in sliced.values()]))
        signal_dates = [d for d in all_dates if start <= d <= end]
        if not signal_dates:
            return float("nan"), 0

        # 3) strategy 1회 생성 (instance state 변경 없는 것은 사전 grep 확인됨)
        try:
            strategy = strategy_factory(params)
        except Exception:
            return float("nan"), 0

        grid = _regime_grid_for(ohlcv_data, cfg.apply_entry_gate)

        # 4) 각 signal date 에서 scan → T+1 진입 → T+1+holding_bars 청산
        trades_pnl: list[float] = []
        for d in signal_dates:
            ctx = _build_ctx(d, sliced, market=cfg.market, regime_grid=grid)
            try:
                candidates = strategy.scan(ctx, top_n=cfg.top_n)
            except Exception:
                continue

            for cand in candidates[: cfg.top_n]:
                full_df = ohlcv_data.get(cand.ticker)
                if full_df is None:
                    continue
                # 미래 봉은 원본에서 — sliced 는 end 까지 잘렸을 수 있음
                future = full_df[full_df.index > d]
                if len(future) < cfg.holding_bars + 1:
                    continue  # 미래 봉 부족 → 스킵
                entry_price = float(future.iloc[0]["open"])
                exit_price = float(future.iloc[cfg.holding_bars]["close"])
                if entry_price <= 0:
                    continue
                if _gap_exceeds(full_df, d, entry_price, cfg.max_entry_gap_pct):
                    continue  # 갭상승 추격 체결 제한 (감사 F6)
                gross = (exit_price - entry_price) / entry_price
                trades_pnl.append(gross - cfg.commission_pct)

        # 5) trade-level Sharpe (annualized)
        if len(trades_pnl) < 2:
            return float("nan"), len(trades_pnl)
        arr = np.array(trades_pnl, dtype=float)
        std = float(arr.std(ddof=0))
        if std < 1e-9:
            return 0.0, len(trades_pnl)
        mean = float(arr.mean())
        sharpe = mean / std * np.sqrt(252.0 / cfg.holding_bars)
        return float(sharpe), len(trades_pnl)

    return scorer


# ---------- BarTracker 어댑터 ------------------------------------------------


@dataclass(frozen=True)
class ScanBarConfig:
    """Bar-by-bar stop/target 추적 평가 설정.

    holding_bars 의 의미가 N봉 scorer 와 다름: **최대 보유**.
    조기 stop/target 도달 시 단축 청산, 미도달 시 holding_bars-th bar close 청산.
    """
    holding_bars: int = 5
    top_n: int = 5
    commission_pct: float = 0.0030
    lookback_buffer_days: int = 60
    market: str = "KOSPI"
    emit_stats: bool = False  # True 시 scorer.last_stats 로 exit_reason 분포 노출
    emit_per_trade: bool = False  # True 시 scorer.per_trade_records 로 trade 단위 기록 노출
    max_entry_gap_pct: float | None = None  # T+1 open 갭상승 한도 — 초과 시 체결 skip (감사 F6). None=무제한
    # False 면 per_ticker_regime 을 안 채워 entry_gate 가 우회된다.
    # 게이트 적용 이전 기준선을 재현할 때만 쓴다.
    apply_entry_gate: bool = True


def _track_position(
    future_df: pd.DataFrame,
    entry_price: float,
    stop_loss: float,
    target: float,
    max_holding_bars: int,
) -> tuple[float, int, str]:
    """T+1 부터 시작한 진입 포지션을 bar-by-bar 추적.

    한 봉 처리 우선순위 (보수적 STOP 우선):
      1. open  ≤ stop  → GAP_DOWN, exit=open (실제 슬리피지 반영)
      2. low   ≤ stop  → STOP,     exit=stop
      3. high  ≥ target → TARGET,  exit=target
      4. bars_held == max → TIME,  exit=close

    Args:
        future_df: T+1 부터 시작하는 OHLCV. caller 가 슬라이스 보장.
        entry_price: 진입가 (참고용, 본 함수는 사용 X — 호출자 PnL 계산에서 사용).
        stop_loss: 손절선.
        target: 익절선 (Candidate.target_2 권장).
        max_holding_bars: 최대 보유 봉 수.

    Returns:
        (exit_price, bars_held, exit_reason)
        exit_reason ∈ {STOP, TARGET, TIME, GAP_DOWN, INSUFFICIENT}
        future_df 가 max_holding_bars 보다 짧으면 (NaN, 0, "INSUFFICIENT") → caller skip.
    """
    if len(future_df) < max_holding_bars:
        return float("nan"), 0, "INSUFFICIENT"

    for i in range(max_holding_bars):
        bar = future_df.iloc[i]
        o = float(bar["open"])
        h = float(bar["high"])
        low = float(bar["low"])
        c = float(bar["close"])
        bars_held = i + 1

        # 1) GAP_DOWN — open 이 이미 stop 아래로 하락
        if o <= stop_loss:
            return o, bars_held, "GAP_DOWN"

        # 2) STOP 우선 (같은 봉 tie-break)
        if low <= stop_loss:
            return stop_loss, bars_held, "STOP"

        # 3) TARGET
        if h >= target:
            return target, bars_held, "TARGET"

        # 4) 최대 보유 만기
        if bars_held >= max_holding_bars:
            return c, bars_held, "TIME"

    # 안전망 — 위 루프에서 반드시 반환됨
    last = future_df.iloc[max_holding_bars - 1]
    return float(last["close"]), max_holding_bars, "TIME"


def make_scan_bartracker_scorer(
    strategy_factory: Callable[[dict], Strategy],
    scoring: ScanBarConfig | None = None,
) -> Callable[
    [dict[str, pd.DataFrame], dict, pd.Timestamp, pd.Timestamp],
    tuple[float, int],
]:
    """WF scorer factory — Candidate.stop_loss/target_2 추적.

    Args:
        strategy_factory: params dict 받아 Strategy 인스턴스 반환.
        scoring: 추적 평가 설정. None 이면 기본값 (3봉/5종목/0.30%).

    Returns:
        scorer(ohlcv_data, params, start, end) → (sharpe, n_trades)
        scoring.emit_stats=True 면 scorer.last_stats 속성에 exit_reason 분포 누적.
    """
    cfg = scoring or ScanBarConfig()

    def scorer(
        ohlcv_data: dict[str, pd.DataFrame],
        params: dict,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> tuple[float, int]:
        # 1) lookback buffer 포함 슬라이스
        buffered_start = start - pd.Timedelta(days=cfg.lookback_buffer_days)
        sliced: dict[str, pd.DataFrame] = {}
        for ticker, df in ohlcv_data.items():
            sub = df[(df.index >= buffered_start) & (df.index <= end)]
            if len(sub) > 0:
                sliced[ticker] = sub
        if not sliced:
            return float("nan"), 0

        # 2) signal 발생 가능 거래일
        all_dates = sorted(set().union(*[df.index for df in sliced.values()]))
        signal_dates = [d for d in all_dates if start <= d <= end]
        if not signal_dates:
            return float("nan"), 0

        # 3) strategy 1회 생성
        try:
            strategy = strategy_factory(params)
        except Exception:
            return float("nan"), 0

        grid = _regime_grid_for(ohlcv_data, cfg.apply_entry_gate)

        # 4) 각 signal date 에서 scan → T+1 진입 → bar-by-bar 청산
        trades_pnl: list[float] = []
        bars_held_all: list[int] = []
        stats = {"STOP": 0, "TARGET": 0, "TIME": 0, "GAP_DOWN": 0}
        per_trade: list[dict] = []

        for d in signal_dates:
            ctx = _build_ctx(d, sliced, market=cfg.market, regime_grid=grid)
            try:
                candidates = strategy.scan(ctx, top_n=cfg.top_n)
            except Exception:
                continue

            for cand in candidates[: cfg.top_n]:
                full_df = ohlcv_data.get(cand.ticker)
                if full_df is None:
                    continue
                future = full_df[full_df.index > d]
                if len(future) < cfg.holding_bars:
                    continue
                entry_price = float(future.iloc[0]["open"])
                if entry_price <= 0:
                    continue
                if _gap_exceeds(full_df, d, entry_price, cfg.max_entry_gap_pct):
                    continue  # 갭상승 추격 체결 제한 (감사 F6)

                exit_price, bars_held, reason = _track_position(
                    future,
                    entry_price=entry_price,
                    stop_loss=cand.stop_loss,
                    target=cand.target_2,
                    max_holding_bars=cfg.holding_bars,
                )
                if reason == "INSUFFICIENT":
                    continue

                gross = (exit_price - entry_price) / entry_price
                pnl_pct = gross - cfg.commission_pct
                trades_pnl.append(pnl_pct)
                bars_held_all.append(bars_held)
                stats[reason] = stats.get(reason, 0) + 1
                if cfg.emit_per_trade:
                    per_trade.append({
                        "signal_date": d,
                        "ticker": cand.ticker,
                        "exit_reason": reason,
                        "pnl_pct": float(pnl_pct),
                        "bars_held": int(bars_held),
                    })

        # 5) emit_stats 통계 노출
        if cfg.emit_stats:
            scorer.last_stats = {  # type: ignore[attr-defined]
                **stats,
                "avg_bars_held": (
                    float(np.mean(bars_held_all)) if bars_held_all else 0.0
                ),
                "entry_gate_applied": grid is not None,
            }
        if cfg.emit_per_trade:
            scorer.per_trade_records = per_trade  # type: ignore[attr-defined]

        # 6) trade-level Sharpe (annualized) — avg_bars_held 기반
        if len(trades_pnl) < 2:
            return float("nan"), len(trades_pnl)
        arr = np.array(trades_pnl, dtype=float)
        std = float(arr.std(ddof=0))
        if std < 1e-9:
            return 0.0, len(trades_pnl)
        mean = float(arr.mean())
        avg_bars = float(np.mean(bars_held_all)) if bars_held_all else float(cfg.holding_bars)
        sharpe = mean / std * np.sqrt(252.0 / max(avg_bars, 1.0))
        return float(sharpe), len(trades_pnl)

    return scorer
