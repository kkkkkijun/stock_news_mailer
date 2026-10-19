# -*- coding: utf-8 -*-
"""페이지 셸(HEAD/CSS/스크립트)과 브리핑 본문 렌더링(publish_site.py 분리)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from render import assets, clock
from render.common import _dday_progress, _dday_text, _e, _event_ddays
from render.config import DDAY_TARGET, HERO_PARTS, PARTS, SITE_TITLE, SLOGAN, TABS, _DOW
from settings import EARNINGS_TICKERS
from render.calview import _render_calendar
from render.earnings import _render_earn_results
from render.files import (_load_earnings, _load_econ_events, _load_fundamentals, _load_prices,
                          _load_backtest, _load_reports, _load_score_history, _load_screen, _load_universe,
                          _load_us_holidays, _slug)
from render.growth import _render_growth, write_growth_fragments
from render.news import _render_part
from render.parse import _fear_greed, _mood_color, _prev_item_tokensets, _split_sections
from render.rwamap import _render_rwa

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
<link rel="icon" type="image/png" sizes="192x192" href="/stock_news_mailer/icon-192.png">
<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>
<link rel="preload" as="style" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" onload="this.onload=null;this.rel='stylesheet'">
<noscript><link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"></noscript>
<script>(function(){try{var t=localStorage.getItem('theme');if(t!=='dark'&&t!=='light'){t=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';}document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"""

CSS = """
:root{
 --bg:#e8ecf1;--page:#f6f8fb;--border:#e6ebf2;
 --ink:#0f1b2d;--ink-2:#1e293b;--muted:#475569;--muted-2:#5b6b80;--faint:#6b7280;
 --card:#fff;--chip:#eaf0fb;--accent:#3a6fd8;--header:#0f1b2d;--nav-track:#eef2f7;
 --hover:#dbe6f8;--chip-ink:#2a56b3;--shadow:rgba(15,27,45,.10);}
/* 라이트 모드 보조 텍스트(--faint/--muted-2/--chip-ink)는 흰 배경 대비 4.5:1 이상(WCAG AA)으로 맞춘 값 */
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
/* 주식 탭 서브탭: 알약형 토글(미국증시 · 코인) */
.sub-tabs.sub-pill{display:inline-flex;gap:2px;padding:4px;border-radius:999px;margin:14px 0 0 40px}   /* 왼쪽 = .part 좌우 여백(본문·상단 탭과 같은 선) */
@media (max-width:600px){.sub-tabs.sub-pill{margin-left:calc(18px + env(safe-area-inset-left,0px))}}
.sub-pill .sub-tab{flex:none;display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:700;
 color:var(--muted-2);border-radius:999px;padding:6px 15px 6px 7px;transition:background .15s,color .15s}
.sub-pill .sub-tab:hover{color:var(--ink)}
.sub-pill .sub-tab.on{background:var(--card);color:var(--ink);font-weight:800;
 box-shadow:0 1px 3px rgba(15,27,45,.14),0 0 0 1px rgba(15,27,45,.04)}
:root[data-theme="dark"] .sub-pill .sub-tab.on{background:#262e3b;box-shadow:0 0 0 1px var(--border),0 1px 3px rgba(0,0,0,.4)}
.pill-ico{width:20px;height:20px;flex-shrink:0;display:block}
.sub-pill .sub-tab:not(.on) .pill-ico{opacity:.85}
.sub-pane .part-head{display:none;}   /* 서브탭이 제목 역할 → 파트 헤더 중복 제거 */
/* 주식 탭 뉴스(B안): 종목 카드 = 머리(가격·추이) + 한 줄 총평·호재/악재 비율 + 기사 한 줄 목록 */
.tk-badge{font-size:12px;font-weight:800;border-radius:7px;padding:3px 9px;
 font-family:ui-monospace,monospace;flex:none;}
.nb-bar{display:flex;gap:6px;align-items:center;margin:4px 0 10px;flex-wrap:wrap}
.nb-f{font:inherit;font-size:12px;font-weight:700;color:var(--muted-2);background:var(--card);
 border:1px solid var(--border);border-radius:999px;padding:5px 12px;cursor:pointer}
.nb-f.on{background:var(--ink);color:var(--page);border-color:var(--ink)}
.nb-sort{margin-left:auto;font:inherit;font-size:12px;font-weight:700;color:var(--muted-2);background:transparent;
 border:0;padding:4px 2px;cursor:pointer}
.nb-list{display:flex;flex-direction:column;gap:10px}
.nb-card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;
 box-shadow:0 1px 3px var(--shadow)}
.nb-head{display:flex;align-items:center;gap:9px;padding:12px 13px 8px}
.nb-nm{font-size:14px;color:var(--ink)}
.nb-sum{margin:0 13px 8px;background:var(--nav-track);border-radius:10px;padding:8px 10px;display:flex;
 flex-direction:column;gap:6px}
.nb-brief{font-size:12.5px;font-weight:700;color:var(--ink);line-height:1.45}
.nb-ai{font-size:10px;font-weight:800;color:#fff;background:var(--accent);border-radius:5px;padding:2px 5px;
 margin-right:6px;vertical-align:1px}
.nb-cnt{display:flex;align-items:center;gap:8px}
.nb-cnt small{font-size:11px;font-weight:600;color:var(--muted-2);white-space:nowrap}
.nb-mood{display:flex;gap:2px;height:6px;flex:1;border-radius:99px;overflow:hidden;background:var(--border)}
.nb-mood i.g{background:#e5484d}.nb-mood i.b{background:#3b82f6}.nb-mood i.n{background:#b6c0cd}
.nb-row{border-top:1px solid var(--border)}
.nb-rh{display:flex;gap:8px;align-items:flex-start;width:100%;text-align:left;font:inherit;color:inherit;
 background:none;border:0;padding:10px 13px;cursor:pointer}
.nb-rh:hover{background:var(--chip)}
.nb-tag{font-size:10.5px;font-weight:800;border-radius:5px;padding:2px 6px;flex-shrink:0;line-height:1.35;margin-top:1px}
.nb-tag.g{background:#fdecec;color:#d9363e}.nb-tag.b{background:#e8f0fe;color:#2563eb}
.nb-tag.n{background:var(--nav-track);color:var(--muted-2)}
:root[data-theme="dark"] .nb-tag.g{background:#3a1d22;color:#ff8b8f}
:root[data-theme="dark"] .nb-tag.b{background:#17263f;color:#7fb0ff}
.nb-tx{flex:1;display:flex;flex-direction:column;gap:2px;min-width:0}
.nb-tx b{font-size:13.5px;line-height:1.42;color:var(--ink);font-weight:700}
.nb-m{font-size:11px;color:var(--faint);display:flex;align-items:center;gap:5px;flex-wrap:wrap}
.nb-car{font-style:normal;color:var(--faint);font-size:18px;line-height:1;transition:transform .15s}
.nb-row.open .nb-car{transform:rotate(90deg)}
.nb-body{display:none;padding:0 13px 12px 13px}
.nb-row.open .nb-body{display:block}
.nb-why{display:inline-block;font-size:11.5px;font-weight:700;color:var(--muted-2);background:var(--nav-track);
 border-radius:6px;padding:2px 7px;margin-bottom:6px}
.nb-body p{margin:0;font-size:13px;color:var(--muted);line-height:1.6}
.nb-orig{font-size:11px;color:var(--faint);margin-top:6px}
.nb-link{display:inline-block;margin-top:6px;font-size:12px;font-weight:700;color:var(--accent)}
.nb-hid{font-size:11px;color:var(--faint);border-top:1px dashed var(--border);padding:7px 13px}
.nb-foot{font-size:11px;color:var(--faint);margin-top:8px}
/* 성장주: 가격 온도계·실적 D-day·점수 변화·정렬, 상세 가격/실적 카드 */
.gr-sort{display:inline-flex;gap:3px;background:var(--nav-track);border-radius:8px;padding:3px;margin-left:auto}
.gr-sort button{font:inherit;font-size:11px;font-weight:700;color:var(--muted-2);background:none;border:0;
 border-radius:6px;padding:3px 9px;cursor:pointer}
.gr-sort button.on{background:var(--ink);color:var(--page)}
#grScreener .sched-head{flex-direction:row;align-items:center;flex-wrap:wrap;gap:8px}
.gr-ed{font-size:10.5px;font-weight:800;color:var(--chip-ink);background:var(--chip);border-radius:6px;
 padding:2px 7px;white-space:nowrap;flex-shrink:0}
.gr-th{display:flex;align-items:center;gap:6px;width:118px;flex-shrink:0}
.gr-th.wide{width:170px}
.gr-th.na{font-size:10.5px;color:var(--faint);white-space:nowrap}
.gr-th-bar{position:relative;flex:1;height:8px;border-radius:4px;
 background:linear-gradient(90deg,#3b82f6,#cbd5e1 50%,#e5484d)}
.gr-th-bar i{position:absolute;top:-3px;width:4px;height:14px;margin-left:-2px;border-radius:2px;
 background:var(--ink);box-shadow:0 0 0 2px var(--card)}
.gr-th-lab{font-size:10.5px;font-weight:800;width:26px;text-align:right}
.gr-th-lab.cheap{color:#2563eb}.gr-th-lab.mid{color:var(--muted-2)}.gr-th-lab.rich{color:#dc2626}
:root[data-theme="dark"] .gr-th-lab.cheap{color:#6aa3ff}
:root[data-theme="dark"] .gr-th-lab.rich{color:#ff7b7f}
.gr-dl{font-size:11px;font-weight:800;width:28px;flex-shrink:0}
.gr-dl.up{color:#e5484d}.gr-dl.dn{color:#3b82f6}.gr-dl.eq{color:var(--faint)}
.gr-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:16px}
.gr-box{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px;
 display:flex;flex-direction:column;gap:10px;min-width:0}
.gr-box-h{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;
 font-weight:800;color:var(--ink)}
.gr-box-h small{display:block;font-size:10px;color:var(--faint);font-weight:600}
.gr-kvs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
.gr-kv{background:var(--chip);border-radius:8px;padding:7px 9px;display:flex;flex-direction:column;min-width:0}
.gr-kv small{font-size:10px;color:var(--muted-2)}
.gr-kv b{font-size:15px;font-weight:800;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gr-none{font-size:12px;color:var(--faint)}
.gr-rk-t{font-size:11px;font-weight:800;color:var(--muted)}
.gr-rk-t small{font-weight:600;color:var(--faint);margin-left:5px}
.gr-rks{display:flex;flex-direction:column;gap:3px}
.gr-rk{display:grid;grid-template-columns:44px 1fr 34px;align-items:center;gap:6px;font-size:10px;
 font-weight:700;color:var(--muted-2);font-variant-numeric:tabular-nums}
.gr-rk-bar{height:6px;background:var(--nav-track);border-radius:3px;overflow:hidden}
.gr-rk-bar i{display:block;height:100%;background:var(--faint);border-radius:3px}
.gr-rk.me{color:var(--ink)}.gr-rk.me .gr-rk-bar i{background:#dc2626}
.gr-dday{font-size:12px;font-weight:800;color:#fff;background:#2a56b3;border-radius:7px;padding:2px 8px}
.gr-sps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;align-items:end}
.gr-sp{display:flex;flex-direction:column;align-items:center;gap:2px}
.gr-sp-bar{width:26px;height:52px;display:flex;align-items:flex-end;background:var(--chip);border-radius:5px;overflow:hidden}
.gr-sp-bar i{display:block;width:100%;border-radius:4px}
.gr-sp-bar i.beat{background:#e5484d}.gr-sp-bar i.miss{background:#3b82f6}
.gr-sp em{font-style:normal;font-size:10px;font-weight:800}
.gr-sp em.beat{color:#e5484d}.gr-sp em.miss{color:#3b82f6}
.gr-sp small{font-size:9.5px;color:var(--faint)}
.gr-hist{border-top:1px dashed var(--border);padding-top:8px;display:flex;flex-direction:column;gap:2px}
.gr-hl{display:flex;justify-content:space-between;font-size:10px;color:var(--faint)}
@media (max-width:600px){
  .gr-2{grid-template-columns:1fr}
  .gr-th{width:auto}.gr-th-bar{display:none}
  .gr-ed{font-size:9.5px;padding:1px 5px}
  .gr-th.wide{width:120px}.gr-th.wide .gr-th-bar{display:block}
}
/* 성장주: 분석 대상 선정 설명 */
.gr-uni{font-size:12px;color:var(--muted-2);margin:-2px 0 12px}
.gr-uni summary{cursor:pointer;font-weight:700;color:var(--faint);padding:2px 0}
.gr-uni[open] summary{color:var(--ink)}
.gr-uni ol{margin:6px 0 0;padding:10px 12px 10px 30px;background:var(--card);border:1px solid var(--border);border-radius:10px;
 display:flex;flex-direction:column;gap:5px;line-height:1.55}
.gr-uni b{color:var(--ink)}
/* 성장주 4단계: 점수 검증(시점 기준 백테스트) */
.bt-verdict{background:var(--card);border:1px solid var(--border);border-left:4px solid #f59e0b;border-radius:10px;
 padding:11px 13px;display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--muted-2)}
.bt-verdict b{font-size:15px;color:var(--ink)}
.bt-verdict em{font-style:normal;font-weight:800;color:var(--ink)}.bt-verdict em.hi{color:var(--accent)}
.bt-verdict small{color:var(--faint)}
.bt-warn{font-size:11.5px;color:var(--faint)}
.bt-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--faint);margin:14px 0 2px}
.bt-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.bt-legend i.w,.bt-svg rect.w,.bt-ax i.w{background:var(--accent);fill:var(--accent)}
.bt-legend i.l,.bt-svg rect.l,.bt-ax i.l{background:#9aa6b8;fill:#9aa6b8}
.bt-svg{width:100%;display:block;max-width:640px}
.bt-svg .ax{stroke:var(--border)}
.bt-svg .v{font-size:13px;font-weight:800;fill:var(--ink);text-anchor:middle}
.bt-svg .dt{font-size:12px;fill:var(--faint);text-anchor:middle}
.bt-box{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:11px 13px;margin-top:12px}
.bt-h{font-size:13px;font-weight:800;color:var(--ink);margin-bottom:8px}
.bt-h small{font-size:11px;font-weight:500;color:var(--faint);margin-left:4px}
.bt-ax{display:grid;grid-template-columns:86px 1fr 62px 34px;gap:8px;align-items:center;font-size:12.5px;padding:3px 0;color:var(--ink)}
.bt-ax-bar{position:relative;height:10px;background:var(--nav-track);border-radius:4px}
.bt-ax-bar::after{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--faint)}
.bt-ax-bar i{position:absolute;top:0;bottom:0;border-radius:3px}
.bt-ax b{text-align:right;font-variant-numeric:tabular-nums}.bt-ax b.w{color:var(--accent)}.bt-ax b.l{color:var(--muted-2)}
.bt-ax small{color:var(--faint);font-size:11px;text-align:right}
.bt-det{margin-top:12px}.bt-det summary{cursor:pointer;font-size:12.5px;font-weight:700;color:var(--muted-2);padding:4px 0}
.bt-det .gt-wrap{margin-top:6px}
.bt-t td.c{text-align:center;color:var(--faint)}.bt-t td.tops{font-size:11.5px;color:var(--muted-2)}
.bt-t td.num.w{color:var(--accent)}
.bt-how{margin-top:12px;font-size:12px;color:var(--muted-2)}.bt-how b{color:var(--ink)}
.bt-how ul{margin:6px 0 0;padding-left:18px;display:flex;flex-direction:column;gap:4px}
.gr-tab{white-space:nowrap}.bt-t td:first-child{white-space:nowrap}
@media (max-width:600px){.gr-tab-x{display:none}.bt-ax{grid-template-columns:72px 1fr 54px 30px;font-size:12px}.bt-t td.tops{min-width:140px}}
/* 성장주 3단계: 전체 선별(나스닥 100)/관심 목록 탭, 표, ★ 즐겨찾기, 토스트 */
.gr-tabs{display:flex;gap:22px;border-bottom:1px solid var(--border);margin-bottom:12px}
.gr-tab{font:inherit;font-size:14px;font-weight:800;color:var(--faint);background:none;border:0;
 padding:0 2px 9px;position:relative;cursor:pointer}
.gr-tab.on{color:var(--ink)}
.gr-tab.on::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--ink)}
.gr-tab small{font-size:11px;font-weight:700;color:var(--faint);background:var(--nav-track);
 border-radius:999px;padding:1px 7px;margin-left:5px}
.gr-tab.on small{background:var(--ink);color:var(--page)}
.gr-sub-h{display:flex;justify-content:flex-end;margin-bottom:10px}
.gt-filters{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-bottom:10px;font-size:12px}
.gt-filters input,.gt-filters select{font:inherit;font-size:12.5px;color:var(--ink);background:var(--card);
 border:1px solid var(--border);border-radius:8px;padding:6px 10px}
.gt-filters input{min-width:160px;flex:1 1 160px;max-width:240px}
.gt-grp{display:inline-flex;align-items:center;gap:3px;background:var(--card);border:1px solid var(--border);
 border-radius:8px;padding:3px 3px 3px 9px;color:var(--muted-2);font-weight:700}
.gt-g,.gt-tog{font:inherit;font-size:11.5px;font-weight:700;color:var(--muted-2);background:none;border:0;
 border-radius:6px;padding:3px 8px;cursor:pointer}
.gt-g.on{background:var(--ink);color:var(--page)}
.gt-tog{background:var(--card);border:1px solid var(--border);padding:5px 10px;border-radius:8px}
.gt-tog.on{background:var(--chip);border-color:var(--accent);color:var(--chip-ink)}
.gt-wrap{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow-x:auto}
.gt{border-collapse:collapse;width:100%;font-size:12.5px}
.gt th{background:var(--nav-track);color:var(--muted-2);font-size:11px;font-weight:700;text-align:left;
 padding:8px 9px;white-space:nowrap}
.gt-th{cursor:pointer;user-select:none}.gt-th.sorted{color:var(--ink)}.gt-th i{font-style:normal}
.gt td{padding:7px 9px;border-top:1px solid var(--border);vertical-align:middle}
.gt-row{cursor:pointer}.gt-row:hover td{background:var(--chip)}
.gt td.n{color:var(--faint);font-weight:700;width:26px;text-align:center;font-variant-numeric:tabular-nums}
.gt td.st,.gt th.st{width:28px;padding-right:0;text-align:center}
.gt-star{font:inherit;font-size:17px;line-height:1;border:0;background:none;cursor:pointer;color:var(--border-strong,#cbd5e1);padding:2px}
.gt-star:hover,.gt-star.on{color:#f5a524}
.gt-tk{display:flex;align-items:center;gap:8px;min-width:0}
.gt-sym{font-size:10.5px;font-weight:800;letter-spacing:.02em;background:var(--nav-track);
 border-radius:6px;padding:3px 5px;min-width:44px;text-align:center;flex-shrink:0;color:var(--ink)}
.gt-nm{display:flex;flex-direction:column;font-weight:700;color:var(--ink);min-width:0}
.gt-nm small{font-weight:500;color:var(--faint);font-size:10.5px}
.gt-tk-in{display:none}
.gt .num{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap;color:var(--ink)}
.gt .num.up{color:#e5484d}.gt .num.dn{color:#3b82f6}
.gt-sub{display:block;font-size:9.5px;color:var(--faint);font-weight:600}
.gt-sub.warn{color:#b45309}
.gt-sc{font-size:15px}.gt-sc.g{color:#16a37f}.gt-sc.y{color:#e0930a}.gt-sc.r{color:#e5484d}
.gt-na{color:var(--faint)}
.gt .c-chips{white-space:nowrap}
.gt-chip{display:inline-block;font-size:10px;font-weight:800;border-radius:5px;padding:1px 6px;margin-right:4px}
.gt-chip.m{background:rgba(229,72,77,.13);color:#b42318}
.gt-chip.d{background:rgba(124,58,237,.13);color:#6d28d9}
.gt-chip.q{background:var(--nav-track);color:var(--muted)}
:root[data-theme="dark"] .gt-chip.m{color:#ff9ca0}
:root[data-theme="dark"] .gt-chip.d{color:#c4b5fd}
.gt-more{display:block;margin:10px auto 0;font:inherit;font-size:12px;font-weight:700;color:var(--chip-ink);
 background:var(--chip);border:1px solid var(--border);border-radius:8px;padding:7px 14px;cursor:pointer}
.gt-foot{font-size:11px;color:var(--faint);margin-top:8px;line-height:1.5}
.gr-toast{position:sticky;top:56px;z-index:5;display:flex;align-items:center;gap:10px;width:max-content;max-width:100%;
 margin:0 0 10px auto;background:var(--header);color:#fff;font-size:12px;font-weight:700;border-radius:10px;
 padding:9px 14px;box-shadow:0 8px 24px var(--shadow)}
.gr-toast[hidden]{display:none}
.gr-undo{font:inherit;font-size:12px;font-weight:800;color:#f5c451;background:none;border:0;cursor:pointer;text-decoration:underline}
@media (max-width:600px){
  .gt .c-rev,.gt .c-opm,.gt .c-th,.gt .c-chips,.gt td.n,.gt th.n,.gt-sym{display:none}
  .gt-tk-in{display:inline;font-weight:700;color:var(--muted-2)}
  .gt td,.gt th{padding:7px 5px}
  .gt-nm{font-size:12px}
  .gt-filters input{max-width:none}
}
/* 선택한 서브탭 컬럼만 표시 */
.sched-2col[data-sub="cal"] .res-col{display:none;}
.sched-2col[data-sub="res"] .cal-col{display:none;}
/* 월간 캘린더(일요일 시작). 칸=높음 지표 약칭 고정, 중간·낮음은 필터 칩(s-med/s-low)일 때만 */
.cal-bar{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-wrap:wrap;}
.cal-title{font-size:15px;font-weight:800;color:var(--ink);min-width:92px;text-align:center;}
.cal-nv{font:inherit;width:30px;height:30px;border-radius:8px;border:1px solid var(--border);
 background:var(--card);color:var(--muted);font-size:17px;line-height:1;cursor:pointer;}
.cal-nv:disabled{opacity:.35;cursor:default;}
.cal-sp{flex:1;}
.imp-chip.fixed{cursor:default;}
.cal-dow,.cal-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:4px;}
.cal-dow{font-size:11px;font-weight:700;color:var(--faint);text-align:center;margin-bottom:4px;}
.cal-dow .sun{color:#e5484d;}.cal-dow .sat{color:#3b82f6;}
.cal-c{font:inherit;text-align:left;color:var(--ink);background:var(--card);
 border:1px solid var(--border);border-radius:9px;min-height:80px;padding:5px;
 display:flex;flex-direction:column;align-items:stretch;gap:3px;overflow:hidden;cursor:pointer;}
.cal-c:hover{border-color:var(--accent);}
.cal-c.out{background:transparent;border-color:transparent;opacity:.35;cursor:default;}
.cal-c.past{opacity:.6;}
.cal-c.today{border-color:var(--ink);}
.cal-c.sel{outline:2px solid var(--accent);outline-offset:-1px;background:var(--chip);opacity:1;}
.cal-dn{font-size:11.5px;font-weight:800;align-self:flex-start;line-height:1.5;}
/* 미국 공휴일: 날짜 옆 상태 태그(휴장/조기폐장) + 국기·이름 줄. 필터와 무관하게 항상 표시 */
.cal-top{display:flex;align-items:center;justify-content:space-between;gap:3px;}
.hol-tag{font-size:9px;font-weight:800;border-radius:4px;padding:0 4px;line-height:1.6;
 white-space:nowrap;color:#fff;}
.hol-tag.closed{background:#64748b;}
.hol-tag .t-mob{display:none;}
.hol-tag.early{background:transparent;color:var(--muted-2);border:1px solid var(--border);}
.hol{display:flex;align-items:center;gap:3px;font-size:9.5px;font-weight:700;
 color:var(--muted-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.hol img{flex-shrink:0;border-radius:1px;box-shadow:0 0 0 1px rgba(0,0,0,.1);}
.hol.closed{color:var(--ink);}
.cal-c.hol-closed{background:var(--nav-track);}
.hol-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;
 padding:8px 3px;border-bottom:1px solid var(--border);color:var(--muted);}
.hol-row b{color:var(--ink);font-weight:700;}
.hol-row img{border-radius:2px;box-shadow:0 0 0 1px rgba(0,0,0,.1);}
.hol-row.closed span{font-weight:800;color:var(--ink);}
.cal-c.sun .cal-dn{color:#e5484d;}.cal-c.sat .cal-dn{color:#3b82f6;}
.cal-c.today .cal-dn{background:var(--ink);color:var(--page);border-radius:999px;padding:0 6px;}
.lab{display:block;font-size:10px;font-weight:800;border-radius:5px;padding:1px 5px;
 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.lab.hi{background:rgba(229,72,77,.13);color:#b42318;}
.lab.md{background:rgba(245,158,11,.16);color:#92400e;}
.lab.lo{background:var(--nav-track);color:var(--muted-2);}
:root[data-theme="dark"] .lab.hi{color:#ff9ca0;}
:root[data-theme="dark"] .lab.md{color:#fbbf24;}
.cal .lab.md,.cal .lab.lo{display:none;}
.cal.s-med .lab.md,.cal.s-low .lab.lo{display:block;}
.lab-more{font-size:9.5px;font-weight:700;color:var(--muted-2);}
.lab-more.mob{display:none;}
.cal-tks{display:flex;flex-wrap:wrap;gap:2px;margin-top:auto;}
.cal-tk{font-family:ui-monospace,monospace;font-size:8.5px;font-weight:800;
 border-radius:4px;padding:1px 4px;line-height:1.4;}
:root[data-theme="dark"] .cal-tk{box-shadow:0 0 0 1px rgba(255,255,255,.28);}  /* 어두운 브랜드색 티커가 배경에 묻히지 않게 */
.cal-dets{margin-top:12px;}
.cal-det,.cal-empty{background:var(--card);border:1px solid var(--border);border-radius:12px;
 padding:10px 12px;}
.cal-det[hidden],.cal-empty[hidden]{display:none;}
.cal-dh{font-size:13px;font-weight:800;color:var(--chip-ink);margin-bottom:4px;
 display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 10px;}
.cal-cnt{display:flex;gap:8px;font-size:10.5px;font-weight:600;color:var(--faint);}
.cal .n-md,.cal .n-lo{display:none;}
.cal.s-med .n-md,.cal.s-low .n-lo{display:inline;}
.cal-det .up-row,.cal-det .rep-item{border-bottom:1px solid var(--border);}
.cal-empty{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--muted);}
.cal-empty b{font-size:13px;color:var(--chip-ink);}
.cal-empty em{font-style:normal;font-size:10.5px;color:var(--faint);}
.cal.s-med.s-low .cal-empty em{display:none;}
.cal .sched-tz2{margin-top:8px;}
@media (max-width:600px){
  .cal-dow,.cal-grid{gap:3px;}
  .cal-c{min-height:60px;padding:4px 3px;border-radius:7px;}
  .lab{font-size:9px;padding:1px 3px;}
  .lab.h2,.lab-more.dsk{display:none;}
  .lab-more.mob{display:block;}
  .cal-tk{font-size:7.5px;padding:0 2px;}
  .cal-title{min-width:0;}
  .hol{font-size:8.5px;}
  .hol img{display:none;}
  .hol-tag{font-size:8px;padding:0 2px;}
  .hol-tag .t-dsk{display:none;}
  .hol-tag .t-mob{display:inline;}
}
.ern-item{border-bottom:1px solid var(--border);border-radius:10px;}
.ern-item:last-child{border-bottom:0;}
.ern-item.open{background:var(--chip);border-bottom-color:transparent;}
.ern{display:flex;align-items:center;gap:9px;padding:9px 6px;}
.ern-item:has(.ern-detail) .ern{cursor:pointer;}
.ern-arrow{color:var(--faint);font-size:10px;flex-shrink:0;transition:transform .15s;}
.ern-item.open .ern-arrow{transform:rotate(180deg);color:var(--accent);}
.ern-tag.rep{font-size:9.5px;font-weight:800;color:#fff;background:#15803d;
 padding:2px 7px;border-radius:5px;flex-shrink:0;}
.ern-tag.wait{font-size:9.5px;font-weight:800;color:#fff;background:#f59e0b;
 padding:2px 7px;border-radius:5px;flex-shrink:0;margin-left:4px;}  /* 발표됐으나 집계 전 */
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
.ev-new{font-size:8.5px;font-weight:800;color:#fff;background:#15803d;
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
.badge-new{font-size:10px;font-weight:800;color:#fff;background:#15803d;
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
  /* 좁은 폭: 슬로건·디데이 블록이 잘리지 않도록 다음 줄로 내리고 우측 정렬 유지 */
  .hd-sub{flex-wrap:wrap;row-gap:10px;}
  .hd-slogan{margin-left:auto;}
  /* 탭 8개가 두 줄로 꺾이지 않도록 한 줄 유지 + 가로 스크롤 */
  .nav{overflow-x:auto;scrollbar-width:none;}
  .nav::-webkit-scrollbar{display:none;}
  .nav a,.nav button{flex:1 0 auto;white-space:nowrap;font-size:12px;padding:8px 9px;}
}
"""


# 내 목표 앱(goal-app.js, Firebase ~120KB) 지연 로드:
#   첫 화면 렌더에 불필요하므로 '내 목표' 탭 또는 로그인 버튼 클릭 시 즉시,
#   아니면 load 이후 유휴 시간에 로드한다. 로드 전 클릭은 모듈 실행 후 재전달.
#   경로는 push.js처럼 절대경로 → 아카이브(archive/) 페이지에서도 404 없이 동작.
_GOAL_LOADER_JS = """<script>
(function(){
  var done=false, pending=null;
  function load(){
    if(done) return; done=true;
    var s=document.createElement('script'); s.type='module';
    s.src='/stock_news_mailer/goal-app.js';
    s.onload=function(){ if(pending){ var p=pending; pending=null; p.click(); } };
    document.body.appendChild(s);
  }
  var slot=document.getElementById('authSlot');
  var tab=document.querySelector('.nav-t[data-p="tpGoal"]');
  if(slot) slot.addEventListener('click', function(){ if(!done){ pending=slot; load(); } });
  if(tab) tab.addEventListener('click', load);
  window.addEventListener('load', function(){
    (window.requestIdleCallback||function(f){ setTimeout(f,1500); })(load);
  });
})();
</script>"""


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
<div class="wrap"><div class="page" role="main">
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
    b.parentNode.querySelectorAll('.sub-tab').forEach(function(x){x.classList.remove('on'); x.setAttribute('aria-selected','false');});
    b.classList.add('on'); b.setAttribute('aria-selected','true');
  });
});
/* 주식 탭 뉴스: 기사 펼침 · 호재/악재 필터 · 정렬 */
document.addEventListener('click', function(ev){
  var rh=ev.target.closest('.nb-rh');
  if(rh){ var r=rh.parentNode, o=r.classList.toggle('open'); rh.setAttribute('aria-expanded', o?'true':'false'); return; }
  var f=ev.target.closest('.nb-f'); if(!f) return;
  var part=f.closest('.part'), k=f.getAttribute('data-f');
  part.querySelectorAll('.nb-f').forEach(function(x){ x.classList.toggle('on', x===f); });
  part.querySelectorAll('.nb-card').forEach(function(c){ var n=0;
    c.querySelectorAll('.nb-row').forEach(function(r){ var ok=!k||r.getAttribute('data-s')===k; r.style.display=ok?'':'none'; if(ok) n++; });
    c.style.display=n?'':'none'; });
});
document.addEventListener('change', function(ev){
  var sel=ev.target.closest('.nb-sort'); if(!sel) return;
  var list=sel.closest('.part').querySelector('.nb-list'), k=sel.value;
  [].slice.call(list.querySelectorAll('.nb-card')).sort(function(a,b){
    var d=k?(+b.getAttribute('data-'+k))-(+a.getAttribute('data-'+k)):0;
    return d||(+a.getAttribute('data-i'))-(+b.getAttribute('data-i')); })
  .forEach(function(c){ list.appendChild(c); });
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


# 주식 탭 서브탭(알약형): 아이콘은 인라인 SVG — 국기 이모지는 Windows에서 "US" 글자로 보여서.
_ICO_US = ('<svg class="pill-ico" viewBox="0 0 20 20" aria-hidden="true"><defs><clipPath id="icoUs">'
           '<circle cx="10" cy="10" r="10"/></clipPath></defs><g clip-path="url(#icoUs)">'
           '<rect width="20" height="20" fill="#fff"/>'
           + "".join(f'<rect y="{y}" width="20" height="1.55" fill="#d62b3a"/>' for y in (0, 3.1, 6.2, 9.3, 12.4, 15.5, 18.6))
           + '<rect width="10" height="10.85" fill="#2b3a8c"/>'
           + "".join(f'<circle cx="{x}" cy="{y}" r=".7" fill="#fff"/>'
                     for x, y in ((2.5, 2.6), (5, 2.6), (7.5, 2.6), (3.75, 5.2), (6.25, 5.2), (2.5, 7.8), (5, 7.8), (7.5, 7.8)))
           + '</g><circle cx="10" cy="10" r="9.6" fill="none" stroke="rgba(0,0,0,.12)" stroke-width=".8"/></svg>')
_ICO_BTC = ('<svg class="pill-ico" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="10" fill="#f7931a"/>'
            '<path d="M7.2 5.4h4.1c1.6 0 2.6.8 2.6 2.1 0 .9-.5 1.5-1.2 1.8 1 .3 1.6 1 1.6 2.1 0 1.5-1.1 2.4-2.9 2.4H7.2z'
            'M9 7v2.5h2c.8 0 1.2-.4 1.2-1.25S11.8 7 11 7zm0 4v2.9h2.3c.9 0 1.4-.5 1.4-1.45S14.2 11 13.3 11z" fill="#fff"/>'
            '<path d="M8.9 4v1.6M10.9 4v1.6M8.9 13.6v1.6M10.9 13.6v1.6" stroke="#fff" stroke-width="1.1" stroke-linecap="round"/></svg>')
_PILL = {"os": (_ICO_US, "미국증시"), "coin": (_ICO_BTC, "코인")}


def _render_tab_panels(rendered: dict[str, str]) -> tuple[list[str], list[str]]:
    """TABS 구성에 따라 (nav 버튼 목록, panel HTML 목록)을 만든다.

    주식(os)·코인(coin)이 함께 있으면 알약형 서브탭(미국증시 · 코인)으로 감싼다."""
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
                ico, lab = _PILL.get(p, ("", pnm))
                ons = " on" if j == 0 else ""
                sty = "" if j == 0 else ' style="display:none"'
                btns.append(f'<button class="sub-tab{ons}" data-sub="{p}" role="tab" '
                            f'aria-selected="{"true" if j == 0 else "false"}">{ico}{_e(lab)}</button>')
                panes.append(f'<div class="sub-pane" data-pane="{p}"{sty}>'
                             f'{rendered[p]}</div>')
            inner = ('<div class="stock-wrap"><div class="sub-tabs sub-pill" role="tablist">'
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
    # 일정 탭: 📅 캘린더(경제지표+실적 예정+지난 실적 보고서 통합) / 📄 실적 결과(분기별 카드)
    # 브리핑 시각이 아닌 "실제 현재 시각" 기준 — 재빌드(refresh) 때도 오늘 표시·
    # 발표된 높음 지표 결과가 맞도록.
    _now_live = clock.now()
    months = _load_econ_events(_now_live) if schedule else []
    sched_html = ""
    if months:
        earns = _load_earnings(_now_live)
        sched_html = _render_calendar(months, earns, _load_reports(), _now_live,
                                      _load_us_holidays())
        res_html, fresh = _render_earn_results(earns, _now_live)
        nb = '<span class="ev-new">NEW</span>' if fresh else ''
        navs.append('<button class="nav-t" data-p="tpS">일정</button>')
        panels.append(
            '<div class="panel" id="tpS"><div class="part">'
            '<div class="sub-tabs">'
            '<button class="sub-tab on" data-sub="cal">📅 캘린더</button>'
            f'<button class="sub-tab" data-sub="res">📄 실적 결과{nb}</button>'
            '</div>'
            '<div class="sched-2col" data-sub="cal">'
            f'<div class="sched-col cal-col">{sched_html}</div>'
            f'<div class="sched-col res-col">{res_html}</div>'
            '</div></div></div>')

    # 성장주 탭: SEC 재무(XBRL) 기반 스크리너 + 종목 심층
    funds = _load_fundamentals()
    if funds:
        navs.append('<button class="nav-t" data-p="tpGrow">🔎 성장주</button>')
        prices, px_asof = _load_prices()
        panels.append('<div class="panel" id="tpGrow">'
                      + _render_growth(funds, now, _load_earnings(now), prices, px_asof,
                                       _load_score_history(), _load_screen(), _load_universe(),
                                       list(EARNINGS_TICKERS), _load_backtest()) + '</div>')

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
               + _GOAL_LOADER_JS)
    return _shell(SITE_TITLE, hd + gauges_html + nav_html + "".join(panels),
                  script=scripts, asset_prefix=asset_prefix)


def write_growth_details(now: datetime) -> int:
    """성장주 상세 카드를 docs/growth/<티커>.html로 쓴다(성장주 탭이 누를 때 불러옴). 반환: 파일 수."""
    import os
    from render import config
    funds = _load_fundamentals()
    if not funds:
        return 0
    prices, px_asof = _load_prices()
    return write_growth_fragments(funds, now, os.path.join(config.DOCS_DIR, "growth"),
                                  _load_earnings(now), prices, px_asof, _load_score_history(),
                                  _load_universe())
