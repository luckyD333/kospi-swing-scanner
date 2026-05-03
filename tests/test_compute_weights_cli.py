"""tests/test_compute_weights_cli.py — compute_weights.py CLI 실패 모드 회귀."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_weights_yml_missing_exits_1(tmp_path: Path) -> None:
    """weights.yml 부재 시 exit 1 + stderr 에 명시 메시지."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    missing_yml = tmp_path / "missing_weights.yml"

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "scripts" / "compute_weights.py"),
            "--cache-root", str(cache_root),
            "--scan-root", str(scan_root),
            "--weights-yml", str(missing_yml),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, f"expected exit 1, got {result.returncode}"
    assert "weights.yml not found" in (result.stderr + result.stdout)
    assert not (cache_root / "dynamic_weights.json").exists()


def test_hmm_import_failure_logs_explicit_message(tmp_path: Path, monkeypatch) -> None:
    """hmmlearn ImportError 시 분리된 경고 메시지 (regime_score=50 fallback)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import compute_weights as cw

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    weights_yml = tmp_path / "weights.yml"
    weights_yml.write_text(
        "priorities:\n"
        "  - key: rr_ratio\n    weight: 100.0\n    direction: higher_better\n    label: RR\n"
        "must_have: []\n"
        "strategy_weights: {}\n"
    )

    def _raise_import_error(_path: Path):
        raise ImportError("No module named 'hmmlearn'")

    monkeypatch.setattr(cw, "load_regime_analysis", lambda _p: None)
    monkeypatch.setattr(cw, "analyze_regime", _raise_import_error)

    result = cw.compute_dynamic_weights(cache_root, scan_root, weights_yml)
    assert result["regime_score"] == 50
    assert result["meta"]["regime_failure"] == "hmmlearn_not_installed"


def test_hmm_value_error_logs_insufficient_data(tmp_path: Path, monkeypatch) -> None:
    """HMM 학습 데이터 부족(ValueError) 시 'insufficient_data' 사유 기록."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import compute_weights as cw

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    weights_yml = tmp_path / "weights.yml"
    weights_yml.write_text(
        "priorities:\n"
        "  - key: rr_ratio\n    weight: 100.0\n    direction: higher_better\n    label: RR\n"
        "must_have: []\n"
        "strategy_weights: {}\n"
    )

    def _raise_value_error(_path: Path):
        raise ValueError("not enough data")

    monkeypatch.setattr(cw, "load_regime_analysis", lambda _p: None)
    monkeypatch.setattr(cw, "analyze_regime", _raise_value_error)

    result = cw.compute_dynamic_weights(cache_root, scan_root, weights_yml)
    assert result["regime_score"] == 50
    assert result["meta"]["regime_failure"] == "insufficient_data"
