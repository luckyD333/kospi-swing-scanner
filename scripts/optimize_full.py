"""scripts/optimize_full.py — KOSPI Train + KOSDAQ Fresh OOS 통합 파라미터 최적화.

29차원 search space (전략 내부 15 + 랭킹 8 + 앙상블 5 + top_n 1) random search.

Walk-forward:
  - KOSPI train (bars 30-65): 400 random samples → top-50 Sharpe
  - KOSPI val   (bars 65-80): top-50 재평가 → PBO 계산 → top-5
  - KOSDAQ OOS  (bars 30-80): top-5 평가 → 3-way 게이트 (PF + win + DD 개선)

산출물: /tmp/optimize_full_runs/<ts>/{train,val,oos}.json + oos_top5.md
"""
from __future__ import annotations

import json
import logging
import math
import random
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev

import pandas as pd

# 프로젝트 루트 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.strategy_base import ScanContext
from core.decision.aggregator import aggregate_candidates
from core.decision.config import Priority, WeightConfig
from core.decision.regret_scorer import RegretWeights, compute_regret_scores
import core.decision.regret_scorer as _rs_module

from strategies.strategy_one_d_v2 import StrategyOneDv2, StrategyOneDv2Config
from strategies.strategy_two_cross_sectional_momentum import (
    StrategyTwoCrossSectionalMomentum, StrategyTwoConfig,
)
from strategies.strategy_three_trend_following import (
    StrategyThreeTrendFollowing, StrategyThreeConfig,
)
from strategies.strategy_four_pullback_ma import (
    StrategyFourPullbackMa, StrategyFourConfig,
)
from strategies.strategy_five_bull_flag import (
    StrategyFiveBullFlag, StrategyFiveConfig,
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ----- 설정 -----
CACHE_ROOT = Path(".cache")
KOSPI_TICKERS_FILE = Path("/tmp/kospi_tickers_pre.txt")
KOSDAQ_TICKERS_FILE = Path("/tmp/kosdaq_tickers.txt")
RUN_DIR_ROOT = Path("/tmp/optimize_full_runs")

N_TRIALS_PHASE_A = 400      # KOSPI train random samples
N_TOP_PHASE_B = 50          # train top-N → val
N_TOP_PHASE_C = 5           # val top-N → KOSDAQ OOS
SCAN_STEP_TRAIN = 3
SCAN_STEP_VAL = 2
SCAN_STEP_OOS = 3
MIN_BARS = 30
SKIP_THRESHOLD = 0.05       # w_s 가 이보다 작으면 strategy skip

# 5 base 전략 name → ensemble weight 매핑 (build_strategies에서 사용)
_STRATEGY_NAMES = {
    "strategy_one_d_v2": "w_s1",
    "strategy_two_cross_sectional_momentum": "w_s2",
    "strategy_three_trend_following": "w_s3",
    "strategy_four_pullback_ma": "w_s4",
    "strategy_five_bull_flag": "w_s5",
}

# S4+S2/S3 confluence penalty prefix
_S4_PREFIXES = ("strategy_four_pullback_ma",)
_S2S3_PREFIXES = ("strategy_two", "strategy_three")

# Aggregator 단일 priority — score 100%
BASE_WEIGHT_CFG = WeightConfig(
    priorities=[Priority(key="score", weight=100.0, direction="higher_better", label="신호강도")],
)


# ============================ Config + Sampling ============================

@dataclass
class Config:
    # S1 (3)
    s1_engulf_strict: bool
    s1_db_freshness: int
    s1_db_price_tolerance: float
    # S2 (3)
    s2_lookback: int
    s2_entry_percentile: float
    s2_rsi_max: float | None
    # S3 (3)
    s3_lookback: int
    s3_atr_filter_multiplier: float
    s3_atr_stop_mult: float
    # S4 (3)
    s4_ma_trend: int
    s4_pullback_lookback: int
    s4_min_vol_ratio: float
    # S5 (3)
    s5_min_pole_pct: float
    s5_vol_shrink_ratio: float
    s5_tight_range_mult: float
    # RegretWeights (4축, sum=1)
    bull_reward: float
    max_drawdown: float
    dist_to_stop: float
    signal_freshness: float
    # Composite weights (3축, sum=1)
    w_opp: float
    w_pot: float
    w_sig: float
    # confluence penalty + top_n
    confluence_penalty: float
    top_n: int
    # 앙상블 가중치 (5축)
    w_s1: float
    w_s2: float
    w_s3: float
    w_s4: float
    w_s5: float


def _sample_dirichlet(k: int, alpha: float = 1.0) -> list[float]:
    """Dirichlet(α) 분포에서 k차원 가중치 샘플, 합=1."""
    raw = [random.gammavariate(alpha, 1.0) for _ in range(k)]
    s = sum(raw)
    return [x / s for x in raw]


def sample_config() -> Config:
    rw = _sample_dirichlet(4)
    cw = _sample_dirichlet(3)
    return Config(
        s1_engulf_strict=random.choice([True, False]),
        s1_db_freshness=random.choice([2, 3, 4, 5]),
        s1_db_price_tolerance=random.choice([0.02, 0.03, 0.05]),
        s2_lookback=random.choice([10, 15, 20, 25]),
        s2_entry_percentile=random.choice([0.65, 0.70, 0.75, 0.80, 0.85]),
        s2_rsi_max=random.choice([70.0, 80.0, None]),
        s3_lookback=random.choice([15, 20, 25, 30]),
        s3_atr_filter_multiplier=random.choice([0.3, 0.5, 0.7, 1.0]),
        s3_atr_stop_mult=random.choice([1.5, 2.0, 2.5, 3.0]),
        s4_ma_trend=random.choice([20, 30, 40]),
        s4_pullback_lookback=random.choice([3, 5, 7]),
        s4_min_vol_ratio=random.choice([0.6, 0.8, 1.0]),
        s5_min_pole_pct=random.choice([0.05, 0.07, 0.08]),
        s5_vol_shrink_ratio=random.choice([0.7, 0.8, 0.9]),
        s5_tight_range_mult=random.choice([2.0, 2.5, 3.0]),
        bull_reward=rw[0], max_drawdown=rw[1], dist_to_stop=rw[2], signal_freshness=rw[3],
        w_opp=cw[0], w_pot=cw[1], w_sig=cw[2],
        confluence_penalty=random.choice([0.5, 0.6, 0.75, 0.85, 1.0]),
        top_n=random.choice([3, 5, 10]),
        w_s1=random.uniform(0.0, 2.0), w_s2=random.uniform(0.0, 2.0),
        w_s3=random.uniform(0.0, 2.0), w_s4=random.uniform(0.0, 2.0),
        w_s5=random.uniform(0.0, 2.0),
    )


def make_default_config() -> Config:
    """현재 default — bb54d17 적용 상태."""
    return Config(
        s1_engulf_strict=False, s1_db_freshness=2, s1_db_price_tolerance=0.03,
        s2_lookback=20, s2_entry_percentile=0.80, s2_rsi_max=None,
        s3_lookback=30, s3_atr_filter_multiplier=0.7, s3_atr_stop_mult=2.5,
        s4_ma_trend=30, s4_pullback_lookback=3, s4_min_vol_ratio=0.8,
        s5_min_pole_pct=0.07, s5_vol_shrink_ratio=0.9, s5_tight_range_mult=2.5,
        bull_reward=0.55, max_drawdown=0.15, dist_to_stop=0.30, signal_freshness=0.00,
        w_opp=0.70, w_pot=0.20, w_sig=0.10,
        confluence_penalty=0.75, top_n=5,
        w_s1=1.0, w_s2=1.0, w_s3=1.0, w_s4=1.0, w_s5=1.0,
    )


# ============================ Strategy Build ============================

def build_strategies(c: Config) -> list:
    """Config → 5 전략 인스턴스 리스트. w_s < SKIP_THRESHOLD 이면 제외."""
    pairs = []
    if c.w_s1 >= SKIP_THRESHOLD:
        pairs.append(("w_s1", StrategyOneDv2(
            StrategyOneDv2Config(
                engulf_strict=c.s1_engulf_strict,
                db_freshness=c.s1_db_freshness,
                db_price_tolerance=c.s1_db_price_tolerance,
            ), timeframe="1D")))
    if c.w_s2 >= SKIP_THRESHOLD:
        pairs.append(("w_s2", StrategyTwoCrossSectionalMomentum(
            StrategyTwoConfig(
                lookback=c.s2_lookback,
                entry_percentile=c.s2_entry_percentile,
                rsi_max=c.s2_rsi_max,
            ), timeframe="1D")))
    if c.w_s3 >= SKIP_THRESHOLD:
        pairs.append(("w_s3", StrategyThreeTrendFollowing(
            StrategyThreeConfig(
                lookback=c.s3_lookback,
                atr_filter_multiplier=c.s3_atr_filter_multiplier,
                atr_stop_mult=c.s3_atr_stop_mult,
            ), timeframe="1D")))
    if c.w_s4 >= SKIP_THRESHOLD:
        pairs.append(("w_s4", StrategyFourPullbackMa(
            StrategyFourConfig(
                ma_trend=c.s4_ma_trend,
                pullback_lookback=c.s4_pullback_lookback,
                min_vol_ratio=c.s4_min_vol_ratio,
            ), timeframe="1D")))
    if c.w_s5 >= SKIP_THRESHOLD:
        pairs.append(("w_s5", StrategyFiveBullFlag(
            StrategyFiveConfig(
                min_pole_pct=c.s5_min_pole_pct,
                vol_shrink_ratio=c.s5_vol_shrink_ratio,
                tight_range_mult=c.s5_tight_range_mult,
            ), timeframe="1D")))
    return pairs


# ============================ Data Loading ============================

def load_data(market: str) -> dict[str, pd.DataFrame]:
    tickers_file = KOSPI_TICKERS_FILE if market == "KOSPI" else KOSDAQ_TICKERS_FILE
    tickers = set(tickers_file.read_text().split())
    result: dict[str, pd.DataFrame] = {}
    for t in tickers:
        path = CACHE_ROOT / "1D" / f"{t}.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df.index = pd.to_datetime(df.index)
        df.columns = [c.lower() for c in df.columns]
        if len(df) >= MIN_BARS and {"open", "high", "low", "close", "volume"}.issubset(df.columns):
            result[t] = df
    return result


def split_periods(data: dict[str, pd.DataFrame], market: str):
    """returns scan_dates list (subsampled by SCAN_STEP)."""
    sample_df = next(iter(data.values()))
    dates = sample_df.index.tolist()
    n = len(dates)
    if market == "KOSPI":
        # train = bars 30-65, val = bars 65-80 (forward 5 봉 여유)
        train_end = min(65, n - 5)
        val_end = min(80, n - 5)
        train_dates = dates[30:train_end:SCAN_STEP_TRAIN]
        val_dates = dates[train_end:val_end:SCAN_STEP_VAL]
        return train_dates, val_dates
    else:  # KOSDAQ
        end = min(80, n - 5)
        oos_dates = dates[30:end:SCAN_STEP_OOS]
        return oos_dates


# ============================ Exit Simulation ============================

def simulate_exit(df, entry_idx, entry_price, stop_loss, target_1, max_hold=5):
    n = len(df)
    for i in range(1, max_hold + 1):
        idx = entry_idx + i
        if idx >= n:
            break
        row = df.iloc[idx]
        if row["open"] <= stop_loss:
            pnl = (row["open"] - entry_price) / entry_price * 100
            return {"pnl_pct": pnl, "is_win": False, "exit": "gap_stop"}
        if row["low"] <= stop_loss:
            pnl = (stop_loss - entry_price) / entry_price * 100
            return {"pnl_pct": pnl, "is_win": False, "exit": "stop"}
        if row["high"] >= target_1:
            pnl = (target_1 - entry_price) / entry_price * 100
            return {"pnl_pct": pnl, "is_win": True, "exit": "target"}
    idx = min(entry_idx + max_hold, n - 1)
    close = df.iloc[idx]["close"]
    pnl = (close - entry_price) / entry_price * 100
    return {"pnl_pct": pnl, "is_win": pnl > 0, "exit": "time"}


# ============================ Evaluator ============================

def evaluate_config(c: Config, data: dict[str, pd.DataFrame], scan_dates: list) -> dict:
    """Config + market data + scan dates → metrics."""
    # 1. regret_scorer 모듈 상수 monkey-patch
    _rs_module._W_OPP = c.w_opp
    _rs_module._W_POT = c.w_pot
    _rs_module._W_SIG_BASE = c.w_sig

    rw = RegretWeights(
        bull_reward=c.bull_reward, max_drawdown=c.max_drawdown,
        dist_to_stop=c.dist_to_stop, signal_freshness=c.signal_freshness,
    )

    strategy_pairs = build_strategies(c)
    if not strategy_pairs:
        return {"n": 0, "pf": 0.0, "sharpe": -99.0, "max_dd": 0.0, "win_rate": 0.0}

    trades = []
    for scan_dt in scan_dates:
        # period 까지 sliced data
        sliced = {t: df[df.index <= scan_dt] for t, df in data.items()
                  if len(df[df.index <= scan_dt]) >= MIN_BARS}
        if not sliced:
            continue

        ctx = ScanContext(
            target_date=scan_dt.strftime("%Y%m%d"),
            universe=tuple(sliced.keys()),
            ohlcv=sliced, ohlcv_by_tf={"1D": sliced},
            names={t: t for t in sliced},
            market_caps={t: 0.0 for t in sliced},
            market="KOSPI",  # placeholder, 본 평가에선 무관
        )

        # 전략별 스캔 + ensemble weight 적용
        all_cands = []
        strategy_ids_present = {}  # sid -> set of tickers
        for wkey, strat in strategy_pairs:
            try:
                cands = strat.scan(ctx, top_n=50)
            except Exception:
                continue
            w = getattr(c, wkey)
            for cand in cands:
                cand.score *= w
                all_cands.append(cand)
            sid = strat.name
            strategy_ids_present.setdefault(sid, set()).update(c2.ticker for c2 in cands)

        if not all_cands:
            continue

        # ticker별 best-score 후보로 dedupe
        best: dict = {}
        for cand in all_cands:
            if cand.ticker not in best or cand.score > best[cand.ticker].score:
                best[cand.ticker] = cand

        # aggregator (score 100% priority) + regret_scorer
        ranked = aggregate_candidates(list(best.values()), BASE_WEIGHT_CFG, pool="STOCK")
        if not ranked:
            continue
        ranked = compute_regret_scores(ranked, weights=rw)

        # S4+S2/S3 confluence penalty
        s4_tickers = {t for sid, ts in strategy_ids_present.items()
                      if any(sid.startswith(p) for p in _S4_PREFIXES) for t in ts}
        s2s3_tickers = {t for sid, ts in strategy_ids_present.items()
                        if any(sid.startswith(p) for p in _S2S3_PREFIXES) for t in ts}
        penalized = s4_tickers & s2s3_tickers
        if penalized and c.confluence_penalty < 1.0:
            for rc in ranked:
                if rc.candidate.ticker in penalized:
                    old = rc.normalized_metrics.get("composite_score", 0.0)
                    rc.normalized_metrics["composite_score"] = old * c.confluence_penalty
            ranked.sort(key=lambda r: (
                -r.normalized_metrics.get("composite_score", 0.0),
                -r.final_score, r.candidate.ticker,
            ))

        # top_n 거래 시뮬
        for rc in ranked[:c.top_n]:
            ticker = rc.candidate.ticker
            df_full = data.get(ticker)
            if df_full is None:
                continue
            try:
                entry_idx = df_full.index.get_loc(scan_dt)
            except KeyError:
                continue
            if entry_idx + 1 >= len(df_full):
                continue
            cand = rc.candidate
            result = simulate_exit(
                df_full, entry_idx,
                float(cand.entry_price), float(cand.stop_loss), float(cand.target_1),
            )
            trades.append(result)

    return compute_metrics(trades)


# ============================ Metrics ============================

def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "pf": 0.0, "sharpe": -99.0, "max_dd": 0.0, "win_rate": 0.0}
    pnls = [t["pnl_pct"] for t in trades]
    wins = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    pf = wins / losses if losses > 0 else 99.0
    avg = mean(pnls)
    sd = stdev(pnls) if len(pnls) > 1 else 1e-6
    sharpe = (avg / sd) * (252 ** 0.5) if sd > 0 else 0.0
    # max DD on cumulative
    cum = 0.0; peak = 0.0; max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
    return {
        "n": len(trades), "pf": round(pf, 3), "sharpe": round(sharpe, 3),
        "max_dd": round(max_dd, 2), "win_rate": round(win_rate, 3),
        "avg_pnl": round(avg, 3),
    }


# ============================ Overfit Guards ============================

def compute_pbo(train_sharpes: list[float], val_sharpes: list[float], n_iter: int = 200) -> float:
    """Combinatorial Symmetric CSCV — train top performer 가 val 에서 bottom 50% 떨어지는 비율."""
    n = len(train_sharpes)
    if n < 4:
        return 0.5
    overfit = 0
    for _ in range(n_iter):
        half = random.sample(range(n), n // 2)
        best_train_in_half = max(half, key=lambda i: train_sharpes[i])
        val_subset_sorted = sorted([val_sharpes[i] for i in half])
        try:
            rank = val_subset_sorted.index(val_sharpes[best_train_in_half]) / max(len(half) - 1, 1)
        except ValueError:
            rank = 0.5
        if rank < 0.5:
            overfit += 1
    return overfit / n_iter


def deflated_sharpe(observed_sr: float, n_trials: int) -> float:
    expected_max = math.sqrt(2 * math.log(max(n_trials, 2)))
    return observed_sr - expected_max


# ============================ Main ============================

def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = RUN_DIR_ROOT / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n{'=' * 70}\n  KOSPI Train + KOSDAQ Fresh OOS 통합 최적화\n  Run dir: {run_dir}\n{'=' * 70}")

    # ---- 데이터 로드 ----
    print("\n[1/5] 데이터 로드...")
    kospi_data = load_data("KOSPI")
    print(f"  KOSPI: {len(kospi_data)} ticker")
    kosdaq_data = load_data("KOSDAQ")
    print(f"  KOSDAQ: {len(kosdaq_data)} ticker")
    if len(kosdaq_data) < 50:
        print(f"\n  ⚠ KOSDAQ ticker {len(kosdaq_data)} 개 < 50 → OOS 불가, 종료")
        return

    train_dates, val_dates = split_periods(kospi_data, "KOSPI")
    oos_dates = split_periods(kosdaq_data, "KOSDAQ")
    print(f"  Train: {len(train_dates)} 스캔일 ({train_dates[0].date()}~{train_dates[-1].date()})")
    print(f"  Val:   {len(val_dates)} 스캔일 ({val_dates[0].date()}~{val_dates[-1].date()})")
    print(f"  OOS:   {len(oos_dates)} 스캔일 ({oos_dates[0].date()}~{oos_dates[-1].date()})")

    # ---- Phase A: KOSPI train 400 samples ----
    print(f"\n[2/5] Phase A — KOSPI train ({N_TRIALS_PHASE_A} random samples)...")
    t0 = time.time()
    results_train = []
    for i in range(N_TRIALS_PHASE_A):
        c = sample_config()
        try:
            m = evaluate_config(c, kospi_data, train_dates)
        except Exception as e:
            m = {"n": 0, "pf": 0.0, "sharpe": -99.0, "max_dd": 0.0, "win_rate": 0.0, "error": str(e)}
        results_train.append((c, m))
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (N_TRIALS_PHASE_A - i - 1)
            print(f"  {i+1}/{N_TRIALS_PHASE_A} ({elapsed:.0f}s, ETA {eta:.0f}s)")

    # 저장
    (run_dir / "train.json").write_text(json.dumps(
        [{"config": asdict(c), "metrics": m} for c, m in results_train],
        ensure_ascii=False, indent=1, default=str,
    ))

    # ---- Phase B: top-50 → KOSPI val ----
    print(f"\n[3/5] Phase B — top-{N_TOP_PHASE_B} 재평가 (KOSPI val)...")
    top_n_b = sorted([r for r in results_train if r[1]["n"] >= 5],
                     key=lambda x: -x[1]["sharpe"])[:N_TOP_PHASE_B]
    print(f"  train n>=5 통과: {len([r for r in results_train if r[1]['n']>=5])}")
    results_val = []
    for c, m_train in top_n_b:
        try:
            m_val = evaluate_config(c, kospi_data, val_dates)
        except Exception as e:
            m_val = {"n": 0, "pf": 0.0, "sharpe": -99.0, "max_dd": 0.0, "win_rate": 0.0, "error": str(e)}
        results_val.append((c, m_train, m_val))

    # PBO 계산
    train_sr = [m["sharpe"] for _, m, _ in results_val]
    val_sr = [m["sharpe"] for _, _, m in results_val]
    pbo = compute_pbo(train_sr, val_sr)
    print(f"  PBO (top-{N_TOP_PHASE_B}): {pbo:.3f} {'< 0.5 ✓ robust' if pbo < 0.5 else '≥ 0.5 ✗ overfit'}")

    (run_dir / "val.json").write_text(json.dumps(
        [{"config": asdict(c), "train_metrics": mt, "val_metrics": mv}
         for c, mt, mv in results_val],
        ensure_ascii=False, indent=1, default=str,
    ))

    # ---- top-5 선별 (val sharpe desc, n>=5) ----
    top5 = sorted([r for r in results_val if r[2]["n"] >= 5],
                  key=lambda x: -x[2]["sharpe"])[:N_TOP_PHASE_C]
    print(f"  val n>=5 통과 후 top-{N_TOP_PHASE_C} 선별")

    # ---- Phase C: KOSDAQ fresh OOS ----
    print(f"\n[4/5] Phase C — KOSDAQ fresh OOS (top-{N_TOP_PHASE_C} + default)...")
    default_c = make_default_config()
    m_default_oos = evaluate_config(default_c, kosdaq_data, oos_dates)
    print(f"  default OOS: PF={m_default_oos['pf']:.2f}, win={m_default_oos['win_rate']:.1%}, "
          f"DD={m_default_oos['max_dd']:.1f}%, n={m_default_oos['n']}")

    results_oos = []
    for rank_idx, (c, m_train, m_val) in enumerate(top5, start=1):
        m_oos = evaluate_config(c, kosdaq_data, oos_dates)
        pf_up = m_oos["pf"] > m_default_oos["pf"]
        win_up = m_oos["win_rate"] > m_default_oos["win_rate"]
        dd_down = m_oos["max_dd"] < m_default_oos["max_dd"]
        passed = pf_up and win_up and dd_down
        dsr = deflated_sharpe(m_oos["sharpe"], N_TRIALS_PHASE_A)
        results_oos.append({
            "rank": rank_idx, "config": asdict(c),
            "train_metrics": m_train, "val_metrics": m_val, "oos_metrics": m_oos,
            "gate": {"pf_up": pf_up, "win_up": win_up, "dd_down": dd_down, "passed": passed},
            "dsr": round(dsr, 3),
        })
        gate_str = "✓ 채택" if passed else "✗ 거부"
        print(f"  rank {rank_idx}: PF={m_oos['pf']:.2f}({'↑' if pf_up else '↓'}) "
              f"win={m_oos['win_rate']:.1%}({'↑' if win_up else '↓'}) "
              f"DD={m_oos['max_dd']:.1f}%({'↓' if dd_down else '↑'}) "
              f"n={m_oos['n']} DSR={dsr:.2f} → {gate_str}")

    (run_dir / "oos.json").write_text(json.dumps({
        "default_oos": m_default_oos,
        "pbo": pbo,
        "top5": results_oos,
    }, ensure_ascii=False, indent=1, default=str))

    # ---- 보고서 ----
    print(f"\n[5/5] 보고서 생성 → {run_dir / 'oos_top5.md'}")
    _write_report(run_dir, results_oos, m_default_oos, pbo, len(train_dates), len(val_dates), len(oos_dates))

    print(f"\n{'=' * 70}\n  완료. cat {run_dir}/oos_top5.md\n{'=' * 70}")


def _write_report(run_dir, results_oos, m_default, pbo, n_train, n_val, n_oos):
    lines = ["# KOSPI Train / KOSDAQ Fresh OOS — Top-5 결과\n"]
    lines.append("## 메서드 요약\n")
    lines.append(f"- Train: KOSPI {n_train} 스캔일, {N_TRIALS_PHASE_A} random samples")
    lines.append(f"- Val:   KOSPI {n_val} 스캔일, top-{N_TOP_PHASE_B} 재평가, PBO 계산")
    lines.append(f"- OOS:   KOSDAQ FRESH {n_oos} 스캔일, top-{N_TOP_PHASE_C} 평가")
    lines.append("- 게이트: PF + win_rate + max_DD 3-way 동시 개선\n")
    lines.append(f"## PBO\n- top-{N_TOP_PHASE_B} PBO: **{pbo:.3f}** {'(< 0.5 robust)' if pbo < 0.5 else '(≥ 0.5 overfit)'}\n")

    lines.append("## Default (현재 운영) OOS 성과\n")
    lines.append(f"- PF: {m_default['pf']:.2f}, win: {m_default['win_rate']:.1%}, "
                 f"max DD: {m_default['max_dd']:.1f}%, trades: {m_default['n']}\n")

    lines.append("## Top-5 OOS (vs default)\n")
    lines.append("| Rank | top_n | penalty | strategy_weights | KOSDAQ PF | win% | max DD | DSR | 게이트 |")
    lines.append("|------|-------|---------|------------------|-----------|------|--------|-----|--------|")
    for r in results_oos:
        c = r["config"]
        m = r["oos_metrics"]
        sws = f"s1={c['w_s1']:.1f},s2={c['w_s2']:.1f},s3={c['w_s3']:.1f},s4={c['w_s4']:.1f},s5={c['w_s5']:.1f}"
        gate = "✓" if r["gate"]["passed"] else "✗"
        lines.append(f"| {r['rank']} | {c['top_n']} | {c['confluence_penalty']:.2f} | {sws} | "
                     f"{m['pf']:.2f} | {m['win_rate']:.1%} | {m['max_dd']:.1f}% | {r['dsr']:.2f} | {gate} |")

    lines.append("\n## RegretWeights / Composite (top-5)\n")
    lines.append("| Rank | bull | dd | dist | fresh | opp | pot | sig |")
    lines.append("|------|------|----|----|-------|-----|-----|-----|")
    for r in results_oos:
        c = r["config"]
        lines.append(f"| {r['rank']} | {c['bull_reward']:.2f} | {c['max_drawdown']:.2f} | "
                     f"{c['dist_to_stop']:.2f} | {c['signal_freshness']:.2f} | "
                     f"{c['w_opp']:.2f} | {c['w_pot']:.2f} | {c['w_sig']:.2f} |")

    lines.append("\n## 전략 내부 파라미터 (top-5)\n")
    lines.append("| Rank | S1 strict/fresh/tol | S2 lb/pct/rsi | S3 lb/atrM/stop | S4 ma/lb/vol | S5 pole/shrink/tight |")
    lines.append("|------|---------------------|---------------|------------------|--------------|----------------------|")
    for r in results_oos:
        c = r["config"]
        s1 = f"{c['s1_engulf_strict']}/{c['s1_db_freshness']}/{c['s1_db_price_tolerance']}"
        s2 = f"{c['s2_lookback']}/{c['s2_entry_percentile']}/{c['s2_rsi_max']}"
        s3 = f"{c['s3_lookback']}/{c['s3_atr_filter_multiplier']}/{c['s3_atr_stop_mult']}"
        s4 = f"{c['s4_ma_trend']}/{c['s4_pullback_lookback']}/{c['s4_min_vol_ratio']}"
        s5 = f"{c['s5_min_pole_pct']}/{c['s5_vol_shrink_ratio']}/{c['s5_tight_range_mult']}"
        lines.append(f"| {r['rank']} | {s1} | {s2} | {s3} | {s4} | {s5} |")

    accepted = sum(1 for r in results_oos if r["gate"]["passed"])
    lines.append(f"\n## 분석\n- 채택 후보: {accepted} / {len(results_oos)}")
    if accepted == 0:
        lines.append("- **현재 default 유지 권장** — over-fit 해소 증거. 추가 데이터 수집 후 재시도 권장.")
    elif accepted >= 3:
        lines.append("- **robust plateau 발견** — top-3 이상 채택. 단일 best 또는 평균 적용 검토.")
    else:
        lines.append(f"- **단일 best 적용 후보** ({accepted}건) — 추가 검증 후 사용자 confirm 필요.")

    (run_dir / "oos_top5.md").write_text("\n".join(lines))


if __name__ == "__main__":
    random.seed(42)
    main()
