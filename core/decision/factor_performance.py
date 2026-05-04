"""
core/decision/factor_performance.py — 팩터 성과 분석 + 동적 가중치 조정.

scan_results 디렉토리의 팩터값을 수집하고, n일후 수익률과의 상관계수를 계산하여
동적 가중치 조정(softmax + floor)을 통해 포트폴리오 최적화를 지원합니다.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from core.cache.ohlcv_disk import OhlcvDiskCache
from core.decision.config import Priority, WeightConfig

logger = logging.getLogger(__name__)


def update_factor_records(
    scan_root: Path | str, cache_root: Path | str, hold_days: int = 3
) -> pd.DataFrame:
    """scan_results 디렉토리를 순회하며 팩터값 + n일후수익률을 parquet에 증분 저장.

    알고리즘:
      1. 기존 parquet 로드 (없으면 빈 DataFrame)
      2. 이미 처리된 날짜 집합 구성
      3. scan_root/manifest.json 읽기 → scan date별 처리
      4. Recency cutoff: 수익률 미확정 날짜는 skip (today - hold_days - 2)
      5. 처리된 날짜는 skip (중복 방지)
      6. 각 scan JSON에서 candidates 팩터값 추출
      7. OhlcvDiskCache로 n일후 수익률 계산
      8. 새 rows concat + parquet 저장 + 반환

    Args:
        scan_root: scan_results 디렉토리 경로
        cache_root: .cache 디렉토리 경로
        hold_days: 보유 기간 (기본값 3)

    Returns:
        전체 factor_records DataFrame (date, ticker, per, roe, momentum_pct,
        rr_ratio, score, return_3d 컬럼)
    """
    scan_root = Path(scan_root)
    cache_root = Path(cache_root)
    factor_records_path = cache_root / "factor_records.parquet"

    # 1. 기존 parquet 로드
    try:
        existing = pd.read_parquet(factor_records_path)
    except (FileNotFoundError, Exception):
        existing = pd.DataFrame(
            {
                "date": pd.Series(dtype="object"),
                "ticker": pd.Series(dtype="object"),
                "per": pd.Series(dtype="float64"),
                "roe": pd.Series(dtype="float64"),
                "momentum_pct": pd.Series(dtype="float64"),
                "rr_ratio": pd.Series(dtype="float64"),
                "score": pd.Series(dtype="float64"),
                "return_3d": pd.Series(dtype="float64"),
            }
        )

    # 2. 이미 처리된 날짜 집합
    processed_dates = (
        set(existing["date"].unique()) if not existing.empty else set()
    )

    # 3. Recency cutoff
    today = date.today()
    cutoff = today - timedelta(days=hold_days + 2)

    # 4. manifest.json 읽기
    manifest_path = scan_root / "manifest.json"
    if not manifest_path.exists():
        logger.warning(f"manifest.json 없음: {manifest_path}")
        return existing

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # 5. OhlcvDiskCache 초기화
    disk_cache = OhlcvDiskCache(cache_root)

    # 6. 새 rows 수집
    new_rows = []

    for manifest_key, manifest_value in manifest.items():
        latest_file = manifest_value.get("latest_file")
        if not latest_file:
            continue

        # latest_file에서 scan date 추출: "20260502/1D/..." → date(2026,5,2)
        parts = latest_file.split("/")
        if len(parts) < 1:
            continue
        try:
            scan_date_str = parts[0]  # e.g., "20260502"
            scan_date = date(
                int(scan_date_str[0:4]),
                int(scan_date_str[4:6]),
                int(scan_date_str[6:8]),
            )
        except (ValueError, IndexError):
            logger.warning(f"scan date 추출 실패: {latest_file}")
            continue

        # Recency cutoff 체크
        if scan_date > cutoff:
            logger.debug(
                f"스킵 (최근): {scan_date} > {cutoff} ({manifest_key})"
            )
            continue

        # 이미 처리된 날짜 체크 (processed_dates는 date 객체 집합)
        if scan_date in processed_dates:
            logger.debug(f"스킵 (기처리): {scan_date} ({manifest_key})")
            continue

        # 7. scan JSON 파일 읽기
        json_file = scan_root / latest_file
        if not json_file.exists():
            logger.warning(f"scan 파일 없음: {json_file}")
            continue

        try:
            scan_data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"scan JSON 파싱 실패 ({json_file}): {e}")
            continue

        candidates = scan_data.get("candidates", [])

        # 8. 각 candidate에서 팩터값 + 수익률 추출
        for cand in candidates:
            ticker = cand.get("ticker")
            if not ticker:
                continue

            metrics = cand.get("metrics", {})
            score = cand.get("score")

            # 팩터값 추출 (없으면 None)
            per = metrics.get("per")
            roe = metrics.get("roe")
            momentum_pct = metrics.get("momentum_pct")
            rr_ratio = metrics.get("rr_ratio")

            # 9. n일후 수익률 계산
            try:
                ohlcv = disk_cache.read(ticker, "1D")
                if ohlcv.empty:
                    logger.debug(
                        f"OHLCV 없음, 스킵: {ticker}/1D"
                    )
                    continue

                # scan_date를 Timestamp로 정규화.
                # 비거래일 scan 결과는 scan_date 이하의 마지막 거래일 종가를 진입가로 사용.
                scan_ts = pd.Timestamp(scan_date).normalize()
                ohlcv_normalized_idx = ohlcv.index.normalize()

                eligible_idxs = (ohlcv_normalized_idx <= scan_ts).nonzero()[0]
                if len(eligible_idxs) == 0:
                    logger.debug(
                        f"scan date 이전 거래일 없음: {ticker} {scan_date}"
                    )
                    continue

                entry_idx = int(eligible_idxs[-1])
                entry_ts = ohlcv_normalized_idx[entry_idx]
                if entry_ts != scan_ts:
                    logger.debug(
                        f"scan date fallback 사용: {ticker} {scan_date} -> "
                        f"{entry_ts.date()}"
                    )

                entry_close = ohlcv.iloc[entry_idx]["close"]

                # hold_days번째 거래일 종가 찾기
                # entry_idx 이후의 데이터 중 hold_days번째 거래일
                future_idx = entry_idx + hold_days
                if future_idx >= len(ohlcv):
                    logger.debug(
                        f"충분한 거래일 없음: {ticker} "
                        f"({len(ohlcv) - entry_idx - 1} < {hold_days})"
                    )
                    continue

                future_close = ohlcv.iloc[future_idx]["close"]

                # 수익률 계산
                return_pct = (future_close - entry_close) / entry_close

                new_rows.append(
                    {
                        "date": scan_date,
                        "ticker": ticker,
                        "per": per,
                        "roe": roe,
                        "momentum_pct": momentum_pct,
                        "rr_ratio": rr_ratio,
                        "score": score,
                        "return_3d": return_pct,
                    }
                )
            except Exception as e:
                logger.debug(
                    f"수익률 계산 실패 ({ticker}/{scan_date}): {e}"
                )
                continue

    # 10. 새 rows concat + 저장
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        # reorder columns to match existing
        new_df = new_df[existing.columns]
        result = pd.concat(
            [existing, new_df],
            ignore_index=True,
        )
        result = result.drop_duplicates(
            subset=["date", "ticker"], keep="last"
        ).reset_index(drop=True)
    else:
        result = existing

    cache_root.mkdir(parents=True, exist_ok=True)
    result.to_parquet(factor_records_path)

    return result


def measure_factor_correlations(
    records: pd.DataFrame, min_samples: int = 15
) -> dict[str, float]:
    """팩터별 수익률 Spearman 상관계수 계산.

    Args:
        records: (date, ticker, per, roe, momentum_pct, rr_ratio, score,
                 return_3d) DataFrame
        min_samples: 최소 샘플 개수

    Returns:
        팩터 key → Spearman 상관계수 dict
        (샘플 부족 시 빈 dict)
    """
    factor_keys = ["per", "roe", "momentum_pct", "rr_ratio", "score"]

    if records.empty or len(records) < min_samples:
        return {}

    correlations = {}
    for key in factor_keys:
        if key not in records.columns:
            continue

        sub = records[["return_3d", key]].dropna()
        if len(sub) < min_samples:
            continue

        corr, _ = stats.spearmanr(sub[key], sub["return_3d"])
        if not np.isnan(corr):
            correlations[key] = round(float(corr), 4)

    return correlations


def correlations_to_weights(
    correlations: dict[str, float],
    base_config: WeightConfig,
    floor_pct: float = 5.0,
) -> WeightConfig:
    """상관계수 → 조정된 WeightConfig 반환 (softmax + floor 적용).

    알고리즘:
      1. correlations 비어있으면 base_config 그대로 반환
      2. 각 priority key에 대해:
         - direction == "lower_better" → 상관계수 부호 반전
         - direction == "higher_better" → 그대로 사용
      3. priority key가 correlations에 없으면 0으로 처리
      4. 음수 clip: max(0, corr)
      5. softmax 변환: exp(clipped) / sum(exp(clipped))
      6. floor 적용: weight < floor_pct → floor_pct로 올림
      7. floor 적용 후 재정규화 (합 = 100)
      8. 새 WeightConfig 반환

    Args:
        correlations: 팩터 key → Spearman 상관계수 dict
        base_config: 기본 WeightConfig
        floor_pct: floor 백분율

    Returns:
        조정된 WeightConfig
    """
    if not correlations:
        return base_config

    # 1. 방향성 조정 + clip
    adjusted_corrs = []
    for priority in base_config.priorities:
        key = priority.key
        corr = correlations.get(key, 0.0)

        if priority.direction == "lower_better":
            corr = -corr

        # Clip to [0, inf]
        corr = max(0.0, corr)
        adjusted_corrs.append(corr)

    # 2. Softmax 변환
    adjusted_corrs_arr = np.array(adjusted_corrs, dtype=float)
    # 모든 값이 0인 경우 균등 가중치
    if np.sum(adjusted_corrs_arr) == 0:
        softmax_weights = np.ones(len(adjusted_corrs_arr)) / len(
            adjusted_corrs_arr
        )
    else:
        exp_vals = np.exp(adjusted_corrs_arr)
        softmax_weights = exp_vals / np.sum(exp_vals)

    # 3. 백분율로 변환
    weights_pct = softmax_weights * 100.0

    # 4. Floor 적용
    floored_weights = np.maximum(weights_pct, floor_pct)

    # 5. 재정규화
    total = np.sum(floored_weights)
    if total > 0:
        final_weights = floored_weights / total * 100.0
    else:
        final_weights = weights_pct

    # 6. 새 WeightConfig 구성 (정규화를 위해 마지막 항목 조정)
    new_priorities = [
        Priority(
            key=priority.key,
            weight=round(float(final_weights[i]), 2),
            direction=priority.direction,
            label=priority.label,
        )
        for i, priority in enumerate(base_config.priorities)
    ]

    # 7. 부동소수점 오차로 합이 정확히 100이 아닐 수 있으므로 마지막 항목 조정
    total_weight = sum(p.weight for p in new_priorities)
    if abs(total_weight - 100.0) > 0.01:
        diff = 100.0 - total_weight
        # 마지막 priority의 weight 조정
        last_idx = len(new_priorities) - 1
        new_priorities[last_idx] = Priority(
            key=new_priorities[last_idx].key,
            weight=round(new_priorities[last_idx].weight + diff, 2),
            direction=new_priorities[last_idx].direction,
            label=new_priorities[last_idx].label,
        )

    return WeightConfig(
        priorities=new_priorities,
        must_have=base_config.must_have,
        strategy_weights=base_config.strategy_weights,
    )
