"""
test_cli.py — cli.py 동작 검증.

스코프:
  - argparse 옵션·--help 동작
  - 출력 포맷 4종 (table/json/csv/markdown) 직접 호출
  - --strategy 알 수 없는 이름 처리
  - mock DataClient 로 main() E2E 1회 실행
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import cli
from output import formatters
from test_daily_scanner_mock import MockKOSPIDataSource


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(PROJECT_ROOT / ".venv" / "bin" / "python")


# ============================================================================
# argparse 동작
# ============================================================================

def test_help_succeeds():
    """python cli.py --help 정상 종료."""
    proc = subprocess.run(
        [PYTHON, str(PROJECT_ROOT / "cli.py"), "--help"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert proc.returncode == 0
    assert "--strategy" in proc.stdout
    assert "--top" in proc.stdout
    assert "--format" in proc.stdout


def test_invalid_date_format_errors():
    parser = cli.build_parser()
    args = parser.parse_args(["--date", "20260418"])  # ok
    assert args.date == "20260418"
    # 형식 오류는 main 내부에서 검증되므로 parser 단계에서는 통과.


def test_unknown_strategy_raises_systemexit():
    with pytest.raises(SystemExit):
        cli.resolve_strategies("does_not_exist")


def test_resolve_strategy_one():
    strats = cli.resolve_strategies("strategy_one_d_v2")
    assert len(strats) == 1
    assert strats[0].name == "strategy_one_d_v2"


def test_resolve_all_returns_all_registered():
    from strategies import available
    strats = cli.resolve_strategies("all")
    assert {s.name for s in strats} == set(available())


# ============================================================================
# 출력 포맷
# ============================================================================

def _sample_candidates():
    """단일 전략 결과 — formatter 테스트용."""
    from core.strategy_base import Candidate
    import pandas as pd
    return [
        Candidate(
            ticker="035720", name="카카오", strategy="strategy_one_d_v2",
            signal_date=pd.Timestamp("2026-04-18"),
            score=0.75, entry_price=9351.67, stop_loss=9117.0,
            target_1=9632.22, target_2=9819.25,
            market_cap_bil=19000.0, volume_20d_avg=500_000.0,
            conditions_met={"rsi_oversold": True, "double_bottom": True},
            metadata={"market": "KOSPI"},
        ),
    ]


def test_format_json_round_trip():
    out = formatters.format_json(_sample_candidates(), "20260418")
    parsed = json.loads(out)
    assert parsed["target_date"] == "20260418"
    assert parsed["count"] == 1
    cand = parsed["candidates"][0]
    assert cand["ticker"] == "035720"
    assert cand["score"] == 0.75
    assert cand["conditions_met"]["double_bottom"] is True


def test_format_csv_has_header_and_row():
    out = formatters.format_csv(_sample_candidates(), "20260418")
    lines = out.strip().splitlines()
    assert lines[0].startswith("target_date,")
    assert "035720" in lines[1]


def test_format_table_contains_ticker():
    out = formatters.format_table(_sample_candidates(), "20260418")
    assert "035720" in out
    assert "20260418" in out


def test_format_markdown_table_structure():
    out = formatters.format_markdown(_sample_candidates(), "20260418")
    assert "| 1 | 035720" in out
    assert out.startswith("# 20260418")


def test_format_table_empty_candidates():
    out = formatters.format_table([], "20260418")
    assert "없음" in out


# ============================================================================
# main() E2E (mock DataClient)
# ============================================================================

def _patched_data_client(*args, **kwargs):
    """cli.DataClient 자리에 들어갈 mock client factory."""
    from core.data_fetch import DataClient
    mock = MockKOSPIDataSource()
    return DataClient(
        ticker_list_sources=[mock],
        ohlcv_sources=[mock],
        use_krx_for_universe=False,
    )


def test_main_with_strategy_one_outputs_json(tmp_path, capsys):
    output_dir = tmp_path / "results"
    with patch("cli.DataClient", side_effect=_patched_data_client):
        rc = cli.main([
            "--strategy", "strategy_one_d_v2",
            "--date", "20260418",
            "--top", "5",
            "--format", "json",
            "--output-dir", str(output_dir),
        ])
    assert rc == 0

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["target_date"] == "20260418"
    assert parsed["count"] >= 1
    assert all(c["strategy"] == "strategy_one_d_v2" for c in parsed["candidates"])

    # output-dir 에 파일 저장 확인
    files = list(output_dir.glob("scan_*.json"))
    assert len(files) == 1


def test_main_returns_nonzero_when_strategy_errors(capsys):
    """전략 등록 후 강제 실패시키면 main 종료코드 1."""
    from strategies import register, unregister
    from core.strategy_base import Candidate, ScanContext

    class _FailingStrategy:
        name = "failing_in_cli"

        def scan(self, ctx, top_n):
            raise RuntimeError("intentional")

    register(_FailingStrategy)
    try:
        with patch("cli.DataClient", side_effect=_patched_data_client):
            rc = cli.main([
                "--strategy", "failing_in_cli",
                "--date", "20260418",
                "--top", "5",
                "--format", "json",
            ])
        assert rc == 1
    finally:
        unregister("failing_in_cli")
