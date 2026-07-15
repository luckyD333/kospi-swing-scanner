"""signals_ui 출력 경로의 ranking 보고서 계약 검증."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from cli import _handle_signals_ui_format


def test_signals_ui_ranking_report_does_not_depend_on_fng_loader(
    tmp_path: Path,
    monkeypatch,
):
    """정보용 F&G를 읽지 않아도 ranking 보고서를 끝까지 생성한다."""
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "market_snapshot.json").write_text(json.dumps({
        "generated_at": "2026-07-15T18:00:00+09:00",
        "source": {},
        "market_indices": {},
        "tickers": {},
    }))
    source_weights = Path(__file__).parents[1] / "weights.yml"
    (tmp_path / "weights.yml").write_text(source_weights.read_text())

    args = SimpleNamespace(
        output_dir=str(tmp_path / "output"),
        market="KOSPI",
        top_n=10,
    )
    result = SimpleNamespace(
        candidates_by_strategy_tf={},
        candidates_by_strategy={},
        target_date="20260715",
    )

    assert _handle_signals_ui_format(args, result) == 0
    assert (tmp_path / "output" / "ranking_report.md").exists()
