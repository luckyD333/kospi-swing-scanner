"""전략별 진입 시그널 컴포넌트 빌더.

매칭(전략) 카드의 ✓/⚠ 리스트에 노출할 컴포넌트를 metadata 에서 추출.
잠재력·기회 점수의 4축과 달리 전략마다 키 셋과 의미가 다르므로 룰을 전략별로 둔다.

각 룰은 metadata dict 를 받아 {key,label,status,value} dict 또는 None 을 반환한다.
None 이면 컴포넌트 리스트에서 누락된다 (조건 미충족 또는 metadata 결측).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

# 전략 1 fallback 변형 (_r1/_r2) 와 timeframe 변형은 동일 룰을 공유.
# strategy_id 정규화 단계에서 base id 로 매핑.
_STRATEGY_ID_BASE: dict[str, str] = {
    "strategy_one_d_v2":      "strategy_one",
    "strategy_one_w_v2":      "strategy_one",
    "strategy_one_1h_v2":     "strategy_one",
    "strategy_one_30m_v2":    "strategy_one",
    "strategy_one_d_v2_r1":   "strategy_one",
    "strategy_one_d_v2_r2":   "strategy_one",
    "strategy_one_w_v2_r1":   "strategy_one",
    "strategy_one_w_v2_r2":   "strategy_one",
    "strategy_one_1h_v2_r1":  "strategy_one",
    "strategy_one_1h_v2_r2":  "strategy_one",
    "strategy_one_30m_v2_r1": "strategy_one",
    "strategy_one_30m_v2_r2": "strategy_one",

    "strategy_two_cross_sectional_momentum": "strategy_two",
    "strategy_two_1h":  "strategy_two",
    "strategy_two_30m": "strategy_two",

    "strategy_three_trend_following": "strategy_three",
    "strategy_three_1h":  "strategy_three",
    "strategy_three_30m": "strategy_three",

    "strategy_four_pullback_ma":     "strategy_four",
    "strategy_four_pullback_ma_1h":  "strategy_four",
    "strategy_four_pullback_ma_30m": "strategy_four",

    "strategy_five_bull_flag":     "strategy_five",
    "strategy_five_bull_flag_1h":  "strategy_five",
    "strategy_five_bull_flag_30m": "strategy_five",
}


@dataclass(frozen=True)
class _Rule:
    key: str
    label: str
    builder: Callable[[dict], Optional[dict]]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _component(key: str, label: str, status: str, value: str | None) -> dict:
    return {"key": key, "label": label, "status": status, "value": value}


def _has_trigger(metadata: dict, *keys: str) -> bool:
    fired = set(metadata.get("triggers_fired") or [])
    return any(k in fired for k in keys)


# ---------------------------------------------------------------------------
# 전략 1 — Mean Reversion (RSI + BB + 쌍바닥 + 장악형 양봉)
# ---------------------------------------------------------------------------

def _one_rsi(metadata: dict) -> dict | None:
    rsi = metadata.get("rsi_14")
    if rsi is None or rsi != rsi:  # NaN
        return None
    rsi = float(rsi)
    if rsi < 30:
        status = "ok"
    elif rsi < 35:
        status = "warn"
    else:
        return None
    return _component("rsi_oversold", "RSI 과매도", status, f"{rsi:.1f}")


def _one_bb(metadata: dict) -> dict | None:
    if not _has_trigger(metadata, "bb_lower_breach"):
        return None
    return _component("bb_lower_touch", "BB 하단 터치", "ok", None)


def _one_double_bottom(metadata: dict) -> dict | None:
    if not _has_trigger(metadata, "double_bottom"):
        return None
    return _component("double_bottom", "쌍바닥", "ok", None)


def _one_engulfing(metadata: dict) -> dict | None:
    if not _has_trigger(metadata, "bullish_engulfing"):
        return None
    return _component("bullish_engulfing", "장악형 양봉", "ok", None)


# ---------------------------------------------------------------------------
# 전략 2 — Cross-sectional Momentum
# ---------------------------------------------------------------------------

def _two_momentum(metadata: dict) -> dict | None:
    pct = metadata.get("momentum_pct")
    if pct is None or pct != pct:
        return None
    pct = float(pct)
    if pct <= 0:
        return None
    status = "ok" if pct >= 0.05 else "warn"
    return _component("momentum_15d", "15일 상대강도", status, f"+{pct * 100:.1f}%")


def _two_top_quartile(metadata: dict) -> dict | None:
    rank = metadata.get("percentile_rank")
    if rank is None or rank != rank:
        return None
    rank = float(rank)
    if rank < 0.75:
        return None
    status = "ok" if rank >= 0.85 else "warn"
    return _component("top_quartile", "상위 25% 진입", status, f"{rank * 100:.0f}%")


# ---------------------------------------------------------------------------
# 전략 3 — Trend Following (Donchian)
# ---------------------------------------------------------------------------

def _three_breakout(metadata: dict) -> dict | None:
    pct = metadata.get("breakout_pct")
    if pct is None or pct != pct:
        return None
    pct = float(pct)
    if pct <= 0:
        return None
    status = "ok" if pct >= 0.01 else "warn"
    return _component("donchian_breakout", "Donchian 20일 돌파", status, f"+{pct * 100:.2f}%")


def _three_volume_surge(metadata: dict) -> dict | None:
    ratio = metadata.get("vol_ratio")
    if ratio is None or ratio != ratio:
        return None
    ratio = float(ratio)
    if ratio < 1.0:
        return None
    status = "ok" if ratio >= 1.5 else "warn"
    return _component("volume_surge", "거래량 동반", status, f"{ratio:.1f}x")


# ---------------------------------------------------------------------------
# 전략 4 — Pullback to MA
# ---------------------------------------------------------------------------

def _four_ma20_uptrend(metadata: dict) -> dict | None:
    pct = metadata.get("above_ma20_pct")
    if pct is None or pct != pct:
        return None
    pct = float(pct)
    if pct <= 0:
        return None
    status = "ok" if pct >= 1.0 else "warn"
    return _component("ma20_uptrend", "MA20 상승 추세", status, f"+{pct:.1f}%")


def _four_pullback_recovery(metadata: dict) -> dict | None:
    # 진입 조건상 ma5 회복은 항상 충족된 상태 (스캐너 통과 후보)
    # metadata 에 ma5 키가 있으면 ok, 없으면 omit (다른 전략 metadata 와의 안전 분기)
    if metadata.get("ma5") is None:
        return None
    return _component("ma5_pullback_recovery", "MA5 눌림목 회복", "ok", None)


def _four_volume_confirm(metadata: dict) -> dict | None:
    ratio = metadata.get("vol_ratio")
    if ratio is None or ratio != ratio:
        return None
    ratio = float(ratio)
    status = "ok" if ratio >= 1.0 else "warn"
    return _component("volume_confirm", "수급 동반", status, f"{ratio:.1f}x")


# ---------------------------------------------------------------------------
# 전략 5 — Bull Flag
# ---------------------------------------------------------------------------

def _five_flagpole(metadata: dict) -> dict | None:
    pole = metadata.get("pole_pct")
    if pole is None or pole != pole:
        return None
    pole = float(pole)
    if pole < 8.0:
        return None
    status = "ok" if pole >= 10.0 else "warn"
    return _component("flagpole", "Flagpole 상승", status, f"+{pole:.1f}%")


def _five_consolidation(metadata: dict) -> dict | None:
    ratio = metadata.get("flag_vol_ratio")
    if ratio is None or ratio != ratio:
        return None
    ratio = float(ratio)
    if ratio >= 0.7:
        return None
    status = "ok" if ratio < 0.6 else "warn"
    return _component("flag_consolidation", "Flag 거래량 수축", status, f"{ratio * 100:.0f}%")


def _five_breakout(metadata: dict) -> dict | None:
    pct = metadata.get("breakout_pct")
    if pct is None or pct != pct:
        return None
    pct = float(pct)
    if pct <= 0:
        return None
    status = "ok" if pct >= 1.0 else "warn"
    return _component("breakout", "돌파", status, f"+{pct:.2f}%")


def _five_volume_expansion(metadata: dict) -> dict | None:
    ratio = metadata.get("vol_ratio")
    if ratio is None or ratio != ratio:
        return None
    ratio = float(ratio)
    if ratio < 1.0:
        return None
    status = "ok" if ratio >= 1.5 else "warn"
    return _component("volume_expansion", "거래량 확장", status, f"{ratio:.1f}x")


# ---------------------------------------------------------------------------
# 전략 ID → 룰 매핑
# ---------------------------------------------------------------------------

_RULES_BY_BASE: dict[str, list[_Rule]] = {
    "strategy_one": [
        _Rule("rsi_oversold",      "RSI 과매도",      _one_rsi),
        _Rule("bb_lower_touch",    "BB 하단 터치",    _one_bb),
        _Rule("double_bottom",     "쌍바닥",          _one_double_bottom),
        _Rule("bullish_engulfing", "장악형 양봉",     _one_engulfing),
    ],
    "strategy_two": [
        _Rule("momentum_15d",  "15일 상대강도",  _two_momentum),
        _Rule("top_quartile",  "상위 25% 진입",  _two_top_quartile),
    ],
    "strategy_three": [
        _Rule("donchian_breakout", "Donchian 20일 돌파", _three_breakout),
        _Rule("volume_surge",      "거래량 동반",        _three_volume_surge),
    ],
    "strategy_four": [
        _Rule("ma20_uptrend",          "MA20 상승 추세",   _four_ma20_uptrend),
        _Rule("ma5_pullback_recovery", "MA5 눌림목 회복",  _four_pullback_recovery),
        _Rule("volume_confirm",        "수급 동반",        _four_volume_confirm),
    ],
    "strategy_five": [
        _Rule("flagpole",          "Flagpole 상승",     _five_flagpole),
        _Rule("flag_consolidation", "Flag 거래량 수축",  _five_consolidation),
        _Rule("breakout",          "돌파",              _five_breakout),
        _Rule("volume_expansion",  "거래량 확장",        _five_volume_expansion),
    ],
}


def build_signal_components(metadata: dict | None, strategy_id: str) -> list[dict]:
    """전략별 진입 시그널 컴포넌트 리스트 산출.

    반환 dict 는 4개 필드 고정: key, label, status (ok/warn/miss), value (str | None).
    'all' 통합 entry 또는 미지정 전략은 빈 리스트를 반환한다.
    """
    if not metadata:
        return []
    base = _STRATEGY_ID_BASE.get(strategy_id)
    rules = _RULES_BY_BASE.get(base or "")
    if not rules:
        return []
    components: list[dict] = []
    for rule in rules:
        comp = rule.builder(metadata)
        if comp is not None:
            components.append(comp)
    return components
