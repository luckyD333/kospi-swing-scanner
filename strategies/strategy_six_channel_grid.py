"""
strategies/strategy_six_channel_grid.py
— 전략6: 추세선·피보나치 채널 격자 (Channel Grid).
(주봉 변형 `_w` 는 같은 봉 수 규칙을 주봉에 적용)

근거:
  - 돌파 후 되돌림(throwback): Bulkowski, 26,542 패턴 표본에서 발생률 약 55%,
    돌파 거래량 평균 이상이면 74%. 되돌림 완료 후 70% 원 추세 재개.
  - 저항→지지 역할 전환(polarity principle): Edwards & Magee, Murphy.
  - 선의 역할은 번호가 아니라 접근 방향으로 정한다 (채널 이론의 대칭 규칙).

정량 룰 (일봉, 종가 시점):
  R1 기하: 룩백 최고점 A + 이후 최고 확정 고점 피벗 B = 레벨 0. A~B 최저점까지 거리 = W.
           격자 L(k,t) = L0(t) + k×W (k = -1 … max_level, 0.5 간격). 지지선 S = 룩백 최저점 P
           + 이후 최고 확정 저점 피벗 Q.
  R2 게이트: 레벨 0 을 종가가 ATR×0.5 이상 상향 돌파(거래량 20일 평균 초과)한 날 d 가
           breakout_window_bars 안에 있고, 그 뒤 레벨 0 - 0.3ATR 아래 마감이 없어야 한다.
  R3 매수: 어느 선이든 어제 위 → 오늘 저가가 선 + 0.3ATR 안 → 오늘 종가 선 위.
           격자선과 지지선이 0.3ATR 안에 겹치면 합류(강한 신호).
  R4 가격: entry = 종가. 목표 = 진입가 위 가장 가까운 선(터치선과 합류한 선 제외)의
           진입 시점·보유 상한 시점 값 중 최소. stop = compute_atr_stop(support=터치선).
           (목표-진입) < min_rr×(진입-손절) 이면 제외.
  R5 점수: 400 + 300×합류 + 200×실측선(0, -1, 지지선) + 100×돌파 거래량 강도.

apply_dynamic_trade_plan 은 호출하지 않는다 (목표가가 R 배수가 아니라 선 값).
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
from ._channel_grid import (
    LineRef,
    build_grid,
    build_support_line,
    channel_reasserted,
    find_breakout_day,
    has_confluence,
    nearest_line_above,
    touched_from_above,
)
from .price_utils import floor_to_tick, round_to_tick

logger = logging.getLogger(__name__)

_TF_NAMES: dict[str, str] = {
    "1D": "strategy_six_channel_grid",
    "1W": "strategy_six_channel_grid_w",
}

# 실제 가격이 닿아 정의된 격자선 (나머지는 투사선). 레벨 -1 도 실측선이지만 게이트가
# 레벨 0 아래 마감을 막으므로 매수 지점이 될 수 없어 넣지 않는다.
_MEASURED_LEVELS = (0.0,)


@dataclass(frozen=True)
class StrategySixConfig:
    lookback_bars: int = 60           # A·P 탐색 창 (S3 channel_width 창과 동일)
    pivot_window: int = 3             # 스윙 피벗 좌우 봉 수 (DoubleBottomSimple 기본값)
    max_level: float = 3.0            # 격자 상한 레벨
    atr_period: int = 14
    breakout_atr_mult: float = 0.5    # 레벨 0 돌파 폭 (S3 방식)
    touch_atr_mult: float = 0.3       # 터치·합류·채널 복귀 허용 밴드
    breakout_window_bars: int = 30    # 돌파일이 이 안에 있어야 게이트 열림
    volume_avg_bars: int = 20
    holding_bars: int = 5             # 목표가 계산용 보유 상한 (ScanBarConfig 기본값과 일치)
    min_rr: float = 1.0               # (목표-진입) / (진입-손절) 하한
    atr_stop_mult: float = 2.5        # compute_atr_stop (S3 값. 지지 항이 항상 채택되어 사실상 비활성)
    atr_stop_support_buffer: float = 0.5
    stop_loss_pct: float = 0.025      # ATR 결측 시 fallback


class StrategySixChannelGrid:
    """추세선·채널 격자: 레벨 0 상향 돌파 후 격자선/지지선 리테스트 매수.

    (주봉 변형 `_w` 는 같은 봉 수 규칙을 주봉에 적용)
    """

    name = "strategy_six_channel_grid"

    def __init__(self, config: StrategySixConfig | None = None, timeframe: str = "1D"):
        if timeframe not in _TF_NAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}. 지원: {list(_TF_NAMES)}")
        cfg = config or StrategySixConfig()
        if cfg.lookback_bars <= 0:
            raise ValueError(f"lookback_bars must be positive, got {cfg.lookback_bars}")
        if cfg.pivot_window <= 0:
            raise ValueError(f"pivot_window must be positive, got {cfg.pivot_window}")
        if cfg.atr_period <= 0:
            raise ValueError(f"atr_period must be positive, got {cfg.atr_period}")
        if cfg.volume_avg_bars <= 1:
            raise ValueError(f"volume_avg_bars must be > 1, got {cfg.volume_avg_bars}")
        self.config = cfg
        self.timeframe = timeframe
        self.name = _TF_NAMES[timeframe]

    # ------------------------------------------------------------------
    # Strategy Protocol
    # ------------------------------------------------------------------

    def scan(self, ctx: ScanContext, top_n: int) -> list[Candidate]:
        cfg = self.config
        min_bars = cfg.lookback_bars + cfg.volume_avg_bars

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
                logger.debug(f"  {ticker} channel grid 계산 실패: {e}")
                continue
            if cand is not None:
                candidates.append(cand)

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_n]

    # ------------------------------------------------------------------

    def _scan_one(self, ctx: ScanContext, ticker: str, df: pd.DataFrame) -> Candidate | None:
        cfg = self.config
        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        close = df["close"].to_numpy(dtype=float)
        volume = df["volume"].to_numpy(dtype=float)
        n = len(df)
        t = n - 1

        # entry gate (S3 와 동일)
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

        # R1 기하
        grid = build_grid(high, low, lookback_bars=cfg.lookback_bars,
                          pivot_window=cfg.pivot_window, max_level=cfg.max_level)
        if grid is None:
            return None
        support = build_support_line(low, lookback_bars=cfg.lookback_bars, pivot_window=cfg.pivot_window)

        # R2 게이트
        d = find_breakout_day(close, volume, atr, grid.baseline, start=grid.i_b,
                              atr_mult=cfg.breakout_atr_mult, vol_bars=cfg.volume_avg_bars)
        if d is None or (t - d) > cfg.breakout_window_bars:
            return None
        if channel_reasserted(close, atr, grid.baseline, d=d, band_mult=cfg.touch_atr_mult):
            return None

        # 오늘 시점 선 목록
        x_future = t + cfg.holding_bars
        refs: list[LineRef] = [
            LineRef("grid", k, grid.level_value(k, t), grid.level_value(k, t - 1), grid.level_value(k, x_future))
            for k in grid.levels
        ]
        if support is not None:
            refs.append(LineRef("support", None, float(support.value_at(t)),
                                float(support.value_at(t - 1)), float(support.value_at(x_future))))

        # R3 터치
        touched = [r for r in refs if touched_from_above(
            low_t=low[t], close_t=close[t], close_prev=close[t - 1],
            ref=r, atr_t=atr_now, band_mult=cfg.touch_atr_mult)]
        if not touched:
            return None
        ref = max(touched, key=lambda r: r.value_now)
        confluence = has_confluence(ref, refs, atr_t=atr_now, band_mult=cfg.touch_atr_mult)

        # R4 가격
        entry = round_to_tick(float(close[t]))
        tref = nearest_line_above(entry=float(entry), refs=refs, touched=ref,
                                  atr_t=atr_now, band_mult=cfg.touch_atr_mult)
        if tref is None:
            return None
        target = floor_to_tick(min(tref.value_now, tref.value_future))
        stop_loss = floor_to_tick(compute_atr_stop(
            float(entry), atr_now, ref.value_now,
            atr_mult=cfg.atr_stop_mult,
            support_buffer=cfg.atr_stop_support_buffer,
            fallback_pct=cfg.stop_loss_pct,
        ))
        if stop_loss >= entry or target <= entry:
            return None
        risk = float(entry - stop_loss)
        reward = float(target - entry)
        if reward < cfg.min_rr * risk:
            return None
        target_confluence = has_confluence(tref, refs, atr_t=atr_now, band_mult=cfg.touch_atr_mult)

        # R5 점수
        avg_vol = float(volume[d - cfg.volume_avg_bars:d].mean())
        vol_strength = min(1.0, max(0.0, volume[d] / max(avg_vol, 1e-9) - 1.0))
        measured = ref.kind == "support" or ref.level in _MEASURED_LEVELS
        score = 400.0 + 300.0 * confluence + 200.0 * measured + 100.0 * vol_strength

        # 메타 (S3 브리지 키 유지)
        risk_pct = risk / entry * 100
        reward_pct = reward / entry * 100
        rr_ratio = 0.0 if risk_pct == 0 else reward_pct / risk_pct
        rr_band = "below" if rr_ratio < 2.0 else ("sweet" if rr_ratio < 2.5 else "over")
        avg_vol_20 = float(volume[t - cfg.volume_avg_bars + 1:t + 1].mean())
        cap_bil = float(ctx.market_caps.get(ticker, 0.0)) / 100_000_000
        return Candidate(
            ticker=ticker,
            name=ctx.names.get(ticker, ticker),
            strategy=self.name,
            signal_date=df.index[t],
            score=score,
            entry_price=entry,
            stop_loss=stop_loss,
            target_1=target,
            target_2=target,
            market_cap_bil=cap_bil,
            volume_20d_avg=avg_vol_20,
            conditions_met={
                "baseline_breakout": True,
                "touch_from_above": True,
                "confluence": bool(confluence),
                "rr_filter_passed": True,
            },
            metadata={
                "source_strategy": self.name,
                "market": ctx.market,
                "atr_14": atr_now,
                "rr_ratio": rr_ratio,
                "rr_band": rr_band,
                # 아래 두 키는 S6 경로에서 읽히지 않지만 형제 전략과 metadata 스키마를 맞추기 위해 유지
                "trade_plan_method": "line_based",
                "trade_plan_support_floor": ref.value_now if ref.value_now < entry else None,
                "touch_kind": ref.kind,
                "grid_level": ref.level,
                "touch_line_value": ref.value_now,
                "confluence": bool(confluence),
                "target_kind": tref.kind,
                "target_level": tref.level,
                "target_confluence": bool(target_confluence),
                "baseline_slope": grid.baseline.slope,
                "channel_width": grid.width,
                "grid_anchor_high_idx": grid.i_a,
                "grid_anchor_pivot_idx": grid.i_b,
                "breakout_day_idx": d,
                "bars_since_breakout": t - d,   # 돌파일 경과 봉 (칩 표시용)
                "bars_since_trigger": 0,        # 진입 계기 = 오늘의 터치 (regret_scorer freshness 의미, 다른 전략과 동일)
                "vol_ratio": float(volume[d] / max(avg_vol, 1e-9)),
                "rsi_14": latest_rsi_or_none(df["close"], period=14),
                "per_ticker_regime": regime,
                "setup_score": setup_score,
                "setup_reasons": setup_reasons,
                "target_1_rationale": "진입가 위 가장 가까운 선의 보유 구간 최소값",
                "target_2_rationale": "target_1 과 동일 (부분 익절 없음)",
            },
        )
