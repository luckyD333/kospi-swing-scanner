"""
strategies/strategy_five_bull_flag.py — Strategy 5: Bull Flag 돌파 매매.

진입 조건:
  1. Flagpole: 최근 pole_lookback봉 시작→종가 +min_pole_pct% 이상 상승
  2. Flag 거래량 수축: flag_bars 평균 거래량 < pole 평균 거래량 × vol_shrink_ratio
  3. 가격 압축: flag_bars 내 고저 범위 < ATR × tight_range_mult
  4. 당일 돌파: close > flag_high (flag 기간 고가 최대값)
  5. 돌파 거래량: volume >= 20일 평균
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from core.indicators import calc_atr, calc_rsi
from core.strategy_base import Candidate, ScanContext

logger = logging.getLogger(__name__)

_TF_NAMES: dict[str, str] = {
    "1D": "strategy_five_bull_flag",
    "1h": "strategy_five_bull_flag_1h",
    "30m": "strategy_five_bull_flag_30m",
}


@dataclass(frozen=True)
class StrategyFiveConfig:
    pole_lookback: int = 15        # flagpole 탐색 기간
    min_pole_pct: float = 0.08     # flagpole 최소 상승 +8%
    flag_bars: int = 7             # flag 압축 기간 (오늘 제외)
    vol_shrink_ratio: float = 0.7  # flag 거래량 수축 비율
    tight_range_mult: float = 1.5  # 가격 압축 판정 (ATR 배수)
    stop_loss_pct: float = 0.025
    min_bars: int = 35
    min_daily_volume: int = 100_000


class StrategyFiveBullFlag:
    """Bull Flag 돌파 — 급등 후 거래량 수축 압축 → 재돌파 진입."""

    name = "strategy_five_bull_flag"

    def __init__(self, config: StrategyFiveConfig | None = None, timeframe: str = "1D"):
        if timeframe not in _TF_NAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}. 지원: {list(_TF_NAMES)}")
        self.config = config or StrategyFiveConfig()
        self.timeframe = timeframe
        self.name = _TF_NAMES[timeframe]

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        cfg = self.config
        min_bars = cfg.pole_lookback + cfg.flag_bars + 5

        tf_data = ctx.ohlcv_by_tf.get(self.timeframe, {}) or ctx.ohlcv
        candidates: list[Candidate] = []

        for ticker in ctx.universe:
            df = tf_data.get(ticker)
            if df is None or len(df) < min_bars:
                continue

            try:
                close = df["close"]
                high = df["high"]
                low = df["low"]
                volume = df["volume"]

                avg_volume = float(volume.iloc[-20:].mean()) if len(df) >= 20 else float(volume.mean())
                if avg_volume < cfg.min_daily_volume:
                    continue

                idx = len(df) - 1
                fb = cfg.flag_bars
                pl = cfg.pole_lookback

                pole_start_close = float(close.iloc[idx - pl - fb])
                pole_end_close = float(close.iloc[idx - fb])

                if pole_start_close <= 0:
                    continue

                # 조건1: flagpole 충분한 상승
                pole_pct = (pole_end_close - pole_start_close) / pole_start_close
                if pole_pct < cfg.min_pole_pct:
                    continue

                # 조건2: flag 거래량 수축 (오늘 제외)
                flag_vol = float(volume.iloc[idx - fb: idx].mean())
                pole_vol = float(volume.iloc[idx - pl - fb: idx - fb].mean())
                if pole_vol <= 0:
                    continue
                if flag_vol >= pole_vol * cfg.vol_shrink_ratio:
                    continue

                # flag 고/저 (오늘 제외)
                flag_high = float(high.iloc[idx - fb: idx].max())
                flag_low = float(low.iloc[idx - fb: idx].min())

                # ATR
                atr_series = calc_atr(high, low, close, 14)
                atr_val = float(atr_series.iloc[-1])
                if pd.isna(atr_val) or atr_val <= 0:
                    continue

                # 조건3: 가격 압축
                flag_range = flag_high - flag_low
                if flag_range >= atr_val * cfg.tight_range_mult:
                    continue

                close_now = float(close.iloc[-1])
                vol_now = float(volume.iloc[-1])

                # 조건4: 당일 flag_high 돌파
                if close_now <= flag_high:
                    continue

                # 조건5: 돌파 거래량
                if vol_now < avg_volume:
                    continue

                # 손절: flag 저점 기준, 단 최대 -5%로 캡 (너무 넓은 손절 방지)
                #       최소 -0.5% 보장 (flag 저점이 진입가 근처일 때 대비)
                entry = close_now
                stop_loss = max(flag_low, entry * (1 - cfg.stop_loss_pct * 2))
                stop_loss = min(stop_loss, entry * (1 - 0.005))

                pole_height = pole_end_close - pole_start_close
                t1 = max(entry * 1.03, entry + pole_height * 0.5)
                t2 = max(t1, entry + pole_height * 1.0)

                breakout_strength = (close_now - flag_high) / atr_val
                vol_ratio = vol_now / avg_volume
                score = float(min(1000.0, max(0.0, breakout_strength * vol_ratio * 200.0)))

                risk_pct = (entry - stop_loss) / entry * 100
                reward_pct_t2 = (t2 - entry) / entry * 100
                rr_ratio = 0.0 if risk_pct == 0 else reward_pct_t2 / risk_pct
                if rr_ratio < 2.0:
                    rr_band = "below"
                elif rr_ratio < 2.5:
                    rr_band = "sweet"
                else:
                    rr_band = "over"

                cap_bil = float(ctx.market_caps.get(ticker, 0.0)) / 100_000_000

                try:
                    _r = calc_rsi(df["close"], period=14).iloc[-1]
                    rsi_14_val: float | None = round(float(_r), 1)
                    if rsi_14_val != rsi_14_val: rsi_14_val = None
                except Exception:
                    rsi_14_val = None

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
                    market_cap_bil=cap_bil,
                    volume_20d_avg=avg_volume,
                    conditions_met={
                        "flagpole_detected": True,
                        "volume_shrink": True,
                        "price_compressed": True,
                        "breakout": True,
                        "volume_confirmed": True,
                    },
                    metadata={
                        "pole_pct": float(pole_pct * 100),
                        "pole_height": float(pole_height),
                        "flag_high": flag_high,
                        "flag_low": flag_low,
                        "flag_vol_ratio": float(flag_vol / pole_vol),
                        "breakout_pct": float((close_now - flag_high) / flag_high * 100),
                        "vol_ratio": float(vol_ratio),
                        "market": ctx.market,
                        "source_strategy": self.name,
                        "rr_ratio": rr_ratio,
                        "rr_band": rr_band,
                        "atr_14": float(atr_val),
                        "rsi_14": rsi_14_val,
                    },
                ))
            except Exception as e:
                logger.debug(f"  {ticker} bull flag 계산 실패: {e}")

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]
