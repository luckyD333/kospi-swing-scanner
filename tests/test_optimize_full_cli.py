"""optimize_full.py 는 --help 로 죽지 않아야 한다."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_help_가_정상_종료한다(tmp_path):
    proc = subprocess.run(
        [sys.executable, "scripts/optimize_full.py", "--help",
         "--run-dir-root", str(tmp_path / "runs")],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )

    assert proc.returncode == 0, proc.stderr
    assert "--kospi-tickers" in proc.stdout


def test_종목_파일이_없으면_이유를_말하고_끝낸다(tmp_path):
    """run_dir 는 tmp_path 아래로 돌린다. 기본값은 /tmp 에 빈 디렉토리를 남긴다."""
    missing = tmp_path / "없는파일.txt"
    proc = subprocess.run(
        [sys.executable, "scripts/optimize_full.py",
         "--kospi-tickers", str(missing),
         "--run-dir-root", str(tmp_path / "runs")],
        cwd=REPO, capture_output=True, text=True, timeout=60,
    )

    assert proc.returncode == 1
    assert "없는파일.txt" in (proc.stdout + proc.stderr)
