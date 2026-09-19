"""_build_ctx 를 직접 부르는 스크립트가 regime_grid 를 넘기는지 확인한다.

넘기지 않으면 entry gate 가 무력화된 채로 조용히 돈다.
"""
from __future__ import annotations

import inspect

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "scripts.wf_strategy_compare",
        "scripts.audit_f5_f6_cost_sensitivity",
        "scripts.wf_validate_gap_filter",
    ],
)
def test_스크립트가_regime_grid_를_넘긴다(module_name):
    mod = __import__(module_name, fromlist=["*"])
    src = inspect.getsource(mod)

    assert "_build_ctx(" in src
    for line in src.splitlines():
        if "_build_ctx(" in line and "import" not in line and "def " not in line:
            assert "regime_grid" in line, f"{module_name}: {line.strip()}"


def test_wf_strategy_compare_가_게이트_해제_플래그를_노출한다():
    from scripts.wf_strategy_compare import build_arg_parser

    assert build_arg_parser().parse_args([]).entry_gate is True
    assert build_arg_parser().parse_args(["--no-entry-gate"]).entry_gate is False
