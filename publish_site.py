# -*- coding: utf-8 -*-
"""브리핑 본문(plain text)을 하나의 웹 페이지(docs/index.html)로 발행.

구성
- 제목: "26년 7월 23일 오전 뉴스 브리핑" (실행 시각 기준 오전/오후)
- 상단 고정 바: 공포탐욕지수 2종(CNN·크립토) + 탭
- 탭: 뉴스(경제·코인시장) / 주식(해외주식·코인) / 부동산
- 라이트 테마 단일, 외부 의존 없는 정적 HTML

GitHub Pages(공개 저장소 = 무료)가 docs/ 를 그대로 서빙한다.
방문자는 GitHub 계정 없이 링크만으로 열람 가능.
"""
import os
import re
import html as _html
from datetime import datetime

import pytz

KST = pytz.timezone("Asia/Seoul")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "docs")

_SECTION_RE = re.compile(r"^(📈|🪙|📊|💹|🌐|🏘️)\s*(.+)$")
_LABEL_RE = re.compile(r"^\[(.+)\]$")
_ITEM_RE = re.compile(r"^(\d+)\.\s*(?:\((.+?)\)\s*)?(.+)$")
_TICKER_RE = re.compile(r"^📰\s*\[(.+?)\]\s*(.+)$")
_FG_RE = re.compile(r"^-\s*(.+?)\s*:\s*(\d+)\s*\((.+?)\)")

# 탭 구성: (탭 이름, 포함할 섹션 제목 키워드)
TABS = [
    ("뉴스", ["경제 PART", "코인시장 PART"]),
    ("주식", ["해외주식 PART", "코인 PART"]),
    ("부동산", ["부동산 PART"]),
]

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f5f6f8;color:#1c1e21;
 font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","맑은 고딕",
 "Apple SD Gothic Neo",system-ui,sans-serif;line-height:1.62;
 -webkit-text-size-adjust:100%}
.wrap{max-width:780px;margin:0 auto;padding:0 14px 56px}
header{padding:26px 2px 14px}
h1{margin:0;font-size:1.32rem;font-weight:700;letter-spacing:-.02em}
.upd{color:#8b9099;font-size:.8rem;margin-top:5px}

.bar{position:sticky;top:0;z-index:10;background:#f5f6f8;
 padding:8px 0 0;margin:0 -14px;border-bottom:1px solid #e3e5e9}
.bar .inner{max-width:780px;margin:0 auto;padding:0 14px}
.fg{display:flex;gap:8px;margin-bottom:8px}
.chip{flex:1;background:#fff;border:1px solid #e3e5e9;border-radius:10px;
 padding:8px 10px;display:flex;align-items:baseline;gap:7px;min-width:0}
.chip .k{font-size:.74rem;color:#8b9099;white-space:nowrap}
.chip .v{font-size:1.06rem;font-weight:700}
.chip .s{font-size:.74rem;color:#8b9099;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
.fear .v{color:#d2453c}.greed .v{color:#1a9b52}.neu .v{color:#6b7280}

.tabs{display:flex;gap:4px}
.tab{flex:1;appearance:none;border:0;background:transparent;cursor:pointer;
 padding:10px 4px 11px;font:inherit;font-size:.9rem;font-weight:600;color:#8b9099;
 border-bottom:2px solid transparent}
.tab.on{color:#1668dc;border-bottom-color:#1668dc}

.panel{display:none}.panel.on{display:block}
section{background:#fff;border:1px solid #e3e5e9;border-radius:12px;
 padding:16px 16px 8px;margin:14px 0}
h2{margin:0 0 8px;font-size:1.04rem;font-weight:700;letter-spacing:-.01em}
.label{margin:14px 0 6px;font-size:.8rem;font-weight:700;color:#1668dc;
 letter-spacing:.02em}
.item{padding:10px 0;border-top:1px solid #f0f1f3}
.item:first-of-type{border-top:0}
.t{font-weight:600}
.tag{display:inline-block;font-size:.7rem;color:#4b5563;background:#f0f1f3;
 border-radius:5px;padding:1px 6px;margin-right:6px;vertical-align:2px;
 font-weight:600}
.sum{margin-top:3px;color:#33363b}
.src{margin-top:3px;color:#9aa0a8;font-size:.78rem}
ul{margin:6px 0 12px;padding-left:17px}
li{margin:4px 0}
p{margin:6px 0 12px}
footer{color:#9aa0a8;font-size:.76rem;margin-top:24px;text-align:center;
 line-height:1.7}
"""


def _split_sections(body):
    """본문을 [(섹션제목, [내용줄])] 로 분해."""
    out, cur = [], None
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = _SECTION_RE.match(s)
        if m:
            cur = (f"{m.group(1)} {m.group(2)}", [])
            out.append(cur)
            continue
        if cur is not None:
            cur[1].append(s)
    return out


def _fear_greed(sections):
    """공포탐욕지수 섹션에서 [(이름, 값, 등급)] 추출."""
    for title, lines in sections:
        if "공포탐욕" in title:
            found = []
            for ln in lines:
                m = _FG_RE.match(ln)
                if m:
                    found.append((m.group(1), m.group(2), m.group(3)))
            return found
    return []


def _fg_class(grade):
    g = (grade or "").lower()
    if "greed" in g or "탐욕" in g:
        return "greed"
    if "fear" in g or "공포" in g:
        return "fear"
    return "neu"


def _render_lines(lines):
    """섹션 내용 줄들을 HTML 로 변환."""
    out = []
    open_item = in_list = False

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

    for s in lines:
        m = _LABEL_RE.match(s)
        if m:
            close_list(); close_item()
            out.append(f'<div class="label">{_html.escape(m.group(1))}</div>')
            continue
        if s.startswith("→"):
            out.append(f'<div class="sum">{_html.escape(s.lstrip("→").strip())}</div>')
            continue
        if s.startswith("(") and s.endswith(")"):
            out.append(f'<div class="src">{_html.escape(s)}</div>')
            continue
        if s[0] in "•-":
            close_item()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_html.escape(s[1:].strip())}</li>")
            continue
        close_list()

        m = _TICKER_RE.match(s)
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

        out.append(f"<p>{_html.escape(s)}</p>")

    close_list(); close_item()
    return "\n".join(out)


def _title(now):
    ampm = "오전" if now.hour < 12 else "오후"
    return f"{now.year % 100}년 {now.month}월 {now.day}일 {ampm} 뉴스 브리핑"


def render_html(body, now=None):
    now = now or datetime.now(KST)
    sections = _split_sections(body)
    fg = _fear_greed(sections)

    chips = []
    for name, val, grade in fg[:2]:
        chips.append(
            f'<div class="chip {_fg_class(grade)}">'
            f'<span class="k">{_html.escape(name)}</span>'
            f'<span class="v">{_html.escape(val)}</span>'
            f'<span class="s">{_html.escape(grade)}</span></div>')
    fg_html = f'<div class="fg">{"".join(chips)}</div>' if chips else ""

    tabs, panels = [], []
    for i, (tab_name, keys) in enumerate(TABS):
        body_html = []
        for title, lines in sections:
            if not any(k in title for k in keys):
                continue
            body_html.append("<section>")
            body_html.append(f"<h2>{_html.escape(title)}</h2>")
            body_html.append(_render_lines(lines))
            body_html.append("</section>")
        on = " on" if i == 0 else ""
        tabs.append(f'<button class="tab{on}" data-p="p{i}">'
                    f'{_html.escape(tab_name)}</button>')
        panels.append(f'<div class="panel{on}" id="p{i}">'
                      f'{"".join(body_html)}</div>')

    stamp = now.strftime("%Y-%m-%d %H:%M KST")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="color-scheme" content="light">
<title>{_html.escape(_title(now))}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>{_html.escape(_title(now))}</h1>
  <div class="upd">최종 업데이트 · {_html.escape(stamp)}</div>
</header>
<div class="bar"><div class="inner">
{fg_html}
<div class="tabs">{"".join(tabs)}</div>
</div></div>
{"".join(panels)}
<footer>
  기사 요약은 각 언론사 보도를 바탕으로 자동 생성되었으며, 저작권은 해당 언론사에 있습니다.<br>
  정보 제공 목적이며 투자 판단의 책임은 본인에게 있습니다.
</footer>
</div>
<script>
document.querySelectorAll('.tab').forEach(function(b){{
  b.addEventListener('click', function(){{
    document.querySelectorAll('.tab').forEach(function(x){{x.classList.remove('on');}});
    document.querySelectorAll('.panel').forEach(function(x){{x.classList.remove('on');}});
    b.classList.add('on');
    document.getElementById(b.dataset.p).classList.add('on');
  }});
}});
</script>
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
