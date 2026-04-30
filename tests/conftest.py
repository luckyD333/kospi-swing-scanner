"""tests/conftest.py — 프로젝트 루트를 import path에 추가"""
import sys
from pathlib import Path

# 프로젝트 루트(이 파일의 상위)를 import path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
