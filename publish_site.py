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
import csv
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
    "PLTR": "#101820",   # Palantir 블랙
    "IREN": "#12B886",   # IREN 그린
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
.sched-head{display:flex;flex-direction:column;gap:8px;margin-bottom:6px;}
.sched-head>span{font-size:14px;font-weight:800;color:var(--ink);
 display:flex;align-items:center;gap:5px;line-height:1.3;}
/* 이모지를 고정 크기 박스로 분리 → OS별 이모지 높이차가 텍스트 위치를 안 밀게 */
.sched-ico{flex-shrink:0;width:19px;height:19px;line-height:19px;text-align:center;
 font-size:15px;overflow:hidden;}
.sched-tz{font-size:10px;color:var(--faint);font-weight:600;}
.imp-filter{display:flex;gap:5px;}
/* 연/월 드롭다운 바 */
.econ-bar{display:flex;align-items:center;justify-content:space-between;
 gap:8px;flex-wrap:wrap;}
.econ-sel{display:flex;gap:6px;}
.econ-sel select{font:inherit;font-size:12.5px;font-weight:700;color:var(--ink);
 background:var(--chip);border:1px solid var(--border);border-radius:8px;
 padding:5px 9px;cursor:pointer;}
.sched-tz2{font-size:10px;color:var(--faint);font-weight:600;text-align:right;}
.imp-chip{display:flex;align-items:center;gap:5px;font:inherit;font-size:11px;
 font-weight:700;padding:4px 10px;border-radius:999px;border:1px solid var(--border);
 background:var(--card);color:var(--muted-2);cursor:pointer;opacity:.5;}
.imp-chip.on{opacity:1;color:var(--ink);}
.imp-chip i{width:8px;height:8px;border-radius:50%;display:block;flex-shrink:0;}
/* 중요도 토글: 컨테이너 클래스(s-high/s-med/s-low)로 행 표시 제어 */
.sched .ev{display:none;}
.sched.s-high .ev[data-imp="HIGH"]{display:flex;}
.sched.s-med .ev[data-imp="MEDIUM"]{display:flex;}
.sched.s-low .ev[data-imp="LOW"]{display:flex;}
.sched-day{font-size:11px;font-weight:800;color:var(--accent);margin:11px 2px 5px;}
.ev{display:flex;align-items:center;gap:7px;padding:7px 3px;
 border-bottom:1px solid var(--border);}
.ev:last-child{border-bottom:0;}
.ev-t{font-size:11.5px;font-weight:700;color:var(--ink);min-width:62px;flex-shrink:0;}
.ev-flag{width:22px;height:16px;border-radius:2px;object-fit:cover;flex-shrink:0;
 box-shadow:0 0 0 1px rgba(0,0,0,.10);background:var(--border);}
.ev-n{flex:1;font-size:12px;font-weight:600;color:var(--ink);line-height:1.35;}
.igauge{display:flex;gap:2px;flex-shrink:0;}
.igauge i{width:8px;height:6px;border-radius:2px;display:block;}
.sched-src{font-size:9.5px;color:var(--faint);text-align:right;margin-top:9px;}
/* 일정 2단: 좌 경제지표 / 우 기업실적 */
/* 일정: 전 기기 공통 서브탭 → 한 번에 한 컬럼(단일) */
.sched-col{min-width:0;width:100%;}
.sub-tabs{display:flex;gap:5px;background:var(--nav-track);border-radius:10px;
 padding:4px;margin-bottom:12px;}
.sub-tab{flex:1;text-align:center;font:inherit;font-size:12.5px;font-weight:700;
 color:var(--muted-2);background:transparent;border:0;border-radius:7px;
 padding:8px 4px;cursor:pointer;}
.sub-tab.on{background:#3a6fd8;color:#fff;}   /* 서브탭 활성=블루(상위 다크와 구분) */
/* 서브탭이 제목 역할 → 컬럼 헤더 중복 제거(경제=제목 숨김·칩 유지 / 기업=헤더 숨김) */
.sched-col.econ .sched-head>span{display:none;}
.sched-col.earn .sched-head{display:none;}
/* 선택한 서브탭 컬럼만 표시 */
.sched-2col[data-sub="econ"] .sched-col.earn{display:none;}
.sched-2col[data-sub="earn"] .sched-col.econ{display:none;}
.ern-item{border-bottom:1px solid var(--border);border-radius:10px;}
.ern-item:last-child{border-bottom:0;}
.ern-item.open{background:var(--chip);border-bottom-color:transparent;}
.ern{display:flex;align-items:center;gap:9px;padding:9px 6px;}
.ern-item:has(.ern-detail) .ern{cursor:pointer;}
.ern-arrow{color:var(--faint);font-size:10px;flex-shrink:0;transition:transform .15s;}
.ern-item.open .ern-arrow{transform:rotate(180deg);color:var(--accent);}
.ern-tag.rep{font-size:9.5px;font-weight:800;color:#fff;background:#16a34a;
 padding:2px 7px;border-radius:5px;flex-shrink:0;}
.ern-tag.wait{font-size:9.5px;font-weight:800;color:#fff;background:#f59e0b;
 padding:2px 7px;border-radius:5px;flex-shrink:0;margin-left:4px;}  /* 발표됐으나 집계 전 */
/* 기업실적 뷰 토글(예정 순 / 분기별) — 서브탭 pill과 구분되게 '밑줄 탭' */
.earn-views{display:flex;gap:20px;margin-bottom:12px;
 border-bottom:1px solid var(--border);}
.ev-view{font:inherit;font-size:12.5px;font-weight:700;color:var(--muted-2);
 background:none;border:0;border-bottom:2px solid transparent;
 padding:5px 2px 9px;margin-bottom:-1px;cursor:pointer;}
.ev-view.on{color:var(--ink);border-bottom-color:var(--ink);}
/* 분기별: 연도(다크 pill) → 분기(파란 pill) 2단 */
.q-years{display:flex;gap:6px;margin-bottom:9px;}
.q-year{font:inherit;font-size:12px;font-weight:800;color:var(--muted-2);
 background:var(--chip);border:1px solid var(--border);border-radius:8px;
 padding:6px 14px;cursor:pointer;}
.q-year.on{background:var(--ink);color:var(--page);border-color:var(--ink);}
.q-quarters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;}
.q-q{font:inherit;font-size:12px;font-weight:700;color:var(--muted-2);
 background:var(--card);border:1px solid var(--border);border-radius:999px;
 padding:5px 13px;cursor:pointer;}
.q-q.on{background:var(--accent);color:#fff;border-color:var(--accent);}
.q-row{display:flex;align-items:center;gap:9px;padding:9px 2px;
 border-bottom:1px solid var(--border);}
.q-row:last-child{border-bottom:0;}
.q-rmain{flex:1;min-width:0;display:flex;flex-direction:column;gap:2px;}
.q-rmain b{font-size:12.5px;font-weight:700;color:var(--ink);}
.q-sub{font-size:10.5px;color:var(--muted);}
.q-surp{font-size:12px;font-weight:800;flex-shrink:0;}
.q-surp.up{color:#e5484d;}.q-surp.dn{color:#3b82f6;}
.q-date{font-size:10.5px;font-weight:700;color:var(--accent);background:var(--chip);
 border-radius:999px;padding:3px 9px;flex-shrink:0;white-space:nowrap;}
/* 실적 보고서 카드 */
.rep-note{font-size:10.5px;color:var(--faint);margin-bottom:9px;}
.rep-item{background:var(--card);border:1px solid var(--border);border-radius:14px;
 margin-bottom:9px;box-shadow:0 1px 5px rgba(15,27,45,.05);overflow:hidden;}
.rep-head{display:flex;align-items:center;gap:8px;padding:11px 13px;cursor:pointer;}
.rep-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
 font-size:12.5px;color:var(--ink);font-weight:700;}
.rep-arrow{flex-shrink:0;color:var(--faint);font-size:11px;transition:transform .15s;}
.rep-item.open .rep-arrow{transform:rotate(180deg);color:var(--accent);}
.rep-body{display:none;padding:2px 13px 13px;}
.rep-item.open .rep-body{display:block;}
.rep-hd{font-size:12px;font-weight:800;color:var(--muted);word-break:keep-all;margin-bottom:9px;}
.up-note{font-size:10.5px;color:var(--faint);margin-bottom:8px;}
.rep-verdict{font-size:11px;font-weight:800;border-radius:7px;padding:3px 9px;
 background:var(--chip);color:var(--muted);}
.rep-verdict.beat{color:#e5484d;background:rgba(229,72,77,.12);}
.rep-verdict.miss{color:#3b82f6;background:rgba(59,130,246,.12);}
.rep-ms{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:11px;}
.rep-m{background:var(--nav-track);border-radius:9px;padding:8px 10px;}
.rep-mk{font-size:9.5px;color:var(--muted);}
.rep-mv{font-size:14px;font-weight:800;margin-top:1px;}
.rep-guide{display:flex;gap:7px;align-items:center;background:var(--nav-track);
 border:1px dashed var(--border);border-radius:9px;padding:8px 11px;
 font-size:11.5px;color:var(--muted);margin-bottom:11px;line-height:1.5;}
.rep-bs{background:var(--nav-track);border-radius:10px;padding:11px 13px;
 display:flex;flex-direction:column;gap:6px;}
.rep-b{display:flex;gap:7px;font-size:12px;color:var(--ink);line-height:1.6;}
.rep-b>span:first-child{color:var(--accent);flex-shrink:0;}
.rep-foot{display:flex;justify-content:space-between;align-items:center;margin-top:10px;}
.rep-foot a{font-size:10.5px;color:var(--accent);text-decoration:none;}
.rep-foot>span{font-size:10px;color:var(--faint);}
/* 예정 뷰(경량 리스트) */
.up-row{display:flex;align-items:center;gap:9px;padding:9px 2px;
 border-bottom:1px solid var(--border);}
.up-row:last-child{border-bottom:0;}
.up-dday{font-size:10px;font-weight:800;color:var(--accent);background:var(--chip);
 border:1px solid var(--border);border-radius:6px;padding:3px 6px;
 min-width:42px;text-align:center;flex-shrink:0;}
.up-main{flex:1;min-width:0;}
.up-t{display:flex;align-items:baseline;gap:7px;}
.up-t b{font-size:12.5px;font-weight:700;}
.up-date{font-size:10.5px;color:var(--muted);}
.up-sub{font-size:10.5px;color:var(--muted);margin-top:2px;line-height:1.45;}
.up-qh{font-size:12px;font-weight:800;color:var(--ink);margin:14px 0 7px;
 padding-bottom:5px;border-bottom:2px solid var(--border);}
.ev-new{font-size:8.5px;font-weight:800;color:#fff;background:#16a34a;
 border-radius:5px;padding:1px 5px;margin-left:5px;vertical-align:middle;}
.up-rec{font-size:10.5px;color:var(--muted);margin-top:3px;display:flex;
 align-items:center;gap:6px;flex-wrap:wrap;}
.up-cnt{color:var(--faint);}
.rec-bar{display:inline-flex;width:56px;height:6px;border-radius:3px;overflow:hidden;
 flex-shrink:0;border:1px solid var(--border);}
.rec-bar i{display:block;height:100%;}
.rec-ratio{font-size:10px;}
/* 실적 결과: 보고서 없는 종목 숫자줄 */
.res-row{display:flex;align-items:center;gap:9px;padding:9px 2px;
 border-bottom:1px solid var(--border);}
.res-row:last-child{border-bottom:0;}
.res-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px;}
.res-main b{font-size:12.5px;font-weight:700;}
.ern-detail{display:none;padding:0 8px 10px;flex-direction:column;gap:7px;}
.ern-item.open .ern-detail{display:flex;}
.ed-b{background:var(--card);border:1px solid var(--border);border-radius:9px;
 padding:9px 12px;}
.ed-b.cur{border-color:var(--accent);border-left-width:3px;}   /* 이번 발표 예상 강조 */
.ed-t{font-size:10px;font-weight:800;color:var(--muted-2);margin-bottom:5px;}
.ed-t.acc{color:var(--accent);}
.ed-p{color:var(--faint);font-weight:600;}
.ed-why{font-size:10px;color:var(--faint);font-weight:500;margin:-2px 0 6px;
 line-height:1.4;}
.ed-r{display:flex;justify-content:space-between;gap:8px;font-size:12px;margin-top:2px;}
.ed-r>span{color:var(--muted-2);}
.ed-r b{color:var(--ink);font-weight:700;text-align:right;}
.ed-sub{color:var(--faint);font-weight:500;font-size:10.5px;}
.ed-rec{display:flex;align-items:center;gap:8px;margin-top:1px;}
.ed-rec b{font-size:13px;}
.ed-bar{flex:1;display:flex;height:8px;border-radius:4px;overflow:hidden;
 background:var(--border);}
.ed-bar i{display:block;}
.ed-sbars{display:flex;align-items:flex-end;gap:11px;height:40px;padding-top:4px;}
.ed-sbar{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;
 gap:3px;}
.ed-sbar i{width:20px;border-radius:2px;display:block;}
.ed-sbar>span{font-size:9px;color:var(--muted-2);font-weight:600;}
.ern-date{display:flex;flex-direction:column;min-width:60px;flex-shrink:0;}
.ern-md{font-size:12px;font-weight:700;color:var(--ink);}
.ern-dd{font-size:9.5px;font-weight:700;color:var(--faint);}
.ern-n{flex:1;font-size:12.5px;font-weight:600;color:var(--ink);}
.ern-when{font-size:10px;color:var(--muted-2);background:var(--chip);
 padding:2px 7px;border-radius:5px;flex-shrink:0;}
.ern-none{font-size:12px;color:var(--faint);padding:10px 2px;}
.page{width:100%;max-width:820px;background:var(--page);color:var(--ink);
 border:1px solid var(--border);border-radius:18px;
 box-shadow:0 12px 44px var(--shadow);overflow:hidden;}
.hd{padding:30px 40px;background:var(--header);color:#fff;}
.hd-top{display:flex;justify-content:space-between;align-items:center;gap:10px;}
.hd-kicker{font-size:12px;font-weight:600;letter-spacing:.04em;color:#94a3b8;}
.hd-links{display:flex;gap:7px;flex-shrink:0;align-items:center;}
.auth-slot{font:inherit;font-size:11.5px;font-weight:700;color:#dbe4f0;
 background:rgba(255,255,255,.14);border:0;border-radius:8px;padding:5px 11px;
 cursor:pointer;white-space:nowrap;}
.goal-root{min-height:120px;}
.goal-msg{font-size:12.5px;color:var(--muted-2);text-align:center;padding:30px 0;}
.hd-archive{font-size:12px;font-weight:600;color:#dbe4f0;
 background:rgba(255,255,255,.12);padding:6px 13px;border-radius:999px;}
.hd-archive:hover{opacity:1;background:rgba(255,255,255,.2);}
.hd h1{font-size:27px;font-weight:700;margin:16px 0 5px;letter-spacing:-.01em;}
.hd-sub{display:flex;justify-content:space-between;align-items:center;gap:10px;
 font-size:13px;color:#94a3b8;}
.hd-updated{display:flex;align-items:flex-start;gap:6px;}
.hd-uptxt{display:flex;flex-direction:column;gap:2px;}
.fresh{display:block;font-size:10px;color:#86efac;font-weight:600;}  /* 신선함=연녹색 */
.fresh.warn{color:#fbbf24;}                            /* 다소 지연=주황 */
.fresh.stale{color:#f87171;font-weight:700;}          /* 업데이트 지연=빨강 */
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
.badge-new{font-size:10px;font-weight:800;color:#fff;background:#16a34a;
 padding:3px 8px;border-radius:5px;letter-spacing:.03em;}
.quotes{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
 gap:8px;margin-bottom:14px;}
.qcard{background:var(--card);border:1px solid var(--border);border-radius:12px;
 padding:11px 13px;}
.qtop{display:flex;align-items:center;gap:6px;margin-bottom:8px;}
.qtop .spark{margin-left:auto;display:block;}
.qprice{font-size:16px;font-weight:700;color:var(--ink);letter-spacing:-.01em;}
.qchg{font-size:12.5px;font-weight:700;margin-top:2px;}
.quotes-asof{font-size:11px;color:var(--faint);margin:-8px 0 14px 2px;}
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
.msel{display:flex;gap:8px;justify-content:center;margin-bottom:12px;}
.msel-sel{font:inherit;font-size:14px;font-weight:600;padding:9px 16px;
 border-radius:10px;border:1px solid var(--border);background:var(--card);
 color:var(--ink);cursor:pointer;}
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
    grid = ('<div class="quotes">'
            + "".join(_quote_card(c) for c in cards) + "</div>")
    asof = next((c.get("asof") for c in cards if c.get("asof")), "")
    if asof:
        grid += (f'<div class="quotes-asof">시세 기준 {_e(asof)} · '
                 'Yahoo Finance</div>')
    return grid


def _news_toks(s):
    """헤드라인 → 2글자 이상 토큰 집합(유사도 비교용)."""
    return {w for w in re.sub(r"[^0-9A-Za-z가-힣 ]", " ", s or "").split()
            if len(w) > 1}


def _prev_item_tokensets(slug, back=2):
    """slug 직전 `back`개 회차의 뉴스 헤드라인 토큰셋 목록.

    직전 브리핑(들)에 이미 나온 사건인지 비교하는 근거. 저장된 data/*.txt 만
    읽으므로 DB 없이 GitHub Actions 에서도 동작(과거 회차는 커밋되어 있음).
    slug 자신은 제외. 이전 회차가 없으면 빈 목록(→ 아무것도 NEW 로 표시 안 함).
    """
    try:
        slugs = sorted(f[:-4] for f in os.listdir(DATA_DIR) if f.endswith(".txt"))
    except OSError:
        return []
    prev = slugs[:slugs.index(slug)] if slug in slugs else slugs
    out = []
    for s in prev[-back:]:
        _now, body = _load_body(os.path.join(DATA_DIR, s + ".txt"))
        for title, sec_lines in _split_sections(body):
            if not any(key in title for _p, _i, _n, key in PARTS):
                continue
            _s, items, _b, _n = _parse_part(sec_lines)
            for it in items:
                t = _news_toks(it.get("title", ""))
                if t:
                    out.append(t)
    return out


def _is_new(headline, prev_sets, thresh=0.6):
    """직전 회차들의 헤드라인과 60% 미만으로 겹치면 '새 뉴스'로 본다."""
    if not prev_sets:
        return False
    h = _news_toks(headline)
    if not h:
        return False
    for p in prev_sets:
        if len(h & p) / min(len(h), len(p)) >= thresh:
            return False
    return True


def _render_part(pid, icon, name, lines, hero=False, quotes=None, prev_sets=None):
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
    # 제목 없는 깨진 항목 제거(모델이 제목을 비우고 테마만 준 경우 등)
    # 예: '5. (성장)' → 파싱 시 제목이 '(성장)' 뿐이고 본문도 없음.
    items = [it for it in items if (it.get("title") or "").strip()
             and not (re.fullmatch(r"\(.*?\)", it["title"].strip())
                      and not (it.get("desc") or "").strip())]
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
            new = ('<span class="badge-new">NEW</span>'
                   if (prev_sets is not None and _is_new(it["title"], prev_sets))
                   else "")
            src = f'<span class="src">{_e(it["src"])}</span>' if it["src"] else ""
            desc = f'<p>{_e(it["desc"])}</p>' if it["desc"] else ""
            cls = "news hero" if is_hero else "news"
            h.append(f'<div class="{cls}"><div class="news-meta">{key}{new}{badge}{src}'
                     f'</div><h3>{_e(it["title"])}</h3>{desc}</div>')
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


def _shell(title, inner, extra_head="", script="", rail=""):
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
</div>{rail}</div>
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
/* 신선도: 빌드 시각 대비 '지금'까지의 경과시간을 뷰 시점에 계산.
   → 빌드가 실패해 페이지가 갱신 안 돼도 지연이 눈에 보임. */
(function(){
  var el=document.querySelector('.fresh[data-built]'); if(!el) return;
  var built=parseInt(el.getAttribute('data-built'),10)*1000;
  if(!built) return;
  function fmt(){
    var diff=Date.now()-built; if(diff<0) diff=0;
    var h=Math.floor(diff/3600000), m=Math.floor((diff%3600000)/60000);
    var ago = h>0 ? (h+'시간 '+(m?m+'분 ':'')+'전') : (m+'분 전');
    el.className='fresh';
    if(h>=24){ el.classList.add('stale'); el.textContent='⚠ '+ago+' · 업데이트 지연'; }
    else if(h>=18){ el.classList.add('warn'); el.textContent='△ '+ago+' · 갱신 지연 가능'; }
    else { el.textContent=ago+' 업데이트'; }
  }
  fmt(); setInterval(fmt, 60000);
})();
</script>"""


def _title(now):
    ampm = "오전" if now.hour < 12 else "오후"
    return f"{now.year % 100}년 {now.month}월 {now.day}일 {ampm} 뉴스 브리핑"


# =========================================================
# 경제지표 일정 (FXStreet CSV → PC 우측 레일 / 모바일 '일정' 탭)
#   data/econ/*.csv (컬럼: Id,Start[UTC],Name,Impact,Currency)
# =========================================================
ECON_DIR = os.path.join(DATA_DIR, "econ")
_WD_KO = ["월", "화", "수", "목", "금", "토", "일"]
# 통화 → ISO 국가코드(flagcdn 국기 이미지용). Windows는 이모지 국기를 못 그려
# 'CN' 같은 글자로 나오므로 실제 국기 이미지를 쓴다.
_CUR_CC = {
    "USD": "us", "EUR": "eu", "JPY": "jp", "CNY": "cn", "KRW": "kr",
    "GBP": "gb", "AUD": "au", "CAD": "ca", "NZD": "nz", "CHF": "ch",
    "HKD": "hk", "INR": "in", "BRL": "br", "MXN": "mx", "ZAR": "za",
}
# 이벤트명 한글 사전(반복되는 유한 집합). 미등록은 영문 유지 후 점차 보강.
_ECON_KO = {
    "Nonfarm Payrolls": "비농업 고용",
    "Unemployment Rate": "실업률",
    "Average Hourly Earnings (MoM)": "시간당 평균임금 (전월比)",
    "Average Hourly Earnings (YoY)": "시간당 평균임금 (전년比)",
    "Labor Force Participation Rate": "경제활동참가율",
    "U6 Underemployment Rate": "U6 불완전고용률",
    "ADP Employment Change": "ADP 민간고용",
    "ADP Employment Change 4-week average": "ADP 민간고용 4주평균",
    "JOLTS Job Openings": "JOLTS 구인건수",
    "Initial Jobless Claims": "신규 실업수당 청구",
    "Challenger Job Cuts": "챌린저 감원",
    "Nonfarm Productivity": "비농업 생산성",
    "Unit Labor Costs": "단위노동비용",
    "Consumer Price Index (MoM)": "소비자물가지수 CPI (전월比)",
    "Consumer Price Index (YoY)": "소비자물가지수 CPI (전년比)",
    "Consumer Price Index ex Food & Energy (MoM)": "근원 CPI (식품·에너지 제외, 전월比)",
    "Consumer Price Index ex Food & Energy (YoY)": "근원 CPI (식품·에너지 제외, 전년比)",
    "Producer Price Index (MoM)": "생산자물가지수 PPI (전월比)",
    "Producer Price Index (YoY)": "생산자물가지수 PPI (전년比)",
    "Producer Price Index ex Food & Energy (MoM)": "근원 PPI (전월比)",
    "Producer Price Index ex Food & Energy (YoY)": "근원 PPI (전년比)",
    "Personal Consumption Expenditures - Price Index (MoM)": "PCE 물가지수 (전월比)",
    "Personal Consumption Expenditures - Price Index (YoY)": "PCE 물가지수 (전년比)",
    "Core Personal Consumption Expenditures - Price Index (MoM)": "근원 PCE 물가지수 (전월比)",
    "Core Personal Consumption Expenditures - Price Index (YoY)": "근원 PCE 물가지수 (전년比)",
    "Core Personal Consumption Expenditures (QoQ)": "근원 PCE (전분기比)",
    "Personal Consumption Expenditures Prices (QoQ)": "PCE 물가 (전분기比)",
    "Personal Income (MoM)": "개인소득 (전월比)",
    "Personal Spending": "개인소비",
    "Retail Sales (MoM)": "소매판매 (전월比)",
    "Retail Sales (YoY)": "소매판매 (전년比)",
    "Retail Sales Control Group": "소매판매 코어(컨트롤그룹)",
    "Retail Sales ex Autos (MoM)": "소매판매 (자동차 제외, 전월比)",
    "ISM Manufacturing PMI": "ISM 제조업 PMI",
    "ISM Manufacturing Employment Index": "ISM 제조업 고용지수",
    "ISM Manufacturing New Orders Index": "ISM 제조업 신규주문지수",
    "ISM Manufacturing Prices Paid": "ISM 제조업 지불물가",
    "ISM Services PMI": "ISM 서비스업 PMI",
    "ISM Services Employment Index": "ISM 서비스업 고용지수",
    "ISM Services New Orders Index": "ISM 서비스업 신규주문지수",
    "ISM Services Prices Paid": "ISM 서비스업 지불물가",
    "S&P Global Composite PMI": "S&P글로벌 종합 PMI",
    "S&P Global Manufacturing PMI": "S&P글로벌 제조업 PMI",
    "S&P Global Services PMI": "S&P글로벌 서비스업 PMI",
    "HCOB Composite PMI": "HCOB 종합 PMI",
    "HCOB Manufacturing PMI": "HCOB 제조업 PMI",
    "HCOB Services PMI": "HCOB 서비스업 PMI",
    "RatingDog Manufacturing PMI": "제조업 PMI (RatingDog)",
    "RatingDog Services PMI": "서비스업 PMI (RatingDog)",
    "NBS Manufacturing PMI": "중국 국가통계국 제조업 PMI",
    "NBS Non-Manufacturing PMI": "중국 국가통계국 비제조업 PMI",
    "Chicago PMI": "시카고 PMI",
    "NY Empire State Manufacturing Index": "뉴욕 엠파이어스테이트 제조업지수",
    "Philadelphia Fed Manufacturing Survey": "필라델피아 연준 제조업지수",
    "Factory Orders (MoM)": "공장주문 (전월比)",
    "Durable Goods Orders": "내구재주문",
    "Durable Goods Orders ex Defense": "내구재주문 (국방 제외)",
    "Durable Goods Orders ex Transportation": "내구재주문 (운송 제외)",
    "Nondefense Capital Goods Orders ex Aircraft": "근원 자본재주문 (항공 제외)",
    "Industrial Production (MoM)": "산업생산 (전월比)",
    "Industrial Production (YoY)": "산업생산 (전년比)",
    "Industrial Production s.a. (MoM)": "산업생산 (계절조정, 전월比)",
    "Gross Domestic Product Annualized": "GDP 연율화",
    "Gross Domestic Product Price Index": "GDP 물가지수",
    "Gross Domestic Product (QoQ)": "GDP (전분기比)",
    "Gross Domestic Product s.a. (QoQ)": "GDP (계절조정, 전분기比)",
    "Gross Domestic Product s.a. (YoY)": "GDP (계절조정, 전년比)",
    "Gross Domestic Product Deflator (YoY)": "GDP 디플레이터 (전년比)",
    "Employment Change (QoQ)": "고용 변화 (전분기比)",
    "Michigan Consumer Sentiment Index": "미시간대 소비자심리지수",
    "Michigan Consumer Expectations Index": "미시간대 소비자기대지수",
    "UoM 1-year Consumer Inflation Expectations": "미시간대 1년 기대인플레이션",
    "UoM 5-year Consumer Inflation Expectation": "미시간대 5년 기대인플레이션",
    "Consumer Confidence": "소비자신뢰지수",
    "Consumer Sentiment Index": "소비자심리지수",
    "Business Climate": "기업환경지수",
    "Economic Sentiment Indicator": "경제심리지수",
    "ZEW Survey – Economic Sentiment": "ZEW 경기전망지수",
    "Sentix Investor Confidence": "Sentix 투자자신뢰지수",
    "Building Permits (MoM)": "건축허가 (전월比)",
    "Housing Starts (MoM)": "주택착공 (전월比)",
    "Existing Home Sales Change (MoM)": "기존주택판매 (전월比)",
    "New Home Sales Change (MoM)": "신규주택판매 (전월比)",
    "Pending Home Sales (MoM)": "잠정주택판매 (전월比)",
    "Housing Price Index (MoM)": "주택가격지수 (전월比)",
    "Monthly Budget Statement": "월간 재정수지",
    "Loan Officer Survey": "대출담당자 서베이",
    "Trade Balance": "무역수지",
    "Trade Balance USD": "무역수지 (달러)",
    "Trade Balance CNY": "무역수지 (위안)",
    "Exports (YoY)": "수출 (전년比)",
    "Exports (YoY) CNY": "수출 (전년比, 위안)",
    "Imports (YoY)": "수입 (전년比)",
    "Imports (YoY) CNY": "수입 (전년比, 위안)",
    "Current Account n.s.a.": "경상수지",
    "Adjusted Merchandise Trade Balance": "조정 상품무역수지",
    "Merchandise Trade Balance Total": "상품무역수지 총액",
    "Harmonized Index of Consumer Prices (MoM)": "조화소비자물가 HICP (전월比)",
    "Core Harmonized Index of Consumer Prices (MoM)": "근원 HICP (전월比)",
    "Core Harmonized Index of Consumer Prices (YoY)": "근원 HICP (전년比)",
    "Economic Bulletin": "ECB 경제전망 보고서",
    "National Consumer Price Index (YoY)": "전국 소비자물가 (전년比)",
    "National CPI ex Food, Energy (YoY)": "전국 근원 CPI (식품·에너지 제외, 전년比)",
    "National CPI ex Fresh Food (YoY)": "전국 근원 CPI (신선식품 제외, 전년比)",
    "Tokyo Consumer Price Index (YoY)": "도쿄 소비자물가 (전년比)",
    "Tokyo CPI ex Food, Energy (YoY)": "도쿄 근원 CPI (식품·에너지 제외, 전년比)",
    "Tokyo CPI ex Fresh Food (YoY)": "도쿄 근원 CPI (신선식품 제외, 전년比)",
    "Labor Cash Earnings (YoY)": "근로자 현금소득 (전년比)",
    "FOMC Minutes": "FOMC 의사록",
    "BoJ Monetary Policy Meeting Minutes": "일본은행 통화정책회의 의사록",
    "BoK Interest Rate Decision": "한국은행 기준금리 결정",
    "PBoC Interest Rate Decision": "중국인민은행 기준금리 결정",
    "Fed's Musalem speech": "연준 무살렘 연설",
    "Construction Spending (MoM)": "건설지출 (전월比)",
    "Consumer Price Index Growth (MoM)": "소비자물가 상승률 (전월比)",
    "Consumer Price Index Growth (YoY)": "소비자물가 상승률 (전년比)",
    "Goods and Services Trade Balance": "상품·서비스 무역수지",
    "Goods Trade Balance": "상품 무역수지",
    "Total Vehicle Sales": "총 차량판매",
    "Redbook Index (YoY)": "레드북 소매판매지수 (전년比)",
    "RealClearMarkets/TIPP Economic Optimism (MoM)": "TIPP 경제낙관지수 (전월比)",
    "API Weekly Crude Oil Stock": "API 주간 원유재고",
    "FX Reserves": "외환보유액",
    "3-Month Bill Auction": "3개월물 국채 입찰",
    "6-Month Bill Auction": "6개월물 국채 입찰",
    "52-Week Bill Auction": "52주물 국채 입찰",
    "4-Week Bill Auction": "4주물 국채 입찰",
    "2-Year Note Auction": "2년물 국채 입찰",
    "3-Year Note Auction": "3년물 국채 입찰",
    "5-Year Note Auction": "5년물 국채 입찰",
    "7-Year Note Auction": "7년물 국채 입찰",
    "10-Year Note Auction": "10년물 국채 입찰",
    "20-Year Bond Auction": "20년물 국채 입찰",
    "30-Year Bond Auction": "30년물 국채 입찰",
    "30-year TIPS Auction": "30년물 물가연동국채 입찰",
    "Continuing Jobless Claims": "연속 실업수당 청구",
    "Initial Jobless Claims 4-week average": "신규 실업수당 청구 4주평균",
    "MBA Mortgage Applications": "MBA 주택담보대출 신청",
    "EIA Crude Oil Stocks Change": "EIA 원유재고 변화",
    "EIA Natural Gas Storage Change": "EIA 천연가스 재고 변화",
    "Baker Hughes US Oil Rig Count": "베이커휴즈 원유 시추기 수",
    "Wholesale Inventories": "도매재고",
    "Business Inventories": "기업재고",
    "Building Permits Change": "건축허가 변화",
    "Housing Starts Change": "주택착공 변화",
    "Import Price Index (MoM)": "수입물가지수 (전월比)",
    "Import Price Index (YoY)": "수입물가지수 (전년比)",
    "Export Price Index (MoM)": "수출물가지수 (전월比)",
    "Export Price Index (YoY)": "수출물가지수 (전년比)",
    "New Home Sales (MoM)": "신규주택판매 건수 (전월比)",
    "Existing Home Sales (MoM)": "기존주택판매 건수 (전월比)",
    "Capacity Utilization": "설비가동률",
    "NAHB Housing Market Index": "NAHB 주택시장지수",
    "NFIB Business Optimism Index": "NFIB 중소기업 낙관지수",
    "Richmond Fed Manufacturing Index": "리치먼드 연준 제조업지수",
    "Kansas Fed Manufacturing Activity": "캔자스 연준 제조업활동",
    "Dallas Fed Manufacturing Business Index": "댈러스 연준 제조업지수",
    "Consumer Credit Change": "소비자신용 변화",
    "USDA WASDE Report": "USDA 세계 농산물 수급전망",
    "Money Supply Growth": "통화량 증가율",
    "Export Price Growth (YoY)": "수출물가 상승률 (전년比)",
    "Import Price Growth (YoY)": "수입물가 상승률 (전년比)",
    "Producer Price Index Growth (MoM)": "생산자물가 상승률 (전월比)",
    "Producer Price Index Growth (YoY)": "생산자물가 상승률 (전년比)",
    "Industrial Output (YoY)": "산업생산 (전년比)",
    "Service Sector Output": "서비스업 생산",
    "BOK Manufacturing BSI": "한국은행 제조업 BSI",
    "Current Account Balance": "경상수지",
    "Consumer Sentiment Index": "소비자심리지수",
}


def _load_econ_events(now):
    """data/econ/*.csv 병합 → MEDIUM/HIGH만, UTC→KST, 'now 이후' 임박순."""
    if not os.path.isdir(ECON_DIR):
        return []
    rows = {}
    for fn in os.listdir(ECON_DIR):
        if not fn.endswith(".csv"):
            continue
        try:
            with open(os.path.join(ECON_DIR, fn), encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    imp = (row.get("Impact") or "").strip().upper()
                    if imp not in ("LOW", "MEDIUM", "HIGH"):
                        continue
                    try:
                        dt = pytz.utc.localize(
                            datetime.strptime((row.get("Start") or "").strip(),
                                              "%m/%d/%Y %H:%M:%S")).astimezone(KST)
                    except ValueError:
                        continue
                    key = row.get("Id") or (row.get("Start", "") + row.get("Name", ""))
                    rows[key] = {"dt": dt, "name": (row.get("Name") or "").strip(),
                                 "impact": imp,
                                 "cur": (row.get("Currency") or "").strip().upper()}
        except OSError:
            continue
    # B 로직: 이번 달=오늘 이후만 · 미래 달=전체 · 지난 달=제외
    cur_ym = now.strftime("%Y-%m")
    today = now.date()
    kept = []
    for e in rows.values():
        ym = e["dt"].strftime("%Y-%m")
        if ym < cur_ym:
            continue
        if ym == cur_ym and e["dt"].date() < today:
            continue
        kept.append(e)
    kept.sort(key=lambda e: e["dt"])
    # 월별로 묶기: [[ym, label, [events...]], ...] (오름차순)
    months = []
    for e in kept:
        ym = e["dt"].strftime("%Y-%m")
        if not months or months[-1][0] != ym:
            months.append([ym, f"{e['dt'].year}년 {e['dt'].month}월", []])
        months[-1][2].append(e)
    return months


def _impact_gauge(imp):
    b = "var(--border)"
    seg = ({"HIGH": ["#e5484d", "#e5484d", "#e5484d"],
            "MEDIUM": ["#f59e0b", "#f59e0b", b]}
           .get(imp, ["#94a3b8", b, b]))   # LOW = 회색 1칸
    return ('<span class="igauge">'
            + "".join(f'<i style="background:{c}"></i>' for c in seg) + "</span>")


def _econ_row(e):
    t = e["dt"].strftime("%I:%M %p").lstrip("0")
    name = _ECON_KO.get(e["name"], e["name"])
    cc = _CUR_CC.get(e["cur"])
    # 국기는 사이트 자체(docs/flags/)에서 같은 출처로 로드(외부 의존 0).
    flag = (f'<img class="ev-flag" src="flags/{cc}.svg" '
            f'alt="{_e(e["cur"])}" title="{_e(e["cur"])}" '
            f'width="22" height="16" decoding="async">'
            if cc else '<span class="ev-flag"></span>')
    return (f'<div class="ev" data-imp="{e["impact"]}"><span class="ev-t">{t}</span>'
            f'{flag}<span class="ev-n">{_e(name)}</span>'
            f'{_impact_gauge(e["impact"])}</div>')


def _render_schedule(months, now):
    """months: [[ym,label,[events]], ...] (오름차순). 연/월 드롭다운으로 전환."""
    if not months:
        return ""
    cur_ym = now.strftime("%Y-%m")
    default_ym = next((m[0] for m in months if m[0] == cur_ym), months[0][0])
    # 기본: 높음·중간 ON, 낮음 OFF (컨테이너 클래스로 서버에서 초기상태 지정→FOUC 없음)
    out = ['<div class="sched s-high s-med"><div class="sched-head">'
           '<div class="econ-bar">'
           '<div class="econ-sel">'
           '<select class="econ-y" aria-label="연도"></select>'
           '<select class="econ-m" aria-label="월"></select>'
           '</div>'
           '<div class="imp-filter">'
           '<button class="imp-chip on" data-k="high"><i style="background:#e5484d"></i>높음</button>'
           '<button class="imp-chip on" data-k="med"><i style="background:#f59e0b"></i>중간</button>'
           '<button class="imp-chip" data-k="low"><i style="background:#94a3b8"></i>낮음</button>'
           '</div></div>'
           '<div class="sched-tz2">시간 기준 KST · 데이터 FXStreet</div>'
           '</div><div class="econ-months" data-default="%s">' % default_ym]
    for ym, label, evs in months:
        hide = "" if ym == default_ym else ' style="display:none"'
        out.append(f'<div class="sched-month" data-ym="{ym}" '
                   f'data-label="{_e(label)}"{hide}>')
        cur_day = None
        for e in evs:
            d = e["dt"].strftime("%Y-%m-%d")
            if d != cur_day:
                if cur_day is not None:
                    out.append("</div>")
                cur_day = d
                out.append(f'<div class="sched-group"><div class="sched-day">'
                           f'{e["dt"].month}월 {e["dt"].day}일 '
                           f'({_WD_KO[e["dt"].weekday()]})</div>')
            out.append(_econ_row(e))
        if cur_day is not None:
            out.append("</div>")
        out.append('</div>')   # .sched-month
    out.append('</div></div>')  # .econ-months / .sched
    return "".join(out)


_SCHED_JS = """<script>
document.querySelectorAll('.sched').forEach(function(sc){
  function groups(){
    sc.querySelectorAll('.sched-group').forEach(function(g){
      var vis=[].some.call(g.querySelectorAll('.ev'),
        function(e){return getComputedStyle(e).display!=='none';});
      g.style.display = vis ? '' : 'none';
    });
  }
  sc.querySelectorAll('.imp-chip').forEach(function(ch){
    ch.addEventListener('click', function(){
      ch.classList.toggle('on');
      sc.classList.toggle('s-'+ch.getAttribute('data-k'),
        ch.classList.contains('on'));
      groups();
    });
  });
  // 연/월 드롭다운: 미리 심어둔 월 섹션 중 선택한 달만 표시
  var wrap=sc.querySelector('.econ-months'),
      selY=sc.querySelector('.econ-y'), selM=sc.querySelector('.econ-m');
  if(wrap && selY && selM){
    var secs=[].slice.call(wrap.querySelectorAll('.sched-month'));
    var data=secs.map(function(s){var ym=s.getAttribute('data-ym');
      return {ym:ym, y:ym.slice(0,4), m:parseInt(ym.slice(5,7),10)};});
    function opt(v,t){var o=document.createElement('option');
      o.value=v;o.textContent=t;return o;}
    var years=[]; data.forEach(function(d){if(years.indexOf(d.y)<0)years.push(d.y);});
    years.forEach(function(y){selY.appendChild(opt(y,y+'년'));});
    function fillM(y,pick){
      selM.innerHTML='';
      var ms=data.filter(function(d){return d.y===y;});
      ms.forEach(function(d){selM.appendChild(opt(d.ym,d.m+'월'));});
      selM.value=(pick && ms.some(function(d){return d.ym===pick;}))?pick:ms[0].ym;
    }
    function show(ym){
      secs.forEach(function(s){
        s.style.display=(s.getAttribute('data-ym')===ym)?'':'none';});
      groups();
    }
    var def=wrap.getAttribute('data-default')||data[0].ym;
    selY.value=def.slice(0,4); fillM(def.slice(0,4),def); show(selM.value);
    selY.addEventListener('change',function(){fillM(selY.value); show(selM.value);});
    selM.addEventListener('change',function(){show(selM.value);});
  }
  groups();
});
document.querySelectorAll('.sub-tab').forEach(function(b){
  b.addEventListener('click', function(){
    var wrap = b.parentNode.parentNode.querySelector('.sched-2col');
    if(wrap) wrap.setAttribute('data-sub', b.getAttribute('data-sub'));
    b.parentNode.querySelectorAll('.sub-tab').forEach(function(x){x.classList.remove('on');});
    b.classList.add('on');
  });
});
document.querySelectorAll('.ern-item').forEach(function(item){
  var row=item.querySelector('.ern');
  if(!row || !item.querySelector('.ern-detail')) return;   // 상세 없으면 클릭 비활성
  row.addEventListener('click', function(){ item.classList.toggle('open'); });
});
document.querySelectorAll('.rep-head').forEach(function(h){
  h.addEventListener('click', function(){ h.parentNode.classList.toggle('open'); });
});
document.querySelectorAll('.ev-view').forEach(function(b){
  b.addEventListener('click', function(){
    var box=b.closest('.sched-earn'); if(!box) return;
    box.querySelectorAll('.ev-view').forEach(function(x){x.classList.remove('on');});
    b.classList.add('on');
    var v=b.getAttribute('data-v');
    var map={up:'.earn-up',r:'.earn-r'};
    Object.keys(map).forEach(function(k){
      var el=box.querySelector(map[k]);
      if(el) el.style.display=(k===v)?'':'none';
    });
  });
});
document.querySelectorAll('.earn-r').forEach(function(box){
  function showQ(cq){
    box.querySelectorAll('.q-q').forEach(function(x){
      x.classList.toggle('on', x.getAttribute('data-q')===cq);});
    box.querySelectorAll('.q-panel').forEach(function(p){
      p.style.display=p.getAttribute('data-q')===cq?'':'none';});
  }
  box.querySelectorAll('.q-year').forEach(function(y){
    y.addEventListener('click', function(){
      box.querySelectorAll('.q-year').forEach(function(x){x.classList.remove('on');});
      y.classList.add('on');
      var yr=y.getAttribute('data-y'), first=null;
      box.querySelectorAll('.q-q').forEach(function(q){
        var vis=q.getAttribute('data-y')===yr;
        q.style.display=vis?'':'none';
        if(vis && !first) first=q;
      });
      if(first) showQ(first.getAttribute('data-q'));
    });
  });
  box.querySelectorAll('.q-q').forEach(function(q){
    q.addEventListener('click', function(){ showQ(q.getAttribute('data-q')); });
  });
});
</script>"""


EARN_FILE = os.path.join(DATA_DIR, "earnings.json")
REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")


def _load_reports():
    try:
        with open(REPORTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _hl(s):
    """실적 요약 가독성: 수치 볼드 + 방향/부호 색(상승·+=빨강 / 하락·−=파랑)."""
    s = _e(s)
    # 금액 단위 축약 먼저: '$265 million' → '$265M' (아래 통화 볼드가 'm'을 깨는 것 방지)
    s = re.sub(r'(\d[\d,.]*)\s*billion\b', r'\1B', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*)\s*million\b', r'\1M', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*\s?%?)(\s*)(증가|성장|상승|개선|급증|확대|호조|흑자)',
               r'<b style="color:#e5484d">\1</b>\2\3', s)
    s = re.sub(r'(\d[\d,.]*\s?%?)(\s*)(감소|하락|부진|축소|악화|손실|둔화|적자)',
               r'<b style="color:#3b82f6">\1</b>\2\3', s)
    s = re.sub(r'(?<![\w>])\+(\d[\d,.]*\s?%?)', r'<b style="color:#e5484d">+\1</b>', s)
    s = re.sub(r'(?<![\w>])-(\d[\d,.]*\s?%?)', r'<b style="color:#3b82f6">-\1</b>', s)
    s = re.sub(r'(\$-?\d[\d,.]*[BMK]?)', r'<b>\1</b>', s)   # 접미사는 대문자만
    return s


def _rec_color(lab):
    """투자의견 단계별 색: 적극매수=진빨강 / 매수=빨강 / 보유=주황 / 매도=파랑 / 적극매도=진파랑."""
    lab = lab or ""
    if "적극 매수" in lab or "strong" in lab.lower() and "buy" in lab.lower():
        return "#b91c1c"
    if "적극 매도" in lab:
        return "#1e40af"
    if "매수" in lab:
        return "#e5484d"
    if "매도" in lab or "축소" in lab:
        return "#3b82f6"
    if "보유" in lab:
        return "#f59e0b"
    return "#64748b"


def _fmt_money(v, k=""):
    """'234 million'→'$234M', '2.36 billion'→'$2.36B'. 통화 지표면 $ 보강."""
    s = str(v or "")
    if "%" in s:
        return s
    s = re.sub(r'(\d[\d,.]*)\s*billion\b', r'\1B', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*)\s*million\b', r'\1M', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*)\s*thousand\b', r'\1K', s, flags=re.I)
    kl = (k or "").lower()
    money_kw = ("매출", "revenue", "이익", "손익", "손실", "income", "ebitda",
                "현금", "유동성", "backlog", "백로그", "계약", "가치", "자산", "부채")
    if ("$" not in s) and (any(w in kl for w in money_kw)):
        s = re.sub(r'^(-?)(\d)', r'\1$\2', s)   # 음수부호 뒤에 $
    return s


def _mv_color(v, dir_=None):
    """지표 값 색: 음수(적자·감소)는 항상 파랑, 그 외 dir(up=빨강/down=파랑), 없으면 부호."""
    vt = (v or "").strip()
    if vt[:1] == "-" or vt[:2] in ("$-", "-$"):   # 음수 값은 무조건 파랑
        return f'<span style="color:#3b82f6">{_e(v)}</span>'
    if dir_ == "up":
        return f'<span style="color:#e5484d">{_e(v)}</span>'
    if dir_ == "down":
        return f'<span style="color:#3b82f6">{_e(v)}</span>'
    if vt[:1] == "+":
        return f'<span style="color:#e5484d">{_e(v)}</span>'
    return _e(v)


def _report_card_html(r, open_=False):
    """8-K 기반 실적 보고서 카드 1개."""
    bg = _ticker_color(r.get("ticker", ""))
    badge = (f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
             f'{_e((r.get("ticker") or "").split("-")[0])}</span>')
    v, sp = r.get("verdict"), r.get("surprise_pos")
    vcls = "beat" if (v == "beat" or sp) else ("miss" if (v == "miss" or sp is False) else "")
    vtxt = {"beat": "어닝 서프라이즈", "miss": "어닝 쇼크", "inline": "예상 부합"}.get(v, "")
    if r.get("surprise"):
        vtxt = (vtxt + " " + ("▲" if sp else "▼") + _e(r["surprise"])).strip()
    verdict = f'<span class="rep-verdict {vcls}">{vtxt}</span>' if vtxt else ""
    metrics = [m for m in (r.get("metrics") or [])
               if not re.search(r'백로그|backlog', m.get("k", ""), re.I)][:4]
    mets = "".join(
        f'<div class="rep-m"><div class="rep-mk">{_e(m.get("k",""))}</div>'
        f'<div class="rep-mv">'
        f'{_mv_color(_fmt_money(m.get("v",""), m.get("k","")), m.get("dir"))}</div></div>'
        for m in metrics)
    ms = f'<div class="rep-ms">{mets}</div>' if mets else ""
    guide = (f'<div class="rep-guide">📈 {_hl(r["guidance"])}</div>'
             if r.get("guidance") else "")
    bullets = "".join(f'<div class="rep-b"><span>•</span><span>{_hl(b)}</span></div>'
                      for b in (r.get("bullets") or []))
    title = f'<div class="rep-hd">{_e(r.get("title",""))}</div>'
    foot = ('<div class="rep-foot">'
            f'<a href="{_e(r.get("url",""))}" target="_blank" rel="noopener">🔗 SEC 8-K 원문</a>'
            '<span>AI 요약 · 참고용</span></div>')
    newb = '<span class="ev-new">NEW</span>' if open_ else ''
    header = (f'<div class="rep-head">{badge}'
              f'<span class="rep-name">{_e(r.get("name",""))} · {_e(r.get("quarter",""))}{newb}</span>'
              f'{verdict}<span class="rep-arrow">▾</span></div>')
    body = (f'<div class="rep-body">{title}{ms}{guide}'
            f'<div class="rep-bs">{bullets}</div>{foot}</div>')
    return f'<div class="rep-item{" open" if open_ else ""}">{header}{body}</div>'


def _rep_cq(r):
    """보고서 분기 라벨('2026 2Q') → cq('2026-2')."""
    p = (r.get("quarter") or "").split()
    return f"{p[0]}-{p[1][:-1]}" if len(p) == 2 and p[1].endswith("Q") else ""
_WHEN_KO = {"amc": "장 마감 후", "bmo": "장 전", "": ""}


def _load_earnings(now):
    """data/earnings.json(큐레이션) → 지난 일정 제외, 날짜순(미정은 뒤)."""
    try:
        with open(EARN_FILE, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError):
        return []
    today, out = now.date(), []
    for r in rows:
        d = None
        if r.get("date"):
            try:
                d = date.fromisoformat(r["date"])
            except ValueError:
                d = None
        # 발표 완료 = 실제 발표 시각(ts)이 지났을 때만 (발표일 당일이어도 시각 전이면 예정)
        ts = r.get("ts")
        reported = bool(ts and now.timestamp() >= ts)
        out.append({"ticker": (r.get("ticker") or "").upper(),
                    "name": r.get("name") or "", "date": d,
                    "ts": r.get("ts"),
                    "est": bool(r.get("est")),
                    "reported": reported,
                    "detail": r.get("detail") or {}})
    out.sort(key=lambda e: (e["date"] is None, e["date"] or date.max))
    return out


def _is_fresh(r, now, days=2):
    """최근 발표(N일 내) 보고서 → 실적 결과 자동 진입 대상."""
    try:
        return 0 <= (now.date() - date.fromisoformat(r.get("date", ""))).days <= days
    except (ValueError, TypeError):
        return False


def _render_earnings(evs, now):
    head = ('<div class="sched sched-earn"><div class="sched-head">'
            '<span><span class="sched-ico">🏢</span>기업실적'
            ' <span class="sched-tz">관심종목</span></span></div>')
    if not evs:
        return head + '<div class="ern-none">등록된 실적 일정이 없습니다.</div></div>'
    fresh = sorted((r for r in _load_reports() if _is_fresh(r, now)),
                   key=lambda r: r.get("date", ""), reverse=True)
    fresh_cq = (fresh[0].get("cq") or _rep_cq(fresh[0])) if fresh else None
    fresh_tk = {r.get("ticker") for r in fresh}
    auto = bool(fresh_cq)   # 최근 발표 있으면 '실적 결과'로 자동 진입
    nb = '<span class="ev-new">NEW</span>' if fresh else ''
    toggle = ('<div class="earn-views">'
              f'<button class="ev-view{"" if auto else " on"}" data-v="up">📅 예정</button>'
              f'<button class="ev-view{" on" if auto else ""}" data-v="r">📄 실적 결과{nb}</button></div>')
    return (head + toggle
            + _render_upcoming(evs, now, show=not auto, skip=fresh_tk)
            + _render_results(evs, now, show=auto, default_cq=fresh_cq, fresh_tk=fresh_tk)
            + '<div class="sched-src">데이터: Yahoo Finance · SEC EDGAR</div></div>')


def _render_upcoming(evs, now, show=True, skip=None):
    """예정 뷰: 분기별 그룹 + 컨센서스(예상 EPS/매출·목표주가·투자의견 색/비율)."""
    up, dn = "#e5484d", "#3b82f6"
    skip = skip or set()
    groups = {}
    for e in sorted(evs, key=lambda x: (x["date"] is None, x["date"] or date.max)):
        if e["ticker"] in skip:      # 최근 발표한 종목은 '실적 결과'로
            continue
        d = e["date"]
        gk = (d.year, (d.month - 1)//3 + 1) if d else (9999, 9)
        gl = f"{d.year} {(d.month-1)//3+1}Q" if d else "미정"
        groups.setdefault(gk, {"label": gl, "rows": []})["rows"].append(e)
    disp = "" if show else ' style="display:none"'
    out = [f'<div class="earn-up"{disp}>'
           '<div class="up-note">발표 예정일·시간 · 한국시간(KST) 기준</div>']
    for gk in sorted(groups):
        out.append(f'<div class="up-qh">{_e(groups[gk]["label"])}</div>')
        for e in groups[gk]["rows"]:
            d = e["date"]
            det = e.get("detail") or {}
            cur, tgt, rec = det.get("cur") or {}, det.get("target") or {}, det.get("rec") or {}
            bg = _ticker_color(e["ticker"])
            badge = (f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
                     f'{_e(e["ticker"].split("-")[0])}</span>')
            ts = e.get("ts")
            if d:
                dd = (d - now.date()).days
                dtxt = "D-DAY" if dd == 0 else (f"D+{-dd}" if dd < 0 else f"D-{dd}")
                md = f'{d.month}/{d.day}({_WD_KO[d.weekday()]})'
                if ts:
                    md += " " + datetime.fromtimestamp(ts, KST).strftime("%H:%M")
                    if e.get("est"):
                        md += " 예상"
            else:
                dtxt, md = "미정", "미정"
            parts = []
            if cur.get("eps") not in (None, "-"):
                parts.append(f'예상 EPS <b>{_e(cur["eps"])}</b>')
            if cur.get("rev") not in (None, "-"):
                gg = ""
                if cur.get("growth"):
                    gg = f' <b style="color:{up if cur.get("growth_pos") else dn}">{_e(cur["growth"])}</b>'
                parts.append(f'매출 <b>{_e(cur["rev"])}</b>{gg}')
            if tgt.get("mean") not in (None, "-"):
                uu = ""
                if tgt.get("upside"):
                    uu = f' <b style="color:{up if tgt.get("upside_pos") else dn}">{_e(tgt["upside"])}</b>'
                parts.append(f'목표 <b>{_e(tgt["mean"])}</b>{uu}')
            subline = " · ".join(parts) if parts else "컨센서스 없음"
            sub2 = ""
            if rec.get("label") not in (None, "-"):
                lab = rec.get("label") or ""
                cnt = (f' <span class="up-cnt">({rec.get("count")}명)</span>'
                       if rec.get("count") else "")
                b_, h_, s_ = rec.get("buy") or 0, rec.get("hold") or 0, rec.get("sell") or 0
                tot = b_ + h_ + s_
                bar = rt = ""
                if tot:
                    bar = ('<span class="rec-bar">'
                           f'<i style="width:{b_/tot*100:.0f}%;background:#e5484d"></i>'
                           f'<i style="width:{h_/tot*100:.0f}%;background:#f59e0b"></i>'
                           f'<i style="width:{s_/tot*100:.0f}%;background:#3b82f6"></i></span>')
                    rt = ('<span class="rec-ratio">'
                          f'<b style="color:#e5484d">매수 {round(b_/tot*100)}%</b> · '
                          f'<b style="color:#f59e0b">보유 {round(h_/tot*100)}%</b> · '
                          f'<b style="color:#3b82f6">매도 {round(s_/tot*100)}%</b></span>')
                sub2 = (f'<div class="up-rec">투자의견 '
                        f'<b style="color:{_rec_color(lab)}">{_e(lab)}</b>{cnt}{bar}{rt}</div>')
            out.append(
                f'<div class="up-row"><span class="up-dday">{dtxt}</span>{badge}'
                f'<div class="up-main"><div class="up-t"><b>{_e(e["name"])}</b>'
                f'<span class="up-date">{md}</span></div>'
                f'<div class="up-sub">{subline}</div>{sub2}</div></div>')
    out.append('</div>')
    return "".join(out)


def _render_results(evs, now, show=False, default_cq=None, fresh_tk=None):
    """실적 결과 뷰: 연/분기 필터 + 발표분(8-K 보고서 있으면 풀카드, 없으면 숫자줄)."""
    fresh_tk = fresh_tk or set()
    rep_list = _load_reports()
    reports = {}
    for r in rep_list:
        cq = r.get("cq") or _rep_cq(r)
        if cq:
            reports[(r.get("ticker"), cq)] = r
    buckets, labels = {}, {}
    for e in evs:
        for q in (e["detail"].get("quarters") or []):
            if not q.get("reported"):
                continue
            cq = q.get("cq")
            if not cq:
                continue
            labels[cq] = q.get("label") or cq
            buckets.setdefault(cq, []).append(
                {"ticker": e["ticker"], "name": e["name"], "q": q,
                 "report": reports.get((e["ticker"], cq))})
    # Yahoo가 아직 '예정'이어도 8-K 보고서가 있으면 결과에 노출(반영 지연 대응)
    ev_name = {e["ticker"]: e["name"] for e in evs}
    for r in rep_list:
        cq = r.get("cq") or _rep_cq(r)
        if not cq:
            continue
        labels.setdefault(cq, r.get("quarter") or cq)
        lst = buckets.setdefault(cq, [])
        ex = next((x for x in lst if x["ticker"] == r.get("ticker")), None)
        if ex:
            ex["report"] = r
        else:
            lst.append({"ticker": r.get("ticker"),
                        "name": r.get("name") or ev_name.get(r.get("ticker"), ""),
                        "q": None, "report": r})
    if not buckets:
        return ('<div class="earn-r" style="display:none">'
                '<div class="ern-none">발표된 실적이 없습니다.</div></div>')
    cqs = sorted(buckets, reverse=True)
    default = default_cq if default_cq in buckets else cqs[0]
    default_year = default.split("-")[0]
    years = sorted({cq.split("-")[0] for cq in cqs}, reverse=True)
    chips = ['<div class="q-years">']
    for y in years:
        chips.append(f'<button class="q-year{" on" if y==default_year else ""}" '
                     f'data-y="{y}">{y}년</button>')
    chips.append('</div><div class="q-quarters">')
    for cq in cqs:
        y, qn = cq.split("-")
        hide = "" if y == default_year else ' style="display:none"'
        on = " on" if cq == default else ""
        chips.append(f'<button class="q-q{on}" data-y="{y}" data-q="{cq}"{hide}>{qn}Q</button>')
    chips.append('</div>')

    def _prio(x):
        # 1) NEW(최근 발표) → 2) 발표 예정(미발표) → 3) 발표됨
        if x.get("report") and x["ticker"] in fresh_tk:
            return 0
        q = x.get("q") or {}
        return 2 if (x.get("report") or q.get("reported")) else 1
    panels = []
    for cq in cqs:
        nrep = sum(1 for x in buckets[cq] if x["report"])
        note = (f'<div class="rep-note">{_e(labels[cq])} · 발표 {len(buckets[cq])}종목'
                f'{f" · 보고서 {nrep}" if nrep else ""} · 출처 SEC 8-K/Yahoo · 참고용</div>')
        items = []
        ordered = sorted(buckets[cq],
                         key=lambda x: ((x.get("report") or {}).get("date") or ""),
                         reverse=True)          # 발표일 최근순
        ordered.sort(key=_prio)                 # NEW → 예정 → 발표됨 (안정 정렬)
        for it in ordered:
            if it["report"]:
                items.append(_report_card_html(it["report"],
                                               open_=it["ticker"] in fresh_tk))
                continue
            q = it["q"]
            bg = _ticker_color(it["ticker"])
            badge = (f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
                     f'{_e(it["ticker"].split("-")[0])}</span>')
            surp = (f'<span class="q-surp {"up" if q.get("surprise_pos") else "dn"}">'
                    f'{"▲" if q.get("surprise_pos") else "▼"} {_e(q.get("surprise") or "")}</span>'
                    if q.get("surprise") else '')
            items.append(
                f'<div class="res-row">{badge}'
                f'<div class="res-main"><b>{_e(it["name"])}</b>'
                f'<span class="q-sub">EPS 실제 {_e(q.get("eps_act","-"))} / '
                f'예상 {_e(q.get("eps_est","-"))}</span></div>{surp}</div>')
        hide = "" if cq == default else ' style="display:none"'
        panels.append(f'<div class="q-panel" data-q="{cq}"{hide}>'
                      + note + "".join(items) + '</div>')
    disp = "" if show else ' style="display:none"'
    return (f'<div class="earn-r"{disp}>'
            + "".join(chips) + "".join(panels) + '</div>')


def _pct_num(s):
    try:
        return float(str(s).replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _fmt_md(s):
    try:
        d = date.fromisoformat(s)
        return f"{d.month}/{d.day}"
    except (TypeError, ValueError):
        return s or ""


def _render_earn_quarters(evs, now):
    """분기별 토글: 캘린더 분기(cq)로 종목 묶어 실제결과/예상 표시."""
    buckets, labels = {}, {}
    for e in evs:
        for q in (e["detail"].get("quarters") or []):
            cq = q.get("cq")
            if not cq:
                continue
            labels[cq] = q.get("label") or cq
            buckets.setdefault(cq, []).append(
                {"ticker": e["ticker"], "name": e["name"], "q": q})
    if not buckets:
        return ('<div class="earn-q" style="display:none">'
                '<div class="ern-none">분기 데이터가 없습니다.</div></div>')
    cqs = sorted(buckets, reverse=True)   # 최근 분기 먼저
    default = next((cq for cq in cqs
                    if any(x["q"].get("reported") for x in buckets[cq])), cqs[0])
    default_year = default.split("-")[0]
    years = sorted({cq.split("-")[0] for cq in cqs}, reverse=True)
    chips = ['<div class="q-years">']
    for y in years:
        chips.append(f'<button class="q-year{" on" if y==default_year else ""}" '
                     f'data-y="{y}">{y}년</button>')
    chips.append('</div><div class="q-quarters">')
    for cq in cqs:
        y, qn = cq.split("-")
        up = not any(x["q"].get("reported") for x in buckets[cq])
        hide = "" if y == default_year else ' style="display:none"'
        on = " on" if cq == default else ""
        chips.append(f'<button class="q-q{on}" data-y="{y}" data-q="{cq}"{hide}>'
                     f'{qn}Q{" · 예정" if up else ""}</button>')
    chips.append('</div>')
    panels = []
    for cq in cqs:
        def _skey(x):
            q = x["q"]
            if q.get("reported"):
                v = _pct_num(q.get("surprise"))
                return (0, -(v if v is not None else -999))
            return (1, 0)
        rws = []
        for it in sorted(buckets[cq], key=_skey):
            q = it["q"]
            bg = _ticker_color(it["ticker"])
            badge = (f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
                     f'{_e(it["ticker"].split("-")[0])}</span>')
            if q.get("reported"):
                sc = "up" if q.get("surprise_pos") else "dn"
                ar = "▲" if q.get("surprise_pos") else "▼"
                right = (f'<span class="q-surp {sc}">{ar} {_e(q.get("surprise") or "")}</span>'
                         if q.get("surprise") else '')
                sub = (f'EPS 실제 {_e(q.get("eps_act", "-"))} / '
                       f'예상 {_e(q.get("eps_est", "-"))}')
            else:
                dt = q.get("date")
                right = (f'<span class="q-date">{_fmt_md(dt)} 예정</span>'
                         if dt else '<span class="q-date">예정</span>')
                sub = (f'예상 EPS {_e(q.get("eps_est", "-"))}'
                       + (f' · 매출 {_e(q.get("rev"))}' if q.get("rev") else ''))
            rws.append(f'<div class="q-row">{badge}'
                       f'<div class="q-rmain"><b>{_e(it["name"])}</b>'
                       f'<span class="q-sub">{sub}</span></div>{right}</div>')
        hide = "" if cq == default else ' style="display:none"'
        panels.append(f'<div class="q-panel" data-q="{cq}"{hide}>'
                      + "".join(rws) + '</div>')
    return ('<div class="earn-q" style="display:none">'
            + "".join(chips) + "".join(panels) + '</div>')


def _earn_detail_html(det, reported):
    """실적 카드 상세(6블록). 데이터 있는 블록만 렌더."""
    if not det:
        return ""
    up, dn = "#e5484d", "#3b82f6"   # 상회/상승=빨강, 하회/하락=파랑
    b = []
    p = det.get("prev")
    if p:
        c = up if p.get("surprise_pos") else dn
        ar = "▲" if p.get("surprise_pos") else "▼"
        sur = (f' · <span style="color:{c};font-weight:800">{ar}{_e(p["surprise"])}</span>'
               if p.get("surprise") else "")
        # 발표 직후엔 Yahoo 실제치 집계 전이라 prev는 여전히 '직전(지난) 분기'가 맞음.
        b.append(
            f'<div class="ed-b"><div class="ed-t">🔄 직전 실적 '
            f'<span class="ed-p">· {_e(p.get("period",""))}</span></div>'
            '<div class="ed-why">지난 분기 실제 실적과 시장 예상치를 비교</div>'
            f'<div class="ed-r"><span>EPS 실제/예상</span>'
            f'<b>{_e(p.get("eps_act","-"))} / {_e(p.get("eps_est","-"))}{sur}</b></div></div>')
    c = det.get("cur")
    if c:
        if reported:
            c_ico, c_ttl, c_note = "🕐", "이번 실적 · 집계 대기", "(발표 완료 · 실제치 집계 중)"
            c_why = "실적은 발표됐고 Yahoo 실제 수치 집계를 기다리는 중 (집계되면 자동 반영)"
            r_lbl = "예상 EPS / 매출 (실제 대기)"
        else:
            c_ico, c_ttl, c_note = "🔜", "이번 발표 예상", "(곧 발표)"
            c_why = "곧 발표할 분기의 애널리스트 예상치(발표 시 실제와 비교)"
            r_lbl = "예상 EPS / 매출"
        b.append(
            f'<div class="ed-b cur"><div class="ed-t acc">{c_ico} {c_ttl} '
            f'<span class="ed-p">· {_e(c.get("period",""))} {c_note}</span></div>'
            f'<div class="ed-why">{c_why}</div>'
            f'<div class="ed-r"><span>{r_lbl}</span><b>{_e(c.get("eps","-"))} '
            f'<span class="ed-sub">{_e(c.get("eps_range",""))}</span> / '
            f'{_e(c.get("rev","-"))}</b></div></div>')
    n = det.get("next")
    if n:
        gc = up if n.get("growth_pos") else dn
        grow = (f'<div class="ed-r"><span>예상 성장(YoY)</span>'
                f'<b style="color:{gc}">{_e(n["growth"])}</b></div>'
                if n.get("growth") else "")
        b.append(
            f'<div class="ed-b"><div class="ed-t">📊 다음 분기 '
            f'<span class="ed-p">· {_e(n.get("period",""))}</span></div>'
            '<div class="ed-why">그 다음 분기에 대한 애널리스트 평균 예상치</div>'
            f'<div class="ed-r"><span>EPS / 매출</span><b>{_e(n.get("eps","-"))} '
            f'<span class="ed-sub">{_e(n.get("eps_range",""))}</span> / '
            f'{_e(n.get("rev","-"))}</b></div>{grow}</div>')
    t = det.get("target")
    if t and t.get("mean") not in (None, "-"):
        uc = up if t.get("upside_pos") else dn
        ups = (f'<div class="ed-r"><span>상승여력 <span class="ed-sub">'
               f'({_e(t.get("range",""))})</span></span>'
               f'<b style="color:{uc}">{_e(t.get("upside",""))}</b></div>'
               if t.get("upside") else "")
        b.append(
            f'<div class="ed-b"><div class="ed-t">🎯 애널리스트 목표주가</div>'
            '<div class="ed-why">애널리스트가 보는 적정 주가(평균) · 상승여력=현재가 대비</div>'
            f'<div class="ed-r"><span>현재 → 목표평균</span>'
            f'<b>{_e(t.get("price"))} → {_e(t.get("mean"))}</b></div>{ups}</div>')
    r = det.get("rec")
    if r and r.get("label") not in (None, "-"):
        bu, ho, se = r.get("buy") or 0, r.get("hold") or 0, r.get("sell") or 0
        tot = (bu + ho + se) or 1
        bar = (f'<span class="ed-bar"><i style="width:{bu/tot*100:.0f}%;background:{up}"></i>'
               f'<i style="width:{ho/tot*100:.0f}%;background:#f59e0b"></i>'
               f'<i style="width:{se/tot*100:.0f}%;background:{dn}"></i></span>')
        lab = r.get("label") or ""
        lc = up if "매수" in lab else (dn if "매도" in lab else "#f59e0b")
        b.append(
            f'<div class="ed-b"><div class="ed-t">👍 투자의견 '
            f'<span class="ed-p">· 애널리스트 {r.get("count","-")}명</span></div>'
            '<div class="ed-why">애널리스트 매수·보유·매도 의견 종합</div>'
            f'<div class="ed-rec"><b style="color:{lc}">{_e(r.get("label"))}</b>{bar}</div>'
            f'<div class="ed-sub">매수 {bu} · 보유 {ho} · 매도 {se}</div></div>')
    rv = det.get("rev")
    if rv and (rv.get("up") is not None or rv.get("down") is not None):
        b.append(
            f'<div class="ed-b"><div class="ed-t">📈 추정치 리비전 '
            f'<span class="ed-p">· 최근 30일</span></div>'
            '<div class="ed-why">최근 30일간 예상 EPS를 올린/내린 애널리스트 수(상향 우세면 긍정 신호)</div>'
            f'<div class="ed-r"><span>상향 / 하향</span><b>'
            f'<span style="color:{up}">↑{rv.get("up",0)}</span> / '
            f'<span style="color:{dn}">↓{rv.get("down",0)}</span></b></div></div>')
    sp = det.get("surprises")
    if sp:
        mx = max((abs(x["v"]) for x in sp), default=1) or 1
        bars = "".join(
            f'<span class="ed-sbar"><i style="height:{max(4, abs(x["v"])/mx*26):.0f}px;'
            f'background:{up if x["pos"] else dn}"></i>'
            f'<span>{_e(x["fmt"])}</span></span>' for x in sp)
        b.append(
            f'<div class="ed-b"><div class="ed-t">📉 최근 {len(sp)}분기 서프라이즈</div>'
            '<div class="ed-why">실제 실적이 예상을 웃돌면 +상회(빨강), 밑돌면 −하회(파랑)</div>'
            f'<div class="ed-sbars">{bars}</div></div>')
    return "".join(b)


def render_html(body, now=None, links="", quotes=None, mark_new=False,
                schedule=False):
    now = now or datetime.now(KST)
    qmap = quotes or {}
    # 직전 회차 대비 '새 뉴스' 표시용 토큰셋(요청 시에만).
    prev_sets = _prev_item_tokensets(_slug(now)) if mark_new else None
    sections = _split_sections(body)
    ampm = "오전" if now.hour < 12 else "오후"

    # 헤더 (요일은 뱃지, 토/일은 색 구분)
    kicker = now.strftime("%Y.%m.%d") + f" · {ampm} 브리핑"
    dcls = {5: " sat", 6: " sun"}.get(now.weekday(), "")
    dowb = f'<span class="dowb{dcls}">{_DOW[now.weekday()]}</span>'
    sub = f"최종 업데이트 {now.strftime('%H:%M')}"
    built_ep = int(now.timestamp())   # 뷰 시점 경과시간(신선도) 계산용
    pct = _dday_progress(now)
    hd = (f'<header class="hd"><div class="hd-top">'
          f'<span class="hd-kicker">{_e(kicker)}</span>'
          f'<div class="hd-links">{links}'
          f'<button id="authSlot" class="auth-slot">로그인</button></div></div>'
          f'<h1>{ampm} 뉴스 브리핑</h1>'
          f'<div class="hd-sub"><span class="hd-updated">{dowb}'
          f'<span class="hd-uptxt"><span>{_e(sub)}</span>'
          f'<span class="fresh" data-built="{built_ep}"></span></span></span>'
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
                                         quotes=qmap.get(pid),
                                         prev_sets=prev_sets)

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

    # 일정 탭: 좌=경제지표 / 우=기업실적 2단(모바일은 세로로 쌓임, 실적 위)
    sched_html = _render_schedule(_load_econ_events(now), now) if schedule else ""
    if sched_html:
        earn_html = _render_earnings(_load_earnings(now), now)
        navs.append('<button class="nav-t" data-p="tpS">일정</button>')
        panels.append(
            '<div class="panel" id="tpS"><div class="part">'
            '<div class="sub-tabs">'
            '<button class="sub-tab on" data-sub="econ">📅 경제지표</button>'
            '<button class="sub-tab" data-sub="earn">🏢 기업실적</button>'
            '</div>'
            '<div class="sched-2col" data-sub="econ">'
            f'<div class="sched-col econ">{sched_html}</div>'
            f'<div class="sched-col earn">{earn_html}</div>'
            '</div></div></div>')

    # 성장주 탭: SEC 재무(XBRL) 기반 스크리너 + 종목 심층
    funds = _load_fundamentals()
    if funds:
        navs.append('<button class="nav-t" data-p="tpGrow">🔎 성장주</button>')
        panels.append(f'<div class="panel" id="tpGrow">{_render_growth(funds, now)}</div>')

    # 내 목표 탭(로그인 후 자산·매매일지). 로직·UI는 goal-app.js가 #goalRoot에 렌더.
    navs.append('<button class="nav-t" data-p="tpGoal">내 목표</button>')
    panels.append('<div class="panel" id="tpGoal">'
                  '<div id="goalRoot" class="goal-root">'
                  '<div class="goal-msg">불러오는 중…</div></div></div>')

    nav_html = (f'<div class="navwrap"><nav class="nav">{"".join(navs)}</nav></div>'
                if navs else "")

    scripts = (_TAB_JS + (_SCHED_JS if sched_html else "")
               + (_GROWTH_JS if funds else "")
               + '<script type="module" src="goal-app.js"></script>')
    return _shell(SITE_TITLE, hd + gauges_html + nav_html + "".join(panels),
                  script=scripts)


# =========================================================
# 지난 브리핑(캘린더)
# =========================================================
_CAL_JS = """<script>
(function(){
  var DATA = __DATA__;
  var selY=document.getElementById('selY'), selM=document.getElementById('selM'),
      box=document.getElementById('calbox'), det=document.getElementById('det');
  if(!selY) return;
  var DOW=['일','월','화','수','목','금','토'];

  var years={}, ymSet={};
  Object.keys(DATA).forEach(function(d){
    years[d.slice(0,4)]=1; ymSet[d.slice(0,7)]=1;
  });
  var yList=Object.keys(years).sort().reverse();

  function monthsOf(y){
    var ms=[];
    for(var m=1;m<=12;m++){ var mm=('0'+m).slice(-2); if(ymSet[y+'-'+mm]) ms.push(mm); }
    return ms.reverse();
  }
  function fill(sel, vals, fmt){
    sel.innerHTML='';
    vals.forEach(function(v){
      var o=document.createElement('option'); o.value=v; o.textContent=fmt(v); sel.appendChild(o);
    });
  }
  function pick(ds){
    box.querySelectorAll('.day.on').forEach(function(x){x.classList.remove('on');});
    var c=box.querySelector('.day.has[data-d="'+ds+'"]'); if(c) c.classList.add('on');
    var v=DATA[ds]||{}, p=ds.split('-');
    var h='<div class="t">'+p[0].slice(2)+'년 '+(+p[1])+'월 '+(+p[2])+'일</div>';
    if(v.am) h+='<a href="'+v.am+'">오전 브리핑</a>';
    if(v.pm) h+='<a href="'+v.pm+'">오후 브리핑</a>';
    if(!v.am&&!v.pm) h+='<span class="none">브리핑이 없습니다.</span>';
    det.innerHTML=h;
  }
  function render(y,m){
    y=+y; m=+m;
    var first=new Date(y,m-1,1).getDay(), dim=new Date(y,m,0).getDate();
    var html='<div class="grid">';
    for(var i=0;i<7;i++) html+='<div class="dow'+(i===0?' sun':'')+'">'+DOW[i]+'</div>';
    for(var b=0;b<first;b++) html+='<div class="day"></div>';
    var firstHas=null, pad=function(n){return ('0'+n).slice(-2);};
    for(var d=1;d<=dim;d++){
      var ds=y+'-'+pad(m)+'-'+pad(d);
      if(DATA[ds]){ html+='<button class="day has" data-d="'+ds+'">'+d+'</button>'; if(!firstHas) firstHas=ds; }
      else html+='<div class="day">'+d+'</div>';
    }
    box.innerHTML=html+'</div>';
    box.querySelectorAll('.day.has').forEach(function(bt){
      bt.addEventListener('click', function(){ pick(bt.getAttribute('data-d')); });
    });
    if(firstHas) pick(firstHas); else det.innerHTML='';
  }
  function onYear(){
    fill(selM, monthsOf(selY.value), function(m){ return (+m)+'월'; });
    render(selY.value, selM.value);
  }
  selY.addEventListener('change', onYear);
  selM.addEventListener('change', function(){ render(selY.value, selM.value); });

  if(!yList.length){ box.innerHTML=''; return; }
  fill(selY, yList, function(y){ return y+'년'; });
  onYear();
})();
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

    hd = ('<header class="hd"><div class="hd-top">'
          '<span class="hd-kicker">ARCHIVE</span>'
          '<div class="hd-links"><a class="hd-archive" href="../index.html">🏠 홈</a></div>'
          '</div><h1>지난 브리핑</h1>'
          f'<div class="hd-sub">총 {len(days)}일 · '
          f'{sum(len(v) for v in days.values())}회분</div></header>')
    search = ('<div class="search"><input id="q" type="search" autocomplete="off"'
              ' placeholder="지난 브리핑에서 검색 (종목·키워드)"></div>'
              '<div class="results" id="results" style="display:none"></div>')
    # 연·월 드롭다운 + 단일 월 캘린더(그 달만; JS가 DATA 로 그림, 누적 안 함)
    msel = ('<div class="msel"><select id="selY" class="msel-sel"></select>'
            '<select id="selM" class="msel-sel"></select></div>')
    inner = (hd + '<div class="calwrap">' + search
             + '<div id="calview">' + msel
             + '<div class="cal" id="calbox"></div>'
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


FUND_FILE = os.path.join(DATA_DIR, "fundamentals.json")
_GR_SIG = {"g": "#16a37f", "y": "#e0930a", "r": "#e5484d"}
_GR_SIGTXT = {"g": "양호", "y": "주의", "r": "경고"}


def _load_fundamentals():
    try:
        with open(FUND_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _gr_money(m):
    if m is None:
        return "—"
    a, s = abs(m), ("-" if m < 0 else "")
    return f"{s}${a/1000:.1f}B" if a >= 1000 else f"{s}${a:.0f}M"


def _gr_spark(vals, color, zero=False, w=118, h=28):
    pts = [v for v in vals if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    if zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    rng = (hi - lo) or 1.0
    n = len(vals)
    coords = []
    for i, v in enumerate(vals):
        if v is None:
            continue
        x = round(i * w / (n - 1), 1)
        y = round(h - 3 - (v - lo) / rng * (h - 6), 1)
        coords.append(f"{x},{y}")
    base = ""
    if zero:
        zy = round(h - 3 - (0 - lo) / rng * (h - 6), 1)
        base = (f'<line x1="0" y1="{zy}" x2="{w}" y2="{zy}" stroke="var(--border)" '
                f'stroke-width="1" stroke-dasharray="2 2"/>')
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:{h}px;margin-top:6px" '
            f'preserveAspectRatio="none">{base}<polyline points="{" ".join(coords)}" '
            f'fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/></svg>')


def _gr_axis_card(title, ax, spark_svg):
    sig = ax.get("sig", "y")
    col = _GR_SIG[sig]
    return (
        '<div style="background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:12px;flex:1;min-width:132px">'
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{col}"></span>'
        f'<span style="font-size:12px;color:var(--muted)">{title}</span>'
        f'<span style="margin-left:auto;font-size:11px;color:{col};font-weight:700">'
        f'{_GR_SIGTXT[sig]}</span></div>'
        f'<div style="font-size:13.5px;font-weight:700;color:var(--ink)">{_e(ax.get("lab",""))}</div>'
        f'{spark_svg}</div>')


def _gr_deep(d):
    tk = _e(d["ticker"])
    col = _ticker_color(d["ticker"])
    ax = d.get("axes", {})
    sc = d.get("score", 0)
    sc_col = "#16a37f" if sc >= 78 else "#e0930a" if sc >= 55 else "#e5484d"
    revs = [q.get("v") for q in d.get("series", {}).get("rev", [])]
    opis = d.get("series", {}).get("opi", [])
    revsr = d.get("series", {}).get("rev", [])
    opms = []
    for r, o in zip(revsr, opis):
        rv, ov = r.get("v"), o.get("v")
        opms.append(round(ov / rv * 100, 1) if (rv and ov is not None) else None)

    head = (
        '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px">'
        f'<button class="gr-back" style="border:1px solid var(--border);background:var(--card);'
        'color:var(--muted);border-radius:8px;padding:5px 9px;font:inherit;font-size:12px;'
        'cursor:pointer">← 목록</button>'
        f'<div style="width:40px;height:40px;border-radius:10px;background:{col}22;color:{col};'
        'display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px">'
        f'{tk}</div><div><div style="font-size:16px;font-weight:800;color:var(--ink)">'
        f'{_e(d["name"])} <span style="font-size:12px;font-weight:600;color:var(--faint)">'
        f'{_e(d.get("sector",""))}</span></div>'
        f'<div style="font-size:11.5px;color:var(--muted-2)">기준 {_e(d.get("asof",""))} · '
        f'매출 {_gr_money(d.get("rev"))} · SEC XBRL</div></div>'
        f'<div style="margin-left:auto;text-align:center"><div style="font-size:30px;font-weight:800;'
        f'line-height:1;color:{sc_col}">{sc}</div>'
        '<div style="font-size:10px;color:var(--faint)">종합점수/100</div></div></div>')

    verdict = (
        '<div style="background:var(--chip);border-radius:12px;padding:12px 14px;margin-bottom:16px;'
        'font-size:13px;line-height:1.6;color:var(--ink)">'
        f'<b style="color:{sc_col}">{_e(d.get("tag",""))}</b> · '
        f'{_e(ax.get("growth",{}).get("lab",""))}, {_e(ax.get("path",{}).get("lab",""))}, '
        f'{_e(ax.get("balance",{}).get("lab",""))}. '
        f'주주가치: {_e(ax.get("shareholder",{}).get("lab",""))}.</div>')

    cards = (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">'
        + _gr_axis_card("① 성장", ax.get("growth", {}), _gr_spark(revs, "#3a6fd8"))
        + _gr_axis_card("② 수익성 경로", ax.get("path", {}), _gr_spark(opms, "#e0930a", zero=True))
        + _gr_axis_card("③ 재무 건전성", ax.get("balance", {}), "")
        + _gr_axis_card("④ 주주가치", ax.get("shareholder", {}), "")
        + '</div>')

    # 매출 막대
    rmax = max([v for v in revs if v is not None] or [1])
    bars = ""
    for q in revsr:
        v = q.get("v")
        hpct = round((v or 0) / rmax * 100)
        last = q is revsr[-1]
        bg = "#3a6fd8" if last else "#3a6fd855"
        bars += (f'<div title="{_e(q.get("cq",""))}: {_gr_money(v)}" style="flex:1;background:{bg};'
                 f'border-radius:3px 3px 0 0;height:{max(hpct,3)}%"></div>')
    story = (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">'
        '<div style="flex:1;min-width:240px;background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:14px">'
        '<div style="font-size:12px;color:var(--muted);margin-bottom:10px">매출 성장 (분기)</div>'
        f'<div style="display:flex;align-items:flex-end;gap:5px;height:80px">{bars}</div>'
        f'<div style="font-size:12px;color:var(--ink);margin-top:8px">최근 {_gr_money(d.get("rev"))}'
        + (f' · <span style="color:#e5484d">YoY {d["rev_yoy"]:+.0f}%</span>' if d.get("rev_yoy") is not None else "")
        + '</div></div>'
        '<div style="flex:1;min-width:240px;background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:14px">'
        '<div style="font-size:12px;color:var(--muted);margin-bottom:10px">적자 갭 (영업이익률 %)</div>'
        f'{_gr_spark(opms, "#e0930a", zero=True, h=70)}'
        f'<div style="font-size:12px;color:var(--ink);margin-top:8px">현재 '
        + (f'{d["opm"]:+.0f}%' if d.get("opm") is not None else "—")
        + (f' · Δ{d["opm_delta"]:+.0f}%p (전년비)' if d.get("opm_delta") is not None else "")
        + '</div></div></div>')

    # 부채→자산 브릿지
    bridge = ""
    br = d.get("bridge")
    if br and br.get("d_debt") and br.get("capex"):
        dd, cx = br["d_debt"], br["capex"]
        ratio = min(100, round(cx / dd * 100)) if dd else 0
        good = ratio >= 60
        msg = (f'늘어난 부채의 {ratio}%가 설비투자(CapEx)로 유입 → '
               + ("<b style=\"color:#16a37f\">투자형 성장</b>" if good
                  else "<b style=\"color:#e5484d\">일부만 투자·점검 필요</b>"))
        bridge = (
            '<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;'
            'padding:14px;margin-bottom:14px">'
            f'<div style="font-size:12px;color:var(--muted);margin-bottom:8px">부채 → 자산 브릿지 · '
            f'지난 1년 부채 {_gr_money(dd)} 증가</div>'
            '<div style="display:flex;height:26px;border-radius:6px;overflow:hidden;gap:2px;margin-bottom:8px">'
            f'<div style="width:{ratio}%;background:#16a37f;min-width:2px"></div>'
            f'<div style="width:{100-ratio}%;background:#cbd5e1"></div></div>'
            f'<div style="font-size:12px;color:var(--ink);line-height:1.5">CapEx {_gr_money(cx)} · {msg}</div></div>')

    # 커스텀 지표(정량 자동 계산)
    runway = "흑자" if (d.get("fcf") or 0) > 0 else (
        f'{round(d["cash"]/(abs(d["fcf"])/12))}개월'
        if (d.get("cash") and d.get("fcf")) else "—")
    rule40 = (round((d.get("rev_yoy") or 0) + (d.get("opm") or 0))
              if (d.get("rev_yoy") is not None and d.get("opm") is not None) else None)
    rnd_txt = f'{d["rnd_pct"]:.0f}%' if d.get("rnd_pct") is not None else "—"
    metrics = (
        '<div style="font-size:12px;font-weight:700;color:var(--muted);margin:6px 0 8px">내 지표(정량 자동)</div>'
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">'
        f'{_gr_kpi("런웨이(현금÷소진)", runway)}'
        f'{_gr_kpi("룰40(성장+마진)", (str(rule40)+"pt") if rule40 is not None else "—")}'
        f'{_gr_kpi("R&D/매출", rnd_txt)}'
        f'{_gr_kpi("FCF(TTM)", _gr_money(d.get("fcf")))}'
        '</div>')

    note = ('<div style="font-size:11.5px;color:var(--faint);margin-top:12px">'
            '수치는 SEC 공시(XBRL·10-K) 원본 기반이며 정성 요약은 AI가 작성했습니다. '
            '투자 판단의 책임은 본인에게 있습니다.</div>')

    return (f'<div class="gr-card" data-tk="{tk}" style="display:none">'
            + head + verdict + cards + story + bridge + metrics
            + _gr_qual(d) + note + '</div>')


def _gr_qual(d):
    q = d.get("qual")
    if not q:
        return ('<div style="font-size:11.5px;color:var(--faint);margin-top:14px">'
                '해자·산업 필연성 등 정성 분석은 10-K 수집 후 표시됩니다.</div>')
    ms = d.get("moat_score")
    cards = (("경쟁 우위 (해자)", q.get("moat", "")),
             ("산업 필연성", q.get("necessity", "")),
             ("확장 시나리오", q.get("expansion", "")))
    inner = "".join(
        '<div style="flex:1;min-width:180px;background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:13px">'
        f'<div style="font-size:12px;color:var(--accent);margin-bottom:5px;font-weight:700">{_e(t)}</div>'
        f'<div style="font-size:12.5px;color:var(--ink);line-height:1.6">{_e(v)}</div></div>'
        for t, v in cards if v)
    risk = ""
    if q.get("risk_note"):
        risk = ('<div style="background:var(--chip);border-radius:10px;padding:10px 12px;'
                'margin-top:10px;font-size:12px;color:var(--ink);line-height:1.55">'
                f'<b style="color:#e5484d">핵심 리스크</b> · {_e(q["risk_note"])}</div>')
    head = ('<div style="display:flex;align-items:center;gap:8px;margin:18px 0 9px;flex-wrap:wrap">'
            '<span style="font-size:12px;font-weight:700;color:var(--muted)">정성 분석</span>'
            + (f'<span style="font-size:11px;color:var(--muted-2)">해자 {ms}점</span>'
               if ms is not None else "")
            + f'<span style="margin-left:auto;font-size:10.5px;color:var(--faint)">'
            + f'10-K {_e(q.get("src",""))} · AI 요약</span></div>')
    return head + '<div style="display:flex;gap:10px;flex-wrap:wrap">' + inner + '</div>' + risk


def _gr_kpi(label, val):
    return ('<div style="flex:1;min-width:120px;background:var(--chip);border-radius:9px;padding:10px 12px">'
            f'<div style="font-size:11px;color:var(--muted-2)">{_e(label)}</div>'
            f'<div style="font-size:18px;font-weight:800;color:var(--ink)">{_e(str(val))}</div></div>')


def _gr_row(d):
    tk = _e(d["ticker"])
    col = _ticker_color(d["ticker"])
    sc = d.get("score", 0)
    sc_col = "#16a37f" if sc >= 78 else "#e0930a" if sc >= 55 else "#e5484d"
    ax = d.get("axes", {})
    dots = "".join(
        f'<span style="width:8px;height:8px;border-radius:50%;background:{_GR_SIG[ax.get(k,{}).get("sig","y")]}"></span>'
        for k in ("growth", "path", "balance", "shareholder"))
    yoy = d.get("rev_yoy")
    yoy_txt = (f'{yoy:+.0f}%' if yoy is not None else "—")
    return (
        f'<div class="gr-row" data-tk="{tk}" data-score="{sc}" '
        'style="display:flex;align-items:center;gap:10px;padding:11px 12px;background:var(--card);'
        'border:1px solid var(--border);border-radius:12px;cursor:pointer">'
        f'<div style="width:34px;height:34px;border-radius:8px;background:{col}22;color:{col};'
        'display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;'
        f'flex-shrink:0">{tk}</div>'
        '<div style="min-width:0;flex:1">'
        f'<div style="font-size:13px;font-weight:700;color:var(--ink)">{_e(d["name"])}</div>'
        f'<div style="font-size:11px;color:var(--muted-2);white-space:nowrap;overflow:hidden;'
        f'text-overflow:ellipsis">{_e(d.get("tag",""))}</div></div>'
        f'<div style="font-size:20px;font-weight:800;color:{sc_col};flex-shrink:0;width:32px;'
        'text-align:center">' + str(sc) + '</div>'
        f'<div style="display:flex;gap:4px;flex-shrink:0">{dots}</div>'
        f'<div style="font-size:13px;font-weight:700;color:#e5484d;width:48px;text-align:right;'
        f'flex-shrink:0">{yoy_txt}</div></div>')


_GROWTH_JS = """<script>
(function(){
 var sc=document.getElementById('grScreener'), dp=document.getElementById('grDeep');
 if(!sc||!dp) return;
 function show(tk){
   dp.querySelectorAll('.gr-card').forEach(function(c){c.style.display=c.getAttribute('data-tk')===tk?'block':'none';});
   sc.style.display='none'; dp.style.display='block'; window.scrollTo(0,0);
 }
 function back(){ dp.style.display='none'; sc.style.display='block'; }
 sc.querySelectorAll('.gr-row').forEach(function(r){
   r.addEventListener('click',function(){show(r.getAttribute('data-tk'));});
 });
 dp.querySelectorAll('.gr-back').forEach(function(b){b.addEventListener('click',back);});
 sc.querySelectorAll('.gr-preset').forEach(function(p){
   p.addEventListener('click',function(){
     sc.querySelectorAll('.gr-preset').forEach(function(x){x.style.opacity='.55';});
     p.style.opacity='1'; var f=p.getAttribute('data-f');
     sc.querySelectorAll('.gr-row').forEach(function(r){
       var ok=(f==='all')||(f==='profit'&&r.getAttribute('data-g0')==='g')||
              (f==='turn'&&r.getAttribute('data-turn')==='1')||
              (f==='cash'&&r.getAttribute('data-cash')==='g');
       r.style.display=ok?'flex':'none';
     });
   });
 });
})();
</script>"""


def _render_growth(funds, now):
    funds = sorted(funds, key=lambda x: -x.get("score", 0))
    presets = (
        '<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px">'
        '<span class="gr-preset" data-f="all" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--ink);cursor:pointer;opacity:1">전체</span>'
        '<span class="gr-preset" data-f="profit" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--muted-2);cursor:pointer;opacity:.55">고성장·흑자</span>'
        '<span class="gr-preset" data-f="turn" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--muted-2);cursor:pointer;opacity:.55">적자 갭 축소</span>'
        '<span class="gr-preset" data-f="cash" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--muted-2);cursor:pointer;opacity:.55">순현금</span></div>')
    rows = []
    for d in funds:
        r = _gr_row(d)
        ax = d.get("axes", {})
        g0 = ax.get("growth", {}).get("sig")
        turn = "1" if (d.get("opm_delta") or 0) >= 3 and (d.get("opm") or 0) < 0 else "0"
        cashsig = ax.get("balance", {}).get("sig")
        r = r.replace('data-score="', f'data-g0="{g0}" data-turn="{turn}" data-cash="{cashsig}" data-score="', 1)
        rows.append(r)
    legend = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:11px;'
        'color:var(--faint)">'
        + "".join(f'<span style="display:inline-flex;align-items:center;gap:5px">'
                  f'<span style="width:8px;height:8px;border-radius:50%;background:{_GR_SIG[s]}"></span>'
                  f'{_GR_SIGTXT[s]}</span>' for s in ("g", "y", "r"))
        + '<span>4축 = 성장·수익성경로·재무건전성·주주가치 · 점수순</span></div>')
    head = ('<div class="sched-head" style="margin-bottom:12px"><span>'
            '<span class="sched-ico">🔎</span>성장주 '
            f'<span class="sched-tz">SEC 재무 · {len(funds)}종목</span></span></div>')
    screener = (f'<div id="grScreener">{head}{presets}'
                f'<div style="display:flex;flex-direction:column;gap:7px">{"".join(rows)}</div>'
                f'{legend}</div>')
    deep = ('<div id="grDeep" style="display:none">'
            + "".join(_gr_deep(d) for d in funds) + '</div>')
    return f'<div class="part">{screener}{deep}</div>'


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
               render_html(body, now=now, links=_LINKS_SNAP, quotes=quotes,
                           mark_new=True))
        latest = (body, now, quotes)
    if latest:
        _write(os.path.join(DOCS_DIR, "index.html"),
               render_html(latest[0], now=latest[1], links=_LINKS_HOME,
                           quotes=latest[2], mark_new=True, schedule=True))
    _write(os.path.join(ARCHIVE_DIR, "index.html"), render_archive_index())
    return len(files)


def publish(body, now=None, quotes=None):
    """최신 페이지 + 회차 스냅샷 + 캘린더 생성. 최신 경로 반환."""
    now = now or datetime.now(KST)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    _save_body(body, now)
    _save_quotes(quotes, now)
    _write(os.path.join(ARCHIVE_DIR, _slug(now) + ".html"),
           render_html(body, now=now, links=_LINKS_SNAP, quotes=quotes,
                       mark_new=True))
    path = os.path.join(DOCS_DIR, "index.html")
    _write(path, render_html(body, now=now, links=_LINKS_HOME, quotes=quotes,
                             mark_new=True, schedule=True))
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
