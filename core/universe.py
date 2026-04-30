"""
core/universe.py — 종목 유니버스 필터.

Strategy D v2 §3.4 (시총·유동성·상장경과·관리종목 등) 구현.
기존 daily_only_scanner.DailyOnlyScanner._filter_universe 의 시총 필터를 이쪽으로 분리.

거래정지/관리종목 제외는 데이터 소스가 메타데이터를 제공하지 않으면 스킵 (현재
KRX Proxy는 status 미제공). 향후 소스 확장 시 hook 추가.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .data_fetch import DataClient
from .data_sources.krx_proxy import CircuitBreakerOpen

logger = logging.getLogger(__name__)


@dataclass
class UniverseFilter:
    """시총 + 유동성 필터 파라미터 (모두 inclusive 범위)."""
    min_market_cap_bil: float = 2000.0      # 최소 시총 (억)
    max_market_cap_bil: float = 30000.0     # 최대 시총 (억)
    min_daily_volume: int = 100_000          # 일 최소 거래량
    market: str = "KOSPI"


@dataclass
class UniverseResult:
    """필터 통과 ticker + 시총 lookup."""
    tickers: List[str]
    cap_lookup: Dict[str, float]   # ticker → 원 단위 시총 (네이버 raw)
    name_lookup: Dict[str, str]    # ticker → 종목명


def build_universe(
    client: DataClient,
    target_date: str,
    filt: UniverseFilter,
) -> UniverseResult:
    """
    Phase 1 유니버스 필터링.

    1) ticker 리스트 확보 (DataClient fallback 체인)
    2) KRX Proxy 로 공식 시총 보강 (use_krx_for_universe=True 시)
    3) 시총 필터 적용 → 통과 ticker 리스트 반환

    실패 모드:
      - strict_mode + KRX Proxy 실패 → RuntimeError 전파 (스캔 중단)
      - 시총 조회 전부 실패 → 필터 없이 전종목 통과 (warning)
    """
    all_tickers = client.get_tickers(filt.market, target_date)

    cap_lookup: Dict[str, float] = {}
    name_lookup: Dict[str, str] = {}

    # 1) KRX Proxy 공식 시총 보강
    if client.use_krx_for_universe:
        logger.info(
            f"  [KRX Proxy] 공식 시총 보강 중... ({len(all_tickers)}종목)"
        )
        try:
            enriched = client.krx_proxy.enrich_with_trade_info(
                tickers=all_tickers,
                market=filt.market,
                bas_dd=target_date,
            )
            cap_lookup = {
                ticker: info["market_cap"]
                for ticker, info in enriched.items()
                if info.get("market_cap", 0) > 0
            }
            name_lookup = {
                ticker: info["name"] for ticker, info in enriched.items()
            }
            logger.info(
                f"  [KRX Proxy] 보강 성공: {len(cap_lookup)}종목 "
                f"(실패/미수집 {len(all_tickers) - len(cap_lookup)}개)"
            )
        except (CircuitBreakerOpen, RuntimeError) as e:
            if client.strict_mode:
                logger.error(
                    f"  [KRX Proxy] 보강 실패 + strict_mode → 스캔 전체 중단: {e}"
                )
                raise RuntimeError(
                    f"KRX Proxy 데이터 수집 불완전. "
                    f"strict_mode=True이므로 중단. 원인: {e}"
                )
            logger.warning(f"  [KRX Proxy] 보강 실패, fallback 진행: {e}")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.warning(f"  [KRX Proxy] 예상 외 오류, fallback 진행: {e}")

    # 2) fallback: 1차 소스 시총 사용
    if not cap_lookup:
        cap_df = client.get_market_cap(filt.market, target_date)
        if not cap_df.empty and "시가총액" in cap_df.columns:
            cap_lookup = cap_df["시가총액"].to_dict()
            if "종목명" in cap_df.columns:
                name_lookup = cap_df["종목명"].to_dict()

    # 3) 시총 lookup 자체가 없으면 필터 우회
    if not cap_lookup:
        logger.warning("  시가총액 조회 실패. 필터 없이 전종목 진행.")
        return UniverseResult(
            tickers=list(all_tickers),
            cap_lookup={},
            name_lookup=name_lookup,
        )

    # 4) 시총 범위 필터 (억 단위)
    filtered = [
        t for t in all_tickers
        if filt.min_market_cap_bil
        <= cap_lookup.get(t, 0) / 100_000_000
        <= filt.max_market_cap_bil
    ]

    return UniverseResult(
        tickers=filtered,
        cap_lookup=cap_lookup,
        name_lookup=name_lookup,
    )
