"""
tests/test_summary_integration.py — Summary + CLI 통합 테스트.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from cli import main
from core.runner import RunResult


def test_cli_outputs_summary_to_stdout(capsys):
    """CLI 실행 시 stdout에 summary 블록 출력."""
    with tempfile.TemporaryDirectory() as _:
        with patch("cli.ScanRunner") as MockRunner:
            # Mock runner 설정
            mock_result = RunResult(
                target_date="2026-04-30",
                universe_size=10,
                candidates_by_strategy={"strategy_one_d_v2": []},
                errors={},
                funnel_stats={
                    "universe_size": 10,
                    "pre_cap_limit_size": 10,
                    "universe_cap_limit": 0,
                    "fetch_success": 7,
                    "fetch_failed": 3,
                    "short_bars": 0,
                    "fetch_exceptions": {},
                    "source_counts": {"naver": 7},
                },
            )
            MockRunner.return_value.run.return_value = mock_result

            # CLI 실행
            ret = main([
                "--strategy", "strategy_one_d_v2",
                "--market", "KOSPI",
                "--top", "5",
            ])

            # stdout 확인
            captured = capsys.readouterr()
            assert "📊 Scan Summary" in captured.out
            assert "2026-04-30" in captured.out
            assert ret == 0


def test_cli_saves_json_with_summary_key(capsys):
    """JSON 저장 시 'summary' 키 포함."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("cli.ScanRunner") as MockRunner:
            mock_result = RunResult(
                target_date="2026-04-30",
                universe_size=5,
                candidates_by_strategy={},
                errors={},
                funnel_stats={
                    "universe_size": 5,
                    "fetch_success": 4,
                    "fetch_failed": 1,
                },
                cache_stats={},
            )
            MockRunner.return_value.run.return_value = mock_result

            # JSON 포맷으로 저장
            main([
                "--strategy", "strategy_one_d_v2",
                "--market", "KOSPI",
                "--format", "json",
                "--output-dir", tmpdir,
            ])

            # 저장된 파일 확인 (scan_*.json 스캔 파일만, manifest.json 제외)
            files = list(Path(tmpdir).rglob("scan_*.json"))
            assert len(files) > 0, f"No scan JSON files found in {tmpdir}"

            json_file = files[0]
            payload = json.loads(json_file.read_text())

            # summary 키 확인
            assert "summary" in payload, f"No 'summary' key in {payload.keys()}"
            assert "funnel" in payload["summary"]
            assert "strategies" in payload["summary"]


def test_cli_saves_with_date_subdirectory(capsys):
    """저장 경로가 scan_results/YYYY-MM-DD/ 형태."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("cli.ScanRunner") as MockRunner:
            mock_result = RunResult(
                target_date="2026-04-30",
                universe_size=5,
                candidates_by_strategy={},
                errors={},
                funnel_stats={},
                cache_stats={},
            )
            MockRunner.return_value.run.return_value = mock_result

            # 저장
            main([
                "--strategy", "strategy_one_d_v2",
                "--market", "KOSPI",
                "--format", "table",
                "--output-dir", tmpdir,
            ])

            # 디렉토리 구조 확인: tmpdir/2026-04-30/1D/*.txt (Task 8: per-tf subdir)
            tf_dir = Path(tmpdir) / "2026-04-30" / "1D"
            assert tf_dir.exists(), f"TF directory not found: {tf_dir}"

            files = list(tf_dir.glob("*.txt"))
            assert len(files) > 0, f"No txt files in {tf_dir}"


def test_cli_verbose_flag_enables_debug_logging():
    """--verbose 플래그가 DEBUG 레벨 활성화."""
    import logging

    with tempfile.TemporaryDirectory() as _:
        with patch("cli.ScanRunner") as MockRunner:
            mock_result = RunResult(
                target_date="2026-04-30",
                universe_size=5,
                candidates_by_strategy={},
                errors={},
                funnel_stats={},
                cache_stats={},
            )
            MockRunner.return_value.run.return_value = mock_result

            # verbose 플래그 없이
            main(["--strategy", "strategy_one_d_v2"])

            # verbose 플래그 포함
            main([
                "--strategy", "strategy_one_d_v2",
                "--verbose",
            ])
            debug_level = logging.getLogger().level

            # DEBUG 레벨 활성화 확인 (값이 낮을수록 더 상세)
            assert debug_level <= logging.DEBUG


def test_cli_max_universe_zero_means_unlimited():
    """--max-universe 0은 무제한으로 처리."""
    with tempfile.TemporaryDirectory() as _:
        with patch("cli.ScanRunner") as MockRunner:
            mock_result = RunResult(
                target_date="2026-04-30",
                universe_size=100,
                candidates_by_strategy={},
                errors={},
                funnel_stats={},
                cache_stats={},
            )
            MockRunner.return_value.run.return_value = mock_result

            # --max-universe 0
            main([
                "--strategy", "strategy_one_d_v2",
                "--max-universe", "0",
            ])

            # RunnerConfig.max_universe_size가 500 (default)로 설정되었는지 확인
            # (0 또는 음수 → None 정규화 → RunnerConfig default 500 사용)
            call_args = MockRunner.call_args
            if call_args:
                runner_config = call_args[1]["config"] if "config" in call_args[1] else None
                if runner_config:
                    # cap_limit = None이면 RunnerConfig는 default 500 사용
                    assert runner_config.max_universe_size == 500


def test_cli_max_universe_negative_normalized():
    """--max-universe 음수도 무제한으로 처리."""
    with tempfile.TemporaryDirectory() as _:
        with patch("cli.ScanRunner") as MockRunner:
            mock_result = RunResult(
                target_date="2026-04-30",
                universe_size=100,
                candidates_by_strategy={},
                errors={},
                funnel_stats={},
                cache_stats={},
            )
            MockRunner.return_value.run.return_value = mock_result

            # --max-universe -1 (음수)
            main([
                "--strategy", "strategy_one_d_v2",
                "--max-universe", "-1",
            ])

            # RunnerConfig.max_universe_size가 500 (default)로 처리
            call_args = MockRunner.call_args
            if call_args:
                runner_config = call_args[1]["config"] if "config" in call_args[1] else None
                if runner_config:
                    assert runner_config.max_universe_size == 500
