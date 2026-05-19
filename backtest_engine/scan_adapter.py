"""scan_adapter.py — Strategy Protocol(scan) → WF scorer 변환.

기존 BacktestEngine 은 StrategyD 전용 (check_entry/check_exit/prepare 필수).
S2~S5 는 scan(ctx, top_n) → list[Candidate] 만 노출하므로 직접 호환 X.

본 모듈은 N봉 단순 PnL 평가:
  - 각 t ∈ [start, end] 마다 ScanContext(ohlcv[index ≤ t]) 생성 (look-ahead 차단)
  - strategy.scan(ctx, top_n) 호출 → top_n Candidate 채택
  - 진입가 = T+1 open (Candidate.entry_price = T close 라 거래 불가)
  - 청산가 = T+1+holding_bars close
  - PnL = (exit - entry)/entry - commission_pct (왕복)
  - trade-level Sharpe = mean/std * sqrt(252 / holding_bars) — annualized

WF scorer 시그니처 (walk_forward.run_walk_forward 와 동일):
    scorer(ohlcv_data, params, start, end) -> (sharpe, n_trades)
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.strategy_base import ScanContext, Strategy


@dataclass(frozen=True)
class ScanPnlConfig:
    """N봉 PnL 평가 설정."""
    holding_bars: int = 3        # 진입 후 N봉 보유 (CLAUDE.md: 1~3일 보유 단기 스윙)
    top_n: int = 5               # scan() 호출당 채택 후보 수 (max_positions=5 매칭)
    commission_pct: float = 0.0030  # 왕복 0.30% (BacktestConfig 기본과 일치)
    lookback_buffer_days: int = 60  # S3·S4 lookback 30 + 여유 (S1=45, S3·S4 더 필요)
    market: str = "KOSPI"


def _build_ctx(
    target_date: pd.Timestamp,
    ohlcv: dict[str, pd.DataFrame],
    market: str,
) -> ScanContext:
    """target_date 이하 봉만 포함한 ScanContext 생성. look-ahead 방지.

    lookback 부족 시 스킵은 각 전략이 책임 (S2~S5 의 min_bars 검사).
    """
    sliced: dict[str, pd.DataFrame] = {}
    for ticker, df in ohlcv.items():
        sub = df[df.index <= target_date]
        if len(sub) > 0:
            sliced[ticker] = sub
    universe = tuple(sliced.keys())
    return ScanContext(
        target_date=target_date.strftime("%Y%m%d"),
        universe=universe,
        ohlcv=sliced,
        names={t: t for t in universe},
        market_caps={t: 10_000.0 for t in universe},  # fragility 측정에는 무관
        market=market,
    )


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

        # 4) 각 signal date 에서 scan → T+1 진입 → T+1+holding_bars 청산
        trades_pnl: list[float] = []
        for d in signal_dates:
            ctx = _build_ctx(d, sliced, market=cfg.market)
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
