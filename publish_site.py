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
import json
import calendar
import html as _html
from datetime import datetime

import pytz

KST = pytz.timezone("Asia/Seoul")
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(HERE, "docs")
ARCHIVE_DIR = os.path.join(DOCS_DIR, "archive")
# 브리핑 원문 텍스트 보관소. 디자인만 바꿀 때 뉴스 재수집·재요약 없이
# 여기서 읽어 페이지만 다시 만든다(rebuild_all).
DATA_DIR = os.path.join(HERE, "data")

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
.dowb{display:inline-block;font-size:.72rem;font-weight:700;color:#6b7280;
 background:#eef0f3;border-radius:6px;padding:2px 8px;vertical-align:4px;
 margin-left:3px}
.dowb.sat{color:#2563eb;background:#e8f0ff}
.dowb.sun{color:#d2453c;background:#fdeceb}
.upd{color:#8b9099;font-size:.8rem;margin-top:5px}

.bar{background:#f5f6f8;padding:8px 0 0;margin:0 -14px;
 border-bottom:1px solid #e3e5e9}
.bar .inner{max-width:780px;margin:0 auto;padding:0 14px}
.fg{margin-bottom:10px}
.chip{display:flex;align-items:baseline;gap:8px;padding:2px 2px}
.chip .k{font-size:.78rem;color:#8b9099;white-space:nowrap;min-width:66px}
.chip .v{font-size:1.06rem;font-weight:700}
.chip .s{font-size:.76rem;color:#8b9099;overflow:hidden;text-overflow:ellipsis;
 white-space:nowrap}
/* 공포탐욕지수 5단계 색상 */
.ef  .v{color:#c0392b}  /* 극단적 공포 */
.fe  .v{color:#e07b39}  /* 공포 */
.neu .v{color:#7a8089}  /* 중립 */
.gr  .v{color:#3f9c56}  /* 탐욕 */
.eg  .v{color:#1e7a3c}  /* 극단적 탐욕 */

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
.nav{margin-top:10px}
.nav a{display:inline-block;padding:7px 13px;margin-right:6px;background:#fff;
 border:1px solid #e3e5e9;border-radius:8px;color:#1c1e21;text-decoration:none;
 font-size:.82rem;font-weight:600}
.nav a:hover{background:#f0f1f3}

/* 지난 브리핑 캘린더 */
.cal{background:#fff;border:1px solid #e3e5e9;border-radius:12px;
 padding:14px 12px;margin:14px 0}
.cal h3{margin:0 0 10px;font-size:.96rem;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}
.dow{text-align:center;font-size:.72rem;color:#9aa0a8;padding:3px 0}
.dow.sun{color:#d2453c}
.day{aspect-ratio:1;border:0;background:transparent;border-radius:8px;font:inherit;
 font-size:.86rem;color:#c8ccd2;display:flex;align-items:center;
 justify-content:center;padding:0}
.day.has{background:#eef4ff;color:#1668dc;font-weight:700;cursor:pointer}
.day.has:hover{background:#dbe8ff}
.day.on{background:#1668dc;color:#fff}
.det{background:#fff;border:1px solid #e3e5e9;border-radius:12px;
 padding:14px 16px;margin:14px 0}
.det .t{font-weight:700;margin-bottom:9px;font-size:.94rem}
.det a{display:inline-block;padding:9px 15px;margin:0 7px 7px 0;border-radius:8px;
 background:#f0f4fb;color:#1668dc;text-decoration:none;font-weight:600;
 font-size:.86rem}
.det a:hover{background:#dbe8ff}
.det .none{color:#9aa0a8;font-size:.85rem}
.empty{color:#8b9099;padding:18px 16px}
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


def _fg_class(value):
    """공포탐욕지수 5단계 (CNN 기준 구간)로 색상 클래스를 정한다.
    0-25 극단적 공포 / 26-45 공포 / 46-55 중립 / 56-75 탐욕 / 76-100 극단적 탐욕
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "neu"
    if v <= 25:
        return "ef"
    if v <= 45:
        return "fe"
    if v <= 55:
        return "neu"
    if v <= 75:
        return "gr"
    return "eg"


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


def _dow_badge(now):
    """제목 옆에 붙는 요일 뱃지 (토=파랑, 일=빨강)."""
    names = ["월", "화", "수", "목", "금", "토", "일"]
    i = now.weekday()
    cls = {5: " sat", 6: " sun"}.get(i, "")
    return f'<span class="dowb{cls}">{names[i]}</span>'


def _slug(now):
    """아카이브 파일명 (예: 2026-07-23-am)."""
    return now.strftime("%Y-%m-%d") + ("-am" if now.hour < 12 else "-pm")


def _label_from_slug(slug):
    """2026-07-23-am → ('26년 7월 23일', '오전') / 형식이 아니면 None."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})-(am|pm)", slug)
    if not m:
        return None
    y, mo, d, ap = m.groups()
    return (f"{int(y) % 100}년 {int(mo)}월 {int(d)}일",
            "오전" if ap == "am" else "오후")


_CAL_JS = """
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
var last = document.querySelector('.day.has');
if (last) { pick(last); }
"""

_DOW = ["일", "월", "화", "수", "목", "금", "토"]


def render_archive_index():
    """docs/archive 를 스캔해 캘린더 형식의 지난 브리핑 페이지를 만든다."""
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

    months = sorted({k[:7] for k in days}, reverse=True)
    cals = []
    cal = calendar.Calendar(firstweekday=6)          # 일요일 시작
    for ym in months:
        y, mo = int(ym[:4]), int(ym[5:7])
        cells = "".join(
            f'<div class="dow{" sun" if i == 0 else ""}">{w}</div>'
            for i, w in enumerate(_DOW))
        for dt in cal.itermonthdates(y, mo):
            if dt.month != mo:
                cells += '<div class="day"></div>'
                continue
            key = dt.strftime("%Y-%m-%d")
            if key in days:
                cells += (f'<button class="day has" data-d="{key}">'
                          f'{dt.day}</button>')
            else:
                cells += f'<div class="day">{dt.day}</div>'
        cals.append(f'<div class="cal"><h3>{y}년 {mo}월</h3>'
                    f'<div class="grid">{cells}</div></div>')

    body = ("".join(cals) if cals
            else '<div class="cal"><div class="empty">저장된 브리핑이 없습니다.</div></div>')
    js = _CAL_JS.replace("__DATA__", json.dumps(days, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="color-scheme" content="light">
<title>지난 브리핑</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>지난 브리핑</h1>
  <div class="upd">총 {len(days)}일 · {sum(len(v) for v in days.values())}회분</div>
  <div class="nav"><a href="../index.html">🏠 홈</a></div>
</header>
{body}
<div class="det" id="det"></div>
</div>
<script>{js}</script>
</body>
</html>
"""


def render_html(body, now=None, nav=""):
    now = now or datetime.now(KST)
    sections = _split_sections(body)
    fg = _fear_greed(sections)

    chips = []
    for name, val, grade in fg[:2]:
        chips.append(
            f'<div class="chip {_fg_class(val)}">'
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
  <h1>{_html.escape(_title(now))} {_dow_badge(now)}</h1>
  <div class="upd">최종 업데이트 · {_html.escape(stamp)}</div>
  {nav}
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


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _save_body(body, now):
    """원문 텍스트를 data/<slug>.txt 로 보관. 첫 줄에 실행 시각을 적어둔다."""
    os.makedirs(DATA_DIR, exist_ok=True)
    _write(os.path.join(DATA_DIR, _slug(now) + ".txt"),
           now.isoformat() + "\n\n" + body)


def _load_body(path):
    """저장본을 (실행시각, 본문) 으로 되돌린다."""
    raw = open(path, encoding="utf-8").read()
    head, _, body = raw.partition("\n\n")
    try:
        now = datetime.fromisoformat(head.strip())
    except ValueError:
        now = None
    return now, body


def _render_pair(body, now):
    """한 회차의 스냅샷 HTML 을 만든다."""
    return render_html(
        body, now=now,
        nav='<div class="nav"><a href="../index.html">🏠 홈</a>'
            '<a href="index.html">📅 지난 브리핑</a></div>')


def rebuild_all():
    """저장된 원문으로 모든 페이지를 다시 렌더링(뉴스 수집·LLM 호출 없음).

    디자인을 바꾼 뒤 실행하면 과거 회차 페이지까지 새 디자인으로 갱신된다.
    """
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
               _render_pair(body, now))
        latest = (body, now)
    if latest:
        _write(os.path.join(DOCS_DIR, "index.html"),
               render_html(latest[0], now=latest[1],
                           nav='<div class="nav">'
                               '<a href="archive/index.html">📅 지난 브리핑</a></div>'))
    _write(os.path.join(ARCHIVE_DIR, "index.html"), render_archive_index())
    return len(files)


def publish(body, now=None):
    """최신 페이지 + 회차 스냅샷 + 지난 브리핑 목록을 생성. 최신 경로 반환.

    docs/index.html                  최신 브리핑
    docs/archive/YYYY-MM-DD-am.html  회차별 스냅샷
    docs/archive/index.html          날짜 목록(매 실행 재생성)
    """
    now = now or datetime.now(KST)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    # 0) 원문 텍스트 보관 (이후 디자인 변경 시 재수집 없이 재렌더링용)
    _save_body(body, now)

    # 1) 회차 스냅샷 (목록/최신으로 돌아가는 링크 포함)
    _write(os.path.join(ARCHIVE_DIR, _slug(now) + ".html"),
           _render_pair(body, now))

    # 2) 최신 페이지
    path = os.path.join(DOCS_DIR, "index.html")
    _write(path, render_html(body, now=now,
                             nav='<div class="nav">'
                                 '<a href="archive/index.html">📅 지난 브리핑</a></div>'))

    # 3) 날짜 목록 (폴더를 스캔하므로 항상 최신 상태)
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
