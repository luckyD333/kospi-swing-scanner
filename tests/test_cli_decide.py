"""
test_cli_decide.py — Phase 2 의사결정 CLI 통합 검증.

검증:
  - scan_results manifest + latest JSON 파일들 로드 → Candidate 복원
  - aggregator + ensemble → ranking markdown
  - 사용자 선택 ticker → Decision Journal 파일 생성
  - cli.py의 --interview / --decide 분기 진입
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


from core.decision.config import Priority, WeightConfig
from core.decision.runner import (
    load_candidates_from_manifest,
    run_decide_journal,
    run_decide_ranking,
)


def _make_scan_results(scan_root: Path, target_date: str = "20260502") -> None:
    """fake scan_results 디렉토리 + 2전략 결과 + manifest."""
    s1_dir = scan_root / target_date / "1D"
    s1_dir.mkdir(parents=True, exist_ok=True)

    def make_payload(strategy: str, candidates: list[dict]) -> dict:
        return {
            "strategy": strategy,
            "date": target_date,
            "timeframe": "1D",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "candidates": candidates,
            "summary": {"count": len(candidates), "filters": {}},
        }

    def cand(rank, ticker, name, score, **metrics):
        base_metrics = {
            "strategy": metrics.pop("strategy", "strat"),
            "signal_date": target_date[:4] + "-" + target_date[4:6] + "-" + target_date[6:],
            "current_price": None,
            "entry_price": 100, "stop_loss": 98,
            "target_1": 102, "target_2": 104,
            "market_cap_bil": 5000, "volume_20d_avg": 1_000_000,
            "risk_pct": 2.0, "reward_pct_t1": 2.0, "reward_pct_t2": 4.0,
            "per": metrics.get("per", 20.0),
            "roe": metrics.get("roe", 10.0),
            "foreign_pct": metrics.get("foreign_pct", 30.0),
            "naver_url": f"https://finance.naver.com/item/main.naver?code={ticker}",
            "conditions_met": metrics.get("conditions_met", {}),
        }
        base_metrics.update({k: v for k, v in metrics.items()
                             if k not in base_metrics})
        return {"rank": rank, "ticker": ticker, "name": name,
                "score": score, "metrics": base_metrics}

    # 전략 1: 005930, 000660
    s1_path = s1_dir / "scan_strategy_one.json"
    s1_path.write_text(json.dumps(make_payload("strategy_one_d_v2", [
        cand(1, "005930", "삼성전자", 800.0, strategy="strategy_one_d_v2",
             per=15.0, roe=15.0),
        cand(2, "000660", "SK하이닉스", 700.0, strategy="strategy_one_d_v2",
             per=20.0, roe=20.0),
    ])))

    # 전략 2: 005930 (교집합), 035720
    s2_path = s1_dir / "scan_strategy_two.json"
    s2_path.write_text(json.dumps(make_payload(
        "strategy_two_cross_sectional_momentum",
        [
            cand(1, "005930", "삼성전자", 900.0,
                 strategy="strategy_two_cross_sectional_momentum",
                 per=15.0, roe=15.0),
            cand(2, "035720", "카카오", 650.0,
                 strategy="strategy_two_cross_sectional_momentum",
                 per=30.0, roe=5.0),
        ],
    )))

    manifest = {
        "strategy_one_d_v2__1D": {
            "date": target_date,
            "latest_file": f"{target_date}/1D/scan_strategy_one.json",
            "formats": ["json"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "strategy_two_cross_sectional_momentum__1D": {
            "date": target_date,
            "latest_file": f"{target_date}/1D/scan_strategy_two.json",
            "formats": ["json"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    (scan_root / "manifest.json").write_text(json.dumps(manifest))


def _weights() -> WeightConfig:
    return WeightConfig(
        priorities=[
            Priority("per", 30.0, "lower_better", "저PER"),
            Priority("roe", 30.0, "higher_better", "고ROE"),
            Priority("score", 30.0, "higher_better", "전략점수"),
            Priority("ensemble_count", 10.0, "higher_better", "다중전략"),
        ],
        must_have=[],
    )


# ---------------------------------------------------------------------------
# load_candidates_from_manifest
# ---------------------------------------------------------------------------

def test_load_candidates_from_manifest(tmp_path):
    scan_root = tmp_path / "scan_results"
    _make_scan_results(scan_root)
    by_strategy = load_candidates_from_manifest(scan_root)
    assert "strategy_one_d_v2" in by_strategy
    assert "strategy_two_cross_sectional_momentum" in by_strategy
    s1 = by_strategy["strategy_one_d_v2"]
    assert {c.ticker for c in s1} == {"005930", "000660"}
    # 펀더멘털 metadata 복원
    samsung = next(c for c in s1 if c.ticker == "005930")
    assert samsung.metadata.get("per") == 15.0
    assert samsung.metadata.get("naver_url").endswith("code=005930")


def test_load_candidates_returns_empty_when_no_manifest(tmp_path):
    by_strategy = load_candidates_from_manifest(tmp_path)
    assert by_strategy == {}


# ---------------------------------------------------------------------------
# run_decide_ranking
# ---------------------------------------------------------------------------

def test_run_decide_ranking_creates_markdown(tmp_path):
    scan_root = tmp_path / "scan_results"
    _make_scan_results(scan_root, target_date="20260502")
    out_path = run_decide_ranking(
        scan_root=scan_root,
        target_date="20260502",
        top_n=3,
        weight_config=_weights(),
    )
    assert out_path.exists()
    content = out_path.read_text()
    # ranking에 005930, 000660, 035720 모두 노출 (top 3)
    assert "005930" in content
    assert "000660" in content
    assert "Top 3" in content or "상위 3" in content
    # 가중치 표 노출
    assert "저PER" in content
    # ensemble_count 표시
    assert "다중전략" in content or "ensemble" in content.lower()


def test_run_decide_ranking_uses_ensemble_count_in_score(tmp_path):
    """교집합 boost: 005930이 다른 종목보다 final_score 우위."""
    scan_root = tmp_path / "scan_results"
    _make_scan_results(scan_root)
    out_path = run_decide_ranking(
        scan_root=scan_root,
        target_date="20260502",
        top_n=5,
        weight_config=_weights(),
    )
    content = out_path.read_text()
    # 005930 (교집합 2) 가 최상위
    lines = [line for line in content.splitlines() if "| 1 |" in line]
    assert lines, "1위 행을 찾지 못함"
    assert "005930" in lines[0]


# ---------------------------------------------------------------------------
# run_decide_journal
# ---------------------------------------------------------------------------

def test_run_decide_journal_creates_per_ticker_files(tmp_path):
    scan_root = tmp_path / "scan_results"
    _make_scan_results(scan_root)
    paths = run_decide_journal(
        scan_root=scan_root,
        target_date="20260502",
        tickers=["005930", "000660"],
        weight_config=_weights(),
        notes="확신 70%",
    )
    assert len(paths) == 2
    for p in paths:
        assert p.exists()
        content = p.read_text()
        assert "Decision Journal" in content
        assert "확신 70%" in content


def test_run_decide_journal_skips_unknown_ticker(tmp_path):
    """후보 풀에 없는 ticker는 skip."""
    scan_root = tmp_path / "scan_results"
    _make_scan_results(scan_root)
    paths = run_decide_journal(
        scan_root=scan_root,
        target_date="20260502",
        tickers=["005930", "999999"],  # 999999 없음
        weight_config=_weights(),
    )
    # 1개만 생성
    assert len(paths) == 1
    assert "005930" in paths[0].name


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def test_cli_decide_flag_creates_ranking_md(tmp_path, monkeypatch):
    """python cli.py --decide --top-n 3 → decision_top3.md."""
    scan_root = tmp_path / "scan_results"
    _make_scan_results(scan_root)
    weights_path = tmp_path / "weights.yml"
    _weights().save(weights_path)

    from cli import main
    rc = main([
        "--decide",
        "--top-n", "3",
        "--weights", str(weights_path),
        "--scan-results-dir", str(scan_root),
        "--date", "20260502",
    ])
    assert rc == 0
    out_md = scan_root / "20260502" / "decision_top3.md"
    assert out_md.exists()


def test_cli_interview_flag_invokes_interview(tmp_path):
    """python cli.py --interview → 인터뷰 호출."""
    weights_path = tmp_path / "weights.yml"
    answers = iter([
        "per", "100", "lower", "저PER",
        "done",
        "done",
    ])
    from cli import main
    with patch("builtins.input", side_effect=lambda *_a, **_kw: next(answers)):
        rc = main(["--interview", "--weights", str(weights_path)])
    assert rc == 0
    assert weights_path.exists()


def test_cli_decide_select_creates_journal(tmp_path):
    """python cli.py --decide --select 005930 --notes '...' → journal 파일."""
    scan_root = tmp_path / "scan_results"
    _make_scan_results(scan_root)
    weights_path = tmp_path / "weights.yml"
    _weights().save(weights_path)

    from cli import main
    rc = main([
        "--decide",
        "--select", "005930",
        "--notes", "테스트 메모",
        "--weights", str(weights_path),
        "--scan-results-dir", str(scan_root),
        "--date", "20260502",
    ])
    assert rc == 0
    journal = scan_root / "20260502" / "journal_005930.md"
    assert journal.exists()
    assert "테스트 메모" in journal.read_text()
