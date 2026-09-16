# -*- coding: utf-8 -*-
"""호환용 파사드. 실제 구현은 render/ 패키지. 기존 import 경로 유지.

생성물
  docs/index.html                  최신 브리핑
  docs/archive/YYYY-MM-DD-am.html  회차 스냅샷
  docs/archive/index.html          날짜 캘린더
  data/YYYY-MM-DD-am.txt           원문 보관(재렌더링용)

입력: main.py가 넘기는 브리핑 본문 문자열, data/*.txt(재렌더 시), data/fundamentals.json, data/econ_results.json, docs/whales.json, docs/rwamap.json
출력: 위 "생성물" 목록(docs/**/*.html)
실행: python publish_site.py rebuild (LLM 호출·뉴스 재수집 없이 저장된 data/*.txt로 전체 페이지 재생성). 평소엔 main.py가 publish()를 호출
관련: main.py, tests/golden_render.py, render/
"""
from render.archive import render_archive_index
from render.config import (
    ARCHIVE_DIR,
    DATA_DIR,
    DOCS_DIR,
    HERO_PARTS,
    KST,
    PARTS,
)
from render.files import _load_body, _load_quotes
from render.layout import render_html
from render.parse import _parse_part, _split_sections
from render.publish import publish, rebuild_all

__all__ = [
    "publish",
    "rebuild_all",
    "render_html",
    "render_archive_index",
    "DATA_DIR",
    "DOCS_DIR",
    "ARCHIVE_DIR",
    "PARTS",
    "HERO_PARTS",
    "_split_sections",
    "_parse_part",
    "_load_body",
    "_load_quotes",
    "KST",
]


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) > 1 and sys.argv[1] == "rebuild":
        n = rebuild_all()
        print(f"저장된 {n}회분으로 전체 페이지를 다시 생성했습니다. "
              "(뉴스 재수집·LLM 호출 없음)")
    else:
        print("사용법: python publish_site.py rebuild")
