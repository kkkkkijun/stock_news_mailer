# -*- coding: utf-8 -*-
"""브리핑 본문(plain text)을 웹 페이지(docs/)로 발행.

디자인은 briefing-template.html 기준.
- 다크 헤더 + 카드형 페이지
- 공포탐욕지수 게이지(그라데이션 트랙 + 마커)
- 섹션 앵커 내비게이션(경제·코인시장·해외주식·코인·부동산)
- 카드형 뉴스 리스트, 요약/흐름·전망 블록

생성물
  docs/index.html                  최신 브리핑
  docs/archive/YYYY-MM-DD-am.html  회차 스냅샷
  docs/archive/index.html          날짜 캘린더
  data/YYYY-MM-DD-am.txt           원문 보관(재렌더링용)
"""
import os
import re
import json
import calendar
import html as _html
from datetime import datetime

import pytz

KST = pytz.timezone("Asia/Seoul")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "docs")
ARCHIVE_DIR = os.path.join(DOCS_DIR, "archive")
# 원문 텍스트 보관소. 디자인만 바꿀 때 뉴스 재수집 없이 재렌더링(rebuild_all).
DATA_DIR = os.path.join(HERE, "data")

_SECTION_RE = re.compile(r"^(📈|🪙|📊|💹|🌐|🏘️)\s*(.+)$")
_LABEL_RE = re.compile(r"^\[(.+)\]$")
_ITEM_RE = re.compile(r"^(\d+)\.\s*(?:\((.+?)\)\s*)?(.+)$")
_TICKER_RE = re.compile(r"^📰\s*\[(.+?)\]\s*(.+)$")
_FG_RE = re.compile(r"^-\s*(.+?)\s*:\s*(\d+)\s*\((.+?)\)")

# (앵커 id, 아이콘, 표시명, 본문 섹션 키워드)
PARTS = [
    ("eco", "💹", "경제", "경제 PART"),
    ("cm", "🌐", "코인시장", "코인시장 PART"),
    ("os", "📈", "해외주식", "해외주식 PART"),
    ("coin", "🪙", "코인", "코인 PART"),
    ("re", "🏘️", "부동산", "부동산 PART"),
]

# 탭 구성: (탭 이름, 포함할 파트 id)
TABS = [
    ("뉴스", ["eco", "cm"]),
    ("주식", ["os", "coin"]),
    ("부동산", ["re"]),
]

# 티커 뱃지 색상 = 각 기업/코인의 브랜드 컬러
# 여기에 없는 티커는 이름 해시로 색을 자동 배정하므로 종목을 바꿔도 동작한다.
TICKER_COLORS = {
    "NVDA": "#76B900",   # NVIDIA 시그니처 그린
    "TSLA": "#E82127",   # Tesla 레드
    "HIMS": "#0F6B5C",   # Hims & Hers 딥그린
    "RDW": "#D0202E",    # Redwire 레드
    "BTC": "#F7931A",    # Bitcoin 오렌지
    "ETH": "#627EEA",    # Ethereum 블루퍼플
    "SOL": "#9945FF",    # Solana 퍼플
    "XRP": "#23292F",
    "DOGE": "#C2A633",
    "AAPL": "#555555",
    "MSFT": "#0078D4",
    "GOOGL": "#4285F4",
    "AMZN": "#FF9900",
    "META": "#0866FF",
    "AMD": "#ED1C24",
}

_DOW = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="color-scheme" content="light">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">"""

CSS = """
*{box-sizing:border-box;}
body{margin:0;font-family:'Pretendard',system-ui,sans-serif;
 -webkit-font-smoothing:antialiased;background:#e8ecf1;}
a{color:#3a6fd8;text-decoration:none;}
a:hover{opacity:.72;}
.wrap{display:flex;justify-content:center;padding:48px 24px;}
.page{width:100%;max-width:820px;background:#f6f8fb;color:#0f1b2d;
 border:1px solid #e6ebf2;border-radius:18px;
 box-shadow:0 12px 44px rgba(15,27,45,.1);overflow:hidden;}
.hd{padding:30px 40px;background:#0f1b2d;color:#fff;}
.hd-top{display:flex;justify-content:space-between;align-items:center;gap:10px;}
.hd-kicker{font-size:12px;font-weight:600;letter-spacing:.04em;color:#94a3b8;}
.hd-links{display:flex;gap:7px;flex-shrink:0;}
.hd-archive{font-size:12px;font-weight:600;color:#dbe4f0;
 background:rgba(255,255,255,.12);padding:6px 13px;border-radius:999px;}
.hd-archive:hover{opacity:1;background:rgba(255,255,255,.2);}
.hd h1{font-size:27px;font-weight:700;margin:16px 0 5px;letter-spacing:-.01em;}
.hd-sub{font-size:13px;color:#94a3b8;}
.dowb{display:inline-block;font-size:11px;font-weight:700;color:#dbe4f0;
 background:rgba(255,255,255,.14);padding:3px 10px;border-radius:999px;
 margin-right:8px;}
.dowb.sat{color:#a8c8ff;background:rgba(120,165,255,.2);}
.dowb.sun{color:#ffb0a8;background:rgba(255,130,120,.2);}
.gauges{display:flex;gap:16px;padding:22px 40px 6px;flex-wrap:wrap;}
.gauge{flex:1;min-width:220px;background:#fff;border:1px solid #e6ebf2;
 border-radius:14px;padding:18px 20px;}
.gauge-label{font-size:12px;color:#64748b;margin-bottom:10px;}
.gauge-row{display:flex;align-items:baseline;gap:10px;margin-bottom:14px;}
.gauge-num{font-size:36px;font-weight:700;line-height:1;color:#0f1b2d;}
.gauge-mood{font-size:12px;font-weight:600;color:#fff;padding:3px 10px;
 border-radius:999px;}
.gauge-track{position:relative;height:6px;border-radius:3px;
 background:linear-gradient(90deg,#c0392b,#d98324,#c9a227,#4a9d5b,#2e7d32);}
.gauge-marker{position:absolute;top:50%;width:12px;height:12px;border-radius:50%;
 background:#fff;border:2.5px solid #0f1b2d;transform:translate(-50%,-50%);}
.gauge-scale{display:flex;justify-content:space-between;font-size:10px;
 color:#94a3b8;margin-top:6px;}
.navwrap{padding:14px 40px 6px;position:sticky;top:0;background:#f6f8fb;z-index:3;}
.nav{display:flex;gap:5px;background:#eef2f7;border:1px solid #e6ebf2;
 border-radius:12px;padding:5px;}
.nav a,.nav button{flex:1;text-align:center;font-size:13px;font-weight:600;
 color:#475569;padding:9px 6px;border-radius:8px;border:0;background:transparent;
 font-family:inherit;cursor:pointer;}
.nav a:hover,.nav button:hover{background:#fff;opacity:1;}
.nav button.on{background:#0f1b2d;color:#fff;}
.nav button.on:hover{background:#0f1b2d;}
.panel{display:none;}
.panel.on{display:block;}
.part{padding:22px 40px;scroll-margin-top:70px;}
.part-head{display:flex;align-items:center;gap:11px;margin-bottom:14px;}
.part-icon{width:32px;height:32px;border-radius:9px;background:#eaf0fb;
 display:flex;align-items:center;justify-content:center;font-size:15px;}
.part-head h2{font-size:18px;font-weight:700;color:#0f1b2d;margin:0;}
.summary{background:#eaf0fb;border-radius:12px;padding:14px 16px;margin-bottom:14px;}
.summary-label{font-size:11px;font-weight:700;color:#3a6fd8;letter-spacing:.05em;
 margin-bottom:5px;}
.summary p{font-size:14px;line-height:1.65;color:#1e293b;margin:0;}
.news-list{display:flex;flex-direction:column;gap:10px;}
.news{display:block;background:#fff;border:1px solid #e6ebf2;border-radius:12px;
 padding:15px 16px;color:inherit;}
.news-meta{display:flex;gap:8px;align-items:center;margin-bottom:9px;}
.tag{font-size:11px;font-weight:700;color:#3a6fd8;background:#eaf0fb;
 padding:3px 9px;border-radius:6px;}
.ticker{font-family:ui-monospace,monospace;font-size:11px;font-weight:700;
 color:#fff;background:#0f1b2d;padding:3px 8px;border-radius:6px;}
.src{margin-left:auto;font-size:11px;color:#94a3b8;}
.news h3{font-size:15.5px;font-weight:600;color:#0f1b2d;line-height:1.45;
 margin:0 0 6px;}
.news p{font-size:13.5px;line-height:1.6;color:#475569;margin:0;}
.outlook{margin-top:14px;}
.outlook-label{font-size:12px;font-weight:700;color:#64748b;margin-bottom:8px;}
.outlook-list{display:flex;flex-direction:column;gap:8px;}
.outlook-item{display:flex;gap:10px;align-items:flex-start;background:#fff;
 border:1px solid #e6ebf2;border-radius:10px;padding:11px 14px;}
.outlook-item .arrow{color:#3a6fd8;font-weight:700;line-height:1.4;}
.outlook-item span:last-child{font-size:13.5px;line-height:1.55;color:#334155;}
.ft{padding:20px 40px 34px;font-size:11px;line-height:1.7;color:#94a3b8;}

/* 지난 브리핑 캘린더 */
.calwrap{padding:22px 40px 6px;}
.cal{background:#fff;border:1px solid #e6ebf2;border-radius:14px;
 padding:16px 14px;margin-bottom:14px;}
.cal h3{margin:0 0 12px;font-size:15px;font-weight:700;color:#0f1b2d;}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;}
.dow{text-align:center;font-size:11px;color:#94a3b8;padding:4px 0;}
.dow.sun{color:#c0392b;}
.day{aspect-ratio:1;border:0;background:transparent;border-radius:9px;font:inherit;
 font-size:13px;color:#cbd5e1;display:flex;align-items:center;
 justify-content:center;padding:0;}
.day.has{background:#eaf0fb;color:#3a6fd8;font-weight:700;cursor:pointer;}
.day.has:hover{background:#dbe6f8;}
.day.on{background:#0f1b2d;color:#fff;}
.det{background:#fff;border:1px solid #e6ebf2;border-radius:14px;padding:16px 18px;}
.det .t{font-weight:700;margin-bottom:10px;font-size:15px;color:#0f1b2d;}
.det a{display:inline-block;padding:10px 16px;margin:0 8px 8px 0;border-radius:9px;
 background:#eaf0fb;color:#3a6fd8;font-weight:600;font-size:13px;}
.det a:hover{opacity:1;background:#dbe6f8;}
.det .none{color:#94a3b8;font-size:13px;}
@media (max-width:600px){
  .wrap{padding:0;}
  .page{border-radius:0;border-left:0;border-right:0;}
  .hd,.gauges,.navwrap,.part,.ft,.calwrap{padding-left:18px;padding-right:18px;}
  .hd h1{font-size:22px;}
  .nav a{font-size:12px;padding:8px 3px;}
}
"""


# =========================================================
# 본문 파싱
# =========================================================
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


def _parse_part(lines):
    """섹션 내용을 (요약문, [뉴스항목], [전망]) 으로 구조화."""
    summary, items, outlook = "", [], []
    mode, cur = "news", None
    for s in lines:
        m = _LABEL_RE.match(s)
        if m:
            lab = m.group(1)
            mode = ("sum" if "한눈에" in lab else
                    "out" if "흐름" in lab else "news")
            cur = None
            continue
        if mode == "sum":
            summary = (summary + " " + s).strip()
            continue
        if mode == "out":
            if s[0] in "•-":
                outlook.append(s[1:].strip())
            continue

        mt = _TICKER_RE.match(s)
        if mt:
            cur = {"kind": "ticker", "label": mt.group(1),
                   "title": mt.group(2), "desc": "", "src": ""}
            items.append(cur)
            continue
        mi = _ITEM_RE.match(s)
        if mi:
            cur = {"kind": "tag", "label": (mi.group(2) or "").strip(),
                   "title": mi.group(3), "desc": "", "src": ""}
            items.append(cur)
            continue
        if cur is not None:
            if s.startswith("→"):
                cur["desc"] = s.lstrip("→").strip()
            elif s.startswith("(") and s.endswith(")"):
                cur["src"] = s[1:-1].strip()
    return summary, items, outlook


def _fear_greed(sections):
    for title, lines in sections:
        if "공포탐욕" in title:
            found = []
            for ln in lines:
                m = _FG_RE.match(ln)
                if m:
                    found.append((m.group(1), m.group(2), m.group(3)))
            return found
    return []


def _mood_color(value):
    """0-24 / 25-44 / 45-55 / 56-75 / 76-100 구간 색상."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "#94a3b8"
    if v <= 24:
        return "#c0392b"
    if v <= 44:
        return "#d98324"
    if v <= 55:
        return "#c9a227"
    if v <= 75:
        return "#4a9d5b"
    return "#2e7d32"


# =========================================================
# 렌더링
# =========================================================
def _e(s):
    return _html.escape(s or "")


def _ticker_color(label):
    """티커 → 브랜드 컬러. 미등록 티커는 이름 해시로 고정 색을 배정."""
    key = (label or "").upper().split("-")[0].strip()
    if key in TICKER_COLORS:
        return TICKER_COLORS[key]
    h = sum(ord(c) * (i + 3) for i, c in enumerate(key)) % 360
    return f"hsl({h},58%,38%)"


def _text_on(bg):
    """배경 밝기에 따라 글자색을 고른다(WCAG 상대휘도 기준).

    단순 대비 비교를 쓰면 Tesla 레드·Ethereum 블루처럼 중간 톤에서 검정이
    간발의 차로 선택되는데, 실제 브랜드는 흰 글자를 쓴다. 밝은 배경
    (NVIDIA 그린·Bitcoin 오렌지 등)에서만 어두운 글자를 쓰도록 임계값을 둔다.
    """
    if not bg.startswith("#"):
        return "#fff"

    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16))
    lum = 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
    return "#0f1b2d" if lum > 0.35 else "#fff"


def _render_part(pid, icon, name, lines):
    summary, items, outlook = _parse_part(lines)
    h = [f'<section class="part" id="{pid}">',
         f'<div class="part-head"><span class="part-icon">{icon}</span>'
         f'<h2>{_e(name)}</h2></div>']
    if summary:
        h.append('<div class="summary"><div class="summary-label">오늘 한눈에</div>'
                 f'<p>{_e(summary)}</p></div>')
    if items:
        h.append('<div class="news-list">')
        for it in items:
            if not it["label"]:
                badge = ""
            elif it["kind"] == "ticker":
                bg = _ticker_color(it["label"])
                badge = (f'<span class="ticker" style="background:{bg};'
                         f'color:{_text_on(bg)};">{_e(it["label"])}</span>')
            else:
                badge = f'<span class="tag">{_e(it["label"])}</span>'
            src = f'<span class="src">{_e(it["src"])}</span>' if it["src"] else ""
            desc = f'<p>{_e(it["desc"])}</p>' if it["desc"] else ""
            h.append(f'<div class="news"><div class="news-meta">{badge}{src}</div>'
                     f'<h3>{_e(it["title"])}</h3>{desc}</div>')
        h.append("</div>")
    if outlook:
        h.append('<div class="outlook"><div class="outlook-label">흐름 · 전망</div>'
                 '<div class="outlook-list">')
        for o in outlook:
            h.append('<div class="outlook-item"><span class="arrow">›</span>'
                     f'<span>{_e(o)}</span></div>')
        h.append("</div></div>")
    h.append("</section>")
    return "".join(h)


def _shell(title, inner, extra_head="", script=""):
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
{HEAD}
<title>{_e(title)}</title>{extra_head}
<style>{CSS}</style>
</head>
<body>
<div class="wrap"><div class="page">
{inner}
<footer class="ft">기사 요약은 각 언론사 보도를 바탕으로 자동 생성되었으며, 저작권은 해당 언론사에 있습니다. 정보 제공 목적이며 투자 판단의 책임은 본인에게 있습니다.</footer>
</div></div>{script}
</body>
</html>
"""


_TAB_JS = """<script>
document.querySelectorAll('.nav-t').forEach(function(b){
  b.addEventListener('click', function(){
    document.querySelectorAll('.nav-t').forEach(function(x){x.classList.remove('on');});
    document.querySelectorAll('.panel').forEach(function(x){x.classList.remove('on');});
    b.classList.add('on');
    document.getElementById(b.getAttribute('data-p')).classList.add('on');
  });
});
</script>"""


def _title(now):
    ampm = "오전" if now.hour < 12 else "오후"
    return f"{now.year % 100}년 {now.month}월 {now.day}일 {ampm} 뉴스 브리핑"


def render_html(body, now=None, links=""):
    now = now or datetime.now(KST)
    sections = _split_sections(body)
    ampm = "오전" if now.hour < 12 else "오후"

    # 헤더 (요일은 뱃지, 토/일은 색 구분)
    kicker = now.strftime("%Y.%m.%d") + f" · {ampm} 브리핑"
    dcls = {5: " sat", 6: " sun"}.get(now.weekday(), "")
    dowb = f'<span class="dowb{dcls}">{_DOW[now.weekday()]}</span>'
    sub = f"최종 업데이트 {now.strftime('%H:%M')} KST"
    hd = (f'<header class="hd"><div class="hd-top">'
          f'<span class="hd-kicker">{_e(kicker)}</span>'
          f'<div class="hd-links">{links}</div></div>'
          f'<h1>{ampm} 뉴스 브리핑</h1>'
          f'<div class="hd-sub">{dowb}{_e(sub)}</div></header>')

    # 공포탐욕 게이지
    gauges = []
    for name, val, grade in _fear_greed(sections)[:2]:
        color = _mood_color(val)
        gauges.append(
            f'<div class="gauge"><div class="gauge-label">{_e(name)}</div>'
            f'<div class="gauge-row"><span class="gauge-num">{_e(val)}</span>'
            f'<span class="gauge-mood" style="background:{color};">{_e(grade)}</span></div>'
            f'<div class="gauge-track"><div class="gauge-marker" style="left:{val}%;"></div></div>'
            '<div class="gauge-scale"><span>공포</span><span>탐욕</span></div></div>')
    gauges_html = f'<div class="gauges">{"".join(gauges)}</div>' if gauges else ""

    # 파트 렌더 (본문에 있는 것만)
    rendered = {}
    for pid, icon, name, key in PARTS:
        lines = next((ls for t, ls in sections if key in t), None)
        if lines is not None:
            rendered[pid] = _render_part(pid, icon, name, lines)

    # 탭 + 패널
    navs, panels, first = [], [], True
    for i, (tab, pids) in enumerate(TABS):
        inner = "".join(rendered[p] for p in pids if p in rendered)
        if not inner:
            continue
        on = " on" if first else ""
        navs.append(f'<button class="nav-t{on}" data-p="tp{i}">{_e(tab)}</button>')
        panels.append(f'<div class="panel{on}" id="tp{i}">{inner}</div>')
        first = False
    nav_html = (f'<div class="navwrap"><nav class="nav">{"".join(navs)}</nav></div>'
                if navs else "")

    return _shell(_title(now), hd + gauges_html + nav_html + "".join(panels),
                  script=_TAB_JS)


# =========================================================
# 지난 브리핑(캘린더)
# =========================================================
_CAL_JS = """<script>
var DATA = __DATA__;
function pick(btn){
  document.querySelectorAll('.day.on').forEach(function(x){x.classList.remove('on');});
  btn.classList.add('on');
  var d = btn.getAttribute('data-d'), v = DATA[d] || {}, p = d.split('-');
  var h = '<div class="t">' + p[0].slice(2) + '년 ' + (+p[1]) + '월 ' + (+p[2]) + '일</div>';
  if (v.am) { h += '<a href="' + v.am + '">오전 브리핑</a>'; }
  if (v.pm) { h += '<a href="' + v.pm + '">오후 브리핑</a>'; }
  if (!v.am && !v.pm) { h += '<span class="none">브리핑이 없습니다.</span>'; }
  document.getElementById('det').innerHTML = h;
}
document.querySelectorAll('.day.has').forEach(function(b){
  b.addEventListener('click', function(){ pick(b); });
});
var f = document.querySelector('.day.has');
if (f) { pick(f); }
</script>"""

_DOW_SHORT = ["일", "월", "화", "수", "목", "금", "토"]


def render_archive_index():
    days = {}
    try:
        names = os.listdir(ARCHIVE_DIR)
    except OSError:
        names = []
    for fn in names:
        if not fn.endswith(".html") or fn == "index.html":
            continue
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})-(am|pm)", fn[:-5])
        if not m:
            continue
        y, mo, d, ap = m.groups()
        days.setdefault(f"{y}-{mo}-{d}", {})[ap] = fn

    cal = calendar.Calendar(firstweekday=6)
    blocks = []
    for ym in sorted({k[:7] for k in days}, reverse=True):
        y, mo = int(ym[:4]), int(ym[5:7])
        cells = "".join(f'<div class="dow{" sun" if i == 0 else ""}">{w}</div>'
                        for i, w in enumerate(_DOW_SHORT))
        for dt in cal.itermonthdates(y, mo):
            if dt.month != mo:
                cells += '<div class="day"></div>'
            elif dt.strftime("%Y-%m-%d") in days:
                cells += (f'<button class="day has" '
                          f'data-d="{dt.strftime("%Y-%m-%d")}">{dt.day}</button>')
            else:
                cells += f'<div class="day">{dt.day}</div>'
        blocks.append(f'<div class="cal"><h3>{y}년 {mo}월</h3>'
                      f'<div class="grid">{cells}</div></div>')

    hd = ('<header class="hd"><div class="hd-top">'
          '<span class="hd-kicker">ARCHIVE</span>'
          '<div class="hd-links"><a class="hd-archive" href="../index.html">🏠 홈</a></div>'
          '</div><h1>지난 브리핑</h1>'
          f'<div class="hd-sub">총 {len(days)}일 · '
          f'{sum(len(v) for v in days.values())}회분</div></header>')
    inner = (hd + '<div class="calwrap">' + "".join(blocks)
             + '<div class="det" id="det"></div></div>')
    js = _CAL_JS.replace("__DATA__", json.dumps(days, ensure_ascii=False))
    return _shell("지난 브리핑", inner, script=js)


# =========================================================
# 발행 / 재렌더링
# =========================================================
def _slug(now):
    return now.strftime("%Y-%m-%d") + ("-am" if now.hour < 12 else "-pm")


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _save_body(body, now):
    os.makedirs(DATA_DIR, exist_ok=True)
    _write(os.path.join(DATA_DIR, _slug(now) + ".txt"),
           now.isoformat() + "\n\n" + body)


def _load_body(path):
    raw = open(path, encoding="utf-8").read()
    head, _, body = raw.partition("\n\n")
    try:
        now = datetime.fromisoformat(head.strip())
    except ValueError:
        now = None
    return now, body


_LINKS_HOME = '<a class="hd-archive" href="archive/index.html">지난 브리핑</a>'
_LINKS_SNAP = ('<a class="hd-archive" href="../index.html">🏠 홈</a>'
               '<a class="hd-archive" href="index.html">지난 브리핑</a>')


def rebuild_all():
    """저장된 원문으로 모든 페이지를 다시 렌더링(뉴스 수집·LLM 호출 없음)."""
    if not os.path.isdir(DATA_DIR):
        return 0
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".txt"))
    latest = None
    for fn in files:
        now, body = _load_body(os.path.join(DATA_DIR, fn))
        if now is None or not body.strip():
            continue
        _write(os.path.join(ARCHIVE_DIR, fn[:-4] + ".html"),
               render_html(body, now=now, links=_LINKS_SNAP))
        latest = (body, now)
    if latest:
        _write(os.path.join(DOCS_DIR, "index.html"),
               render_html(latest[0], now=latest[1], links=_LINKS_HOME))
    _write(os.path.join(ARCHIVE_DIR, "index.html"), render_archive_index())
    return len(files)


def publish(body, now=None):
    """최신 페이지 + 회차 스냅샷 + 캘린더 생성. 최신 경로 반환."""
    now = now or datetime.now(KST)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    _save_body(body, now)
    _write(os.path.join(ARCHIVE_DIR, _slug(now) + ".html"),
           render_html(body, now=now, links=_LINKS_SNAP))
    path = os.path.join(DOCS_DIR, "index.html")
    _write(path, render_html(body, now=now, links=_LINKS_HOME))
    _write(os.path.join(ARCHIVE_DIR, "index.html"), render_archive_index())
    return path


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
