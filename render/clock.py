"""현재 시각 단일 진입점. 테스트(골든 렌더)에서 고정 시각으로 바꿔 끼우기 위해 분리."""
from datetime import datetime

from render.config import KST


def now():
    return datetime.now(KST)
