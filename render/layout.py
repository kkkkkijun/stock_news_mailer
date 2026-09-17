# -*- coding: utf-8 -*-
"""페이지 셸(HEAD/CSS/스크립트)과 브리핑 본문 렌더링(publish_site.py 분리)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from render import assets, clock
from render.common import _dday_progress, _dday_text, _e, _event_ddays
from render.config import DDAY_TARGET, HERO_PARTS, PARTS, SITE_TITLE, SLOGAN, TABS, _DOW
from render.earnings import _render_earnings
from render.files import _load_earnings, _load_econ_events, _load_fundamentals, _slug
from render.growth import _render_growth
from render.news import _render_part
from render.parse import _fear_greed, _mood_color, _prev_item_tokensets, _split_sections
from render.rwamap import _render_rwa
from render.schedule import _render_schedule

HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#0f1b2d">
<link rel="manifest" href="/stock_news_mailer/manifest.webmanifest">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="MARKET BRIEF">
<link rel="apple-touch-icon" href="/stock_news_mailer/icon-180.png">
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
.ev.has-res{align-items:flex-start;}
.ev.has-res .igauge{margin-top:5px;}
.ev.has-res .ev-t{padding-top:1px;}
.ev.past .ev-t{color:var(--faint);}
.ev-body{flex:1;min-width:0;}
.ev-body .ev-n{display:flex;align-items:center;gap:6px;flex-wrap:wrap;}
.ev-done{font-size:9px;font-weight:800;color:#fff;background:var(--ink);border-radius:5px;
 padding:2px 5px;letter-spacing:.02em;}
.ev-res{display:flex;align-items:center;gap:7px;margin-top:5px;font-size:10.5px;font-weight:600;
 color:var(--muted);white-space:nowrap;flex-wrap:wrap;}
.ev-res .act{font-size:12.5px;font-weight:800;color:var(--ink);}
.ev-res .k{color:var(--faint);margin-right:2px;}
.ev-vs{font-size:10px;font-weight:800;border-radius:6px;padding:2px 6px;line-height:1.3;}
.ev-vs.beat{color:#e5484d;background:rgba(229,72,77,.12);}
.ev-vs.miss{color:#3b82f6;background:rgba(59,130,246,.12);}
.ev-vs.inl{color:var(--muted);background:var(--nav-track);}
.ev-pre{display:flex;gap:8px;margin-top:4px;font-size:10.5px;color:var(--faint);font-weight:600;}
.ev-pre b{color:var(--muted);font-weight:700;}
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
/* A안: 언더라인 서브탭(주식 탭) — 상단 뉴스탭과 통일감 */
.sub-tabs.sub-underline{gap:22px;background:none;border-radius:0;padding:0 2px;
 border-bottom:1px solid var(--border);}
.sub-underline .sub-tab{flex:none;font-size:14px;font-weight:800;color:var(--faint);
 background:none;border-radius:0;padding:8px 2px 11px;position:relative;
 display:flex;align-items:center;gap:6px;}
.sub-underline .sub-tab.on{background:none;color:var(--ink);}
.sub-underline .sub-tab.on::after{content:"";position:absolute;left:0;right:0;
 bottom:-1px;height:2.5px;background:var(--ink);border-radius:2px;}
.sub-underline .subcnt{font-size:11px;font-weight:700;color:var(--faint);
 background:var(--nav-track);border-radius:999px;padding:1px 7px;}
.sub-underline .sub-tab.on .subcnt{color:#fff;background:var(--ink);}
.sub-pane .part-head{display:none;}   /* 서브탭이 제목 역할 → 파트 헤더 중복 제거 */
.tk-groups{display:flex;flex-direction:column;gap:10px;}
.tk-group{background:var(--card);border:1px solid var(--border);border-radius:14px;
 padding:12px 13px;box-shadow:0 1px 3px var(--shadow);}
.tk-ghead{display:flex;align-items:center;gap:9px;}
.tk-badge{font-size:12px;font-weight:800;border-radius:7px;padding:3px 9px;
 font-family:ui-monospace,monospace;flex:none;}
.tk-name{font-size:12.5px;font-weight:700;color:var(--muted);}
.tk-group .news.tk-item{background:transparent;border:0;box-shadow:none;
 padding:11px 0 0;margin:0;}
.tk-group .tk-item + .tk-item{border-top:1px solid var(--border);margin-top:0;padding-top:11px;}
.tk-group .tk-rest .tk-item:first-child{border-top:1px solid var(--border);padding-top:11px;}
.tk-rest{display:none;}
.tk-group.open .tk-rest{display:block;}
.tk-more{width:100%;margin-top:10px;font:inherit;font-size:12px;font-weight:700;
 color:var(--accent);background:var(--chip);border:1px solid var(--border);
 border-radius:9px;padding:8px;cursor:pointer;}
.tk-caret{font-size:10px;}
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
.hd{padding:30px 40px;background:var(--header);color:#fff;
 padding-top:calc(30px + env(safe-area-inset-top,0px));}
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
#pushBtn{cursor:pointer;font-family:inherit;border:0;}
#pushBtn[data-on]{background:rgba(92,157,255,.28);color:#cfe0ff;opacity:1;}
.hd h1{font-size:27px;font-weight:700;margin:16px 0 5px;letter-spacing:-.01em;}
.hd-sub{display:flex;justify-content:space-between;align-items:center;gap:10px;
 font-size:13px;color:#94a3b8;}
.hd-left{display:flex;flex-direction:column;gap:9px;align-items:flex-start;}
.hd-updated{display:flex;align-items:flex-start;gap:6px;}
/* 단기 이벤트 디데이 pill(요일 배지와 같은 형태, 연한 빨강) */
.hd-ev{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;font-weight:700;
 color:#ffd6d6;background:rgba(255,120,120,.16);border:1px solid rgba(255,140,140,.28);
 padding:4px 11px 4px 8px;border-radius:999px;white-space:nowrap;}
.hd-ev b{font-size:12.5px;color:#fff;letter-spacing:.02em;}
.hd-ev-dt{color:#f3b4b4;font-weight:600;opacity:.85;}
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
@media (max-width:600px){#top,#theme{bottom:calc(16px + env(safe-area-inset-bottom,0px));
 width:42px;height:42px;line-height:40px;font-size:18px;}#top{right:16px;}#theme{left:16px;}}

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
  .hd,.gauges,.navwrap,.part,.ft,.calwrap{
    padding-left:calc(18px + env(safe-area-inset-left,0px));
    padding-right:calc(18px + env(safe-area-inset-right,0px));}
  .hd h1{font-size:22px;}
  .nav a{font-size:12px;padding:8px 3px;}
}
"""


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

_PWA_JS = """<script>
if('serviceWorker' in navigator){
  window.addEventListener('load', function(){
    navigator.serviceWorker.register('/stock_news_mailer/sw.js').catch(function(){});
  });
}
</script>
<script src="/stock_news_mailer/push.js" defer></script>"""


def _shell(title, inner, extra_head="", script="", rail="", asset_prefix=""):
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
{HEAD}
<title>{_e(title)}</title>{extra_head}
{assets.tag_css(asset_prefix)}
</head>
<body>
<div class="wrap"><div class="page">
{inner}
<footer class="ft">기사 요약은 각 언론사 보도를 바탕으로 자동 생성되었으며, 저작권은 해당 언론사에 있습니다. 정보 제공 목적이며 투자 판단의 책임은 본인에게 있습니다.</footer>
</div>{rail}</div>
<button id="theme" aria-label="다크/라이트 테마 전환" title="테마 전환">🌙</button>
<button id="top" aria-label="맨 위로">↑</button>
{script}{assets.site_scripts_tag(asset_prefix)}
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
document.querySelectorAll('.sub-tab').forEach(function(b){
  b.addEventListener('click', function(){
    var host = b.parentNode.parentNode, sub = b.getAttribute('data-sub');
    var col = host.querySelector('.sched-2col');
    if(col) col.setAttribute('data-sub', sub);
    host.querySelectorAll('.sub-pane').forEach(function(p){
      p.style.display = (p.getAttribute('data-pane')===sub) ? '' : 'none';
    });
    b.parentNode.querySelectorAll('.sub-tab').forEach(function(x){x.classList.remove('on');});
    b.classList.add('on');
  });
});
document.querySelectorAll('.tk-more').forEach(function(b){
  b.addEventListener('click', function(){
    var g=b.closest('.tk-group'); if(!g) return;
    var open=g.classList.toggle('open');
    b.innerHTML = open ? '접기 <span class="tk-caret">▴</span>'
                       : '뉴스 '+b.getAttribute('data-n')+'건 더 보기 <span class="tk-caret">▾</span>';
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


def _render_header(now: datetime, ampm: str, links: str) -> str:
    """헤더(kicker/제목/최종 업데이트/D-day 진행바) HTML 조각을 만든다."""
    kicker = now.strftime("%Y.%m.%d") + " · MARKET BRIEF"
    dcls = {5: " sat", 6: " sun"}.get(now.weekday(), "")
    dowb = f'<span class="dowb{dcls}">{_DOW[now.weekday()]}</span>'
    sub = f"최종 업데이트 {now.strftime('%H:%M')}"
    built_ep = int(now.timestamp())   # 뷰 시점 경과시간(신선도) 계산용
    pct = _dday_progress(now)
    pills = "".join(
        f'<span class="hd-ev">{_e(label)} <b>{_e(dtxt)}</b> <span class="hd-ev-dt">{_e(dt)}</span></span>'
        for label, dtxt, dt in _event_ddays(now))
    return (f'<header class="hd"><div class="hd-top">'
            f'<span class="hd-kicker">{_e(kicker)}</span>'
            f'<div class="hd-links">{links}'
            f'<button id="pushBtn" class="hd-archive" onclick="togglePush()">🔔 알림</button>'
            f'<button id="authSlot" class="auth-slot">로그인</button></div></div>'
            f'<h1>{ampm} 뉴스 브리핑</h1>'
            f'<div class="hd-sub"><div class="hd-left"><span class="hd-updated">{dowb}'
            f'<span class="hd-uptxt"><span>{_e(sub)}</span>'
            f'<span class="fresh" data-built="{built_ep}"></span></span></span>'
            f'{pills}</div>'
            f'<span class="hd-slogan">{_e(SLOGAN)}'
            f'<span class="hd-pct">{_e(_dday_text(now))} · {pct:.2f}%</span>'
            f'<span class="hd-bar"><i style="width:{pct:.3f}%"></i></span>'
            f'<span class="hd-target">목표일 {DDAY_TARGET:%Y.%m.%d}</span>'
            f'</span></div></header>')


def _render_gauges(sections: list[tuple[str, list[str]]]) -> str:
    """공포탐욕 게이지(최대 2개) HTML 조각을 만든다. 대상이 없으면 빈 문자열."""
    gauges = []
    for name, val, grade in _fear_greed(sections)[:2]:
        color = _mood_color(val)
        gauges.append(
            f'<div class="gauge"><div class="gauge-label">{_e(name)}</div>'
            f'<div class="gauge-row"><span class="gauge-num">{_e(val)}</span>'
            f'<span class="gauge-mood" style="background:{color};">{_e(grade)}</span></div>'
            f'<div class="gauge-track"><div class="gauge-marker" style="left:{val}%;"></div></div>'
            '<div class="gauge-scale"><span>공포</span><span>탐욕</span></div></div>')
    return f'<div class="gauges">{"".join(gauges)}</div>' if gauges else ""


def _render_parts(sections: list[tuple[str, list[str]]], qmap: dict[str, Any],
                   prev_sets: dict[str, set[str]] | None) -> dict[str, str]:
    """본문에 실제로 존재하는 파트만 렌더링해 {part_id: html} 딕셔너리로 반환."""
    rendered = {}
    for pid, icon, name, key in PARTS:
        lines = next((ls for t, ls in sections if key in t), None)
        if lines is not None:
            rendered[pid] = _render_part(pid, icon, name, lines,
                                         hero=(pid in HERO_PARTS),
                                         quotes=qmap.get(pid),
                                         prev_sets=prev_sets,
                                         group_by_ticker=(pid in {"os", "coin"}))
    return rendered


def _render_tab_panels(rendered: dict[str, str]) -> tuple[list[str], list[str]]:
    """TABS 구성에 따라 (nav 버튼 목록, panel HTML 목록)을 만든다.

    주식(os)·코인(coin)이 함께 있으면 서브탭(밑줄 스타일)으로 감싼다."""
    _PART_META = {pid: (icon, nm) for pid, icon, nm, _k in PARTS}
    navs, panels, first = [], [], True
    for i, (tab, pids) in enumerate(TABS):
        have = [p for p in pids if p in rendered]
        if not have:
            continue
        if pids == ["os", "coin"] and len(have) > 1:
            btns, panes = [], []
            for j, p in enumerate(have):
                _pico, pnm = _PART_META.get(p, ("", p))
                ons = " on" if j == 0 else ""
                sty = "" if j == 0 else ' style="display:none"'
                cnt = rendered[p].count('class="tk-ghead"')   # 종목 수
                cntchip = f' <span class="subcnt">{cnt}</span>' if cnt else ""
                btns.append(f'<button class="sub-tab{ons}" data-sub="{p}">'
                            f'{_e(pnm)}{cntchip}</button>')
                panes.append(f'<div class="sub-pane" data-pane="{p}"{sty}>'
                             f'{rendered[p]}</div>')
            inner = ('<div class="stock-wrap"><div class="sub-tabs sub-underline">'
                     + "".join(btns) + '</div>' + "".join(panes) + '</div>')
        else:
            inner = "".join(rendered[p] for p in have)
        on = " on" if first else ""
        navs.append(f'<button class="nav-t{on}" data-p="tp{i}">{_e(tab)}</button>')
        panels.append(f'<div class="panel{on}" id="tp{i}">{inner}</div>')
        first = False
    return navs, panels


def _render_extra_panels(now: datetime, schedule: bool,
                          navs: list[str], panels: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """일정/성장주/지도/내 목표 탭을 navs·panels에 이어붙이고 (sched_html, funds)를 반환.

    반환값은 이후 스크립트 태그 조립(assets.tag 조건)에 쓰인다."""
    # 일정 탭: 좌=경제지표 / 우=기업실적 2단(모바일은 세로로 쌓임, 실적 위)
    # 일정(경제지표)은 브리핑 시각이 아닌 "실제 현재 시각" 기준 — 재빌드(refresh) 때도
    # 발표된 높음 지표 결과가 유지되도록.
    _now_live = clock.now()
    sched_html = (_render_schedule(_load_econ_events(_now_live), _now_live)
                  if schedule else "")
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

    # 🗺️ 지도 탭: Ostium(주식·지수·원자재) + Hyperliquid 고래(암호화폐) 심리 지도.
    # 암호화폐 카테고리는 JS가 whales.json(기존 고래 데이터)에서 읽는다.
    navs.append('<button class="nav-t" data-p="tpMap">🗺️ 지도</button>')
    panels.append(f'<div class="panel" id="tpMap">{_render_rwa()}</div>')

    # 내 목표 탭(로그인 후 자산·매매일지). 로직·UI는 goal-app.js가 #goalRoot에 렌더.
    navs.append('<button class="nav-t" data-p="tpGoal">내 목표</button>')
    panels.append('<div class="panel" id="tpGoal">'
                  '<div id="goalRoot" class="goal-root">'
                  '<div class="goal-msg">불러오는 중…</div></div></div>')
    return sched_html, funds


def render_html(body: str, now: datetime | None = None, links: str = "",
                 quotes: dict[str, Any] | None = None, mark_new: bool = False,
                 schedule: bool = False, asset_prefix: str = "") -> str:
    """브리핑 본문(plain text)을 완성된 페이지 HTML로 렌더링한다.

    schedule=True 인 경우(홈)에만 경제지표/기업실적 '일정' 탭을 채워 넣는다."""
    now = now or clock.now()
    qmap = quotes or {}
    # 직전 회차 대비 '새 뉴스' 표시용 토큰셋(요청 시에만).
    prev_sets = _prev_item_tokensets(_slug(now)) if mark_new else None
    sections = _split_sections(body)
    ampm = "오전" if now.hour < 12 else "오후"

    hd = _render_header(now, ampm, links)
    gauges_html = _render_gauges(sections)

    rendered = _render_parts(sections, qmap, prev_sets)
    navs, panels = _render_tab_panels(rendered)
    sched_html, funds = _render_extra_panels(now, schedule, navs, panels)

    nav_html = (f'<div class="navwrap"><nav class="nav">{"".join(navs)}</nav></div>'
                if navs else "")

    scripts = (assets.tag("tab.js", asset_prefix)
               + (assets.tag("sched.js", asset_prefix) if sched_html else "")
               + (assets.tag("growth.js", asset_prefix) if funds else "")
               + assets.tag("rwa.js", asset_prefix)
               + '<script type="module" src="goal-app.js"></script>')
    return _shell(SITE_TITLE, hd + gauges_html + nav_html + "".join(panels),
                  script=scripts, asset_prefix=asset_prefix)
