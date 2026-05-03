"""tests/test_collect_pipeline.py — collect.py manifest 동적 가중치 상태 회귀."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_manifest_records_dynamic_weights_failure(tmp_path: Path) -> None:
    """compute_weights.py exit 1 시 manifest 에 dynamic_weights_computed=False 기록."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import collect as col

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    manifest_path = cache_root / "manifest.json"
    manifest_path.write_text(json.dumps({"tickers_meta": {}, "base_tfs": ["1D"]}))

    fake_result = MagicMock(returncode=1, stderr="weights.yml not found", stdout="")

    cfg = col.CollectConfig(market="KOSPI", cache_root=cache_root, scan_root=scan_root)
    with patch.object(col, "_subprocess_run", return_value=fake_result):
        col._update_dynamic_weights_status(cfg, manifest_path)

    updated = json.loads(manifest_path.read_text())
    assert updated["dynamic_weights_computed"] is False
    assert "weights.yml not found" in updated.get("dynamic_weights_error", "")


def test_manifest_records_dynamic_weights_success(tmp_path: Path) -> None:
    """compute_weights.py exit 0 시 manifest 에 dynamic_weights_computed=True 기록."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts import collect as col

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    manifest_path = cache_root / "manifest.json"
    manifest_path.write_text(json.dumps({"tickers_meta": {}, "base_tfs": ["1D"]}))

    fake_result = MagicMock(returncode=0, stderr="", stdout="dynamic_weights 저장")

    cfg = col.CollectConfig(market="KOSPI", cache_root=cache_root, scan_root=scan_root)
    with patch.object(col, "_subprocess_run", return_value=fake_result):
        col._update_dynamic_weights_status(cfg, manifest_path)

    updated = json.loads(manifest_path.read_text())
    assert updated["dynamic_weights_computed"] is True
    assert "dynamic_weights_error" not in updated
