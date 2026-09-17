# -*- coding: utf-8 -*-
"""HTML 정규화 비교 테스트 헬퍼(Stage 3b-i: CSS/JS 인라인 → 정적 자산화 검증용).

두 가지를 검사한다.

1) 정규화 동치성: 두 디렉터리의 짝지어진 .html 파일에서 <style>...</style>,
   <script ...>...</script>(인라인·외부 불문), <link rel="stylesheet" ...> 를 모두
   제거한 나머지 텍스트가 바이트 단위로 동일한지 비교(=CSS/JS를 정적 파일로 옮긴 것 외
   페이지 내용에 회귀가 없는지).

2) 자산 내용 동치성: "새 렌더"의 각 페이지가 참조하는 자산 파일(assets/*.css, assets/*.js)의
   내용을 태그 순서대로 이어붙인 것이, "이전 렌더"의 같은 페이지에서 제거된 인라인
   <style>/<script> 블록을 문서 순서대로 이어붙인 것과 같은 내용인지 확인한다(CSS·JS 각각).
   단, site.js/archive.js처럼 여러 상수를 한 파일로 묶을 때는 지시대로 블록 사이에
   개행을 하나씩 끼워 넣으므로(원본은 상수끼리 구분자 없이 그대로 이어붙어 있었음),
   그 의도된 개행 삽입만큼의 차이는 실제 내용 손상이 아니다 — 그래서 JS 비교는 두 쪽
   모두에서 개행 문자를 제거한 뒤 비교한다(공백만 차이나면 OK, 그 외 문자가 다르면 DIFF).
   이미 외부 참조였던 <script src="...">(goal-app.js·push.js 등, assets/ 밖)는 이전에도
   지금도 인라인이 아니므로 두 쪽 다 집계에서 제외한다.

사용:
    python tests/normalize_html.py <old_dir> <new_dir>
"""
from __future__ import annotations

import os
import re
import sys
import urllib.parse

_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.S)
_SCRIPT_BLOCK_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.S)
_LINK_STYLESHEET_RE = re.compile(r'<link\b[^>]*rel="stylesheet"[^>]*>')

_STYLE_TAG_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S)
_SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S)
_LINK_TAG_RE = re.compile(r'<link\b([^>]*)rel="stylesheet"([^>]*)>')
_SRC_ATTR_RE = re.compile(r'src="([^"]*)"')
_HREF_ATTR_RE = re.compile(r'href="([^"]*)"')


def strip_all(html: str) -> str:
    """<style>/<script>/<link rel=stylesheet> 를 모두 제거한 나머지 텍스트."""
    html = _STYLE_BLOCK_RE.sub("", html)
    html = _SCRIPT_BLOCK_RE.sub("", html)
    html = _LINK_STYLESHEET_RE.sub("", html)
    return html


def _resolve(html_path, url):
    """href/src 값(쿼리스트링 포함 가능)을 파일 경로로. 외부(http)면 None."""
    url = url.split("?", 1)[0]
    if url.startswith("http://") or url.startswith("https://") or url.startswith("//"):
        return None
    url = urllib.parse.unquote(url)
    return os.path.normpath(os.path.join(os.path.dirname(html_path), url))


def _is_asset_path(path):
    return path is not None and ("assets" + os.sep) in (path + os.sep)


def old_inline_blocks(html: str) -> tuple[list[str], list[str]]:
    """(css_list, js_list): 문서 순서대로 <style> 본문, <script>(src 없는 것) 본문."""
    css_list = [m.group(1) for m in _STYLE_TAG_RE.finditer(html)]
    js_list = []
    for m in _SCRIPT_TAG_RE.finditer(html):
        attrs, body = m.group(1), m.group(2)
        if _SRC_ATTR_RE.search(attrs):
            continue   # 이미 외부 참조(goal-app.js, push.js 등) — 집계 제외
        js_list.append(body)
    return css_list, js_list


def new_asset_contributions(html: str, html_path: str) -> tuple[list[str], list[str]]:
    """(css_list, js_list): 문서 순서대로,
    - <style> 본문(옮기지 않고 남아있다면) 또는 <link rel=stylesheet href=".../assets/*.css">가
      가리키는 로컬 파일의 내용
    - <script>(src 없음) 본문(예: 테마 초기화 인라인, 의도적으로 안 옮김) 또는
      <script src=".../assets/*.js">가 가리키는 로컬 파일의 내용
    goal-app.js·push.js처럼 assets/ 밖을 가리키는 외부 참조는 제외(이전에도 인라인이 아니었음)."""
    css_list, js_list = [], []
    for m in _STYLE_TAG_RE.finditer(html):
        css_list.append(m.group(1))
    for m in _LINK_TAG_RE.finditer(html):
        attrs = m.group(1) + m.group(2)
        hm = _HREF_ATTR_RE.search(attrs)
        if not hm:
            continue
        path = _resolve(html_path, hm.group(1))
        if _is_asset_path(path) and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                css_list.append(f.read())
    for m in _SCRIPT_TAG_RE.finditer(html):
        attrs, body = m.group(1), m.group(2)
        sm = _SRC_ATTR_RE.search(attrs)
        if not sm:
            js_list.append(body)   # 여전히 인라인(예: HEAD 테마 초기화 스크립트, 의도적으로 유지)
            continue
        path = _resolve(html_path, sm.group(1))
        if _is_asset_path(path) and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                js_list.append(f.read())
        # else: assets/ 밖의 외부 참조(goal-app.js, push.js) — 이전에도 인라인이 아니었으므로 제외
    return css_list, js_list


def check_normalized_equivalence(old_dir: str, new_dir: str) -> bool:
    ok = True
    old_files = {os.path.relpath(os.path.join(dp, f), old_dir).replace(os.sep, "/")
                 for dp, _dn, fs in os.walk(old_dir) for f in fs if f.endswith(".html")}
    new_files = {os.path.relpath(os.path.join(dp, f), new_dir).replace(os.sep, "/")
                 for dp, _dn, fs in os.walk(new_dir) for f in fs if f.endswith(".html")}
    for rel in sorted(old_files | new_files):
        if rel not in old_files or rel not in new_files:
            print(f"MISSING {rel} (old={rel in old_files} new={rel in new_files})")
            ok = False
            continue
        with open(os.path.join(old_dir, rel), encoding="utf-8") as f:
            a = strip_all(f.read())
        with open(os.path.join(new_dir, rel), encoding="utf-8") as f:
            b = strip_all(f.read())
        if a == b:
            print(f"OK    {rel}")
        else:
            print(f"DIFF  {rel}")
            ok = False
    return ok


def check_asset_equivalence(old_dir: str, new_dir: str) -> bool:
    ok = True
    new_files = sorted(os.path.relpath(os.path.join(dp, f), new_dir).replace(os.sep, "/")
                        for dp, _dn, fs in os.walk(new_dir) for f in fs if f.endswith(".html"))
    for rel in new_files:
        old_path = os.path.join(old_dir, rel)
        new_path = os.path.join(new_dir, rel)
        if not os.path.isfile(old_path):
            print(f"SKIP  {rel} (구 렌더에 없음)")
            continue
        with open(old_path, encoding="utf-8") as f:
            old_html = f.read()
        with open(new_path, encoding="utf-8") as f:
            new_html = f.read()
        old_css, old_js = old_inline_blocks(old_html)
        new_css, new_js = new_asset_contributions(new_html, new_path)
        css_a, css_b = "".join(old_css), "".join(new_css)
        # JS: site.js/archive.js처럼 여러 상수를 한 파일로 합칠 때 지시대로 블록 사이에 개행을
        # 하나 끼워 넣는다(원본은 구분자 없이 이어붙어 있었음) — 그 의도된 개행만 제외하고 비교.
        js_a = "".join(old_js).replace("\n", "")
        js_b = "".join(new_js).replace("\n", "")
        css_ok = css_a == css_b
        js_ok = js_a == js_b
        if css_ok and js_ok:
            print(f"OK    {rel}  (css {len(css_a)}B, js {len(js_a)}B)")
        else:
            print(f"DIFF  {rel}  css_ok={css_ok} js_ok={js_ok}")
            if not css_ok:
                print(f"      css old={len(css_a)}B new={len(css_b)}B")
            if not js_ok:
                print(f"      js  old={len(js_a)}B new={len(js_b)}B")
            ok = False
    return ok


def main(old_dir: str, new_dir: str) -> int:
    print("== 1) 정규화 동치성(HTML, style/script/link 제거 후 비교) ==")
    ok1 = check_normalized_equivalence(old_dir, new_dir)
    print()
    print("== 2) 자산 내용 동치성(참조 자산 파일 vs 구 렌더 인라인 블록) ==")
    ok2 = check_asset_equivalence(old_dir, new_dir)
    print()
    if ok1 and ok2:
        print("ALL OK")
        return 0
    print("FAILED" + ("" if ok1 else " (정규화 동치성)") + ("" if ok2 else " (자산 내용 동치성)"))
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
