"""
screener.py — 다중 타임프레임 스크리너

여러 종목 × 여러 타임프레임(30m/1h/2h/4h/1D)을 스크리닝하여
현재 진입 시그널이 있는 종목 리스트 + 매수/매도/손절 가격을 반환한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .detectors import (
    DoubleBottomDetector,
    DoubleBottomSimple,
)
from .strategy import StrategyD, StrategyDConfig

# 지원 타임프레임
SUPPORTED_TIMEFRAMES = ["30m", "1h", "2h", "4h", "1D"]


@dataclass
class ScreenerHit:
    """스크리너 결과: 단일 종목 × 단일 타임프레임"""
    ticker: str
    timeframe: str
    signal_time: pd.Timestamp
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    confidence: float
    conditions_met: dict[str, bool]

    @property
    def risk_pct(self) -> float:
        return (self.entry_price - self.stop_loss) / self.entry_price * 100

    @property
    def reward_pct_target_1(self) -> float:
        return (self.target_1 - self.entry_price) / self.entry_price * 100

    @property
    def reward_pct_target_2(self) -> float:
        return (self.target_2 - self.entry_price) / self.entry_price * 100

    @property
    def risk_reward_ratio(self) -> float:
        if self.risk_pct == 0:
            return 0.0
        return self.reward_pct_target_2 / self.risk_pct

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "timeframe": self.timeframe,
            "signal_time": str(self.signal_time),
            "entry_price": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2),
            "confidence": round(self.confidence, 3),
            "risk_pct": round(self.risk_pct, 2),
            "reward_pct_t1": round(self.reward_pct_target_1, 2),
            "reward_pct_t2": round(self.reward_pct_target_2, 2),
            "rr_ratio": round(self.risk_reward_ratio, 2),
            "conditions_met": {k: v for k, v in self.conditions_met.items() if v},
        }


@dataclass
class ScreenerResult:
    """전체 스크리닝 결과"""
    scan_time: datetime
    total_scanned: int
    hits: list[ScreenerHit]

    def top_by_confidence(self, n: int = 10) -> list[ScreenerHit]:
        return sorted(self.hits, key=lambda h: h.confidence, reverse=True)[:n]

    def filter_by_timeframe(self, timeframe: str) -> list[ScreenerHit]:
        return [h for h in self.hits if h.timeframe == timeframe]

    def multi_timeframe_confluence(self, min_timeframes: int = 2) -> list[str]:
        """여러 타임프레임에서 동시에 시그널 난 종목"""
        by_ticker: dict[str, list[str]] = {}
        for h in self.hits:
            by_ticker.setdefault(h.ticker, []).append(h.timeframe)
        return [
            ticker for ticker, tfs in by_ticker.items()
            if len(set(tfs)) >= min_timeframes
        ]

    def summary_table(self, top_n: int = 20) -> pd.DataFrame:
        """상위 N개를 DataFrame으로 반환"""
        top = self.top_by_confidence(top_n)
        if not top:
            return pd.DataFrame()
        rows = [h.to_dict() for h in top]
        df = pd.DataFrame(rows)
        # conditions_met은 표에서 간결하게
        df["conditions_count"] = df["conditions_met"].apply(len)
        df = df.drop(columns=["conditions_met"])
        return df


# ============================================================================
# 다중 타임프레임 스크리너
# ============================================================================

class MultiTimeframeScreener:
    """다중 타임프레임 + 다종목 스크리너"""

    def __init__(
        self,
        strategy_config: StrategyDConfig | None = None,
        detector: DoubleBottomDetector | None = None,
        timeframes: list[str] | None = None,
    ):
        self.strategy_config = strategy_config or StrategyDConfig(min_lookback_bars=25)
        self.detector_factory = detector
        self.timeframes = timeframes or SUPPORTED_TIMEFRAMES

    def _get_strategy(self) -> StrategyD:
        det = self.detector_factory if self.detector_factory else DoubleBottomSimple()
        return StrategyD(config=self.strategy_config, double_bottom_detector=det)

    def scan_single_ticker(
        self,
        ticker: str,
        data_by_timeframe: dict[str, pd.DataFrame],
    ) -> list[ScreenerHit]:
        """단일 종목의 여러 타임프레임 스캔"""
        hits = []
        for tf, df in data_by_timeframe.items():
            if tf not in self.timeframes:
                continue
            hit = self._scan_single_tf(ticker, tf, df)
            if hit is not None:
                hits.append(hit)
        return hits

    def _scan_single_tf(
        self,
        ticker: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> ScreenerHit | None:
        """단일 종목 × 단일 타임프레임 스캔 (최신 봉에서 진입 조건 체크)"""
        strategy = self._get_strategy()
        prepared = strategy.prepare(df)
        if len(prepared) < self.strategy_config.min_lookback_bars + 1:
            return None

        # 최신 봉에서 진입 조건 체크
        idx = len(prepared) - 1
        signal = strategy.check_entry(prepared, idx, ticker=ticker)
        if signal is None:
            return None

        return ScreenerHit(
            ticker=ticker,
            timeframe=timeframe,
            signal_time=signal.timestamp,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_1=signal.target_1,
            target_2=signal.target_2,
            confidence=signal.confidence,
            conditions_met=signal.conditions_met,
        )

    def scan_multi(
        self,
        universe: dict[str, dict[str, pd.DataFrame]],
    ) -> ScreenerResult:
        """
        여러 종목 × 여러 타임프레임 스캔.

        Args:
            universe: {ticker: {timeframe: DataFrame}}

        Returns:
            ScreenerResult
        """
        hits: list[ScreenerHit] = []
        for ticker, data_by_tf in universe.items():
            ticker_hits = self.scan_single_ticker(ticker, data_by_tf)
            hits.extend(ticker_hits)

        return ScreenerResult(
            scan_time=datetime.now(),
            total_scanned=len(universe),
            hits=hits,
        )


# ============================================================================
# 타임프레임 리샘플링 헬퍼
# ============================================================================

def resample_ohlcv(
    df_1m: pd.DataFrame,
    target_timeframe: str,
) -> pd.DataFrame:
    """
    1분봉(또는 더 작은 봉)에서 상위 타임프레임으로 리샘플링.

    Args:
        df_1m: OHLCV DataFrame (index=datetime)
        target_timeframe: "30m", "1h", "2h", "4h", "1D"
    """
    freq_map = {
        "30m": "30min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "1D": "1D",
    }
    if target_timeframe not in freq_map:
        raise ValueError(f"unsupported timeframe: {target_timeframe}")

    freq = freq_map[target_timeframe]
    resampled = df_1m.resample(freq).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return resampled
