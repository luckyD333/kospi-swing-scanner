from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SignalRecord:
    strategy: str
    ticker: str
    signal_date: pd.Timestamp
    score: float        # 0~1 신뢰도 (rank_bucket 계산에 사용)
    entry_price: float  # 당일 open 근처 진입 희망가


class HistoricalSignalGenerator:
    """전략별 역사적 신호 추출기 (rolling window, no network)."""

    STRATEGY_NAMES = [
        "strategy_one",
        "strategy_two",
        "strategy_three",
        "strategy_four",
        "strategy_five",
    ]

    def __init__(self, min_lookback: int = 25) -> None:
        self.min_lookback = min_lookback

    def extract(
        self,
        strategy_name: str,
        ohlcv_map: dict[str, pd.DataFrame],
    ) -> list[SignalRecord]:
        """캐시 1D OHLCV에서 전략 신호를 rolling으로 추출."""
        extractor = {
            "strategy_one": self._extract_strategy_one,
            "strategy_two": self._extract_strategy_two,
            "strategy_three": self._extract_strategy_three,
            "strategy_four": self._extract_strategy_four,
            "strategy_five": self._extract_strategy_five,
        }.get(strategy_name)
        if extractor is None:
            return []
        try:
            return extractor(ohlcv_map)
        except Exception as e:
            print(f"[warning] {strategy_name} 신호 추출 실패: {e}")
            return []

    # ── Strategy 1: RSI + BB 쌍바닥 ─────────────────────────────────────────

    def _extract_strategy_one(self, ohlcv_map: dict[str, pd.DataFrame]) -> list[SignalRecord]:
        from backtest_engine.strategy import StrategyD, StrategyDConfig

        strategy = StrategyD(config=StrategyDConfig(min_lookback_bars=self.min_lookback))
        records: list[SignalRecord] = []
        for ticker, df in ohlcv_map.items():
            try:
                prepared = strategy.prepare(df)
                for idx in range(self.min_lookback, len(prepared)):
                    sig = strategy.check_entry(prepared, idx, ticker=ticker)
                    if sig is not None:
                        records.append(
                            SignalRecord(
                                strategy="strategy_one",
                                ticker=ticker,
                                signal_date=prepared.index[idx],
                                score=float(sig.confidence),
                                entry_price=float(sig.entry_price),
                            )
                        )
            except Exception:
                continue
        return records

    # ── Strategy 2: Cross-Sectional Momentum ────────────────────────────────

    def _extract_strategy_two(self, ohlcv_map: dict[str, pd.DataFrame]) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        any_df = next(iter(ohlcv_map.values()), None)
        if any_df is None:
            return records

        for idx in range(21, len(any_df)):
            date = any_df.index[idx]
            rets: dict[str, float] = {}
            for ticker, df in ohlcv_map.items():
                if date not in df.index:
                    continue
                i = df.index.get_loc(date)
                if i < 20:
                    continue
                rets[ticker] = float(df["close"].iloc[i] / df["close"].iloc[i - 20] - 1)

            if len(rets) < 10:
                continue

            vals = sorted(rets.values())
            p80 = float(np.percentile(vals, 80))
            for ticker, r in rets.items():
                if r >= p80:
                    score = float(np.searchsorted(vals, r) / len(vals))
                    entry = float(ohlcv_map[ticker].loc[date, "open"])
                    records.append(SignalRecord("strategy_two", ticker, date, score, entry))

        return records

    # ── Strategy 3: Donchian 채널 돌파 ──────────────────────────────────────

    def _extract_strategy_three(self, ohlcv_map: dict[str, pd.DataFrame]) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for ticker, df in ohlcv_map.items():
            if len(df) < self.min_lookback + 1:
                continue
            vol_ma = df["volume"].rolling(20).mean()
            high_20 = df["high"].rolling(20).max().shift(1)
            atr = (df["high"] - df["low"]).rolling(20).mean()

            for idx in range(self.min_lookback, len(df)):
                bar = df.iloc[idx]
                h20 = high_20.iloc[idx]
                v_ma = vol_ma.iloc[idx]
                a = atr.iloc[idx]
                if pd.isna(h20) or pd.isna(v_ma) or a <= 0:
                    continue
                if bar["close"] > h20 and bar["volume"] > v_ma:
                    score = min(float((bar["close"] - h20) / a), 1.0)
                    records.append(
                        SignalRecord(
                            strategy="strategy_three",
                            ticker=ticker,
                            signal_date=df.index[idx],
                            score=max(score, 0.0),
                            entry_price=float(bar["open"]),
                        )
                    )
        return records

    # ── Strategy 4: MA 추세 + MA5 눌림목 회복 ───────────────────────────────

    def _extract_strategy_four(self, ohlcv_map: dict[str, pd.DataFrame]) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for ticker, df in ohlcv_map.items():
            if len(df) < self.min_lookback + 1:
                continue
            ma20 = df["close"].rolling(20).mean()
            ma5 = df["close"].rolling(5).mean()

            for idx in range(self.min_lookback, len(df)):
                bar = df.iloc[idx]
                m20 = ma20.iloc[idx]
                m5 = ma5.iloc[idx]
                prev_m5 = ma5.iloc[idx - 1] if idx > 0 else m5
                if pd.isna(m20) or pd.isna(m5):
                    continue
                # MA20 상향 추세 + MA5가 MA20 아래에서 회복 중
                if bar["close"] > m20 and prev_m5 < m20 and bar["close"] > m5:
                    score = min(float((bar["close"] - m5) / (m20 * 0.02 + 1e-9)), 1.0)
                    records.append(
                        SignalRecord(
                            strategy="strategy_four",
                            ticker=ticker,
                            signal_date=df.index[idx],
                            score=max(score, 0.0),
                            entry_price=float(bar["open"]),
                        )
                    )
        return records

    # ── Strategy 5: Bull Flag ────────────────────────────────────────────────

    def _extract_strategy_five(self, ohlcv_map: dict[str, pd.DataFrame]) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for ticker, df in ohlcv_map.items():
            if len(df) < self.min_lookback + 1:
                continue
            for idx in range(self.min_lookback, len(df)):
                bar = df.iloc[idx]
                close_5d_ago = df["close"].iloc[idx - 5]
                if close_5d_ago <= 0:
                    continue
                ret_5d = float(bar["close"] / close_5d_ago - 1)
                # 5일 수익률 +8% 이상 + 당일 양봉
                if ret_5d > 0.08 and bar["close"] > bar["open"]:
                    score = min(ret_5d, 1.0)
                    records.append(
                        SignalRecord(
                            strategy="strategy_five",
                            ticker=ticker,
                            signal_date=df.index[idx],
                            score=float(score),
                            entry_price=float(bar["open"]),
                        )
                    )
        return records
