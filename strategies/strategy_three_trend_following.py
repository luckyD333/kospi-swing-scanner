"""
strategies/strategy_three_trend_following.py
— 전략3: Time-series Trend-Following (Donchian Channel).

학술 근거:
  - Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum",
    Journal of Financial Economics, Vol. 104, pp. 228-250
  - Donchian (1960s) 고전 N-day 채널 돌파 시스템

정량 룰:
  1. 직전 lookback 봉(오늘 제외) high 의 최고치 = channel_high
     직전 lookback 봉 low 의 최저치 = channel_low
  2. close[-1] > channel_high → 상방 돌파 후보
  3. ATR 필터: (close - channel_high) ≥ ATR × atr_filter_multiplier
     (whipsaw 방어 — 충분히 강한 돌파만)
  4. score = 돌파 강도 ((close - channel_high) / channel_high) 정규화
  5. SL = max(채널 저점 보존, 진입가 × (1 - stop_loss_pct))   ← 더 보수적
  6. TP1 = +3%, TP2 = +5% (또는 채널 갱신까지 동적 보유)

전략1·2 와의 분산 효과:
  - vs Mean Reversion: 상관 -0.3 (반대 방향 신호)
  - vs Cross-sectional Momentum: 상관 +0.2 (모두 상방, 메커니즘 다름)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from core.indicators import calc_atr, latest_rsi_or_none
from core.strategy_base import Candidate, ScanContext

from .price_utils import floor_to_tick, populate_limit_fields, round_to_tick

logger = logging.getLogger(__name__)

_TF_NAMES: dict[str, str] = {
    "1D": "strategy_three_trend_following",
    "1h": "strategy_three_1h",
    "30m": "strategy_three_30m",
}


@dataclass(frozen=True)
class StrategyThreeConfig:
    lookback: int = 20                  # Donchian 채널 봉 수
    atr_period: int = 14                # ATR 계산 기간
    atr_filter_multiplier: float = 0.5  # 돌파 폭 ≥ ATR × mult 만 진입 (0=비활성)
    stop_loss_pct: float = 0.025        # 진입가 -2.5% (보수적 SL 한계)
    target_1_pct: float = 0.03          # +3%
    target_2_pct: float = 0.05          # +5% (ATR 미산출 시 fallback)
    atr_target_mult: float = 3.0        # target_2 = entry + ATR×mult
    score_scale: float = 20000.0        # breakout_pct × scale → score (0..1000 cap; 5% 돌파 = 1000점)


class StrategyThreeTrendFollowing:
    """Donchian Channel 돌파 기반 추세 추종."""

    name = "strategy_three_trend_following"

    def __init__(self, config: StrategyThreeConfig | None = None, timeframe: str = "1D"):
        if timeframe not in _TF_NAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}. 지원: {list(_TF_NAMES)}")
        cfg = config or StrategyThreeConfig()
        if cfg.lookback <= 0:
            raise ValueError(f"lookback must be positive, got {cfg.lookback}")
        if cfg.atr_period <= 0:
            raise ValueError(f"atr_period must be positive, got {cfg.atr_period}")
        if cfg.atr_filter_multiplier < 0:
            raise ValueError(
                f"atr_filter_multiplier must be ≥ 0, got {cfg.atr_filter_multiplier}"
            )
        self.config = cfg
        self.timeframe = timeframe
        self.name = _TF_NAMES[timeframe]

    # ------------------------------------------------------------------
    # Strategy Protocol
    # ------------------------------------------------------------------

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        cfg = self.config
        # 채널 산출에 lookback+1, ATR 산출에 atr_period+1 봉 필요.
        min_bars = max(cfg.lookback + 1, cfg.atr_period + 1)

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

                # 1) Donchian 채널 — 직전 lookback 봉 (오늘 제외)
                channel_high = float(high.iloc[-(cfg.lookback + 1):-1].max())
                channel_low = float(low.iloc[-(cfg.lookback + 1):-1].min())
                close_now = float(close.iloc[-1])

                # 2) 데이터 품질 가드 (channel_high <= 0 등 비정상 데이터 즉시 배제)
                if channel_high <= 0 or channel_low <= 0:
                    continue

                # 3) 돌파 신호
                if close_now <= channel_high:
                    continue
                breakout_pct = (close_now - channel_high) / channel_high

                # 3.5) PR-E (P1-3): 단일일 급등 페널티 — 추세 추종 한정
                # NAV 괴리율 회귀·단일 호가 체결 가능성을 추세로 오인하는 결함 차단.
                prev_change_pct = 0.0
                if len(close) >= 2 and float(close.iloc[-2]) > 0:
                    prev_change_pct = (
                        (close_now - float(close.iloc[-2])) / float(close.iloc[-2]) * 100.0
                    )
                if prev_change_pct >= 30.0:
                    continue  # +30% 이상 → 후보 풀에서 제외
                pump_penalty = 0.5 if prev_change_pct >= 20.0 else 1.0

                # 4) ATR 필터
                atr_series = calc_atr(high, low, close, period=cfg.atr_period)
                atr_now = float(atr_series.iloc[-1])
                if pd.isna(atr_now) or atr_now <= 0:
                    continue
                if cfg.atr_filter_multiplier > 0:
                    if (close_now - channel_high) < atr_now * cfg.atr_filter_multiplier:
                        continue

                # 5) Score = 돌파 강도 (cap [0, 1]) × pump_penalty (PR-E)
                score = float(min(1000.0, max(0.0, breakout_pct * cfg.score_scale)))
                score *= pump_penalty

                # 6) SL = max(채널 저점 -1%, 진입가 -2.5%)
                #    더 보수적(=진입가에 가까운) 쪽 선택.
                #    0.99 배수: 채널 저점이 정확한 지지선이 아닐 수 있으므로 1% safety
                #    margin 을 추가해 채널 저점을 살짝 하회. 채널이 깊을 때는 자연스럽게
                #    -2.5% 손절이 더 빡빡하므로 그쪽이 채택됨.
                entry = round_to_tick(close_now)
                sl_channel = channel_low * 0.99
                sl_pct = entry * (1 - cfg.stop_loss_pct)
                stop_loss_raw = max(sl_channel, sl_pct)
                if stop_loss_raw >= entry:
                    # 안전: SL 이 close 보다 크면 -2.5% 강제
                    stop_loss_raw = entry * (1 - cfg.stop_loss_pct)
                stop_loss = floor_to_tick(stop_loss_raw)

                t1 = round_to_tick(entry * (1 + cfg.target_1_pct))
                t2 = round_to_tick(entry + atr_now * cfg.atr_target_mult)
                t2 = max(t2, t1)

                cap_won = ctx.market_caps.get(ticker, 0.0)
                cap_bil = float(cap_won) / 100_000_000
                avg_vol_20 = float(df["volume"].iloc[-20:].mean()) \
                    if len(df) >= 20 else float(df["volume"].mean())

                # 신규 metadata 키 계산
                risk_pct = (entry - stop_loss) / entry * 100
                reward_pct_t2 = (t2 - entry) / entry * 100
                rr_ratio = 0.0 if risk_pct == 0 else reward_pct_t2 / risk_pct
                if rr_ratio < 2.0:
                    rr_band = "below"
                elif rr_ratio < 2.5:
                    rr_band = "sweet"
                else:
                    rr_band = "over"

                # ATR 14일은 이미 계산했으므로 재사용
                atr_14 = float(atr_now) if atr_now is not None else None

                rsi_14_val = latest_rsi_or_none(df["close"], period=14)

                df_30m = ctx.ohlcv_by_tf.get("30m", {}).get(ticker)
                limit_entry, limit_stop = populate_limit_fields(df_30m, entry, stop_loss)

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
                    volume_20d_avg=avg_vol_20,
                    conditions_met={
                        "breakout_above_channel_high": True,
                        "atr_filter_passed": cfg.atr_filter_multiplier == 0.0
                            or (close_now - channel_high) >= atr_now * cfg.atr_filter_multiplier,
                    },
                    metadata={
                        "channel_high": channel_high,
                        "channel_low": channel_low,
                        "channel_mid": (channel_high + channel_low) / 2,
                        "breakout_pct": float(breakout_pct),
                        "atr": atr_now,
                        "lookback": cfg.lookback,
                        "market": ctx.market,
                        "source_strategy": self.name,
                        "rr_ratio": rr_ratio,
                        "rr_band": rr_band,
                        "atr_14": atr_14,
                        "rsi_14": rsi_14_val,
                        # PR-E: 단일일 급등 추적 (≥30% 는 이미 차단)
                        "prev_change_pct": prev_change_pct,
                        "pump_penalty": pump_penalty,
                    },
                ))
            except Exception as e:
                logger.debug(f"  {ticker} trend 계산 실패: {e}")
                continue

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]
