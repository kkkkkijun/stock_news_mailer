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
from datetime import datetime, date

import pytz

KST = pytz.timezone("Asia/Seoul")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "docs")
ARCHIVE_DIR = os.path.join(DOCS_DIR, "archive")
# 원문 텍스트 보관소. 디자인만 바꿀 때 뉴스 재수집 없이 재렌더링(rebuild_all).
DATA_DIR = os.path.join(HERE, "data")

_SECTION_RE = re.compile(r"^(📈|🪙|📊|💹|🌐|🏘️|💬)\s*(.+)$")
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
    ("trump", "💬", "트럼프", "트럼프 PART"),
]

# 핵심(히어로) 강조를 적용할 섹션 = LLM 중요도 랭킹이 있는 섹션만.
# 주식(os)·코인(coin)은 '관련성+최신' 정렬이라 1번=최중요가 아니므로 제외.
HERO_PARTS = {"eco", "cm", "re", "trump"}

# 탭 구성: (탭 이름, 포함할 파트 id)
TABS = [
    ("뉴스", ["eco", "cm"]),
    ("주식", ["os", "coin"]),
    ("부동산", ["re"]),
    ("트럼프", ["trump"]),
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
<meta name="color-scheme" content="light dark">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<script>(function(){try{var t=localStorage.getItem('theme');if(t!=='dark'&&t!=='light'){t=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"""

CSS = """
:root{
 --bg:#e8ecf1;--page:#f6f8fb;--border:#e6ebf2;
 --ink:#0f1b2d;--ink-2:#1e293b;--muted:#475569;--muted-2:#64748b;--faint:#94a3b8;
 --card:#fff;--chip:#eaf0fb;--accent:#3a6fd8;--header:#0f1b2d;--nav-track:#eef2f7;
 --hover:#dbe6f8;--chip-ink:#3a6fd8;--shadow:rgba(15,27,45,.10);}
:root[data-theme="dark"]{
 --bg:#0b0e13;--page:#12161d;--border:#262c36;
 --ink:#e7ecf3;--ink-2:#d6dde8;--muted:#aab6c6;--muted-2:#9aa7b8;--faint:#8b96a6;
 --card:#1a1f28;--chip:#1c2735;--accent:#6f9bef;--header:#0c1017;--nav-track:#161c25;
 --hover:#243244;--chip-ink:#8fb4f5;--shadow:rgba(0,0,0,.5);}
*{box-sizing:border-box;}
body{margin:0;font-family:'Pretendard',system-ui,sans-serif;
 -webkit-font-smoothing:antialiased;background:var(--bg);color:var(--ink);
 transition:background .2s,color .2s;}
a{color:var(--accent);text-decoration:none;}
a:hover{opacity:.72;}
.wrap{display:flex;justify-content:center;padding:48px 24px;}
.page{width:100%;max-width:820px;background:var(--page);color:var(--ink);
 border:1px solid var(--border);border-radius:18px;
 box-shadow:0 12px 44px var(--shadow);overflow:hidden;}
.hd{padding:30px 40px;background:var(--header);color:#fff;}
.hd-top{display:flex;justify-content:space-between;align-items:center;gap:10px;}
.hd-kicker{font-size:12px;font-weight:600;letter-spacing:.04em;color:#94a3b8;}
.hd-links{display:flex;gap:7px;flex-shrink:0;}
.hd-archive{font-size:12px;font-weight:600;color:#dbe4f0;
 background:rgba(255,255,255,.12);padding:6px 13px;border-radius:999px;}
.hd-archive:hover{opacity:1;background:rgba(255,255,255,.2);}
.hd h1{font-size:27px;font-weight:700;margin:16px 0 5px;letter-spacing:-.01em;}
.hd-sub{display:flex;justify-content:space-between;align-items:center;gap:10px;
 font-size:13px;color:#94a3b8;}
.hd-slogan{display:flex;flex-direction:column;align-items:flex-end;gap:3px;
 font-size:15.5px;font-weight:700;color:#f5c451;white-space:nowrap;
 flex-shrink:0;letter-spacing:.01em;text-align:right;}
.hd-bar{width:168px;max-width:44vw;height:7px;border-radius:4px;
 background:rgba(255,255,255,.14);overflow:hidden;margin-top:3px;}
.hd-bar>i{display:block;height:100%;border-radius:4px;background:#5c9dff;}
.hd-pct{font-size:13px;font-weight:600;color:#86b7ff;}
.hd-target{font-size:11px;font-weight:500;color:#7c8aa0;margin-top:3px;}
.dowb{display:inline-block;font-size:11px;font-weight:700;color:#dbe4f0;
 background:rgba(255,255,255,.14);padding:3px 10px;border-radius:999px;
 margin-right:8px;}
.dowb.sat{color:#a8c8ff;background:rgba(120,165,255,.2);}
.dowb.sun{color:#ffb0a8;background:rgba(255,130,120,.2);}
.gauges{display:flex;gap:16px;padding:16px 40px 4px;flex-wrap:wrap;}
.gauge{flex:1;min-width:220px;background:var(--card);border:1px solid var(--border);
 border-radius:14px;padding:10px 20px 11px;}
.gauge-label{font-size:11px;color:var(--muted-2);margin-bottom:4px;}
.gauge-row{display:flex;align-items:baseline;gap:9px;margin-bottom:7px;}
.gauge-num{font-size:23px;font-weight:700;line-height:1;color:var(--ink);}
.gauge-mood{font-size:11px;font-weight:600;color:#fff;padding:2px 9px;
 border-radius:999px;}
.gauge-track{position:relative;height:5px;border-radius:3px;
 background:linear-gradient(90deg,#c0392b,#d98324,#c9a227,#4a9d5b,#2e7d32);}
.gauge-marker{position:absolute;top:50%;width:11px;height:11px;border-radius:50%;
 background:#fff;border:2.5px solid var(--ink);transform:translate(-50%,-50%);}
.gauge-scale{display:flex;justify-content:space-between;font-size:10px;
 color:var(--faint);margin-top:4px;}
.navwrap{padding:14px 40px 6px;position:sticky;top:0;background:var(--page);z-index:3;}
.nav{display:flex;gap:5px;background:var(--nav-track);border:1px solid var(--border);
 border-radius:12px;padding:5px;}
.nav a,.nav button{flex:1;text-align:center;font-size:13px;font-weight:600;
 color:var(--muted);padding:9px 6px;border-radius:8px;border:0;background:transparent;
 font-family:inherit;cursor:pointer;}
.nav a:hover,.nav button:hover{background:var(--card);opacity:1;}
.nav button.on{background:var(--ink);color:var(--page);}
.nav button.on:hover{background:var(--ink);}
.panel{display:none;}
.panel.on{display:block;}
.part{padding:22px 40px;scroll-margin-top:70px;}
.part-head{display:flex;align-items:center;gap:11px;margin-bottom:14px;}
.part-icon{width:32px;height:32px;border-radius:9px;background:var(--chip);
 display:flex;align-items:center;justify-content:center;font-size:15px;}
.part-head h2{font-size:18px;font-weight:700;color:var(--ink);margin:0;}
.summary{background:var(--chip);border-radius:12px;padding:14px 16px;margin-bottom:14px;}
.summary-label{font-size:11px;font-weight:700;color:var(--chip-ink);letter-spacing:.05em;
 margin-bottom:5px;}
.summary p{font-size:14px;line-height:1.65;color:var(--ink-2);margin:0;}
.news-list{display:flex;flex-direction:column;gap:10px;}
.news{display:block;background:var(--card);border:1px solid var(--border);border-radius:12px;
 padding:15px 16px;color:inherit;}
.news-meta{display:flex;gap:8px;align-items:center;margin-bottom:9px;}
.tag{font-size:11px;font-weight:700;color:var(--chip-ink);background:var(--chip);
 padding:3px 9px;border-radius:6px;}
.ticker{font-family:ui-monospace,monospace;font-size:11px;font-weight:700;
 color:#fff;background:var(--ink);padding:3px 8px;border-radius:6px;}
.src{margin-left:auto;font-size:11px;color:var(--faint);}
.news h3{font-size:15.5px;font-weight:600;color:var(--ink);line-height:1.45;
 margin:0 0 6px;}
.news p{font-size:13.5px;line-height:1.6;color:var(--muted);margin:0;}
.news.hero{border-left:4px solid var(--accent);box-shadow:0 4px 14px var(--shadow);}
.news.hero h3{font-size:16.5px;font-weight:700;}
.badge-key{font-size:10px;font-weight:800;color:#fff;background:var(--accent);
 padding:3px 8px;border-radius:5px;letter-spacing:.03em;}
.quotes{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
 gap:8px;margin-bottom:14px;}
.qcard{background:var(--card);border:1px solid var(--border);border-radius:12px;
 padding:11px 13px;}
.qtop{display:flex;align-items:center;gap:6px;margin-bottom:8px;}
.qtop .spark{margin-left:auto;display:block;}
.qprice{font-size:16px;font-weight:700;color:var(--ink);letter-spacing:-.01em;}
.qchg{font-size:12.5px;font-weight:700;margin-top:2px;}
.outlook{margin-top:14px;}
.outlook-label{font-size:12px;font-weight:700;color:var(--muted-2);margin-bottom:8px;}
.outlook-list{display:flex;flex-direction:column;gap:8px;}
.outlook-item{display:flex;gap:10px;align-items:flex-start;background:var(--card);
 border:1px solid var(--border);border-radius:10px;padding:11px 14px;}
.outlook-item .arrow{color:var(--accent);font-weight:700;line-height:1.4;}
.outlook-item span:last-child{font-size:13.5px;line-height:1.55;color:var(--ink-2);}
.note{margin-top:12px;font-size:12px;line-height:1.6;color:var(--faint);}
.ft{padding:20px 40px 34px;font-size:11px;line-height:1.7;color:var(--faint);}

/* 플로팅 버튼: 맨 위로 / 테마 전환 */
#top,#theme{position:fixed;bottom:24px;z-index:20;width:46px;height:46px;
 border:1px solid var(--border);border-radius:50%;cursor:pointer;padding:0;
 font-size:20px;line-height:44px;text-align:center;
 box-shadow:0 6px 18px var(--shadow);
 transition:opacity .2s,visibility .2s,transform .15s;}
#top{right:24px;background:var(--ink);color:var(--page);border-color:transparent;
 opacity:0;visibility:hidden;}
#top.show{opacity:.94;visibility:visible;}
#top:hover{opacity:1;transform:translateY(-2px);}
#theme{left:24px;background:var(--card);color:var(--ink);}
#theme:hover{transform:translateY(-2px);}
@media (max-width:600px){#top,#theme{bottom:16px;width:42px;height:42px;
 line-height:40px;font-size:18px;}#top{right:16px;}#theme{left:16px;}}

/* 지난 브리핑 검색 + 캘린더 */
.search{margin-bottom:14px;}
.search input{width:100%;font:inherit;font-size:14px;padding:12px 15px;
 border-radius:12px;border:1px solid var(--border);background:var(--card);color:var(--ink);}
.search input::placeholder{color:var(--faint);}
.results{margin-bottom:14px;}
.ritem{display:block;background:var(--card);border:1px solid var(--border);
 border-radius:10px;padding:11px 14px;margin-bottom:8px;color:inherit;}
.ritem:hover{opacity:1;border-color:var(--accent);}
.ritem .rt{font-size:13.5px;font-weight:600;color:var(--ink);line-height:1.45;}
.ritem .rm{font-size:11px;color:var(--faint);margin-top:3px;}
.rnone{color:var(--faint);font-size:13px;padding:10px 2px;}
.calwrap{padding:22px 40px 6px;}
.cal{background:var(--card);border:1px solid var(--border);border-radius:14px;
 padding:16px 14px;margin-bottom:14px;}
.cal h3{margin:0 0 12px;font-size:15px;font-weight:700;color:var(--ink);}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;}
.dow{text-align:center;font-size:11px;color:var(--faint);padding:4px 0;}
.dow.sun{color:#e0685c;}
.day{aspect-ratio:1;border:0;background:transparent;border-radius:9px;font:inherit;
 font-size:13px;color:var(--faint);display:flex;align-items:center;
 justify-content:center;padding:0;}
.day.has{background:var(--chip);color:var(--chip-ink);font-weight:700;cursor:pointer;}
.day.has:hover{background:var(--hover);}
.day.on{background:var(--ink);color:var(--page);}
.det{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px 18px;}
.det .t{font-weight:700;margin-bottom:10px;font-size:15px;color:var(--ink);}
.det a{display:inline-block;padding:10px 16px;margin:0 8px 8px 0;border-radius:9px;
 background:var(--chip);color:var(--chip-ink);font-weight:600;font-size:13px;}
.det a:hover{opacity:1;background:var(--hover);}
.det .none{color:var(--faint);font-size:13px;}
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
    """섹션 내용을 (요약, [항목], [전망], 전망라벨, 노트) 로 구조화.

    - [오늘 한눈에] → 요약 문단
    - 숫자 항목(1. …) / 티커(📰 …) → 뉴스/발언 카드
    - '• …' 불릿 → 전망 리스트(라벨은 직전 [ ] 이름 유지)
    - '※ …' → 하단 노트
    """
    summary, items, blocks, note = "", [], [], ""
    curblock, cur, cur_label = None, None, ""
    mode = "items"
    for s in lines:
        m = _LABEL_RE.match(s)
        if m:
            cur_label = m.group(1)
            mode = "sum" if "한눈에" in cur_label else "items"
            cur = curblock = None
            continue
        if s.startswith("※"):
            note = (note + " " + s.lstrip("※").strip()).strip()
            continue
        if mode == "sum":
            summary = (summary + " " + s).strip()
            continue
        if s and s[0] in "•-":
            txt = s[1:].strip()
            if txt:                      # 빈 불릿은 무시
                if curblock is None:
                    curblock = (cur_label or "흐름·전망", [])
                    blocks.append(curblock)
                curblock[1].append(txt)
            cur = None
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
    return summary, items, blocks, note


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


def _spark_svg(vals, color, w=58, h=20, pad=2):
    """종가 시계열 → 미니 스파크라인 SVG(폴리라인)."""
    vals = [v for v in (vals or []) if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = pad + (w - 2 * pad) * i / (n - 1)
        y = pad + (h - 2 * pad) * (1 - (v - lo) / rng)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'aria-hidden="true"><polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round"/></svg>')


def _quote_card(q):
    """시세 dict → 카드 HTML. 한국식 색관례(상승 빨강 ▲ / 하락 파랑 ▼)."""
    sym = (q.get("ticker") or "").strip()
    disp = sym.split("-")[0] or sym
    chg = q.get("chg")
    if chg is None:
        color, chg_txt, sp_color = "var(--faint)", "—", "#9aa7b8"
    elif chg >= 0:
        color = sp_color = "#e5484d"
        chg_txt = f"▲ {chg:.2f}%"
    else:
        color = sp_color = "#3b82f6"
        chg_txt = f"▼ {abs(chg):.2f}%"
    bg = _ticker_color(sym)
    spark = _spark_svg(q.get("spark"), sp_color)
    price = q.get("price")
    price_txt = f"${price:,.2f}" if isinstance(price, (int, float)) else "—"
    return (f'<div class="qcard"><div class="qtop">'
            f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
            f'{_e(disp)}</span>{spark}</div>'
            f'<div class="qprice">{price_txt}</div>'
            f'<div class="qchg" style="color:{color};">{chg_txt}</div></div>')


def _render_quotes(cards):
    cards = [c for c in (cards or []) if c]
    if not cards:
        return ""
    return ('<div class="quotes">'
            + "".join(_quote_card(c) for c in cards) + "</div>")


def _render_part(pid, icon, name, lines, hero=False, quotes=None):
    summary, items, blocks, note = _parse_part(lines)
    h = [f'<section class="part" id="{pid}">',
         f'<div class="part-head"><span class="part-icon">{icon}</span>'
         f'<h2>{_e(name)}</h2></div>']
    quotes_html = _render_quotes(quotes)
    if quotes_html:
        h.append(quotes_html)
    if summary:
        h.append('<div class="summary"><div class="summary-label">오늘 한눈에</div>'
                 f'<p>{_e(summary)}</p></div>')
    if items:
        h.append('<div class="news-list">')
        for i, it in enumerate(items):
            is_hero = hero and i == 0          # 섹션의 1번 뉴스만 핵심 강조
            if not it["label"]:
                badge = ""
            elif it["kind"] == "ticker":
                bg = _ticker_color(it["label"])
                badge = (f'<span class="ticker" style="background:{bg};'
                         f'color:{_text_on(bg)};">{_e(it["label"])}</span>')
            else:
                badge = f'<span class="tag">{_e(it["label"])}</span>'
            key = '<span class="badge-key">핵심</span>' if is_hero else ""
            src = f'<span class="src">{_e(it["src"])}</span>' if it["src"] else ""
            desc = f'<p>{_e(it["desc"])}</p>' if it["desc"] else ""
            cls = "news hero" if is_hero else "news"
            h.append(f'<div class="{cls}"><div class="news-meta">{key}{badge}{src}</div>'
                     f'<h3>{_e(it["title"])}</h3>{desc}</div>')
        h.append("</div>")
    for label, bullets in blocks:
        if not bullets:
            continue
        h.append(f'<div class="outlook"><div class="outlook-label">{_e(label)}</div>'
                 '<div class="outlook-list">')
        for o in bullets:
            h.append('<div class="outlook-item"><span class="arrow">›</span>'
                     f'<span>{_e(o)}</span></div>')
        h.append("</div></div>")
    if note:
        h.append(f'<div class="note">{_e(note)}</div>')
    h.append("</section>")
    return "".join(h)


# 브라우저 탭에 표시되는 사이트 제목(고정)
SITE_TITLE = "브리핑노트 | 경제·주식·코인·부동산 핵심 뉴스"
# 헤더 우측 하단(최종 업데이트와 같은 줄)에 표시되는 슬로건 + 디데이
SLOGAN = "🎯 40살 140억"
DDAY_TARGET = date(2032, 12, 31)   # 93년생 만 40세 진입 직전
DDAY_START = date(2026, 7, 30)     # 진행 바 0% 기준(추적 시작일) → 목표일에 100%


def _dday_text(now):
    d = (DDAY_TARGET - now.date()).days
    if d > 0:
        return f"🗓️ D-{d:,}"
    if d == 0:
        return "🗓️ D-DAY"
    return "🗓️ 달성"


def _dday_progress(now):
    """DDAY_START → DDAY_TARGET 경과율(%). 하루 지날수록 바가 찬다."""
    total = (DDAY_TARGET - DDAY_START).days
    if total <= 0:
        return 100.0
    done = (now.date() - DDAY_START).days
    return max(0.0, min(100.0, done / total * 100))

# 맨 위로 가기 버튼 동작 (스크롤 200px 이상이면 노출)
_TOP_JS = """<script>
(function(){
  var t=document.getElementById('top');
  if(!t)return;
  function s(){ t.classList.toggle('show', window.pageYOffset>200); }
  window.addEventListener('scroll',s,{passive:true}); s();
  t.addEventListener('click',function(){ window.scrollTo({top:0,behavior:'smooth'}); });
})();
</script>"""


_THEME_JS = """<script>
(function(){
  var b=document.getElementById('theme'); if(!b)return;
  function ic(){ b.textContent =
    document.documentElement.getAttribute('data-theme')==='dark' ? '☀️' : '🌙'; }
  ic();
  b.addEventListener('click', function(){
    var n = document.documentElement.getAttribute('data-theme')==='dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', n);
    try{ localStorage.setItem('theme', n); }catch(e){}
    ic();
  });
})();
</script>"""


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
</div></div>
<button id="theme" aria-label="다크/라이트 테마 전환" title="테마 전환">🌙</button>
<button id="top" aria-label="맨 위로">↑</button>
{script}{_TOP_JS}{_THEME_JS}
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


def render_html(body, now=None, links="", quotes=None):
    now = now or datetime.now(KST)
    qmap = quotes or {}
    sections = _split_sections(body)
    ampm = "오전" if now.hour < 12 else "오후"

    # 헤더 (요일은 뱃지, 토/일은 색 구분)
    kicker = now.strftime("%Y.%m.%d") + f" · {ampm} 브리핑"
    dcls = {5: " sat", 6: " sun"}.get(now.weekday(), "")
    dowb = f'<span class="dowb{dcls}">{_DOW[now.weekday()]}</span>'
    sub = f"최종 업데이트 {now.strftime('%H:%M')}"
    pct = _dday_progress(now)
    hd = (f'<header class="hd"><div class="hd-top">'
          f'<span class="hd-kicker">{_e(kicker)}</span>'
          f'<div class="hd-links">{links}</div></div>'
          f'<h1>{ampm} 뉴스 브리핑</h1>'
          f'<div class="hd-sub"><span>{dowb}{_e(sub)}</span>'
          f'<span class="hd-slogan">{_e(SLOGAN)}'
          f'<span class="hd-pct">{_e(_dday_text(now))} · {pct:.2f}%</span>'
          f'<span class="hd-bar"><i style="width:{pct:.3f}%"></i></span>'
          f'<span class="hd-target">목표일 {DDAY_TARGET:%Y.%m.%d}</span>'
          f'</span></div></header>')

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
            rendered[pid] = _render_part(pid, icon, name, lines,
                                         hero=(pid in HERO_PARTS),
                                         quotes=qmap.get(pid))

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

    return _shell(SITE_TITLE, hd + gauges_html + nav_html + "".join(panels),
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

_SEARCH_JS = """<script>
(function(){
  var SIDX = __SEARCH__;
  var q=document.getElementById('q'),
      rs=document.getElementById('results'),
      cv=document.getElementById('calview');
  if(!q) return;
  function esc(s){ return String(s).replace(/[&<>]/g,
    function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }
  function run(){
    var term=(q.value||'').trim().toLowerCase();
    if(!term){ rs.innerHTML=''; rs.style.display='none'; cv.style.display=''; return; }
    cv.style.display='none'; rs.style.display='';
    var out=[], n=0;
    for(var i=0;i<SIDX.length && n<80;i++){
      var b=SIDX[i];
      for(var j=0;j<b.items.length;j++){
        var it=b.items[j];
        if(it.t.toLowerCase().indexOf(term)>=0){
          var dd=b.d.slice(2).replace(/-/g,'.'), ap=(b.ap==='am'?'오전':'오후');
          out.push('<a class="ritem" href="'+b.link+'">'
            +'<div class="rt">['+esc(it.s)+'] '+esc(it.t)+'</div>'
            +'<div class="rm">'+dd+' '+ap+' 브리핑</div></a>');
          if(++n>=80) break;
        }
      }
    }
    rs.innerHTML = out.length ? out.join('')
      : '<div class="rnone">‘'+esc(q.value.trim())+'’ 와 일치하는 뉴스가 없습니다.</div>';
  }
  q.addEventListener('input', run);
})();
</script>"""


def _search_index():
    """저장된 원문에서 (날짜·회차·헤드라인·섹션) 검색 색인을 만든다."""
    idx = []
    try:
        files = sorted((f for f in os.listdir(DATA_DIR) if f.endswith(".txt")),
                       reverse=True)
    except OSError:
        return idx
    for fn in files:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})-(am|pm)", fn[:-4])
        if not m:
            continue
        y, mo, d, ap = m.groups()
        _now, body = _load_body(os.path.join(DATA_DIR, fn))
        if not body.strip():
            continue
        items = []
        for title, lines in _split_sections(body):
            name = next((nm for _p, _i, nm, key in PARTS if key in title), None)
            if not name:
                continue
            _s, its, _b, _n = _parse_part(lines)
            for it in its:
                if it["title"]:
                    items.append({"t": it["title"], "s": name})
        if items:
            idx.append({"d": f"{y}-{mo}-{d}", "ap": ap,
                        "link": fn[:-4] + ".html", "items": items})
    return idx


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
    search = ('<div class="search"><input id="q" type="search" autocomplete="off"'
              ' placeholder="지난 브리핑에서 검색 (종목·키워드)"></div>'
              '<div class="results" id="results" style="display:none"></div>')
    inner = (hd + '<div class="calwrap">' + search
             + '<div id="calview">' + "".join(blocks)
             + '<div class="det" id="det"></div></div></div>')
    js = _CAL_JS.replace("__DATA__", json.dumps(days, ensure_ascii=False))
    js += _SEARCH_JS.replace(
        "__SEARCH__", json.dumps(_search_index(), ensure_ascii=False))
    return _shell(SITE_TITLE, inner, script=js)


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


def _save_quotes(quotes, now):
    """시세 데이터를 회차별 동반 JSON으로 저장(있을 때만). rebuild 시 재사용."""
    if not quotes:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, _slug(now) + ".quotes.json"),
              "w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False)


def _load_quotes(slug):
    path = os.path.join(DATA_DIR, slug + ".quotes.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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
        quotes = _load_quotes(fn[:-4])
        _write(os.path.join(ARCHIVE_DIR, fn[:-4] + ".html"),
               render_html(body, now=now, links=_LINKS_SNAP, quotes=quotes))
        latest = (body, now, quotes)
    if latest:
        _write(os.path.join(DOCS_DIR, "index.html"),
               render_html(latest[0], now=latest[1], links=_LINKS_HOME,
                           quotes=latest[2]))
    _write(os.path.join(ARCHIVE_DIR, "index.html"), render_archive_index())
    return len(files)


def publish(body, now=None, quotes=None):
    """최신 페이지 + 회차 스냅샷 + 캘린더 생성. 최신 경로 반환."""
    now = now or datetime.now(KST)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    _save_body(body, now)
    _save_quotes(quotes, now)
    _write(os.path.join(ARCHIVE_DIR, _slug(now) + ".html"),
           render_html(body, now=now, links=_LINKS_SNAP, quotes=quotes))
    path = os.path.join(DOCS_DIR, "index.html")
    _write(path, render_html(body, now=now, links=_LINKS_HOME, quotes=quotes))
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
