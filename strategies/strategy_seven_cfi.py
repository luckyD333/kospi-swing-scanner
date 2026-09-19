"""
strategies/strategy_seven_cfi.py — 전략7: CFI 하이킨아시 추세 전환 (CFI Reversal).

원본: TradingView Pine Script 지표 "CLUVIC Favorite Indicator" 의
tradeType == "CFI기법" 분기 (하이킨아시 + Donchian 추적 손절선).

정량 룰 (일봉, 종가 시점):
  R1 전환: 하이킨아시 종가가 직전 depth 봉 하이킨아시 채널 상단을 넘어 추세 방향이
           하락(-1) 에서 상승(+1) 으로 바뀐 봉. 원본 crossover(closeHA, tslTR) 과
           등가다 (근거는 _cfi.cfi_direction docstring).
  R2 필터: 진입가가 매물대 POC 위에 있거나, 직전 파동 피보나치 61.8% 가격 밴드 안이다.
           둘 중 하나만 충족해도 통과한다.
  R3 가격: entry = 종가. stop/target 은 apply_dynamic_trade_plan 이 ATR + score
           percentile 로 산정하고, 추적 손절선 tsl 을 손절가 하한으로 넘긴다.
  R4 점수: 400 + 200×매물대 통과 + 150×피보 통과 + 250×돌파 강도 (상한 1000).

원본은 기준 시간 간격 기본값이 60분이지만 이 전략은 일봉 전용이다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.cache.close_resolver import resolve_close_index
from core.decision.entry_gate import is_strategy_allowed
from core.decision.setup_quality import (
    SETUP_SCORE_THRESHOLD_DEFAULT,
    trend_setup_quality,
)
from core.indicators import calc_atr, latest_rsi_or_none
from core.strategy_base import Candidate, ScanContext

from ._atr_stop import compute_atr_stop
from ._cfi import cfi_direction, heikin_ashi, last_wave_fib, volume_poc
from ._trade_plan_apply import apply_dynamic_trade_plan
from .price_utils import floor_to_tick, populate_limit_fields, round_to_tick

logger = logging.getLogger(__name__)

_TF_NAMES: dict[str, str] = {
    "1D": "strategy_seven_cfi",
}


@dataclass(frozen=True)
class StrategySevenConfig:
    """CFI 전략 파라미터. 기본값은 원본 스크립트 기본값을 일봉으로 옮긴 것."""
    depth: int = 5                    # 원본 depthTR
    atr_period: int = 14
    vp_lookback: int = 200            # 원본 lookbackVP
    vp_bins: int = 500                # 원본 maxBarsVP
    fib_pivot_window: int = 6         # 원본 lenZZ
    fib_ratio: float = 0.618
    fib_band_atr_mult: float = 0.5
    # 아래 3개는 apply_dynamic_trade_plan 이 실패했을 때의 임시 가격 산식에만 쓰인다.
    atr_stop_mult: float = 2.5
    atr_stop_support_buffer: float = 0.5
    stop_loss_pct: float = 0.025
    r_target_1: float = 1.0
    r_target_2: float = 2.5


class StrategySevenCfi:
    """하이킨아시 채널 추세 전환 + 매물대·피보나치 필터."""

    name = "strategy_seven_cfi"

    def __init__(self, config: StrategySevenConfig | None = None, timeframe: str = "1D"):
        if timeframe not in _TF_NAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}. 지원: {list(_TF_NAMES)}")
        cfg = config or StrategySevenConfig()
        if cfg.depth <= 1:
            raise ValueError(f"depth must be > 1, got {cfg.depth}")
        if cfg.vp_lookback <= 0:
            raise ValueError(f"vp_lookback must be > 0, got {cfg.vp_lookback}")
        if cfg.vp_bins <= 0:
            raise ValueError(f"vp_bins must be > 0, got {cfg.vp_bins}")
        if cfg.atr_period <= 0:
            raise ValueError(f"atr_period must be > 0, got {cfg.atr_period}")
        if cfg.fib_pivot_window <= 0:
            raise ValueError(f"fib_pivot_window must be > 0, got {cfg.fib_pivot_window}")
        self.config = cfg
        self.timeframe = timeframe
        self.name = _TF_NAMES[timeframe]

    # ------------------------------------------------------------------
    # Strategy Protocol
    # ------------------------------------------------------------------

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        cfg = self.config
        # 매물대 룩백이 가장 긴 요구치다. ATR 워밍업 봉을 더해 여유를 둔다.
        min_bars = cfg.vp_lookback + cfg.atr_period + 1

        tf_data = ctx.ohlcv_by_tf.get(self.timeframe, {}) or ctx.ohlcv
        fetched_at = ctx.meta.get("manifest_collected_at") if ctx.meta else None
        candidates: list[Candidate] = []
        for ticker in ctx.universe:
            df = tf_data.get(ticker)
            if df is None or len(df) < min_bars:
                continue
            if resolve_close_index(df, fetched_at) == -2:
                df = df.iloc[:-1]
                if len(df) < min_bars:
                    continue

            try:
                cand = self._scan_one(ctx, ticker, df)
            except Exception as e:  # 종목 단위 실패는 스캔 전체를 멈추지 않는다 (S3 관례)
                logger.debug(f"  {ticker} CFI 계산 실패: {e}")
                continue
            if cand is not None:
                candidates.append(cand)

        candidates.sort(key=lambda c: c.score, reverse=True)
        result = candidates[:top_n]
        apply_dynamic_trade_plan(result, self.name)
        return result

    # ------------------------------------------------------------------

    def _scan_one(self, ctx: ScanContext, ticker: str, df: pd.DataFrame) -> Candidate | None:
        cfg = self.config
        open_ = df["open"].to_numpy(dtype=float)
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        close = df["close"].to_numpy(dtype=float)
        volume = df["volume"].to_numpy(dtype=float)
        t = len(df) - 1

        # entry gate (S3/S6 와 동일)
        regime = ctx.per_ticker_regime.get(ticker)
        d_1h = ctx.donchian_1h_by_ticker.get(ticker)
        if d_1h is not None:
            setup = trend_setup_quality(d_1h)
            setup_score: int | None = setup.score
            setup_reasons = list(setup.reasons)
        else:
            setup_score = None
            setup_reasons = None
        if not is_strategy_allowed(self.name, regime, setup_score):
            return None
        if setup_score is not None and setup_score < SETUP_SCORE_THRESHOLD_DEFAULT:
            return None

        atr = calc_atr(df["high"], df["low"], df["close"], period=cfg.atr_period).to_numpy(dtype=float)
        atr_now = float(atr[t])
        if np.isnan(atr_now) or atr_now <= 0:
            return None

        # R1 추세 전환
        _, ha_high, ha_low, ha_close = heikin_ashi(open_, high, low, close)
        direction, tsl = cfi_direction(ha_high, ha_low, ha_close, depth=cfg.depth)
        if not (direction[t] == 1 and direction[t - 1] == -1):
            return None
        tsl_now = float(tsl[t])
        if np.isnan(tsl_now) or tsl_now <= 0:
            return None

        entry = round_to_tick(float(close[t]))

        # R2 매물대 POC 또는 피보나치 되돌림 (둘 중 하나)
        poc = volume_poc(high, low, volume, lookback=cfg.vp_lookback, bins=cfg.vp_bins)
        poc_ok = poc is not None and float(entry) > poc
        fib = last_wave_fib(high, low, pivot_window=cfg.fib_pivot_window, ratio=cfg.fib_ratio)
        fib_ok = fib is not None and abs(float(entry) - fib) <= cfg.fib_band_atr_mult * atr_now
        if not (poc_ok or fib_ok):
            return None

        # R3 임시 가격 — apply_dynamic_trade_plan 이 덮어쓴다.
        # 그 함수가 skip 하는 경우(ATR 결측 등)에만 아래 값이 최종값으로 남는다.
        support_floor = tsl_now if tsl_now < float(entry) else None
        stop_loss = floor_to_tick(compute_atr_stop(
            float(entry), atr_now, support_floor if support_floor is not None else 0.0,
            atr_mult=cfg.atr_stop_mult,
            support_buffer=cfg.atr_stop_support_buffer,
            fallback_pct=cfg.stop_loss_pct,
        ))
        if stop_loss >= entry or stop_loss <= 0:
            return None
        risk = float(entry - stop_loss)
        target_1 = round_to_tick(float(entry) + cfg.r_target_1 * risk)
        target_2 = round_to_tick(float(entry) + cfg.r_target_2 * risk)
        if not (stop_loss < entry < target_1 <= target_2):
            return None

        # R4 점수
        res_prev = float(np.nanmax(ha_high[t - cfg.depth:t]))
        strength = float(np.clip((ha_close[t] - res_prev) / atr_now, 0.0, 1.0))
        score = min(1000.0, 400.0 + 200.0 * poc_ok + 150.0 * fib_ok + 250.0 * strength)

        # 메타 (S3/S6 브리지 키 유지)
        reward = float(target_1 - entry)
        risk_pct = risk / entry * 100
        reward_pct = reward / entry * 100
        rr_ratio = 0.0 if risk_pct == 0 else reward_pct / risk_pct
        rr_band = "below" if rr_ratio < 2.0 else ("sweet" if rr_ratio < 2.5 else "over")
        avg_vol_20 = float(volume[max(0, t - 19):t + 1].mean())
        cap_bil = float(ctx.market_caps.get(ticker, 0.0)) / 100_000_000
        df_30m = ctx.ohlcv_by_tf.get("30m", {}).get(ticker)
        limit_entry, limit_stop = populate_limit_fields(df_30m, entry, stop_loss)

        return Candidate(
            ticker=ticker,
            name=ctx.names.get(ticker, ticker),
            strategy=self.name,
            signal_date=df.index[t],
            score=score,
            entry_price=entry,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            limit_entry=limit_entry,
            limit_stop=limit_stop,
            market_cap_bil=cap_bil,
            volume_20d_avg=avg_vol_20,
            conditions_met={
                "direction_flip": True,
                "poc_above": bool(poc_ok),
                "fib_touch": bool(fib_ok),
            },
            metadata={
                "source_strategy": self.name,
                "market": ctx.market,
                "atr_14": atr_now,
                "rr_ratio": rr_ratio,
                "rr_band": rr_band,
                "trade_plan_support_floor": support_floor,
                "tsl": tsl_now,
                "poc": poc,
                "poc_above": bool(poc_ok),
                "fib_618": fib,
                "fib_touch": bool(fib_ok),
                "direction_flipped": True,
                "ha_channel_high": res_prev,
                "breakout_strength": round(strength, 4),
                "bars_since_trigger": 0,   # 진입 계기 = 오늘의 전환
                "rsi_14": latest_rsi_or_none(df["close"], period=14),
                "per_ticker_regime": regime,
                "setup_score": setup_score,
                "setup_reasons": setup_reasons,
                "target_1_rationale": "ATR + score percentile 기반 1R",
                "target_2_rationale": "ATR + score percentile 기반 2.5R",
            },
        )
