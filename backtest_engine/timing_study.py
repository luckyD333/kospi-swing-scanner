from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd


class EntryWindow(str, Enum):
    MORNING = "morning"      # 오전 9:30~10:00 ≈ open 가격
    AFTERNOON = "afternoon"  # 오후 14:00~15:00 ≈ open + 0.8×(close-open)


@dataclass
class TimingStudyConfig:
    entry_windows: list[EntryWindow] = field(default_factory=lambda: list(EntryWindow))
    hold_periods: list[int] = field(default_factory=lambda: [0, 1, 2, 3])
    rank_buckets: int = 4
    commission_pct: float = 0.0025
    min_lookback_bars: int = 25
    top_n_tickers: int = 500


@dataclass
class TimingTrade:
    strategy: str
    ticker: str
    signal_date: pd.Timestamp
    rank_bucket: int          # 1=상위 25%(신뢰도 높음), 4=하위 25%
    entry_window: EntryWindow
    hold_days: int
    entry_price: float
    exit_price: float
    commission_pct: float = 0.0025

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        raw = (self.exit_price / self.entry_price - 1.0) * 100
        return raw - self.commission_pct * 100


@dataclass
class TimingStudyResult:
    trades: list[TimingTrade]
    summary: pd.DataFrame
    config: TimingStudyConfig


class TimingStudyEngine:
    """신호 + OHLCV로 TimingTrade 목록 생성."""

    def calc_entry_price(self, bar: pd.Series, window: EntryWindow) -> float:
        if window == EntryWindow.MORNING:
            return float(bar["open"])
        # 14:00 ≈ 거래 시간(09:00~15:30)의 80% 지점
        return float(bar["open"] + 0.8 * (bar["close"] - bar["open"]))

    def calc_exit_price(
        self,
        df: pd.DataFrame,
        signal_date: pd.Timestamp,
        hold_days: int,
    ) -> float | None:
        try:
            idx = df.index.get_loc(signal_date)
        except KeyError:
            return None
        exit_idx = idx + hold_days
        if exit_idx >= len(df):
            return None
        return float(df["close"].iloc[exit_idx])

    def compute_trades(
        self,
        signals: list,
        ohlcv_map: dict[str, pd.DataFrame],
        config: TimingStudyConfig,
    ) -> list[TimingTrade]:
        if not signals:
            return []

        scores = [s.score for s in signals]
        quartiles = np.percentile(scores, [25, 50, 75])

        def get_bucket(score: float) -> int:
            if score >= quartiles[2]:
                return 1
            if score >= quartiles[1]:
                return 2
            if score >= quartiles[0]:
                return 3
            return 4

        trades: list[TimingTrade] = []
        for sig in signals:
            df = ohlcv_map.get(sig.ticker)
            if df is None or sig.signal_date not in df.index:
                continue
            bar = df.loc[sig.signal_date]
            if bar["open"] <= 0 or bar["close"] <= 0:
                continue
            bucket = get_bucket(sig.score)
            for window in config.entry_windows:
                entry_price = self.calc_entry_price(bar, window)
                for hold_days in config.hold_periods:
                    exit_price = self.calc_exit_price(df, sig.signal_date, hold_days)
                    if exit_price is None:
                        continue
                    trades.append(
                        TimingTrade(
                            strategy=sig.strategy,
                            ticker=sig.ticker,
                            signal_date=sig.signal_date,
                            rank_bucket=bucket,
                            entry_window=window,
                            hold_days=hold_days,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            commission_pct=config.commission_pct,
                        )
                    )
        return trades


class MetricsAggregator:
    def aggregate(self, trades: list[TimingTrade]) -> pd.DataFrame:
        if not trades:
            return pd.DataFrame()
        rows = [
            {
                "strategy": t.strategy,
                "entry_window": t.entry_window,
                "hold_days": t.hold_days,
                "rank_bucket": t.rank_bucket,
                "pnl_pct": t.pnl_pct,
            }
            for t in trades
        ]
        df = pd.DataFrame(rows)
        group_keys = ["strategy", "entry_window", "hold_days", "rank_bucket"]
        result = (
            df.groupby(group_keys)["pnl_pct"]
            .agg(
                avg_return="mean",
                win_rate=lambda x: (x > 0).mean(),
                profit_factor=lambda x: x[x > 0].sum() / max(-x[x < 0].sum(), 1e-9),
                sample_n="count",
            )
            .reset_index()
        )
        return result.sort_values(
            ["strategy", "rank_bucket", "avg_return"],
            ascending=[True, True, False],
        )


def _df_to_md(df: pd.DataFrame, float_fmt: str = ".2f") -> str:
    """tabulate 없이 DataFrame을 markdown 테이블로 변환."""
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append(format(v, float_fmt))
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


class ReportFormatter:
    def format(self, summary: pd.DataFrame, config: TimingStudyConfig) -> str:
        if summary.empty:
            return "# 결과 없음\n신호가 충분하지 않아 분석할 수 없어요."

        lines = [
            "# 전략별 매수/매도 타이밍 최적화 백테스트 결과",
            "",
            f"- 진입 시간대: {[w.value for w in config.entry_windows]}",
            f"- 보유 기간: {config.hold_periods}일",
            f"- 수수료: {config.commission_pct * 100:.2f}%",
            "",
            "## 최적 조합 Top 10 (avg_return 기준)",
            "",
        ]
        top10 = summary.nlargest(10, "avg_return")[
            [
                "strategy",
                "entry_window",
                "hold_days",
                "rank_bucket",
                "avg_return",
                "win_rate",
                "profit_factor",
                "sample_n",
            ]
        ].copy()
        top10["entry_window"] = top10["entry_window"].apply(
            lambda x: x.value if isinstance(x, EntryWindow) else x
        )
        lines.append(_df_to_md(top10))
        lines += ["", "## 전략별 매트릭스 (avg_return %)", ""]

        for strategy in sorted(summary["strategy"].unique()):
            lines.append(f"### {strategy}")
            sub = summary[summary["strategy"] == strategy].pivot_table(
                index=["entry_window", "rank_bucket"],
                columns="hold_days",
                values="avg_return",
                aggfunc="mean",
            ).reset_index()
            sub["entry_window"] = sub["entry_window"].apply(
                lambda x: x.value if isinstance(x, EntryWindow) else x
            )
            lines.append(_df_to_md(sub))
            lines.append("")

        lines += [
            "## 추천 (rank_bucket=1 기준)",
            "",
            "신뢰도 상위 25% 신호(Q1) 기준 최적 조합:",
            "",
        ]
        best = summary[summary["rank_bucket"] == 1].nlargest(5, "avg_return")
        for _, row in best.iterrows():
            win = row["entry_window"]
            win_str = win.value if isinstance(win, EntryWindow) else str(win)
            lines.append(
                f"- **{row['strategy']}**: {win_str} 진입, "
                f"{int(row['hold_days'])}일 보유 → "
                f"avg {row['avg_return']:.2f}%, "
                f"승률 {row['win_rate'] * 100:.0f}% "
                f"(n={int(row['sample_n'])})"
            )

        return "\n".join(lines)
