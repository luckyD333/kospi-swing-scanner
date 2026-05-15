# output/signals_builder.py
from __future__ import annotations

from dataclasses import dataclass
import logging
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    # type-check 전용 import (런타임 import cycle 회피)
    from core.decision.regret_scorer import RegretWeights

from core.decision.order_type_classifier import (
    OrderTypeIntent,
    classify as classify_order_type,
    korean_label,
)
from core.decision.product_type import (
    ProductType, to_pool, classify_asset_class,
)
from core.decision.signal_status import compute_signal_status
from core.decision.tradability_filter import (
    FilterThresholds,
    apply as apply_tradability_filter,
    write_rejection_log,
)
from output.models import (
    Fundamentals, Flow,
    SignalsPayload, Signal, TradePlan, Ranking, LiveQuote, LiveQuoteDisplay,
    StrategyContext, MarketSnapshot, MarketIndexDisplay,
    DecisionFactor, DecisionMeta, RegretFactor,
)
from output.signal_components import build_signal_components

# 기회 점수(regret_score) 4축 breakdown — UI 표시용 라벨 (시장 무관).
REGRET_FACTOR_LABELS: dict[str, str] = {
    "bull_reward":      "목표 수익",
    "max_drawdown":     "손절 위험(역)",
    "dist_to_stop":     "손절까지 여유",
    "signal_freshness": "신호 신선도",
}

# ─────────────────────────────────────────────────────────────────────
# 시장별 최적화 파라미터 (OOS 검증 2026-05-15, scripts/optimize_market_separate.py)
#
# KOSPI: Rank 2 (PF 4.62, win 79%, DD 17%, DSR 7.75)
#   ⚠ OOS = bb54d17 윈도우와 동일 → forward-walk 30일 재검증 권장 (2026-06-14~)
# KOSDAQ: Rank 1 (PF 3.50, win 58%, DD 22%, DSR 4.64)  — fresh OOS validated
# ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MarketRankingConfig:
    """시장별 ranking pipeline 파라미터 묶음.

    - regret_weights: RegretWeights — 기회 점수 4축 가중치 (합=1.0)
    - composite_weights: (opp, pot, sig) — 3-score 합성 가중치 (합=1.0)
    - confluence_penalty: float — S4+S2/S3 중복 시 composite_score 배수 (1.0=no-op)
    - strategy_score_weights: base strategy name → score multiplier (앙상블)
    - factor_label_weights: factor key → UI 표시 가중치 (×100, 합=100)
    """
    regret_weights: RegretWeights
    composite_weights: tuple[float, float, float]
    confluence_penalty: float
    strategy_score_weights: dict[str, float]
    factor_label_weights: dict[str, float]


def _base_strategy(sid: str) -> str:
    """strategy id prefix → base name 매핑 (S1~S5)."""
    for base in ("strategy_one", "strategy_two", "strategy_three", "strategy_four", "strategy_five"):
        if sid.startswith(base):
            return base
    return sid


def _build_market_configs() -> dict[str, MarketRankingConfig]:
    """RegretWeights import 시점 지연 — 모듈 import cycle 회피."""
    from core.decision.regret_scorer import RegretWeights
    return {
        "KOSPI": MarketRankingConfig(
            regret_weights=RegretWeights(
                bull_reward=0.22, max_drawdown=0.13, dist_to_stop=0.32, signal_freshness=0.33,
            ),
            composite_weights=(0.24, 0.61, 0.15),
            confluence_penalty=1.0,
            strategy_score_weights={
                "strategy_one":   0.88,
                "strategy_two":   0.46,
                "strategy_three": 1.03,
                "strategy_four":  0.56,
                "strategy_five":  0.30,
            },
            factor_label_weights={
                "bull_reward": 22.0, "max_drawdown": 13.0,
                "dist_to_stop": 32.0, "signal_freshness": 33.0,
            },
        ),
        "KOSDAQ": MarketRankingConfig(
            regret_weights=RegretWeights(
                bull_reward=0.04, max_drawdown=0.61, dist_to_stop=0.31, signal_freshness=0.04,
            ),
            composite_weights=(0.20, 0.23, 0.57),
            confluence_penalty=1.0,
            strategy_score_weights={
                "strategy_one":   0.48,
                "strategy_two":   0.18,
                "strategy_three": 1.36,
                "strategy_four":  0.99,
                "strategy_five":  0.27,
            },
            factor_label_weights={
                "bull_reward":  4.0, "max_drawdown": 61.0,
                "dist_to_stop": 31.0, "signal_freshness":  4.0,
            },
        ),
    }


# Default market = KOSPI (디폴트로 KOSPI 친화 설정 활성)
DEFAULT_MARKET = "KOSPI"
_MARKET_CONFIGS: dict[str, MarketRankingConfig] | None = None


def _market_config(market: str | None) -> MarketRankingConfig:
    """market name → MarketRankingConfig. Unknown 시장은 DEFAULT_MARKET fallback."""
    global _MARKET_CONFIGS
    if _MARKET_CONFIGS is None:
        _MARKET_CONFIGS = _build_market_configs()
    m = (market or DEFAULT_MARKET).upper()
    if m not in _MARKET_CONFIGS:
        m = DEFAULT_MARKET
    return _MARKET_CONFIGS[m]

if TYPE_CHECKING:
    from core.decision.config import WeightConfig

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

_STRATEGY_ONE_LABEL = ("STRATEGY ONE", "MEAN REVERSION")
_STRATEGY_LABELS: dict[str, tuple[str, str]] = {
    # 전략 1: Mean Reversion (RSI+BB+쌍바닥+장악형) — 모든 timeframe + r1/r2 fallback
    "strategy_one_d_v2":      _STRATEGY_ONE_LABEL,
    "strategy_one_w_v2":      _STRATEGY_ONE_LABEL,
    "strategy_one_1h_v2":     _STRATEGY_ONE_LABEL,
    "strategy_one_30m_v2":    _STRATEGY_ONE_LABEL,
    "strategy_one_d_v2_r1":   _STRATEGY_ONE_LABEL,
    "strategy_one_d_v2_r2":   _STRATEGY_ONE_LABEL,
    "strategy_one_w_v2_r1":   _STRATEGY_ONE_LABEL,
    "strategy_one_w_v2_r2":   _STRATEGY_ONE_LABEL,
    "strategy_one_1h_v2_r1":  _STRATEGY_ONE_LABEL,
    "strategy_one_1h_v2_r2":  _STRATEGY_ONE_LABEL,
    "strategy_one_30m_v2_r1": _STRATEGY_ONE_LABEL,
    "strategy_one_30m_v2_r2": _STRATEGY_ONE_LABEL,
    # 전략 2: Cross-sectional Momentum
    "strategy_two_cross_sectional_momentum": ("STRATEGY TWO", "MOMENTUM"),
    "strategy_two_1h":  ("STRATEGY TWO", "MOMENTUM"),
    "strategy_two_30m": ("STRATEGY TWO", "MOMENTUM"),
    # 전략 3: Trend Following (Donchian)
    "strategy_three_trend_following": ("STRATEGY THREE", "TREND FOLLOWING"),
    "strategy_three_1h":  ("STRATEGY THREE", "TREND FOLLOWING"),
    "strategy_three_30m": ("STRATEGY THREE", "TREND FOLLOWING"),
    # 전략 4: Pullback to MA
    "strategy_four_pullback_ma":     ("STRATEGY FOUR", "PULLBACK MA"),
    "strategy_four_pullback_ma_1h":  ("STRATEGY FOUR", "PULLBACK MA"),
    "strategy_four_pullback_ma_30m": ("STRATEGY FOUR", "PULLBACK MA"),
    # 전략 5: Bull Flag
    "strategy_five_bull_flag":     ("STRATEGY FIVE", "BULL FLAG"),
    "strategy_five_bull_flag_1h":  ("STRATEGY FIVE", "BULL FLAG"),
    "strategy_five_bull_flag_30m": ("STRATEGY FIVE", "BULL FLAG"),
}

# strategy가 metadata에 저장하는 소문자 값 → Pydantic Literal 대문자 값
_BAND_MAP: dict[str, str] = {
    "below": "UNDER",
    "sweet": "SWEET",
    "over":  "OVER",
}

# 전략 1 1h fallback 변형은 순차 실행 시 동일 ticker를 중복 노출하지 않음.
_RAW_SIGNAL_DEDUP_GROUP_BY_STRATEGY_ID: dict[str, str] = {
    "strategy_one_1h_v2": "strategy_one_1h_v2",
    "strategy_one_1h_v2_r1": "strategy_one_1h_v2",
    "strategy_one_1h_v2_r2": "strategy_one_1h_v2",
}


def _infer_timeframe_from_id(strategy_id: str) -> str:
    """strategy_id 토큰으로 timeframe 추정. Candidate.timeframe 이 비어있을 때 fallback."""
    sid = strategy_id.lower()
    if "_30m" in sid:
        return "30m"
    if "_1h" in sid:
        return "1h"
    if "_w_v2" in sid or sid.endswith("_w") or "_1w" in sid:
        return "1W"
    return "1D"


def _fmt_krw(val: int | None) -> str | None:
    if val is None:
        return None
    bil = val / 1e8
    if bil >= 10000:
        jo  = int(bil // 10000)
        rem = int(bil % 10000)
        return f"{jo}조 {rem:,}억" if rem else f"{jo}조"
    return f"{int(bil):,}억"


def _fmt_pct(val: float | None, positive_prefix: str = "") -> str | None:
    if val is None:
        return None
    prefix = positive_prefix if val > 0 else ""
    return f"{prefix}{val:.2f}%"


def _direction(change_pct: float) -> str:
    if change_pct > 0:
        return "up"
    elif change_pct < 0:
        return "down"
    return "flat"


def _format_target_display(target_date: str | None, now_kst: datetime) -> str:
    """target_date(YYYYMMDD or YYYY-MM-DD)와 현재 KST를 비교해 사용자 친화 라벨 생성.

    - 오늘 이고 < 15:30 → "YYYY-MM-DD (장중)"
    - 오늘 이고 < 16:00 → "YYYY-MM-DD (장 마감 직후)"
    - 그 외 → "YYYY-MM-DD"
    """
    if not target_date:
        return ""
    raw = target_date.replace("-", "")
    try:
        td = datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return target_date
    iso = td.isoformat()
    if td == now_kst.date():
        if now_kst.hour < 15 or (now_kst.hour == 15 and now_kst.minute < 30):
            return f"{iso} (장중)"
        if now_kst.hour < 16:
            return f"{iso} (장 마감 직후)"
    return iso


def _timeframe_sort_key(tf: str) -> tuple[int, str]:
    order = {"1D": 0, "1W": 1, "1h": 2, "30m": 3}
    return (order.get(tf, 99), tf)


def compute_signal_strength_percentile(
    c,
    all_candidates: list,
) -> float:
    """풀 내 c.score cross-sectional percentile (0~100).

    풀 전체 기준 상대 위치. 단독이면 50.0 (중립).
    """
    if len(all_candidates) <= 1:
        return 50.0
    rank = sum(1 for x in all_candidates if x.score < c.score)
    pct = rank / (len(all_candidates) - 1) * 100
    return round(pct, 1)


def _dedup_raw_candidates(
    candidates_by_strategy: dict[str, list],
) -> dict[str, list]:
    """raw strategy entry dedup.

    요청된 전략 1 1h base/r1/r2 조합만 대상으로, 먼저 등록된 ticker 를 유지한다.
    """
    dedup_seen: dict[str, set[str]] = {}
    filtered: dict[str, list] = {}
    for strategy_id, candidates in candidates_by_strategy.items():
        dedup_group = _RAW_SIGNAL_DEDUP_GROUP_BY_STRATEGY_ID.get(strategy_id)
        kept: list = []
        for cand in candidates:
            if dedup_group is None:
                kept.append(cand)
                continue
            seen = dedup_seen.setdefault(dedup_group, set())
            if cand.ticker in seen:
                continue
            seen.add(cand.ticker)
            kept.append(cand)
        if kept:
            filtered[strategy_id] = kept
    return filtered


def build_signals_payload(
    snapshot: MarketSnapshot,
    candidates_by_strategy: dict[str, list],
    market_regime: dict | None = None,
    weight_config: "WeightConfig | None" = None,
    target_date: str | None = None,
    tradability_filter: bool = False,
    tradability_thresholds: FilterThresholds | None = None,
    rejection_log_path: str | None = None,
    market: str | None = None,
) -> SignalsPayload:
    filtered_candidates_by_strategy = _dedup_raw_candidates(candidates_by_strategy)

    # 시장별 최적 파라미터 dispatch (KOSPI Rank 2 / KOSDAQ Rank 1 OOS validated)
    _mcfg = _market_config(market)
    _factor_labels = _mcfg.factor_label_weights  # _build_signal 에서 사용

    # 앙상블 strategy score multiplier — 시장별 가중치 적용.
    # 모든 ranking·display 가 score 기반이므로 단일 위치 곱셈으로 전체 적용.
    for _sid, _cands in filtered_candidates_by_strategy.items():
        _w = _mcfg.strategy_score_weights.get(_base_strategy(_sid), 1.0)
        if _w != 1.0:
            for _c in _cands:
                _c.score *= _w

    # PR-D: 거래가능성 hard filter — ranking 이전 차단 (default off, cli/runner 가 enable).
    # 통과 ticker 만 candidates_by_strategy 에 남김 → signals 리스트 + ranking 모두 영향.
    if tradability_filter:
        all_flat = [
            c for cs in filtered_candidates_by_strategy.values() for c in cs
        ]
        _, rejected = apply_tradability_filter(all_flat, tradability_thresholds)
        rejected_tickers = {r.ticker for r in rejected}
        if rejection_log_path:
            write_rejection_log(rejected, rejection_log_path)
        if rejected_tickers:
            filtered_candidates_by_strategy = {
                sid: [c for c in cs if c.ticker not in rejected_tickers]
                for sid, cs in filtered_candidates_by_strategy.items()
            }
            # 빈 strategy 제거
            filtered_candidates_by_strategy = {
                sid: cs for sid, cs in filtered_candidates_by_strategy.items() if cs
            }
            logger.info(
                f"  tradability_filter 차단: {len(rejected)}건 "
                f"(통과 ticker {len({c.ticker for cs in filtered_candidates_by_strategy.values() for c in cs})}개)",
            )

    # 전략 레이블 기준 상위 20개 제한
    # TF별 최소 5개 보장 + 나머지 슬롯은 전체 score 상위로 채움
    MAX_PER_STRATEGY = 20
    MIN_PER_TF = 5

    label_to_pairs: dict[str, list[tuple[str, object]]] = {}
    for sid, cands in filtered_candidates_by_strategy.items():
        label = _STRATEGY_LABELS.get(sid, (sid.upper(), ""))[0]
        label_to_pairs.setdefault(label, []).extend((sid, c) for c in cands)

    new_filtered: dict[str, list] = {}
    for pairs in label_to_pairs.values():
        # TF별 그룹화
        tf_groups: dict[str, list[tuple[str, object]]] = {}
        for sid, c in pairs:
            tf = getattr(c, "timeframe", None) or _infer_timeframe_from_id(sid)
            tf_groups.setdefault(tf, []).append((sid, c))

        # TF별 최소 보장 선점
        guaranteed: list[tuple[str, object]] = []
        pool: list[tuple[str, object]] = []
        for tf_pairs in tf_groups.values():
            tf_pairs.sort(key=lambda x: x[1].score, reverse=True)
            guaranteed.extend(tf_pairs[:MIN_PER_TF])
            pool.extend(tf_pairs[MIN_PER_TF:])

        # 남은 슬롯은 pool에서 score 상위로
        remaining = MAX_PER_STRATEGY - len(guaranteed)
        if remaining > 0 and pool:
            pool.sort(key=lambda x: x[1].score, reverse=True)
            guaranteed.extend(pool[:remaining])

        for sid, c in guaranteed:
            new_filtered.setdefault(sid, []).append(c)
    filtered_candidates_by_strategy = new_filtered

    # market_indices (display-ready)
    mi_display: dict[str, MarketIndexDisplay] = {}
    label_map = {
        "kospi": "코스피", "kosdaq": "코스닥",
        "usd_krw": "USD/KRW", "wti": "WTI",
        "kr_treasury_3y": "국고채3Y", "vix": "VIX",
    }

    def _fmt_index_value(key: str, val: float) -> str:
        if key == "usd_krw":
            return f"{val:,.2f}"
        if key == "wti":
            return f"${val:.2f}"
        if key == "kr_treasury_3y":
            return f"{val:.2f}%"
        return f"{val:,.2f}"

    def _fmt_index_change(key: str, chg: float) -> str:
        prefix = "+" if chg > 0 else ""
        if key == "kr_treasury_3y":
            return f"{prefix}{chg:.2f}"
        return _fmt_pct(chg, positive_prefix="+") or "0.00%"

    for key, idx in snapshot.market_indices.items():
        val = idx.value if hasattr(idx, "value") else idx["value"]
        chg = idx.change_pct if hasattr(idx, "change_pct") else idx["change_pct"]
        mi_display[key] = MarketIndexDisplay(
            label=label_map.get(key, key),
            value_display=_fmt_index_value(key, val),
            change_display=_fmt_index_change(key, chg),
            direction=_direction(chg),
        )

    # 전체 candidates 수집 → score 내림차순 정렬
    all_candidates: list[tuple[str, object]] = []
    for strategy_id, candidates in filtered_candidates_by_strategy.items():
        for c in candidates:
            all_candidates.append((strategy_id, c))
    all_candidates.sort(key=lambda x: x[1].score, reverse=True)
    total = len(all_candidates)

    # 의사결정 스코어 계산 (weight_config 제공 시)
    ticker_to_ranked: dict = {}
    ranked_for_all: list = []
    if weight_config is not None:
        try:
            from core.decision.aggregator import aggregate_candidates
            from core.decision.ensemble import compute_weighted_ensemble_score
            from core.decision.regret_scorer import compute_regret_scores

            weighted_scores = compute_weighted_ensemble_score(
                filtered_candidates_by_strategy, weight_config.strategy_weights
            )
            # ticker별 best-score 후보로 deduplicate (1D/1W 전략만)
            # aggregator 팩터(fundamentals, momentum_3m, regime)가 1D 개념이라
            # 1h/30m 후보를 섞으면 cross-sectional 비교 기준이 흐려짐.
            # 1h/30m 신호는 Signal 카드로 출력되지만 ranking/잠재력 점수 없이 참고용.
            _RANKING_TFS = {"1D", "1W"}
            best_per_ticker: dict[str, object] = {}
            for _sid, c in all_candidates:
                if _infer_timeframe_from_id(_sid) not in _RANKING_TFS:
                    continue
                if c.ticker not in best_per_ticker or c.score > best_per_ticker[c.ticker].score:
                    best_per_ticker[c.ticker] = c
            # ensemble_score + regime_score 메타 주입
            # regime_score: weights.yml 10% 항목 — market_regime["1d"]["score"] 에서 추출.
            # runner.py 는 --decide 모드에서만 주입하므로 일반 스캔 흐름에서 별도 주입 필요.
            _regime_score_val: int | None = None
            try:
                _raw = (market_regime or {}).get("1d", {}).get("score")
                if _raw is not None:
                    # 표시용 score 가 소수로 내려올 수 있으므로 round 로 정규화 (내림 왜곡 방지).
                    _regime_score_val = int(round(float(_raw)))
            except (TypeError, ValueError):
                _regime_score_val = None
            for ticker, cand in best_per_ticker.items():
                ws = weighted_scores.get(ticker, 1.0)
                meta_patch: dict = {
                    "ensemble_score": ws,
                    "ensemble_count": int(round(ws)),
                }
                if _regime_score_val is not None:
                    meta_patch["regime_score"] = _regime_score_val
                cand.metadata = {**(cand.metadata or {}), **meta_patch}

            # PR-B: 풀별 분리 ranking — STOCK 풀과 ETN_ETF 풀이 서로 영향 없이 독립 산출.
            # OTHER 풀(REIT/SPAC/UNKNOWN)은 ranking 미진입 (D2: 안전 분리).
            stock_cands, etn_etf_cands = [], []
            for cand in best_per_ticker.values():
                pt = (getattr(cand, "metadata", None) or {}).get("product_type", "UNKNOWN")
                if pt == "STOCK":
                    stock_cands.append(cand)
                elif pt in ("ETN", "ETF"):
                    etn_etf_cands.append(cand)
                # 그 외 (REIT/SPAC/UNKNOWN) → ranking 미진입
            ranked_stock = aggregate_candidates(stock_cands, weight_config, pool="STOCK")
            ranked_etn_etf = aggregate_candidates(etn_etf_cands, weight_config, pool="ETN_ETF")
            # 풀별 regret 도 독립 산출 — 시장별 RegretWeights + composite_weights 주입
            if ranked_stock:
                ranked_stock = compute_regret_scores(
                    ranked_stock, ensemble_scores=weighted_scores,
                    weights=_mcfg.regret_weights,
                    composite_weights=_mcfg.composite_weights,
                )
            if ranked_etn_etf:
                ranked_etn_etf = compute_regret_scores(
                    ranked_etn_etf, ensemble_scores=weighted_scores,
                    weights=_mcfg.regret_weights,
                    composite_weights=_mcfg.composite_weights,
                )
            ranked = list(ranked_stock) + list(ranked_etn_etf)

            # S4+S2/S3 confluence 페널티 — 시장별 penalty (현재 KOSPI/KOSDAQ 모두 1.0)
            _S4_PREFIXES = ("strategy_four_pullback_ma",)
            _S2S3_PREFIXES = ("strategy_two", "strategy_three")
            _CONFLUENCE_PENALTY = _mcfg.confluence_penalty
            s4_tickers = {
                c.ticker
                for sid, cs in filtered_candidates_by_strategy.items()
                if any(sid.startswith(p) for p in _S4_PREFIXES)
                for c in cs
            }
            s2s3_tickers = {
                c.ticker
                for sid, cs in filtered_candidates_by_strategy.items()
                if any(sid.startswith(p) for p in _S2S3_PREFIXES)
                for c in cs
            }
            penalized_tickers = s4_tickers & s2s3_tickers
            if penalized_tickers:
                for rc in ranked:
                    if rc.candidate.ticker in penalized_tickers:
                        old_cs = rc.normalized_metrics.get("composite_score", 0.0)
                        rc.normalized_metrics["composite_score"] = round(old_cs * _CONFLUENCE_PENALTY, 4)
                        rc.normalized_metrics["confluence_penalty"] = True
                ranked.sort(key=lambda r: (
                    -r.normalized_metrics.get("composite_score", 0.0),
                    -r.final_score,
                    r.candidate.ticker,
                ))
                for _i, rc in enumerate(ranked, start=1):
                    rc.normalized_metrics["composite_rank"] = _i
                    rc.normalized_metrics["regret_rank"] = _i

            ranked_for_all = ranked
            ticker_to_ranked = {rc.candidate.ticker: rc for rc in ranked}
        except Exception as e:
            logger.warning(f"의사결정 스코어 계산 실패 (생략): {e}")

    def _build_signal(
        strategy_id: str,
        label: str,
        category: str,
        tf: str,
        c,
        fallback_rank: int,
        fallback_total: int,
        all_candidates_for_percentile: list | None = None,
    ) -> Signal:
        meta = getattr(c, "metadata", {}) or {}
        entry = int(getattr(c, "entry_price", 0))
        stop  = int(getattr(c, "stop_loss",   0))
        t1    = int(getattr(c, "target_1",    0))
        t2_raw = getattr(c, "target_2", None)
        t2    = int(t2_raw) if t2_raw else None
        # PR-G: T2-T1 < 1.5% × entry → 단일 목표로 통합
        if t2 is not None and entry > 0 and (t2 - t1) < entry * 0.015:
            t2 = None

        limit_entry_raw = getattr(c, "limit_entry", None)
        limit_stop_raw  = getattr(c, "limit_stop", None)
        limit_entry = int(limit_entry_raw) if limit_entry_raw else None
        limit_stop  = int(limit_stop_raw)  if limit_stop_raw  else None

        rr_ratio = float(meta.get("rr_ratio", 0.0))
        rr_band_raw = str(meta.get("rr_band", "below")).lower()
        rr_band = _BAND_MAP.get(rr_band_raw, "UNDER")
        atr_14_raw = meta.get("atr_14")
        atr_14 = int(atr_14_raw) if atr_14_raw else None
        rsi_14_raw = meta.get("rsi_14")
        rsi_14 = float(rsi_14_raw) if (rsi_14_raw is not None and rsi_14_raw == rsi_14_raw) else None

        ticker_snap = snapshot.tickers.get(c.ticker)
        cp   = ticker_snap.current_price if ticker_snap else entry
        chg  = ticker_snap.change_pct    if ticker_snap else 0.0
        vol  = ticker_snap.volume        if ticker_snap else 0
        mcap = ticker_snap.market_cap_krw if ticker_snap else None
        fund = ticker_snap.fundamentals   if ticker_snap else Fundamentals()
        flow = ticker_snap.flow           if ticker_snap else Flow()

        naver_url = str(meta.get("naver_url", ""))

        rc = ticker_to_ranked.get(c.ticker)
        decision: DecisionMeta | None = None
        # ranking 우선순위: composite_rank > regret_rank > fallback_rank
        if rc is not None:
            r_rank = int(rc.normalized_metrics.get(
                "composite_rank", rc.normalized_metrics.get("regret_rank", fallback_rank)
            ))
            r_total = int(rc.normalized_metrics.get(
                "composite_total", rc.normalized_metrics.get("regret_total", fallback_total)
            ))
            r_score = float(rc.normalized_metrics.get(
                "composite_score", rc.normalized_metrics.get("regret_score", c.score)
            ))
        else:
            r_rank = fallback_rank
            r_total = fallback_total
            r_score = round(c.score, 1)

        if rc is not None and weight_config is not None:
            prio_map = {p.key: p for p in weight_config.priorities}
            factors = [
                DecisionFactor(
                    key=key,
                    label=prio_map[key].label,
                    weight=prio_map[key].weight,
                    normalized=rc.normalized_metrics.get(key, 0.0),
                    contribution=contrib,
                )
                for key, contrib in rc.contributions.items()
                if key in prio_map
            ]
            factors.sort(key=lambda f: f.contribution, reverse=True)
            mr = rc.normalized_metrics.get("regret_score")
            # 4축 breakdown — regret_scorer 가 저장한 individual normalized rank 사용.
            regret_factors_list: list[RegretFactor] | None = [
                RegretFactor(
                    key=k,
                    label=REGRET_FACTOR_LABELS[k],
                    weight=_factor_labels[k],
                    normalized=float(rc.normalized_metrics[f"regret_{k}"]),
                    contribution=round(
                        _factor_labels[k]
                        * float(rc.normalized_metrics[f"regret_{k}"]),
                        4,
                    ),
                )
                for k in _factor_labels
                if f"regret_{k}" in rc.normalized_metrics
            ] or None
            decision = DecisionMeta(
                final_score=rc.final_score,
                factors=factors,
                max_regret=float(mr) if mr is not None else None,
                regret_score=float(mr) if mr is not None else None,
                regret_factors=regret_factors_list,
            )

        sig_date = getattr(c, "signal_date", None)
        signal_date_iso: str | None = None
        if sig_date is not None and hasattr(sig_date, "isoformat"):
            try:
                iso = sig_date.isoformat()
                if isinstance(iso, str):
                    signal_date_iso = iso
            except Exception:
                signal_date_iso = None

        # PR-B: ProductType / Pool 메타 — candidate.metadata 에서 추출 후 Signal 노출
        pt_raw = str(meta.get("product_type") or "UNKNOWN")
        try:
            pt_enum = ProductType(pt_raw)
        except ValueError:
            pt_enum = ProductType.UNKNOWN
        pool_value = to_pool(pt_enum).value

        # PR-K (P3-1): tradability_score — RankedCandidate 에서 추출
        tradability_s: float | None = (
            float(rc.normalized_metrics["tradability_score"])
            if rc is not None and "tradability_score" in rc.normalized_metrics
            else None
        )

        # PR-L (P4): confirmation_level + active_regime
        confirmation_lv: str | None = meta.get("confirmation_level") or None
        active_regime_lbl: str | None = (
            (market_regime or {}).get("1d", {}).get("regime") or None
        )

        # PR-C (P1-1): 주문 타입 의도 분류 — limit_entry 우선, 없으면 entry 사용
        ref_entry = float(limit_entry if limit_entry else entry)
        try:
            order_intent = (
                classify_order_type(ref_entry, float(cp))
                if cp > 0 else OrderTypeIntent.IMMEDIATE
            )
        except Exception:
            order_intent = OrderTypeIntent.IMMEDIATE
        order_label_ko = korean_label(order_intent)

        # Task 2: asset_class 분류 — candidate.metadata 의 product_type + 종목명 사용
        asset_class_value: str | None = None
        try:
            product_type_str = str(meta.get("product_type") or "UNKNOWN")
            product_type_enum = ProductType(product_type_str)
            asset_class_enum = classify_asset_class(product_type_enum, c.name)
            asset_class_value = asset_class_enum.value
        except (ValueError, AttributeError):
            asset_class_value = None

        # 전략 고유 진입 시그널 컴포넌트 ('all' aggregator 는 빈 리스트 반환)
        signal_components_list = build_signal_components(meta, strategy_id) or None

        return Signal(
            ticker=c.ticker,
            name=c.name,
            strategy=StrategyContext(
                id=strategy_id, label=label, category=category, timeframe=tf,
            ),
            trade_plan=TradePlan(
                entry=entry, stop=stop, target_1=t1, target_2=t2,
                rr_ratio=rr_ratio, rr_band=rr_band, atr_14=atr_14, rsi_14=rsi_14,
                limit_entry=limit_entry, limit_stop=limit_stop,
                order_type_intent=order_intent.value,
                order_type_label_ko=order_label_ko,
            ),
            ranking=Ranking(
                score=round(r_score, 1),
                signal_strength=(
                    compute_signal_strength_percentile(c, all_candidates_for_percentile)
                    if all_candidates_for_percentile else round(c.score / 10.0, 1)
                ),
                rank=r_rank,
                percentile=(
                    round((1 - r_rank / r_total) * 100, 1)
                    if r_total > 1 else 100.0
                ),
                decision=decision,
            ),
            live_quote=LiveQuote(
                current_price=cp, change_pct=chg, volume=vol, market_cap_krw=mcap,
                **{"_display": LiveQuoteDisplay(
                    current_price=f"{cp:,}",
                    change=_fmt_pct(chg, positive_prefix="+") or "0.00%",
                    direction=_direction(chg),
                    volume=f"{vol:,}",
                    market_cap=_fmt_krw(mcap),
                )}
            ),
            fundamentals=fund,
            flow=flow,
            external_links={"naver_finance": naver_url} if naver_url else {},
            signal_date=signal_date_iso,
            product_type=pt_enum.value,
            pool=pool_value,
            tradability_score=tradability_s,
            confirmation_level=confirmation_lv,
            active_regime=active_regime_lbl,
            asset_class=asset_class_value,
            signal_components=signal_components_list,
        )

    def _is_actionable(sig: Signal) -> bool:
        """compute_signal_status 가 VALID 인 신호만 signals.json 에 포함.

        '오늘 매수할 종목' 만 노출 — current_price >= target_1 (TARGET_REACHED) /
        current_price <= stop (STOPPED_OUT) / signal_date 4 거래일 초과 (STALE) 후보 자동 제외.
        """
        status = compute_signal_status(
            current_price=sig.live_quote.current_price,
            stop=sig.trade_plan.limit_stop or sig.trade_plan.stop,
            target_1=sig.trade_plan.target_1,
            signal_date_str=sig.signal_date,
            timeframe=sig.strategy.timeframe,
        )
        return status == "VALID"

    signals: list[Signal] = []
    # all_candidates 리스트에서 candidate 객체만 추출 (percentile rank 계산용)
    candidates_for_percentile = [c for _, c in all_candidates]
    for rank_idx, (strategy_id, c) in enumerate(all_candidates, start=1):
        label, category = _STRATEGY_LABELS.get(
            strategy_id, (strategy_id.upper(), ""),
        )
        tf = getattr(c, "timeframe", None) or _infer_timeframe_from_id(strategy_id)
        sig = _build_signal(
            strategy_id, label, category, tf, c, rank_idx, total,
            all_candidates_for_percentile=candidates_for_percentile,
        )
        if _is_actionable(sig):
            signals.append(sig)

    # 'all' 통합 entry — ticker dedup + regret 기반 정렬
    if ranked_for_all:
        n_all = len(ranked_for_all)
        # all entry용 percentile 계산: ranked_for_all 의 candidate 리스트
        all_entry_candidates = [rc.candidate for rc in ranked_for_all]
        for rc in ranked_for_all:
            c = rc.candidate
            origin_tf = getattr(c, "timeframe", None) or _infer_timeframe_from_id(
                getattr(c, "strategy", "") or "",
            )
            sig = _build_signal(
                "all", "ALL", "MULTI", origin_tf, c,
                fallback_rank=int(rc.normalized_metrics.get(
                    "composite_rank", rc.normalized_metrics.get("regret_rank", 1)
                )),
                fallback_total=n_all,
                all_candidates_for_percentile=all_entry_candidates,
            )
            if _is_actionable(sig):
                signals.append(sig)

    by_strategy: dict[str, int] = {}
    by_rr_band: dict[str, int] = {}
    for s in signals:
        by_strategy[s.strategy.label] = by_strategy.get(s.strategy.label, 0) + 1
        by_rr_band[s.trade_plan.rr_band] = by_rr_band.get(s.trade_plan.rr_band, 0) + 1

    has_all_entry = any(s.strategy.id == "all" for s in signals)
    strategy_names = sorted({
        s.strategy.label for s in signals if s.strategy.id != "all"
    })
    timeframe_names = sorted({
        s.strategy.timeframe for s in signals if s.strategy.timeframe
    }, key=_timeframe_sort_key)

    now_kst = datetime.now(KST)
    target_date_iso = ""
    if target_date:
        raw = target_date.replace("-", "")
        try:
            target_date_iso = datetime.strptime(raw, "%Y%m%d").date().isoformat()
        except ValueError:
            target_date_iso = target_date
    return SignalsPayload(
        generated_at=now_kst.isoformat(),
        generated_at_display=now_kst.strftime("%Y-%m-%d %H:%M KST"),
        target_date=target_date_iso,
        target_date_display=_format_target_display(target_date, now_kst),
        asof=now_kst.isoformat(),
        market_indices=mi_display,
        market_regime=market_regime,
        filters={
            "strategies": (["ALL"] if has_all_entry else []) + strategy_names,
            "timeframes":  ["ALL"] + timeframe_names,
            "sort_options": ["score", "rr_ratio", "entry"],
        },
        signals=signals,
        stats={
            "total_signals": len(signals),
            "by_strategy": by_strategy,
            "by_rr_band":  by_rr_band,
        },
    )
