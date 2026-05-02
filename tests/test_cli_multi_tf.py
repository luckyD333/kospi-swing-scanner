"""
Task 8: CLI --timeframes + per-tf 출력 디렉토리 검증.

검증:
  - --timeframes 1D 1W 지정 시 strategy_one_d_v2, strategy_one_w_v2 선택
  - runner_timeframes 가 전략 인스턴스에서 자동 추출
  - save_output 이 scan_results/{date}/{tf}/ 에 저장
  - --timeframes 미지정 시 기존 단일-TF 동작 유지
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from cli import _resolve_by_timeframes, resolve_strategies, save_output

# ---------------------------------------------------------------- resolve_strategies


def test_resolve_by_timeframes_1d_1w():
    strategies = _resolve_by_timeframes(["1D", "1W"])
    tfs = {getattr(s, "timeframe", None) for s in strategies}
    assert "1D" in tfs
    assert "1W" in tfs


def test_resolve_by_timeframes_excludes_others():
    strategies = _resolve_by_timeframes(["30m"])
    tfs = {getattr(s, "timeframe", None) for s in strategies}
    assert tfs == {"30m"} or "30m" in tfs
    assert "1D" not in tfs
    assert "1W" not in tfs


def test_resolve_strategies_with_timeframes_overrides_name():
    # --timeframes 가 있으면 --strategy 이름 무시하고 TF 기반 선택
    strategies = resolve_strategies("strategy_one_d_v2", timeframes=["1W"])
    assert any(getattr(s, "timeframe", None) == "1W" for s in strategies)
    assert not any(getattr(s, "timeframe", None) == "1D" for s in strategies)


def test_resolve_strategies_no_timeframes_uses_name():
    strategies = resolve_strategies("strategy_one_d_v2", timeframes=None)
    assert len(strategies) == 1
    assert strategies[0].name == "strategy_one_d_v2"


# ---------------------------------------------------------------- save_output per-tf subdir


def test_save_output_creates_tf_subdir(tmp_path):
    body = "ticker,score\n005930,0.8\n"
    path = save_output(
        body=body,
        fmt="csv",
        target_date="20260430",
        strategy_name="strategy_one_w_v2",
        output_dir=tmp_path,
        tf="1W",
    )
    assert path is not None
    # 파일이 {tmp_path}/20260430/1W/ 하위에 있어야 함
    assert "1W" in str(path)
    assert path.parent == tmp_path / "20260430" / "1W"
    assert path.exists()


def test_save_output_no_tf_uses_date_subdir(tmp_path):
    body = "ticker,score\n005930,0.8\n"
    path = save_output(
        body=body,
        fmt="csv",
        target_date="20260430",
        strategy_name="strategy_one_d_v2",
        output_dir=tmp_path,
        tf=None,
    )
    assert path is not None
    assert path.parent == tmp_path / "20260430"


# ---------------------------------------------------------------- CLI 인자 → RunnerConfig.timeframes


def test_main_passes_timeframes_to_runner(tmp_path):
    """--timeframes 1D 1W 시 RunnerConfig.timeframes=["1D","1W"] 로 ScanRunner 생성."""
    captured = {}

    class _FakeRunner:
        def __init__(self, client, config):
            captured["timeframes"] = config.timeframes

        def run(self, strategies, target_date=None):
            from core.runner import RunResult
            return RunResult(
                target_date="20260430",
                universe_size=0,
                candidates_by_strategy={},
                candidates_by_strategy_tf={},
            )

    with patch("cli.ScanRunner", _FakeRunner), \
         patch("cli.DataClient", MagicMock()), \
         patch("cli.formatters.format_run_summary", return_value=""), \
         patch("cli.formatters.format_run_summary_json", return_value={}):
        from cli import main
        main(["--timeframes", "1D", "1W", "--date", "20260430"])

    assert set(captured["timeframes"]) == {"1D", "1W"}
