"""pytest 공통 fixture"""
import sys
from pathlib import Path

import pytest

# 부모 디렉토리를 import path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backtest_engine.scenarios import ScenarioBuilder


@pytest.fixture
def perfect_double_bottom_scenario():
    return ScenarioBuilder.perfect_double_bottom()


@pytest.fixture
def fake_double_bottom_scenario():
    return ScenarioBuilder.fake_double_bottom_loss()


@pytest.fixture
def gap_down_scenario():
    return ScenarioBuilder.gap_down_loss()


@pytest.fixture
def time_stop_scenario():
    return ScenarioBuilder.time_stop_breakeven()


@pytest.fixture
def uptrend_scenario():
    return ScenarioBuilder.no_signal_uptrend()


@pytest.fixture
def choppy_scenario():
    return ScenarioBuilder.choppy_no_signal()
