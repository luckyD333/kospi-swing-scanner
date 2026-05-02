"""
tests/test_output_formatters.py — Output formatter 테스트.
"""
import csv
import io
import json
from datetime import datetime

import pandas as pd

from core.strategy_base import Candidate
from output.formatters import format_csv, format_json, format_table


def make_candidate(
    rank: int,
    ticker: str = "000660",
    name: str = "SK하이닉스",
    strategy: str = "strategy_one_d_v2",
    score: float = 820.0,
    entry_price: float = 140500.0,
    stop_loss: float = 130000.0,
    target_1: float = 155000.0,
    target_2: float = 170000.0,
) -> Candidate:
    """테스트용 Candidate 팩토리."""
    return Candidate(
        ticker=ticker,
        name=name,
        strategy=strategy,
        signal_date=pd.Timestamp("2026-05-01"),
        score=score,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        market_cap_bil=5000.0,
        volume_20d_avg=500000.0,
        conditions_met={"rsi_oversold": True, "bb_lower": True},
        metadata={"source": "naver"},
    )


def test_format_json_schema_compliance():
    """JSON 결과가 표준 schema를 준수하는지 확인."""
    candidates = [
        make_candidate(1, ticker="000660", name="SK하이닉스", score=820.0),
        make_candidate(2, ticker="005930", name="삼성전자", score=750.0),
    ]

    result_json = format_json(
        candidates,
        target_date="2026-05-01",
        strategy_name="strategy_one_d_v2",
        timeframe="1D",
        filters={"min_cap_bil": 2000, "market": "KOSPI"},
    )

    # JSON parse 검증
    payload = json.loads(result_json)

    # 필수 최상위 키 확인
    assert "strategy" in payload
    assert payload["strategy"] == "strategy_one_d_v2"
    assert "date" in payload
    assert payload["date"] == "2026-05-01"
    assert "timeframe" in payload
    assert payload["timeframe"] == "1D"
    assert "generated_at" in payload
    assert "candidates" in payload
    assert "summary" in payload

    # generated_at 형식 검증 (ISO8601)
    try:
        dt = datetime.fromisoformat(payload["generated_at"])
        assert dt.tzinfo is not None  # timezone-aware
    except ValueError:
        raise AssertionError(f"generated_at 형식 오류: {payload['generated_at']}")

    # candidates 구조 검증
    assert len(payload["candidates"]) == 2
    for i, cand_obj in enumerate(payload["candidates"], 1):
        assert cand_obj["rank"] == i
        assert "ticker" in cand_obj
        assert "name" in cand_obj
        assert "score" in cand_obj
        assert "metrics" in cand_obj

        # metrics 내용 확인
        metrics = cand_obj["metrics"]
        assert "entry_price" in metrics
        assert "stop_loss" in metrics
        assert "target_1" in metrics
        assert "target_2" in metrics
        assert "market_cap_bil" in metrics
        assert "volume_20d_avg" in metrics
        assert "risk_pct" in metrics
        assert "reward_pct_t1" in metrics
        assert "reward_pct_t2" in metrics

    # summary 구조 검증
    assert payload["summary"]["count"] == 2
    assert "filters" in payload["summary"]
    assert payload["summary"]["filters"]["min_cap_bil"] == 2000
    assert payload["summary"]["filters"]["market"] == "KOSPI"


def test_format_json_with_default_strategy_name():
    """strategy_name=None 일 때 strategy 키가 생략되는지 확인."""
    candidates = [make_candidate(1)]

    result_json = format_json(
        candidates,
        target_date="2026-05-01",
        strategy_name=None,  # None 이면 키 생략
        timeframe="1D",
    )

    payload = json.loads(result_json)

    # strategy 키가 없거나 None이 아닌지 확인 (생략됨)
    assert "strategy" not in payload or payload.get("strategy") is None
    assert "date" in payload
    assert "candidates" in payload


def test_format_json_candidate_metrics_wrapping():
    """_candidate_to_row() 의 필드들이 metrics 로 올바르게 래핑되는지."""
    candidate = Candidate(
        ticker="000660",
        name="SK하이닉스",
        strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-01"),
        score=820.0,
        entry_price=140500.0,
        stop_loss=130000.0,
        target_1=155000.0,
        target_2=170000.0,
        market_cap_bil=5000.0,
        volume_20d_avg=500000.0,
        conditions_met={"rsi_oversold": True},
        metadata={"source": "naver"},
    )

    result_json = format_json(
        [candidate],
        target_date="2026-05-01",
        strategy_name="strategy_one_d_v2",
        timeframe="1D",
    )

    payload = json.loads(result_json)
    cand = payload["candidates"][0]

    # 최상위에만 있어야 할 필드
    assert cand["rank"] == 1
    assert cand["ticker"] == "000660"
    assert cand["name"] == "SK하이닉스"
    assert cand["score"] == 820.0

    # metrics 안에 있어야 할 필드
    metrics = cand["metrics"]
    assert metrics["entry_price"] == 140500.0
    assert metrics["stop_loss"] == 130000.0
    assert metrics["target_1"] == 155000.0
    assert metrics["target_2"] == 170000.0
    assert metrics["market_cap_bil"] == 5000.0
    assert metrics["volume_20d_avg"] == 500000.0

    # rank/ticker/name/score 가 metrics 안에 없는지 확인 (최상위로 옮겨짐)
    assert "rank" not in metrics
    assert "ticker" not in metrics
    assert "name" not in metrics
    assert "score" not in metrics


def test_format_json_empty_filters():
    """filters=None 일 때 빈 dict 로 처리되는지."""
    candidates = [make_candidate(1)]

    result_json = format_json(
        candidates,
        target_date="2026-05-01",
        strategy_name="strategy_one_d_v2",
        timeframe="1D",
        filters=None,  # None 이면 {} 로 처리
    )

    payload = json.loads(result_json)
    assert payload["summary"]["filters"] == {}


def test_format_json_default_timeframe():
    """timeframe 기본값이 "1D" 인지 확인."""
    candidates = [make_candidate(1)]

    result_json = format_json(
        candidates,
        target_date="2026-05-01",
        strategy_name="strategy_one_d_v2",
        # timeframe 지정 안 함 (기본값 "1D" 사용)
    )

    payload = json.loads(result_json)
    assert payload["timeframe"] == "1D"


def test_format_json_candidate_ranking():
    """여러 candidate 의 rank 가 1부터 순차적으로 매겨지는지."""
    candidates = [
        make_candidate(1, ticker="000660"),
        make_candidate(2, ticker="005930"),
        make_candidate(3, ticker="000720"),
    ]

    result_json = format_json(
        candidates,
        target_date="2026-05-01",
        strategy_name="strategy_one_d_v2",
    )

    payload = json.loads(result_json)
    for i, cand in enumerate(payload["candidates"], 1):
        assert cand["rank"] == i


def test_format_json_generated_at_is_kst():
    """generated_at 이 KST timezone 을 포함하는지 (Asia/Seoul)."""
    candidates = [make_candidate(1)]

    result_json = format_json(
        candidates,
        target_date="2026-05-01",
        strategy_name="strategy_one_d_v2",
    )

    payload = json.loads(result_json)
    generated_at_str = payload["generated_at"]

    # ISO8601 형식이고 +09:00 또는 +08:00 (대선 시간) 를 포함해야 함
    assert "T" in generated_at_str  # ISO 기본 형식
    dt = datetime.fromisoformat(generated_at_str)
    assert dt.tzinfo is not None


# ============================================================================
# Phase 1: 펀더멘털 컬럼 (per/roe/foreign_pct/naver_url) 출력
# ============================================================================

def _make_candidate_with_fundamentals(**meta_overrides):
    """metadata에 펀더멘털 키가 채워진 Candidate (runner 사후 주입 시뮬레이션)."""
    metadata = {
        "per": 33.59,
        "roe": 10.85,
        "foreign_pct": 49.27,
        "naver_url": "https://finance.naver.com/item/main.naver?code=005930",
    }
    metadata.update(meta_overrides)
    return Candidate(
        ticker="005930",
        name="삼성전자",
        strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-01"),
        score=820.0,
        entry_price=140500.0,
        stop_loss=130000.0,
        target_1=155000.0,
        target_2=170000.0,
        market_cap_bil=5000.0,
        volume_20d_avg=500000.0,
        metadata=metadata,
    )


def test_format_json_includes_fundamentals_in_metrics():
    """JSON metrics에 per/roe/foreign_pct/naver_url 포함."""
    cand = _make_candidate_with_fundamentals()
    payload = json.loads(format_json([cand], target_date="2026-05-01"))
    metrics = payload["candidates"][0]["metrics"]
    assert metrics["per"] == 33.59
    assert metrics["roe"] == 10.85
    assert metrics["foreign_pct"] == 49.27
    assert metrics["naver_url"] == "https://finance.naver.com/item/main.naver?code=005930"


def test_format_json_handles_none_fundamentals():
    """결측치(None) 펀더멘털도 JSON null 로 직렬화."""
    cand = _make_candidate_with_fundamentals(per=None, roe=None, foreign_pct=None)
    payload = json.loads(format_json([cand], target_date="2026-05-01"))
    metrics = payload["candidates"][0]["metrics"]
    assert metrics["per"] is None
    assert metrics["roe"] is None
    assert metrics["foreign_pct"] is None
    # naver_url은 항상 채워짐
    assert metrics["naver_url"].startswith("https://finance.naver.com/item/main.naver?code=")


def test_format_csv_includes_fundamentals_columns():
    """CSV에 per/roe/foreign_pct/naver_url 컬럼 포함."""
    cand = _make_candidate_with_fundamentals()
    csv_text = format_csv([cand], target_date="2026-05-01")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert "per" in reader.fieldnames
    assert "roe" in reader.fieldnames
    assert "foreign_pct" in reader.fieldnames
    assert "naver_url" in reader.fieldnames
    assert rows[0]["per"] == "33.59"
    assert rows[0]["roe"] == "10.85"
    assert rows[0]["naver_url"] == "https://finance.naver.com/item/main.naver?code=005930"


def test_format_csv_empty_fundamentals_renders_blank():
    """결측 펀더멘털은 CSV에서 빈 문자열로 렌더 (None은 csv writer가 빈 칸으로)."""
    cand = _make_candidate_with_fundamentals(per=None, roe=None, foreign_pct=None)
    csv_text = format_csv([cand], target_date="2026-05-01")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert rows[0]["per"] == ""
    assert rows[0]["roe"] == ""


def test_format_table_shows_fundamentals_in_top5_detail():
    """table 출력 상위 5 상세 블록에 PER/ROE/외인비율 표시."""
    cand = _make_candidate_with_fundamentals()
    out = format_table([cand], target_date="2026-05-01")
    # 상세 블록에만 (메인 표 가독성 위해 메인 표는 변경 안 함)
    assert "PER" in out
    assert "ROE" in out
    assert "33.59" in out
    assert "10.85" in out


def test_format_json_metrics_includes_strategy_specific_metadata():
    """전략별 고유 metadata(momentum_pct, channel_high 등)가 JSON metrics에 모두 포함."""
    cand = Candidate(
        ticker="005930", name="삼성전자", strategy="strategy_two_cross_sectional_momentum",
        signal_date=pd.Timestamp("2026-05-01"),
        score=720.0, entry_price=70000.0, stop_loss=68000.0,
        target_1=72000.0, target_2=74000.0,
        metadata={
            "momentum_pct": 7.5,
            "lookback": 15,
            "rank": 0.92,
            "market": "KOSPI",
            "per": 33.59, "roe": 10.85, "foreign_pct": 49.27,
            "naver_url": "https://finance.naver.com/item/main.naver?code=005930",
        },
    )
    payload = json.loads(format_json([cand], target_date="2026-05-01"))
    metrics = payload["candidates"][0]["metrics"]
    # 전략별 고유 키
    assert metrics["momentum_pct"] == 7.5
    assert metrics["lookback"] == 15
    # Phase 1 펀더멘털 키도 그대로
    assert metrics["per"] == 33.59
    assert metrics["naver_url"].startswith("https://")


def test_format_json_metrics_includes_conditions_met():
    """conditions_met dict(전략 진입 근거)가 JSON metrics 안에 포함."""
    cand = Candidate(
        ticker="005930", name="삼성전자", strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-01"),
        score=820.0, entry_price=140500.0, stop_loss=130000.0,
        target_1=155000.0, target_2=170000.0,
        conditions_met={"rsi_oversold": True, "bb_lower": True, "double_bottom": False},
    )
    payload = json.loads(format_json([cand], target_date="2026-05-01"))
    metrics = payload["candidates"][0]["metrics"]
    assert metrics["conditions_met"] == {
        "rsi_oversold": True, "bb_lower": True, "double_bottom": False,
    }


def test_format_csv_does_not_break_on_dynamic_metadata():
    """전략별 metadata가 있어도 CSV는 고정 컬럼만 유지 (extrasaction='ignore')."""
    cand = Candidate(
        ticker="005930", name="삼성전자", strategy="strategy_three",
        signal_date=pd.Timestamp("2026-05-01"),
        score=720.0, entry_price=70000.0, stop_loss=68000.0,
        target_1=72000.0, target_2=74000.0,
        metadata={
            "channel_high": 71000.0, "channel_low": 65000.0, "breakout_pct": 0.05,
            "atr": 1500.0,  # CSV에는 없는 키
        },
    )
    csv_text = format_csv([cand], target_date="2026-05-01")
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    # 동적 키들은 CSV 컬럼에 없어야 함
    assert "channel_high" not in reader.fieldnames
    assert "atr" not in reader.fieldnames
    # 기존 고정 컬럼은 정상
    assert rows[0]["ticker"] == "005930"


def test_format_markdown_includes_fundamentals_columns():
    """Markdown 출력에 PER/ROE/외인% 컬럼 표시."""
    from output.formatters import format_markdown

    cand = _make_candidate_with_fundamentals()
    md = format_markdown([cand], target_date="2026-05-01")
    assert "PER" in md
    assert "ROE" in md
    assert "외인" in md
    assert "33.59" in md
    assert "10.85" in md
    assert "49.27" in md


def test_format_markdown_renders_na_for_missing_fundamentals():
    """metadata에 펀더멘털 키 없는 Candidate는 N/A 표기."""
    from output.formatters import format_markdown

    cand = Candidate(
        ticker="000020", name="동화약품", strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-01"),
        score=600.0,
        entry_price=10000.0, stop_loss=9700.0,
        target_1=10300.0, target_2=10500.0,
    )
    md = format_markdown([cand], target_date="2026-05-01")
    # 동화약품 행에 N/A 노출
    line = next(line for line in md.splitlines() if "동화약품" in line)
    assert "N/A" in line


def test_format_table_handles_missing_fundamentals_metadata():
    """metadata에 펀더멘털 키 없는 Candidate (legacy) 도 KeyError 없이 출력."""
    cand = Candidate(
        ticker="005930", name="삼성전자", strategy="strategy_one_d_v2",
        signal_date=pd.Timestamp("2026-05-01"),
        score=820.0, entry_price=140500.0, stop_loss=130000.0,
        target_1=155000.0, target_2=170000.0,
    )
    # 예외 없이 정상 작동해야 함
    out = format_table([cand], target_date="2026-05-01")
    assert "삼성전자" in out
