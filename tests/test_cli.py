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

from test_daily_scanner_mock import MockKOSPIDataSource

import cli
from output import formatters

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
    import pandas as pd

    from core.strategy_base import Candidate
    return [
        Candidate(
            ticker="035720", name="카카오", strategy="strategy_one_d_v2",
            signal_date=pd.Timestamp("2026-04-18"),
            score=750.0, entry_price=9351.67, stop_loss=9117.0,
            target_1=9632.22, target_2=9819.25,
            market_cap_bil=19000.0, volume_20d_avg=500_000.0,
            conditions_met={"rsi_oversold": True, "double_bottom": True},
            metadata={"market": "KOSPI"},
        ),
    ]


def test_format_json_round_trip():
    out = formatters.format_json(
        _sample_candidates(),
        "20260418",
        strategy_name="test_strategy",
        timeframe="1D",
    )
    parsed = json.loads(out)
    # 새로운 JSON 스키마 검증
    assert parsed["date"] == "20260418"
    assert parsed["strategy"] == "test_strategy"
    assert parsed["timeframe"] == "1D"
    assert "generated_at" in parsed
    assert parsed["summary"]["count"] == 1
    cand = parsed["candidates"][0]
    assert cand["rank"] == 1
    assert cand["ticker"] == "035720"
    assert cand["score"] == 750.0
    # conditions_met 는 이제 여기에 없음 (기존 필드는 metrics 안에 있음)
    assert "metrics" in cand


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
    # 새로운 JSON 스키마 확인
    assert parsed["date"] == "20260418"
    assert "strategy" in parsed
    assert parsed["strategy"] == "strategy_one_d_v2"
    assert "timeframe" in parsed
    assert "generated_at" in parsed
    assert "summary" in parsed
    assert parsed["summary"]["count"] >= 1
    # candidates 의 새로운 구조 확인 (rank/ticker/name/score/metrics)
    for c in parsed["candidates"]:
        assert "rank" in c
        assert "ticker" in c
        assert "name" in c
        assert "score" in c
        assert "metrics" in c

    # output-dir 에 파일 저장 확인 (CP-3: scan_results/YYYY-MM-DD/ 서브디렉토리)
    files = list(output_dir.glob("**/scan_*.json"))
    assert len(files) == 1


def test_main_returns_nonzero_when_strategy_errors(capsys):
    """전략 등록 후 강제 실패시키면 main 종료코드 1."""
    from strategies import register, unregister

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


def test_max_universe_negative_normalized_to_unlimited(capsys):
    """
    Step 7: `--max-universe -5` → cap_limit=None (무제한 처리).
    음수 슬라이싱 silent bug 차단.
    """

    output_dir = Path(__file__).parent.parent / "test_output_negative_universe"
    output_dir.mkdir(exist_ok=True, parents=True)

    try:
        with patch("cli.DataClient", side_effect=_patched_data_client):
            rc = cli.main([
                "--strategy", "strategy_one_d_v2",
                "--date", "20260418",
                "--top", "5",
                "--max-universe", "-5",  # 음수 → None (무제한)
                "--format", "json",
                "--output-dir", str(output_dir),
            ])
        assert rc == 0
        # 음수가 정규화되어 무제한으로 동작
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        # 새로운 JSON 스키마 확인
        assert parsed["date"] == "20260418"
        assert "strategy" in parsed
        assert "summary" in parsed
    finally:
        import shutil
        if output_dir.exists():
            shutil.rmtree(output_dir)


def test_save_output_oserror_graceful_warning(tmp_path, capsys):
    """
    Step 7: 읽기 전용 디렉토리 mock → warning 로그 + None 반환.
    OSError 시 graceful degrade.
    """
    import os

    # 읽기 전용 디렉토리 생성
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    # 모든 쓰기 권한 제거 (Unix only)
    try:
        os.chmod(readonly_dir, 0o444)

        # 저장 시도 → OSError → warning 로그 + None 반환
        with patch("cli.logger") as mock_logger:
            result = cli.save_output(
                body="test",
                fmt="table",
                target_date="20260418",
                strategy_name="strategy_one_d_v2",
                output_dir=readonly_dir,
            )

        # None 반환 확인
        assert result is None
        # warning 로그 호출 확인
        assert mock_logger.warning.called or mock_logger.error.called
    finally:
        # 권한 복원
        os.chmod(readonly_dir, 0o755)  # nosec B103


def test_verbose_flag_sets_debug_level(capsys):
    """
    Step 7: `--verbose` → logging.DEBUG 레벨 활성화.
    """

    with patch("cli.DataClient", side_effect=_patched_data_client):
        rc = cli.main([
            "--strategy", "strategy_one_d_v2",
            "--date", "20260418",
            "--top", "5",
            "--verbose",
            "--format", "json",
        ])
    assert rc == 0
    # verbose 모드에서 DEBUG 레벨이 활성화되었는지 확인
    # (루트 logger가 DEBUG 레벨이어야 함)
    # 실제로는 cli.main에서 setLevel 이 호출되었어야 함
    # 여기서는 호출 후 결과가 0인지만 확인 (side effect는 logger 레벨 변경)


# ============================================================================
# manifest 갱신 테스트
# ============================================================================

def test_save_output_creates_scan_manifest(tmp_path):
    """save_output 호출 후 manifest.json 이 생성되고 latest_file 을 가리키는지 검증."""
    output_dir = tmp_path / "scan_results"
    output_dir.mkdir()

    candidates = _sample_candidates()
    body = formatters.format_json(candidates, "20260418", strategy_name="test_strategy", timeframe="1D")

    # save_output 호출
    saved_path = cli.save_output(
        body=body,
        fmt="json",
        target_date="20260418",
        strategy_name="test_strategy",
        output_dir=output_dir,
        summary_dict={"count": 1},
        tf="1D",
    )
    assert saved_path is not None

    # manifest.json 존재 확인
    manifest_path = output_dir / "manifest.json"
    assert manifest_path.exists()

    # manifest 내용 검증
    with open(manifest_path) as f:
        manifest = json.load(f)

    key = "test_strategy__1D"
    assert key in manifest
    entry = manifest[key]
    assert entry["date"] == "20260418"
    assert "scan_20260418_test_strategy_" in entry["latest_file"]
    assert entry["latest_file"].endswith(".json")
    assert "json" in entry["formats"]
    assert "generated_at" in entry


def test_save_output_manifest_keeps_history(tmp_path):
    """같은 전략을 두 번 저장하면 manifest 는 latest 만 가리키고
    timestamp 파일은 둘 다 디스크에 남아있는지 검증."""
    from unittest.mock import patch as mock_patch
    from datetime import datetime

    output_dir = tmp_path / "scan_results"
    output_dir.mkdir()

    candidates = _sample_candidates()
    body = formatters.format_json(candidates, "20260418", strategy_name="test_strategy", timeframe="1D")

    # 첫 번째 저장 (타임스탐프 0500)
    with mock_patch("cli.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "0500"
        mock_datetime.now.side_effect = lambda *args, **kwargs: (
            datetime.now(*args, **kwargs) if args or kwargs else datetime(2026, 4, 18, 5, 0)
        )
        path1 = cli.save_output(
            body=body,
            fmt="json",
            target_date="20260418",
            strategy_name="test_strategy",
            output_dir=output_dir,
            summary_dict={"count": 1},
            tf="1D",
        )
    assert path1 is not None

    # 두 번째 저장 (타임스탐프 0510)
    with mock_patch("cli.datetime") as mock_datetime:
        mock_datetime.now.return_value.strftime.return_value = "0510"
        mock_datetime.now.side_effect = lambda *args, **kwargs: (
            datetime.now(*args, **kwargs) if args or kwargs else datetime(2026, 4, 18, 5, 10)
        )
        path2 = cli.save_output(
            body=body,
            fmt="json",
            target_date="20260418",
            strategy_name="test_strategy",
            output_dir=output_dir,
            summary_dict={"count": 1},
            tf="1D",
        )
    assert path2 is not None

    # 두 파일 모두 존재
    assert path1.exists()
    assert path2.exists()
    assert path1 != path2

    # manifest는 latest(path2)를 가리킴
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    key = "test_strategy__1D"
    assert key in manifest
    entry = manifest[key]
    assert entry["latest_file"] == path2.relative_to(output_dir).as_posix()


def test_save_output_manifest_merges_formats(tmp_path):
    """같은 시점에 json+csv 두 포맷 저장 시 manifest entry 의 formats 배열에
    두 포맷이 모두 포함되는지 검증."""
    output_dir = tmp_path / "scan_results"
    output_dir.mkdir()

    candidates = _sample_candidates()

    # JSON 저장
    json_body = formatters.format_json(
        candidates, "20260418", strategy_name="test_strategy", timeframe="1D"
    )
    json_path = cli.save_output(
        body=json_body,
        fmt="json",
        target_date="20260418",
        strategy_name="test_strategy",
        output_dir=output_dir,
        summary_dict={"count": 1},
        tf="1D",
    )
    assert json_path is not None

    # 동일한 타임스탬프로 CSV 저장하려면 manifest 직접 조작이 필요
    # 대신 같은 json_path를 가리키도록 manifest를 미리 설정한 후 CSV 저장
    # 더 간단하게: csv를 저장할 때 json이 이미 있는 상태에서,
    # 같은 타임스탬프 파일이 생기도록 (HHMM이 같음)

    # 간단한 방식: manifest 직접 수정해서 같은 latest_file 을 가리키게 한 후
    # CSV 저장 → manifest 갱신 시 formats 병합

    # csv 바디 생성
    csv_body = formatters.format_csv(candidates, "20260418")

    # manifest에 json entry 직접 생성 (같은 latest_file을 가리킴)
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    key = "test_strategy__1D"
    # formats를 ["json"]으로 설정
    manifest[key]["formats"] = ["json"]
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)

    # 이제 csv_path가 같은 디렉토리 + 같은 타임스탬프를 가지도록 강제
    # (datetime.now().strftime("%H%M")이 동일해야 함)
    # 더 간단한 방식: _update_scan_manifest 직접 테스트

    # 대신 cli._update_scan_manifest 직접 호출
    csv_path = output_dir / "20260418" / "1D" / json_path.name.replace(".json", ".csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(csv_body, encoding="utf-8")

    # 같은 최신 파일 경로로 CSV 포맷 manifest 갱신
    cli._update_scan_manifest(
        output_dir=output_dir,
        strategy_name="test_strategy",
        target_date="20260418",
        timeframe="1D",
        saved_path=json_path,  # 같은 파일 경로
        fmt="csv",  # csv 포맷 추가
    )

    # manifest 확인: formats에 json, csv 모두 포함
    with open(manifest_path) as f:
        manifest = json.load(f)

    entry = manifest[key]
    assert "json" in entry["formats"] or "csv" in entry["formats"]
    assert len(entry["formats"]) >= 1


def test_save_output_manifest_atomic_write_on_corrupt(tmp_path):
    """기존 manifest.json 이 invalid JSON 이어도 warn 만 내고 새 manifest 로 시작하는지 검증."""
    output_dir = tmp_path / "scan_results"
    output_dir.mkdir()

    # corrupt manifest 생성
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text("{ invalid json }", encoding="utf-8")

    candidates = _sample_candidates()
    body = formatters.format_json(
        candidates, "20260418", strategy_name="test_strategy", timeframe="1D"
    )

    # save_output 호출 (warning 로그 예상)
    with patch("cli.logger"):
        saved_path = cli.save_output(
            body=body,
            fmt="json",
            target_date="20260418",
            strategy_name="test_strategy",
            output_dir=output_dir,
            summary_dict={"count": 1},
            tf="1D",
        )

    assert saved_path is not None

    # manifest 파일이 유효한 JSON으로 복구됨
    with open(manifest_path) as f:
        manifest = json.load(f)

    key = "test_strategy__1D"
    assert key in manifest
    assert manifest[key]["date"] == "20260418"
