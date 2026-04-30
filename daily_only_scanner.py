"""
daily_only_scanner.py — 일봉만으로 KOSPI 전종목 Strategy D v2 스크리닝 (legacy CLI).

Sub-1 이후: 데이터 소스 / DataClient / 유니버스 필터는 core/ 패키지에서 import.
Sub-3에서 cli.py 로 대체된 후 본 파일은 삭제 예정.

re-export (테스트 호환): DailyDataSource, DataClient, KRXProxySource, CircuitBreaker,
                         CircuitBreakerOpen, NaverSource, PykrxSource, FDRSource.

실행:
    python daily_only_scanner.py                # 당일 기준 스캔
    python daily_only_scanner.py --date 20260418 # 특정일 기준
    python daily_only_scanner.py --top 20        # 상위 20개만

의존성:
    pip install pykrx finance-datareader pandas numpy scipy ta
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# Strategy D v2 백테스트 엔진
from backtest_engine.strategy import StrategyD, StrategyDConfig
from backtest_engine.detectors import (
    DoubleBottomSimple,
    DoubleBottomFractal,
    DoubleBottomProminence,
)
from backtest_engine.screener import ScreenerHit

# core/ 공통 모듈 (Sub-1 추출 산출물)
from core.data_sources.base import DailyDataSource
from core.data_sources.pykrx import PykrxSource
from core.data_sources.fdr import FDRSource
from core.data_sources.krx_proxy import (
    KRXProxySource,
    CircuitBreaker,
    CircuitBreakerOpen,
)
from core.data_sources.naver import NaverSource
from core.data_fetch import DataClient
from core.universe import UniverseFilter, build_universe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# 일봉 전용 스크리너
# ============================================================================

@dataclass
class ScanConfig:
    """일봉 스크리너 설정"""
    market: str = "KOSPI"                  # "KOSPI", "KOSDAQ", "KRX"
    min_market_cap_bil: float = 2000.0      # 최소 시총 2천억
    max_market_cap_bil: float = 30000.0     # 최대 시총 3조
    min_daily_volume: int = 100_000         # 일 최소 거래량
    lookback_days: int = 90                 # 지표 계산용 과거 기간
    top_n: int = 20                          # 최종 출력 상위 N개
    detector_name: str = "simple"            # "simple" / "fractal" / "prominence"


@dataclass
class ScanCandidate:
    """스크리닝 결과 단일 종목"""
    ticker: str
    name: str
    market: str
    current_price: float
    market_cap_bil: float
    volume_20d_avg: float
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    confidence: float
    conditions_met: Dict[str, bool]

    @property
    def risk_pct(self) -> float:
        return (self.entry_price - self.stop_loss) / self.entry_price * 100

    @property
    def reward_pct_t1(self) -> float:
        return (self.target_1 - self.entry_price) / self.entry_price * 100

    @property
    def reward_pct_t2(self) -> float:
        return (self.target_2 - self.entry_price) / self.entry_price * 100


class DailyOnlyScanner:
    """
    일봉 전용 KOSPI/KOSDAQ 스크리너.

    Phase 1: 유니버스 필터 (시총, 거래량) — core.universe.build_universe 위임
    Phase 2: Strategy D v2 진입 조건 체크
    Phase 3: confidence 순 정렬 및 매수/손절/익절 가격 출력
    """

    def __init__(
        self,
        client: Optional[DataClient] = None,
        config: Optional[ScanConfig] = None,
    ):
        self.client = client or DataClient()
        self.config = config or ScanConfig()

    def _build_strategy(self) -> StrategyD:
        det_map = {
            "simple": DoubleBottomSimple(),
            "fractal": DoubleBottomFractal(),
            "prominence": DoubleBottomProminence(prominence_pct=0.015),
        }
        detector = det_map.get(self.config.detector_name, DoubleBottomSimple())
        return StrategyD(
            config=StrategyDConfig(min_lookback_bars=25),  # BB 20 + 여유 5
            double_bottom_detector=detector,
        )

    def scan(self, target_date: Optional[str] = None) -> List[ScanCandidate]:
        """전종목 일봉 스캔"""
        if target_date is None:
            target_date = self._latest_business_day()

        end_str = target_date
        start_dt = datetime.strptime(target_date, "%Y%m%d") - timedelta(
            days=self.config.lookback_days + 30
        )
        start_str = start_dt.strftime("%Y%m%d")

        logger.info(f"🔍 스캔 시작: {self.config.market} @ {target_date}")

        # Phase 1: 유니버스 필터 (core/universe 위임)
        tickers = self._filter_universe(target_date)
        logger.info(f"📊 Phase 1 유니버스: {len(tickers)}종목")

        # Phase 2: Strategy D 진입 조건 체크
        candidates = []
        strategy = self._build_strategy()
        failed = 0

        for i, ticker in enumerate(tickers):
            if (i + 1) % 50 == 0:
                logger.info(f"  진행: {i+1}/{len(tickers)} (hits: {len(candidates)})")

            try:
                df = self.client.get_ohlcv(ticker, start_str, end_str)
                if len(df) < 30:
                    continue

                # 거래량 필터
                avg_volume = float(df["volume"].tail(20).mean())
                if avg_volume < self.config.min_daily_volume:
                    continue

                # Strategy D 진입 체크
                prepared = strategy.prepare(df)
                last_idx = len(prepared) - 1
                signal = strategy.check_entry(prepared, last_idx, ticker=ticker)

                if signal is not None:
                    name = self.client.get_ticker_name(ticker)
                    cap_bil = self._get_cap_for_ticker(ticker, target_date)

                    candidate = ScanCandidate(
                        ticker=ticker,
                        name=name,
                        market=self.config.market,
                        current_price=float(df["close"].iloc[-1]),
                        market_cap_bil=cap_bil,
                        volume_20d_avg=avg_volume,
                        entry_price=signal.entry_price,
                        stop_loss=signal.stop_loss,
                        target_1=signal.target_1,
                        target_2=signal.target_2,
                        confidence=signal.confidence,
                        conditions_met=signal.conditions_met,
                    )
                    candidates.append(candidate)

            except Exception as e:
                failed += 1
                if failed <= 3:
                    logger.debug(f"  {ticker} 분석 실패: {e}")

        logger.info(
            f"✅ Phase 2 완료: 시그널 {len(candidates)}개, 실패 {failed}개"
        )

        # confidence 내림차순 정렬
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[: self.config.top_n]

    # ------------------------------------------------------------------
    # 내부 helpers
    # ------------------------------------------------------------------

    def _filter_universe(self, target_date: str) -> List[str]:
        """시총·유동성 필터 (core.universe.build_universe 위임)."""
        result = build_universe(
            self.client,
            target_date,
            UniverseFilter(
                min_market_cap_bil=self.config.min_market_cap_bil,
                max_market_cap_bil=self.config.max_market_cap_bil,
                min_daily_volume=self.config.min_daily_volume,
                market=self.config.market,
            ),
        )
        # 호환을 위해 cap_lookup 보존 (_get_cap_for_ticker 가 사용)
        self._cap_lookup = result.cap_lookup
        return result.tickers

    def _get_cap_for_ticker(self, ticker: str, target_date: str) -> float:
        """억 단위"""
        cap_won = getattr(self, "_cap_lookup", {}).get(ticker, 0)
        return float(cap_won) / 100_000_000

    def _latest_business_day(self) -> str:
        """최근 영업일 (주말/장 시작 전 고려)"""
        today = date.today()
        now = datetime.now()
        # 장 마감(15:30) 이전이면 전일 기준
        if now.hour < 16:
            today -= timedelta(days=1)
        while today.weekday() >= 5:  # 주말
            today -= timedelta(days=1)
        return today.strftime("%Y%m%d")


# ============================================================================
# 출력 포맷터
# ============================================================================

def print_results(candidates: List[ScanCandidate], target_date: str):
    if not candidates:
        print("\n  ⚠️  진입 조건 충족 종목 없음\n")
        return

    print("\n" + "=" * 90)
    print(f"  🎯 {target_date} 장 마감 기준 — 매수 후보 {len(candidates)}개")
    print("=" * 90)

    # 요약 테이블
    print()
    print(f"  {'순위':>4}  {'종목코드':<8}  {'종목명':<15}  {'현재가':>10}  "
          f"{'시총(억)':>10}  {'Conf':>5}  {'손절':>8}  {'목표1':>8}  {'목표2':>8}")
    print("  " + "─" * 86)

    for i, c in enumerate(candidates, 1):
        print(
            f"  {i:>4}  {c.ticker:<8}  {c.name[:15]:<15}  {c.current_price:>10,.0f}  "
            f"{c.market_cap_bil:>10,.0f}  {c.confidence:>5.2f}  "
            f"{-c.risk_pct:>7.2f}%  +{c.reward_pct_t1:>6.2f}%  +{c.reward_pct_t2:>6.2f}%"
        )

    # 상세 정보
    print()
    print("─" * 90)
    print("  📋 상세 매수 정보 (상위 5개)")
    print("─" * 90)

    for i, c in enumerate(candidates[:5], 1):
        print(f"\n  ────── #{i}  [{c.ticker}] {c.name}  ──────")
        print(f"     시총               : {c.market_cap_bil:>12,.0f} 억원")
        print(f"     20일 평균 거래량    : {c.volume_20d_avg:>12,.0f} 주")
        print(f"     Confidence          : {c.confidence:>12.1%}")
        print(f"     ")
        print(f"     💰 진입가 (매수)    : {c.entry_price:>12,.0f} 원")
        print(f"     🛑 손절가           : {c.stop_loss:>12,.0f} 원 ({-c.risk_pct:+.2f}%)")
        print(f"     🎯 1차 목표 (익절)  : {c.target_1:>12,.0f} 원 (+{c.reward_pct_t1:.2f}%)")
        print(f"     🎯 2차 목표 (익절)  : {c.target_2:>12,.0f} 원 (+{c.reward_pct_t2:.2f}%)")
        print(f"     ⏰ 최대 보유        : 3 거래일 (미도달 시 시간 손절)")
        conds = [k for k, v in c.conditions_met.items() if v]
        print(f"     ✓ 충족 조건 ({len(conds)}): {', '.join(conds[:6])}{'...' if len(conds) > 6 else ''}")

    print("\n" + "=" * 90 + "\n")


def save_json(candidates: List[ScanCandidate], target_date: str, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"scan_{target_date}_{datetime.now().strftime('%H%M')}.json"
    filepath = output_dir / filename

    data = {
        "scan_time": datetime.now().isoformat(),
        "target_date": target_date,
        "count": len(candidates),
        "candidates": [asdict(c) for c in candidates],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 결과 저장: {filepath}")
    return filepath


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="일봉 전용 KOSPI/KOSDAQ Strategy D v2 스크리너"
    )
    parser.add_argument("--market", default="KOSPI", choices=["KOSPI", "KOSDAQ", "KRX"])
    parser.add_argument("--date", help="기준일 (YYYYMMDD). 미지정 시 최근 영업일")
    parser.add_argument("--top", type=int, default=20, help="상위 N개 (기본 20)")
    parser.add_argument("--detector", default="simple",
                        choices=["simple", "fractal", "prominence"])
    parser.add_argument("--min-cap", type=float, default=2000.0,
                        help="최소 시총 (억, 기본 2000)")
    parser.add_argument("--max-cap", type=float, default=30000.0,
                        help="최대 시총 (억, 기본 30000)")
    parser.add_argument("--output-dir", default="scan_results")
    parser.add_argument("--no-save", action="store_true", help="JSON 저장 안 함")
    parser.add_argument(
        "--no-krx", action="store_true",
        help="KRX 공식 Proxy 보강 비활성화 (네이버/pykrx만 사용)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="엄격 모드: KRX Proxy 데이터가 불완전하면 스캔 전체 중단 "
             "(Circuit Breaker OPEN 또는 실패율 50%% 초과 시)",
    )
    args = parser.parse_args()

    if args.date:
        try:
            datetime.strptime(args.date, "%Y%m%d")
        except ValueError:
            parser.error(f"--date 형식 오류: '{args.date}' (YYYYMMDD 형식 필요, 예: 20260418)")

    config = ScanConfig(
        market=args.market,
        min_market_cap_bil=args.min_cap,
        max_market_cap_bil=args.max_cap,
        top_n=args.top,
        detector_name=args.detector,
    )

    client = DataClient(
        use_krx_for_universe=not args.no_krx,
        strict_mode=args.strict,
    )
    scanner = DailyOnlyScanner(client=client, config=config)

    target = args.date or scanner._latest_business_day()
    candidates = scanner.scan(target_date=target)

    print_results(candidates, target)

    if not args.no_save and candidates:
        save_json(candidates, target, Path(args.output_dir))


if __name__ == "__main__":
    main()
