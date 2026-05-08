"""
strategies/strategy_four_pullback_ma.py — Strategy 4: 눌림목 매매 (Pullback to MA).

진입 조건:
  1. close > MA20 — 상승 추세 확인
  2. 최근 N봉(전일까지) 중 close < MA5 인 봉 존재 — 눌림목 발생
  3. close[-1] >= MA5[-1] — 당일 MA5 회복
  4. volume[-1] >= avg_volume_20d * min_vol_ratio — 수급 동반
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from core.cache.close_resolver import resolve_close_index
from core.decision.entry_gate import is_strategy_allowed
from core.decision.setup_quality import (
    SETUP_SCORE_THRESHOLD_DEFAULT,
    trend_setup_quality,
)
from core.indicators import calc_atr, latest_rsi_or_none, moving_average
from core.strategy_base import Candidate, ScanContext

from .price_utils import floor_to_tick, populate_limit_fields, round_to_tick

logger = logging.getLogger(__name__)

_TF_NAMES: dict[str, str] = {
    "1D": "strategy_four_pullback_ma",
    "1h": "strategy_four_pullback_ma_1h",
    "30m": "strategy_four_pullback_ma_30m",
}


@dataclass(frozen=True)
class StrategyFourConfig:
    ma_trend: int = 20          # 추세 확인 SMA
    ma_pullback: int = 5        # 눌림목/회복 SMA
    pullback_lookback: int = 5  # 눌림목 감지 기간 (전일까지 N봉)
    min_vol_ratio: float = 0.8  # 당일 거래량 / 20일 평균
    stop_loss_pct: float = 0.025
    target_1_pct: float = 0.03
    target_2_pct: float = 0.05          # ATR 미산출 시 fallback
    atr_target_mult: float = 3.0        # target_2 = entry + ATR×mult
    min_bars: int = 25
    min_daily_volume: int = 100_000
    use_donchian_levels: bool = False   # 30m Donchian 기반 trade_plan 산출 (Optional)


class StrategyFourPullbackMa:
    """MA 눌림목 매매 — 상승 추세 중 단기 이평 이탈 후 회복 진입."""

    name = "strategy_four_pullback_ma"

    def __init__(self, config: StrategyFourConfig | None = None, timeframe: str = "1D"):
        if timeframe not in _TF_NAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}. 지원: {list(_TF_NAMES)}")
        self.config = config or StrategyFourConfig()
        self.timeframe = timeframe
        self.name = _TF_NAMES[timeframe]

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        cfg = self.config
        min_bars = max(cfg.min_bars, cfg.ma_trend + 1)

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
                close = df["close"]
                volume = df["volume"]

                avg_volume = float(volume.iloc[-20:].mean()) if len(df) >= 20 else float(volume.mean())
                if avg_volume < cfg.min_daily_volume:
                    continue

                ma20 = moving_average(close, cfg.ma_trend)
                ma5 = moving_average(close, cfg.ma_pullback)

                ma20_now = float(ma20.iloc[-1])
                ma5_now = float(ma5.iloc[-1])
                close_now = float(close.iloc[-1])
                vol_now = float(volume.iloc[-1])

                if pd.isna(ma20_now) or pd.isna(ma5_now) or ma20_now <= 0:
                    continue

                # 조건1: MA20 위 (추세 살아있음)
                if close_now <= ma20_now:
                    continue

                # 조건2: 전일까지 최근 N봉 중 MA5 이탈 봉 존재
                lb = cfg.pullback_lookback
                prev_close = close.iloc[-(lb + 1):-1]
                prev_ma5 = ma5.iloc[-(lb + 1):-1]
                if not bool((prev_close < prev_ma5).any()):
                    continue

                # 조건3: 당일 MA5 회복
                if close_now < ma5_now:
                    continue

                # 조건4: 수급 동반
                if vol_now < avg_volume * cfg.min_vol_ratio:
                    continue

                entry = round_to_tick(close_now)
                # MA20 이 핵심 지지선 — MA20-0.5% 와 pct 중 더 보수적(높은) 손절 채택
                sl_ma20 = ma20_now * (1 - 0.005)
                sl_pct = entry * (1 - cfg.stop_loss_pct)
                stop_loss = floor_to_tick(max(sl_ma20, sl_pct))

                atr_series = calc_atr(df["high"], df["low"], close, 14)
                atr_val = float(atr_series.iloc[-1])
                atr_14 = None if pd.isna(atr_val) else atr_val

                t1 = round_to_tick(entry * (1 + cfg.target_1_pct))
                if atr_14 is not None:
                    t2 = round_to_tick(entry + atr_14 * cfg.atr_target_mult)
                    t2 = max(t2, t1)
                else:
                    t2 = round_to_tick(entry * (1 + cfg.target_2_pct))

                above_ma20_pct = close_now / ma20_now - 1
                # 5000 배수: +0.2% 위 → score ≈ 10, +10% 위 → score = 500 (추세 강도 비례)
                score = float(min(1000.0, max(0.0, above_ma20_pct * 5000.0)))

                risk_pct = (entry - stop_loss) / entry * 100
                reward_pct_t2 = (t2 - entry) / entry * 100
                rr_ratio = 0.0 if risk_pct == 0 else reward_pct_t2 / risk_pct
                if rr_ratio < 2.0:
                    rr_band = "below"
                elif rr_ratio < 2.5:
                    rr_band = "sweet"
                else:
                    rr_band = "over"

                rsi_14_val = latest_rsi_or_none(df["close"], period=14)

                cap_bil = float(ctx.market_caps.get(ticker, 0.0)) / 100_000_000

                df_30m = ctx.ohlcv_by_tf.get("30m", {}).get(ticker)
                limit_entry, limit_stop = populate_limit_fields(df_30m, entry, stop_loss)

                # Entry gate: 1d regime + 1h setup_score (추세 추종 setup)
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
                    continue
                if setup_score is not None and setup_score < SETUP_SCORE_THRESHOLD_DEFAULT:
                    continue

                candidates.append(Candidate(
                    ticker=ticker,
                    name=ctx.names.get(ticker, ticker),
                    strategy=self.name,
                    signal_date=df.index[-1],
                    score=score,
                    entry_price=entry,
                    stop_loss=stop_loss,
                    target_1=t1,
                    target_2=t2,
                    limit_entry=limit_entry,
                    limit_stop=limit_stop,
                    market_cap_bil=cap_bil,
                    volume_20d_avg=avg_volume,
                    conditions_met={
                        "above_ma20": True,
                        "pullback_detected": True,
                        "ma5_recovered": True,
                        "volume_confirmed": True,
                    },
                    metadata={
                        "ma20": ma20_now,
                        "ma5": ma5_now,
                        "above_ma20_pct": float(above_ma20_pct * 100),
                        "vol_ratio": float(vol_now / avg_volume),
                        "market": ctx.market,
                        "source_strategy": self.name,
                        "rr_ratio": rr_ratio,
                        "rr_band": rr_band,
                        "atr_14": atr_14,
                        "rsi_14": rsi_14_val,
                        "per_ticker_regime": regime,
                        "setup_score": setup_score,
                        "setup_reasons": setup_reasons,
                        "bars_since_trigger": 0,
                    },
                ))
            except Exception as e:
                logger.debug(f"  {ticker} pullback 계산 실패: {e}")

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]
