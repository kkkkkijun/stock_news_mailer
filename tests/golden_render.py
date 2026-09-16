"""골든 렌더 하네스: 저장된 data/ 원문으로 사이트 전체를 **고정 시각**에 재생성한다.

리팩터 전후로 각각 실행해 출력 디렉터리를 `diff -r` 하면, 렌더 결과가 바이트 단위로
동일한지(= 동작 회귀 없음) 기계적으로 확인할 수 있다. LLM·네트워크 호출 없음.

사용:
    python tests/golden_render.py <out_dir>
    # 변경 전:  python tests/golden_render.py /tmp/golden/before
    # 변경 후:  python tests/golden_render.py /tmp/golden/after
    # 비교:     diff -rq /tmp/golden/before /tmp/golden/after

고정 시각을 쓰는 이유: 일정 탭 등은 "실제 현재 시각" 기준으로 과거/미래를 나누므로,
시각을 고정하지 않으면 두 실행 사이의 시간차만으로 diff가 생긴다.

입력: 이미 저장된 data/*.txt 등 원문(네트워크·LLM 호출 없음), publish_site.py
출력: <out_dir> 아래에 재생성된 정적 페이지(docs/**/*.html 상당)
실행: python tests/golden_render.py <out_dir>
관련: publish_site.py
"""
import os
import shutil
import sys
from datetime import datetime

import pytz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import publish_site as ps  # noqa: E402  (ROOT를 sys.path에 넣은 뒤 import)

FIXED_NOW = pytz.timezone("Asia/Seoul").localize(datetime(2026, 9, 16, 12, 0, 0))


class FrozenDatetime(datetime):
    """datetime.now()만 고정 시각을 돌려주는 서브클래스(strptime 등은 그대로)."""

    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW.astimezone(tz) if tz else FIXED_NOW.replace(tzinfo=None)


def main(out_dir: str) -> int:
    out_dir = os.path.abspath(out_dir)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    ps.datetime = FrozenDatetime
    ps.DOCS_DIR = out_dir
    ps.ARCHIVE_DIR = os.path.join(out_dir, "archive")
    n = ps.rebuild_all()
    print(f"rendered {n} pages -> {out_dir}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
