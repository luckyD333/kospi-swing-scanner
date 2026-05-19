"""tests/conftest.py — 프로젝트 루트를 import path에 추가 + pytest 마커 등록"""
import sys
from pathlib import Path

import pytest

# 프로젝트 루트(이 파일의 상위)를 import path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config):
    """커스텀 마커 등록 — 알 수 없는 마커 경고 회피."""
    config.addinivalue_line(
        "markers",
        "sensitivity: 파라미터 민감도 자동화 테스트 (실행 시간 길어서 default skip, "
        "-m sensitivity 명시 필요)",
    )


def pytest_collection_modifyitems(config, items):
    """-m sensitivity 명시 안 하면 sensitivity 마커 테스트를 default skip."""
    marker_expr = config.getoption("-m", default="") or ""
    if "sensitivity" in marker_expr:
        return  # 명시 호출 시 skip 안 함
    skip_sens = pytest.mark.skip(reason="sensitivity 테스트는 -m sensitivity 명시 필요")
    for item in items:
        if "sensitivity" in item.keywords:
            item.add_marker(skip_sens)
