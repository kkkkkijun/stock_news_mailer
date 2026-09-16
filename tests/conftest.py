# -*- coding: utf-8 -*-
"""pytest 공통 설정. 저장소 루트를 sys.path에 넣어 모듈을 직접 import할 수 있게 한다.

입력: 없음
출력: 없음(부수효과로 sys.path 조정)
실행: pytest가 자동으로 로드
관련: tests/test_*.py
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
