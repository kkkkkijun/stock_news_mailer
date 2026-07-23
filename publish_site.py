# -*- coding: utf-8 -*-
"""브리핑 본문(plain text)을 하나의 웹 페이지(docs/index.html)로 발행.

GitHub Pages(공개 저장소 = 무료)가 docs/ 폴더를 그대로 서빙한다.
방문자는 GitHub 계정 없이 링크만으로 볼 수 있다.

main.py 가 build_body() 결과를 넘겨 호출한다.
"""
import os
import re
import html as _html
from datetime import datetime

import pytz

KST = pytz.timezone("Asia/Seoul")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "docs")

# 본문에서 대제목으로 인식할 섹션들 (이모지 + 'PART' 또는 공포탐욕지수)
_SECTION_RE = re.compile(r"^(📈|🪙|📊|💹|🌐|🏘️)\s*(.+)$")
# [오늘 한눈에] 같은 소제목
_LABEL_RE = re.compile(r"^\[(.+)\]$")
# "1. (테마) 제목" 형태의 뉴스 항목
_ITEM_RE = re.compile(r"^(\d+)\.\s*(?:\((.+?)\)\s*)?(.+)$")
# "📰 [NVDA] 제목" 형태의 티커 뉴스 항목
_TICKER_RE = re.compile(r"^📰\s*\[(.+?)\]\s*(.+)$")

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--tx:#1f2328;--sub:#6b7280;--line:#e5e7eb;--ac:#2563eb}
@media (prefers-color-scheme:dark){
  :root{--bg:#0f1115;--card:#171a21;--tx:#e6e8eb;--sub:#9aa1ab;--line:#272b33;--ac:#7aa2ff}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
  font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","맑은 고딕",
  "Apple SD Gothic Neo",system-ui,sans-serif;line-height:1.65;
  -webkit-text-size-adjust:100%}
.wrap{max-width:820px;margin:0 auto;padding:20px 16px 60px}
header{padding:22px 0 8px}
h1{margin:0;font-size:1.5rem;letter-spacing:-.02em}
.meta{color:var(--sub);font-size:.86rem;margin-top:6px}
section{background:var(--card);border:1px solid var(--line);border-radius:14px;
  padding:18px 18px 6px;margin:16px 0}
h2{margin:0 0 10px;font-size:1.15rem;letter-spacing:-.01em}
.label{margin:16px 0 6px;font-weight:700;font-size:.92rem;color:var(--ac)}
.item{margin:10px 0 14px}
.item .t{font-weight:600}
.tag{display:inline-block;font-size:.72rem;color:var(--ac);
  border:1px solid var(--ac);border-radius:999px;padding:1px 7px;margin-right:6px;
  vertical-align:1px}
.sum{color:var(--tx);margin:3px 0 0}
.src{color:var(--sub);font-size:.8rem;margin-top:2px}
ul{margin:6px 0 12px;padding-left:18px}
li{margin:4px 0}
p{margin:6px 0 12px}
.item .sum,.item .src{margin-left:0}
footer{color:var(--sub);font-size:.8rem;margin-top:26px;text-align:center;
  line-height:1.7}
"""


def _render_body(body):
    """plain text 브리핑을 섹션 카드 HTML 로 변환.

    뉴스 항목은 제목·요약·출처를 하나의 .item 블록으로 묶는다.
    """
    out = []
    open_sec = open_item = in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def close_item():
        nonlocal open_item
        if open_item:
            out.append("</div>")
            open_item = False

    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue

        m = _SECTION_RE.match(s)
        if m:
            close_list(); close_item()
            if open_sec:
                out.append("</section>")
            out.append("<section>")
            out.append(f"<h2>{_html.escape(m.group(1)+' '+m.group(2))}</h2>")
            open_sec = True
            continue

        if not open_sec:          # 맨 위 "[오늘의 뉴스 요약] ..." 등
            continue

        m = _LABEL_RE.match(s)
        if m:
            close_list(); close_item()
            out.append(f'<div class="label">{_html.escape(m.group(1))}</div>')
            continue

        if s.startswith("→"):     # 뉴스 요약 (항목 안에 들어감)
            out.append(f'<div class="sum">{_html.escape(s.lstrip("→").strip())}</div>')
            continue
        if s.startswith("(") and s.endswith(")"):   # (매체 · 시각)
            out.append(f'<div class="src">{_html.escape(s)}</div>')
            continue

        if s[0] in "•-":          # 전망 불릿 / 공포탐욕지수 항목
            close_item()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_html.escape(s[1:].strip())}</li>")
            continue
        close_list()

        m = _TICKER_RE.match(s)     # 📰 [NVDA] 제목  (해외주식·코인 PART)
        if m:
            close_item()
            out.append('<div class="item"><div class="t">'
                       f'<span class="tag">{_html.escape(m.group(1))}</span>'
                       f'{_html.escape(m.group(2))}</div>')
            open_item = True
            continue

        m = _ITEM_RE.match(s)
        if m:
            close_item()
            tag = (f'<span class="tag">{_html.escape(m.group(2))}</span>'
                   if m.group(2) else "")
            out.append('<div class="item"><div class="t">'
                       f'{tag}{_html.escape(m.group(3))}</div>')
            open_item = True
            continue

        out.append(f"<p>{_html.escape(s)}</p>")   # 일반 문단(오늘 한눈에 등)

    close_list(); close_item()
    if open_sec:
        out.append("</section>")
    return "\n".join(out)


def render_html(body, now=None):
    now = now or datetime.now(KST)
    stamp = now.strftime("%Y-%m-%d %H:%M KST")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>오늘의 뉴스 브리핑</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>오늘의 뉴스 브리핑</h1>
  <div class="meta">최종 업데이트 · {_html.escape(stamp)} &nbsp;|&nbsp; 매일 오전·오후 자동 갱신</div>
</header>
{_render_body(body)}
<footer>
  기사 요약은 각 언론사 보도를 바탕으로 자동 생성되었으며, 저작권은 해당 언론사에 있습니다.<br>
  정보 제공 목적이며 투자 판단의 책임은 본인에게 있습니다.
</footer>
</div>
</body>
</html>
"""


def publish(body, now=None):
    """docs/index.html 생성. 생성된 경로를 반환."""
    os.makedirs(DOCS_DIR, exist_ok=True)
    path = os.path.join(DOCS_DIR, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_html(body, now=now))
    return path


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sample = sys.stdin.read()
    print(publish(sample))
