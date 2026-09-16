# -*- coding: utf-8 -*-
"""정적 자산(CSS/JS) 기록 + 캐시버스터 해시. 페이지는 인라인 대신 <link>/<script src>로 참조."""
import functools
import hashlib
import os
import re

# <script[ ...]>내용</script> 에서 첫 블록만 추출(내용, 그 뒤 나머지 원문). 이 모듈이 다루는
# 상수들은 <script> 태그를 자체 포함하고 있어(예: _PWA_JS는 인라인 블록 뒤에 이미 외부 참조인
# push.js 태그가 붙어있음) 파일에는 순수 JS만 쓰고, 이미 외부 참조인 태그는 그대로 남긴다.
_SCRIPT_RE = re.compile(r"<script(?:\s[^>]*)?>(.*?)</script>", re.S)

# 공통(모든 페이지 종류에 항상 등장) 스크립트를 담는 파일. 순서 고정.
_SITE_JS_PARTS = ("_TOP_JS", "_THEME_JS", "_PWA_JS")


def _split_script(text):
    m = _SCRIPT_RE.search(text)
    if not m:
        return text, ""
    return m.group(1), text[m.end():]


def _hash10(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:10]


@functools.lru_cache(maxsize=None)
def _asset(name):
    """(파일 내용, 해시10자) 반환. 원본 상수는 지연 임포트(레이아웃↔자산 순환 임포트 회피)."""
    if name == "site.css":
        from render.layout import CSS
        content = CSS
    elif name == "site.js":
        from render.layout import _TOP_JS, _THEME_JS, _PWA_JS
        top_js, _tail = _split_script(_TOP_JS)
        theme_js, _tail = _split_script(_THEME_JS)
        pwa_js, _tail = _split_script(_PWA_JS)
        content = "\n".join([top_js, theme_js, pwa_js])
    elif name == "tab.js":
        from render.layout import _TAB_JS
        content, _tail = _split_script(_TAB_JS)
    elif name == "sched.js":
        from render.schedule import _SCHED_JS
        content, _tail = _split_script(_SCHED_JS)
    elif name == "growth.js":
        from render.growth import _GROWTH_JS
        content, _tail = _split_script(_GROWTH_JS)
    elif name == "rwa.js":
        from render.rwamap import _RWA_JS
        content, _tail = _split_script(_RWA_JS)
    else:
        raise KeyError(name)
    return content, _hash10(content.encode("utf-8"))


def _pwa_tail():
    """_PWA_JS 중 site.js로 옮긴 인라인 블록 뒤에 남는 원문(이미 외부 참조인 push.js 태그)."""
    from render.layout import _PWA_JS
    _content, tail = _split_script(_PWA_JS)
    return tail


_STATIC_NAMES = ("site.css", "site.js", "tab.js", "sched.js", "growth.js", "rwa.js")


def write_assets(config):
    """정적 CSS/JS를 config.DOCS_DIR/assets/ 에 기록. rebuild_all()/publish() 시작 시 호출.

    (archive.js는 브리핑 날짜 인덱스·검색 색인을 담아 렌더마다 내용이 바뀌므로 여기서 쓰지
    않는다 — render.archive.render_archive_index()가 write_archive_js()로 직접 기록한다.)
    """
    out_dir = os.path.join(config.DOCS_DIR, "assets")
    os.makedirs(out_dir, exist_ok=True)
    hashes = {}
    for name in _STATIC_NAMES:
        content, h = _asset(name)
        with open(os.path.join(out_dir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        hashes[name] = h
    return hashes


def write_archive_js(config, js_text, prefix):
    """CAL_JS+SEARCH_JS(데이터 치환 완료)를 archive.js로 기록하고 <script src> 태그를 반환."""
    out_dir = os.path.join(config.DOCS_DIR, "assets")
    os.makedirs(out_dir, exist_ok=True)
    h = _hash10(js_text.encode("utf-8"))
    with open(os.path.join(out_dir, "archive.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(js_text)
    return f'<script src="{prefix}assets/archive.js?v={h}"></script>'


def tag(name, prefix):
    """<script src="{prefix}assets/{name}?v={hash}"></script>"""
    _content, h = _asset(name)
    return f'<script src="{prefix}assets/{name}?v={h}"></script>'


def tag_css(prefix):
    """<link rel="stylesheet" href="{prefix}assets/site.css?v={hash}">"""
    _content, h = _asset("site.css")
    return f'<link rel="stylesheet" href="{prefix}assets/site.css?v={h}">'


def site_scripts_tag(prefix):
    """body 끝 공통 스크립트(TOP_JS+THEME_JS+PWA_JS) 자리를 대신하는 태그.

    _PWA_JS 뒤에 이미 붙어있던 외부 참조(push.js) 태그는 옮기지 않고 그대로 붙인다."""
    return tag("site.js", prefix) + _pwa_tail()
