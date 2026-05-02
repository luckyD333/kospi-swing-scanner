"""
strategy.py — Strategy D v2 진입/청산 판별

입력: OHLCV DataFrame + 지표
출력: TradeSignal (진입) 또는 청산 결정
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from .core import (
    ExitReason,
    Position,
    TradeSignal,
    calc_bollinger,
    calc_macd,
    calc_rsi,
)
from .detectors import (
    DoubleBottomDetector,
    DoubleBottomSimple,
    count_consecutive_bearish,
    is_today_bullish,
)

logger = logging.getLogger(__name__)


def _check_engulf(df: pd.DataFrame, idx: int, strict: bool) -> bool:
    """장악형 양봉 판정. strict=False 이면 완화 기준(전일 종가 +0.5% 돌파) 사용."""
    if idx < 1 or idx >= len(df):
        return False
    prev = df.iloc[idx - 1]
    curr = df.iloc[idx]
    if not (prev["close"] < prev["open"]):
        return False
    if not (curr["close"] > curr["open"]):
        return False
    if strict:
        return bool(curr["open"] <= prev["close"] and curr["close"] >= prev["open"])
    return bool(curr["close"] >= prev["close"] * 1.005)


@dataclass
class StrategyDConfig:
    """Strategy D v2 파라미터"""
    # 지표
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    bb_period: int = 20
    bb_std: float = 2.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # 진입 조건
    consecutive_bearish_min: int = 3
    bb_breach_lookback: int = 5  # 최근 N봉 내 BB 하단 이탈 확인

    # 청산 조건
    target_1_pct: float = 0.03   # +3% (1차 목표)
    target_2_pct: float = 0.05   # +5% (2차 목표)
    stop_loss_pct: float = 0.025 # -2.5% (고정 손절)
    gap_down_pct: float = 0.03   # -3% 갭다운 손절
    time_stop_bars: int = 3      # N봉 경과 시간 손절

    # 진입 조건 — engulfing 엄격도
    engulf_strict: bool = True  # False: curr["close"] >= prev["close"] * 1.005

    # RR sweet spot 필터 (PR #3)
    use_rr_filter: bool = False  # RR 필터 활성화 여부
    min_rr_ratio: float = 2.0    # 최소 손익비
    sweet_spot_rr_low: float = 2.0   # sweet spot 하한
    sweet_spot_rr_high: float = 2.5  # sweet spot 상한

    # 유니버스
    min_lookback_bars: int = 40


class StrategyD:
    """Strategy D v2 진입/청산 엔진"""

    def __init__(
        self,
        config: StrategyDConfig | None = None,
        double_bottom_detector: DoubleBottomDetector | None = None,
    ):
        self.config = config or StrategyDConfig()
        self.detector = double_bottom_detector or DoubleBottomSimple()

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        """OHLCV에 지표 추가"""
        df = df.copy()
        df["rsi"] = calc_rsi(df["close"], self.config.rsi_period)
        mid, upper, lower = calc_bollinger(
            df["close"], self.config.bb_period, self.config.bb_std
        )
        df["bb_mid"] = mid
        df["bb_upper"] = upper
        df["bb_lower"] = lower
        macd_line, signal_line, hist = calc_macd(
            df["close"],
            self.config.macd_fast,
            self.config.macd_slow,
            self.config.macd_signal,
        )
        df["macd"] = macd_line
        df["macd_signal"] = signal_line
        df["macd_hist"] = hist
        return df

    # ------------------------------------------------------------------
    # 진입 판별
    # ------------------------------------------------------------------
    def check_entry(
        self,
        df: pd.DataFrame,
        idx: int,
        ticker: str = "TEST",
    ) -> TradeSignal | None:
        """
        idx 시점에서 진입 조건 체크. 충족 시 TradeSignal 반환.

        df는 prepare()로 지표가 계산된 상태여야 함.
        """
        if idx < self.config.min_lookback_bars:
            return None
        if idx >= len(df):
            return None

        current = df.iloc[idx]
        conditions = {}

        # 조건 1: 최근 N봉 내 RSI 과매도 이력
        # (진입 봉에서는 이미 RSI가 회복 중일 수 있으므로, lookback으로 체크)
        rsi_lookback = 10
        recent_rsi = df["rsi"].iloc[max(0, idx - rsi_lookback + 1) : idx + 1]
        conditions["rsi_oversold"] = bool(
            (recent_rsi <= self.config.rsi_oversold + 2).any()
        )

        # 조건 2a: 최근 연속 음봉 또는 2b: BB 하단 이탈
        consec = count_consecutive_bearish(df, idx - 1)  # 전일까지의 연속 음봉
        bb_lookback = self.config.bb_breach_lookback
        recent = df.iloc[max(0, idx - bb_lookback + 1) : idx + 1]
        bb_breach = bool(
            (recent["low"] <= recent["bb_lower"]).any()
            or (recent["close"] <= recent["bb_lower"]).any()
        )
        conditions["consecutive_bearish"] = consec >= self.config.consecutive_bearish_min
        conditions["bb_lower_breach"] = bb_breach
        conditions["sell_pressure"] = conditions["consecutive_bearish"] or conditions["bb_lower_breach"]

        # 조건 3: 상승 장악형 양봉 (당일 또는 직전 1봉)
        engulf_today = _check_engulf(df, idx, self.config.engulf_strict)
        engulf_yesterday = _check_engulf(df, idx - 1, self.config.engulf_strict)
        conditions["bullish_engulfing"] = engulf_today or engulf_yesterday

        # 조건 4: 쌍바닥 감지
        search_df = df.iloc[: idx + 1].tail(40)  # 최근 40봉으로 탐색
        db_result = self.detector.detect(search_df)
        conditions["double_bottom"] = db_result is not None

        # 조건 4+: 2차 바닥이 BB 내부 + 당일 양봉
        conditions["second_bottom_inside_bb"] = False
        conditions["today_bullish"] = is_today_bullish(df, idx)
        if db_result is not None:
            # 실제 df의 idx로 변환
            absolute_idx_2 = idx - (len(search_df) - 1) + db_result.second_bottom_idx
            if 0 <= absolute_idx_2 < len(df):
                bb_lower = df.iloc[absolute_idx_2]["bb_lower"]
                if not pd.isna(bb_lower):
                    conditions["second_bottom_inside_bb"] = (
                        df.iloc[absolute_idx_2]["low"] >= bb_lower * 0.99
                    )

        # 모든 필수 조건 AND
        required = [
            "rsi_oversold",
            "sell_pressure",
            "bullish_engulfing",
            "double_bottom",
            "today_bullish",
        ]
        all_met = all(conditions.get(k, False) for k in required)

        if not all_met:
            return None

        # Confidence 계산
        confidence = 0.55  # base
        if conditions.get("second_bottom_inside_bb"):
            confidence += 0.10
        # 거래량 패닉 셀 흡수 확인
        if db_result is not None:
            try:
                vol_series = df["volume"].iloc[max(0, idx - 20) : idx + 1]
                vol_avg = float(vol_series.mean())
                first_idx = idx - (len(search_df) - 1) + db_result.first_bottom_idx
                second_idx = idx - (len(search_df) - 1) + db_result.second_bottom_idx
                if 0 <= first_idx < len(df) and 0 <= second_idx < len(df):
                    v1 = float(df.iloc[first_idx]["volume"])
                    v2 = float(df.iloc[second_idx]["volume"])
                    if v1 >= vol_avg * 2.0:
                        confidence += 0.10
                    if v2 < v1 * 0.5:
                        confidence += 0.10
            except Exception as e:
                logger.debug(f"거래량 부스터 계산 실패: {e}")
        # MACD 히스토그램 반등
        if idx >= 2:
            h0, h1, h2 = df["macd_hist"].iloc[idx - 2 : idx + 1]
            if not any(pd.isna(x) for x in [h0, h1, h2]) and h2 > h1:
                confidence += 0.10

        confidence = min(confidence, 1.0)

        # 진입가/손절/목표
        entry_price = float(current["close"])
        stop_loss = entry_price * (1 - self.config.stop_loss_pct)
        target_1 = entry_price * (1 + self.config.target_1_pct)
        target_2 = entry_price * (1 + self.config.target_2_pct)

        # RR 계산
        risk_pct = self.config.stop_loss_pct
        reward_pct_t2 = self.config.target_2_pct
        rr_ratio = reward_pct_t2 / max(risk_pct, 1e-9)  # 0 분할 방지

        # RR band 분류
        if rr_ratio < self.config.sweet_spot_rr_low:
            rr_band = "below"
        elif rr_ratio < self.config.sweet_spot_rr_high:
            rr_band = "sweet"
        else:
            rr_band = "over"

        # RR 필터 적용
        if self.config.use_rr_filter and rr_ratio < self.config.min_rr_ratio:
            return None

        # metadata 구성
        signal_metadata = {
            "rr_ratio": round(rr_ratio, 4),
            "rr_band": rr_band,
        }

        return TradeSignal(
            timestamp=df.index[idx],
            ticker=ticker,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=target_1,
            target_2=target_2,
            confidence=round(confidence, 4),
            conditions_met=conditions,
            metadata=signal_metadata,
        )

    # ------------------------------------------------------------------
    # 청산 판별
    # ------------------------------------------------------------------
    def check_exit(
        self,
        position: Position,
        bar: pd.Series,
        bars_held: int,
    ) -> ExitReason | None:
        """
        현재 봉에서 청산 조건 충족 여부 체크.

        순서: 갭다운 → 손절 → 익절 → 시간 손절
        """
        open_price = float(bar["open"])
        high_price = float(bar["high"])
        low_price = float(bar["low"])

        # 1) 갭다운 손절 (시가 기준 -3% 이상 갭다운)
        gap_threshold = position.entry_price * (1 - self.config.gap_down_pct)
        if open_price <= gap_threshold and bars_held >= 1:
            return ExitReason.GAP_DOWN

        # 2) 고정 손절
        if low_price <= position.stop_loss:
            return ExitReason.STOP_LOSS

        # 3) 2차 목표 (보유 2일째 이상만 체크)
        if bars_held >= 1 and high_price >= position.target_2:
            return ExitReason.TARGET_2

        # 4) 1차 목표
        if high_price >= position.target_1:
            return ExitReason.TARGET_1

        # 5) 시간 손절
        if bars_held >= self.config.time_stop_bars:
            return ExitReason.TIME_STOP

        return None

    def execute_exit(
        self,
        position: Position,
        bar: pd.Series,
        reason: ExitReason,
    ) -> float:
        """청산 가격 결정"""
        if reason == ExitReason.GAP_DOWN:
            return float(bar["open"])
        elif reason == ExitReason.STOP_LOSS:
            return min(position.stop_loss, float(bar["open"]))
        elif reason == ExitReason.TARGET_1:
            return position.target_1
        elif reason == ExitReason.TARGET_2:
            return position.target_2
        elif reason == ExitReason.TIME_STOP:
            return float(bar["close"])
        return float(bar["close"])
