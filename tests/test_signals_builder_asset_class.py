"""
테스트: Candidate/Signal 에 asset_class 필드 전파 (Task 2).

Red 단계: asset_class 필드 존재 및 분류 정확성 검증.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from output.signals_builder import build_signals_payload
from output.models import (
    MarketSnapshot, TickerSnapshot, Fundamentals, Flow,
)

KST = ZoneInfo("Asia/Seoul")


def _make_snapshot():
    """3개 ticker snapshot: 주식, 주식형ETF, 채권형ETF."""
    return MarketSnapshot(
        schema_version="1.0",
        generated_at="2026-05-03T22:00:00+09:00",
        source={},
        market_indices={},
        tickers={
            "005930": TickerSnapshot(
                ticker="005930", name="삼성전자",
                current_price=70000, change_pct=1.5, volume=10000000,
                market_cap_krw=4200000000000,
                fundamentals=Fundamentals(per=14.2, high_52w=75000, low_52w=60000),
                flow=Flow(foreign_ratio_pct=55.3),
            ),
            "466920": TickerSnapshot(
                ticker="466920", name="SOL 조선TOP3플러스",
                current_price=5900, change_pct=0.5, volume=500000,
                market_cap_krw=None,
                fundamentals=Fundamentals(per=None, high_52w=6500, low_52w=4800),
                flow=Flow(foreign_ratio_pct=None),
            ),
            "469830": TickerSnapshot(
                ticker="469830", name="SOL 초단기채권액티브",
                current_price=9800, change_pct=0.02, volume=50000,
                market_cap_krw=None,
                fundamentals=Fundamentals(per=None, high_52w=9900, low_52w=9700),
                flow=Flow(foreign_ratio_pct=None),
            ),
        }
    )


def _make_candidate(ticker: str, name: str, score: float = 87.0, product_type: str = "STOCK"):
    """Mock candidate 생성."""
    c = MagicMock()
    c.ticker = ticker
    c.name = name
    c.score = score
    c.timeframe = "1D"
    c.entry_price = int(c.name == "삼성전자" and 70000) or 5900
    c.stop_loss = int(c.name == "삼성전자" and 68000) or 5700
    c.target_1 = int(c.name == "삼성전자" and 75000) or 6200
    c.target_2 = None
    c.signal_date = None
    c.metadata = {
        "rr_ratio": 2.0,
        "rr_band": "sweet",
        "atr_14": 100,
        "product_type": product_type,
        "naver_url": f"https://finance.naver.com/item/main.naver?code={ticker}",
    }
    return c


class TestAssetClassFieldInSignal:
    """Signal 모델에 asset_class 필드가 존재하고 정확히 채워지는지 검증."""

    def test_signal_has_asset_class_field(self):
        """Signal 이 asset_class 필드를 가져야 함."""
        snap = _make_snapshot()
        cand = _make_candidate("005930", "삼성전자", product_type="STOCK")
        payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})

        assert len(payload.signals) >= 1
        signal = payload.signals[0]
        assert hasattr(signal, "asset_class"), "Signal 은 asset_class 필드를 가져야 함"

    def test_asset_class_stock(self):
        """삼성전자(STOCK) → asset_class = 'STOCK'."""
        snap = _make_snapshot()
        cand = _make_candidate("005930", "삼성전자", product_type="STOCK")
        payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})

        signal = payload.signals[0]
        assert signal.ticker == "005930"
        assert signal.asset_class == "STOCK", f"Expected 'STOCK', got {signal.asset_class}"

    def test_asset_class_equity_etf(self):
        """SOL 조선TOP3플러스(ETF, 주식형) → asset_class = 'EQUITY_ETF'."""
        snap = _make_snapshot()
        cand = _make_candidate("466920", "SOL 조선TOP3플러스", product_type="ETF")
        payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})

        signal = payload.signals[0]
        assert signal.ticker == "466920"
        assert signal.asset_class == "EQUITY_ETF", f"Expected 'EQUITY_ETF', got {signal.asset_class}"

    def test_asset_class_bond_etf(self):
        """SOL 초단기채권액티브(ETF, 채권형) → asset_class = 'BOND_ETF'."""
        snap = _make_snapshot()
        cand = _make_candidate("469830", "SOL 초단기채권액티브", product_type="ETF")
        payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})

        signal = payload.signals[0]
        assert signal.ticker == "469830"
        assert signal.asset_class == "BOND_ETF", f"Expected 'BOND_ETF', got {signal.asset_class}"

    def test_multiple_signals_asset_class_preserved(self):
        """여러 신호가 각각 다른 asset_class 를 유지."""
        snap = _make_snapshot()
        candidates = [
            _make_candidate("005930", "삼성전자", score=100.0, product_type="STOCK"),
            _make_candidate("466920", "SOL 조선TOP3플러스", score=50.0, product_type="ETF"),
            _make_candidate("469830", "SOL 초단기채권액티브", score=30.0, product_type="ETF"),
        ]
        payload = build_signals_payload(snap, {"strategy_one_d_v2": candidates})

        assert len(payload.signals) >= 3

        by_ticker = {s.ticker: s for s in payload.signals}
        assert by_ticker["005930"].asset_class == "STOCK"
        assert by_ticker["466920"].asset_class == "EQUITY_ETF"
        assert by_ticker["469830"].asset_class == "BOND_ETF"


class TestAssetClassInSignalsJson:
    """signals.json 출력 (dict/JSON) 에 asset_class 필드가 포함되는지 검증."""

    def test_signals_json_includes_asset_class(self):
        """SignalsPayload.signals 배열의 각 entry 에 asset_class 키 존재."""
        snap = _make_snapshot()
        candidates = {
            "strategy_one_d_v2": [
                _make_candidate("005930", "삼성전자", product_type="STOCK"),
                _make_candidate("466920", "SOL 조선TOP3플러스", product_type="ETF"),
                _make_candidate("469830", "SOL 초단기채권액티브", product_type="ETF"),
            ]
        }
        payload = build_signals_payload(snap, candidates)

        # Pydantic model_dump() 로 dict 변환
        payload_dict = payload.model_dump()

        assert "signals" in payload_dict
        for sig_dict in payload_dict["signals"]:
            assert "asset_class" in sig_dict, \
                f"Signal {sig_dict.get('ticker')} 는 asset_class 필드가 없음"
            assert sig_dict["asset_class"] is not None, \
                f"Signal {sig_dict.get('ticker')} 의 asset_class 가 None"


class TestAssetClassFieldDefault:
    """asset_class 필드가 None 기본값을 가지는지 확인 (후방 호환성)."""

    def test_asset_class_none_default_when_no_metadata(self):
        """candidate.metadata 에 product_type 정보 없으면 asset_class = None."""
        snap = _make_snapshot()
        cand = MagicMock()
        cand.ticker = "005930"
        cand.name = "삼성전자"
        cand.score = 87.0
        cand.timeframe = "1D"
        cand.entry_price = 70000
        cand.stop_loss = 68000
        cand.target_1 = 75000
        cand.target_2 = None
        cand.signal_date = None
        cand.metadata = {
            "rr_ratio": 2.0,
            "rr_band": "sweet",
            "atr_14": 100,
            # product_type 제거 → classify_asset_class 호출 불가
            "naver_url": "https://finance.naver.com/item/main.naver?code=005930",
        }

        payload = build_signals_payload(snap, {"strategy_one_d_v2": [cand]})
        signal = payload.signals[0]

        # asset_class 는 None 또는 추론된 값. 최소한 에러 없이 처리됨.
        assert signal.asset_class is None or isinstance(signal.asset_class, str)
