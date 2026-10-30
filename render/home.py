# -*- coding: utf-8 -*-
"""메인 홈 탭: 주요 지표 띠 · 나스닥 100 히트맵 · 내 종목 · 다가오는 일정 · 오늘 한눈에.

지표 띠와 히트맵은 home.js가 /stock_news_mailer/treemap.json(treemap.py, 매시 갱신)을 불러와 그린다.
나머지는 브리핑 본문·실적·경제지표로 렌더 시점에 만든다(브리핑·refresh 재빌드 때 갱신).
최신 페이지(index)에만 붙는다 — 지난 회차 페이지에 '지금' 시세가 섞이지 않게.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from render.common import _e, _text_on, _ticker_color
from render.config import _TICKER_KO
from render.parse import _parse_part
from render.schedule import _econ_short

_CUR_KO = {"USD": "미국", "JPY": "일본", "EUR": "유로존", "CNY": "중국", "GBP": "영국", "KRW": "한국",
           "CAD": "캐나다", "AUD": "호주", "CHF": "스위스", "NZD": "뉴질랜드"}
_WD = "월화수목금토일"
# (아이콘, 이름, 본문 섹션 키, 파트 id)
_SUMMARIES = (("💹", "경제", "경제 PART", "eco"), ("🪙", "코인", "코인시장 PART", "cm"),
              ("🏘️", "부동산", "부동산 PART", "re"), ("💬", "트럼프", "트럼프 PART", "trump"))


def _first_sentence(s: str) -> str:
    m = re.match(r"(.+?[다요]\.)(\s|$)", s or "")
    return m.group(1) if m else (s or "")


def _when(dt: datetime, now: datetime, with_time: bool = True) -> str:
    day = "오늘" if dt.date() == now.date() else "내일" if dt.date() == (now + timedelta(days=1)).date() \
        else f"{dt.month}/{dt.day} ({_WD[dt.weekday()]})"
    return f"{day} {dt:%H:%M}" if with_time and (dt.hour or dt.minute) else day


def home_events(econ_months: list, earnings: list[dict[str, Any]], now: datetime,
                days: int = 7, limit: int = 6) -> list[dict[str, Any]]:
    """중요도 높음 경제지표(같은 시각·같은 약칭은 한 줄) + 관심 종목 실적(같은 날은 한 줄) → 가까운 순 limit개."""
    end = now + timedelta(days=days)
    rows: dict[tuple, dict[str, Any]] = {}
    for mo in econ_months:
        for e in mo[2]:
            dt = e.get("dt")
            if e.get("impact") != "HIGH" or not dt or not (now - timedelta(minutes=30) <= dt <= end):
                continue
            short = _econ_short(e["name"])
            key = ("eco", dt.date(), short)          # 같은 날 같은 약칭(BoJ 결정·기자회견 등)은 첫 시각 한 줄
            if key in rows and rows[key]["dt"] <= dt:
                continue
            res = e.get("res") or {}
            note = (f'예상 {res["cons"]}' if res.get("cons") else f'직전 {res["prev"]}' if res.get("prev") else "")
            big = "Election" in e["name"]
            if "Midterm" in e["name"]:
                short = "중간선거"
            rows[key] = {"dt": dt, "kind": "big" if big else "eco", "note": note,
                         "label": f'{_CUR_KO.get(e.get("cur"), e.get("cur") or "")} {short}'.strip()}
    by_day: dict[Any, list[str]] = {}
    for x in earnings:
        d = x.get("date")
        if d and now.date() <= d <= end.date():
            by_day.setdefault(d, []).append(x["ticker"])
    for d, tks in by_day.items():
        dt = now.tzinfo.localize(datetime(d.year, d.month, d.day)) if hasattr(now.tzinfo, "localize") \
            else datetime(d.year, d.month, d.day, tzinfo=now.tzinfo)
        rows[("earn", d)] = {"dt": dt, "kind": "earn", "label": "·".join(tks) + " 실적", "note": "", "allday": True}
    out = sorted(rows.values(), key=lambda r: (r["dt"].date(), r.get("allday", False), r["dt"]))
    return out[:limit]


def _ticker_stats(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    st: dict[str, dict[str, Any]] = {}
    for it in items:
        if it.get("kind") != "ticker":
            continue
        d = st.setdefault(it["label"], {"g": 0, "b": 0, "n": 0, "brief": ""})
        if it.get("sent") in ("g", "b", "n"):
            d[it["sent"]] += 1
        if it.get("brief"):
            d["brief"] = it["brief"]
    return st


def render_home(sections: list[tuple[str, list[str]]], qmap: dict[str, Any], now: datetime,
                econ_months: list, earnings: list[dict[str, Any]], tab_of: dict[str, str]) -> str:
    """홈 패널 HTML. tab_of = {파트 id: 패널 id} — 카드를 누르면 그 탭으로 이동."""
    def lines_of(key):
        return next((ls for t, ls in sections if key in t), None)

    # ③ 내 종목: 호재 많은 순(같으면 악재 적은 순), 4개 + 모두 보기
    os_lines = lines_of("해외주식 PART")
    my = ""
    if os_lines:
        _s, items, _b, _n = _parse_part(os_lines)
        st = _ticker_stats(items)
        qs = {q.get("ticker"): q for q in (qmap.get("os") or []) if q}
        pos = {t: i for i, t in enumerate(st)}
        order = sorted(st, key=lambda t: (-st[t]["g"], st[t]["b"], pos[t]))
        rows = []
        for t in order[:4]:
            bg = _ticker_color(t)
            q = qs.get(t) or {}
            chg = q.get("chg")
            ch = (f'<em class="{"up" if chg >= 0 else "dn"}">{"▲" if chg >= 0 else "▼"}{abs(chg):.2f}%</em>'
                  if isinstance(chg, (int, float)) else "")
            dots = "".join(f'<i class="{k}"></i>' * st[t][k] for k in "gbn")
            rows.append(f'<button type="button" class="hm-my" data-go="{tab_of.get("os", "")}" data-t="{_e(t)}">'
                        f'<span class="tk-badge" style="background:{bg};color:{_text_on(bg)}">{_e(t)}</span>'
                        f'<span class="hm-my-t"><b>{_e(_TICKER_KO.get(t, t))}</b><span>{_e(st[t]["brief"])}</span></span>'
                        f'<span class="hm-my-r">{ch}<span class="hm-dots" aria-label="호재 {st[t]["g"]} 악재 {st[t]["b"]}">{dots}</span></span></button>')
        if rows:
            my = ('<section class="hm-card"><div class="hm-h"><b>내 종목</b><span>호재 많은 순 · 누르면 뉴스</span></div>'
                  + "".join(rows)
                  + f'<button type="button" class="hm-more" data-go="{tab_of.get("os", "")}">{len(order)}종목 모두 보기 ›</button></section>')

    # ④ 다가오는 일정
    evs = home_events(econ_months, earnings, now)
    sched = ""
    if evs:
        sched = ('<section class="hm-card"><div class="hm-h"><b>다가오는 일정</b><span>중요도 높음 + 관심 종목 실적</span></div>'
                 + "".join(f'<div class="hm-ev {r["kind"]}"><span class="hm-ev-d">{_e(_when(r["dt"], now, not r.get("allday")))}</span>'
                           f'<b>{_e(r["label"])}</b>' + (f'<span class="hm-ev-x">{_e(r["note"])}</span>' if r["note"] else "")
                           + '</div>' for r in evs)
                 + ('<button type="button" class="hm-more" data-go="tpS">일정 전체 보기 ›</button>' if "tpS" in tab_of.values() else "")
                 + '</section>')

    # ⑤ 오늘 한눈에
    sums = []
    for ic, nm, key, pid in _SUMMARIES:
        ls = lines_of(key)
        s = _parse_part(ls)[0] if ls else ""
        if s:
            sums.append(f'<button type="button" class="hm-sm" data-go="{tab_of.get(pid, "")}">'
                        f'<span class="hm-sm-k">{ic} {nm}</span><span class="hm-sm-p">{_e(_first_sentence(s))}</span></button>')
    today = ('<section class="hm-card"><div class="hm-h"><b>오늘 한눈에</b>'
             f'<span>{now.month}/{now.day} 브리핑 요약 · 누르면 해당 탭</span></div>' + "".join(sums) + '</section>') if sums else ""

    # ①② 지표 띠·히트맵 자리(home.js가 채움)
    tm = ('<section class="hm-card"><div class="hm-h"><b>나스닥 100 히트맵</b><span id="hmAsof">불러오는 중…</span></div>'
          '<div id="hmTm" class="hm-tm"></div>'
          '<div class="hm-lg"><span>−3%</span><i style="background:#1d4ed8"></i><i style="background:#5b8def"></i>'
          '<i style="background:#c7d6f2"></i><i class="z"></i><i style="background:#f3c6c8"></i>'
          '<i style="background:#e5484d"></i><i style="background:#b4232a"></i><span>+3%</span>'
          '<span class="hm-lg-x">크기 = 시가총액 · 매시 갱신</span></div></section>')
    return ('<div class="part hm">'
            '<div id="hmIx" class="hm-ix" aria-label="주요 지표"></div>'
            + tm + f'<div class="hm-two">{my}{sched}</div>' + today + '</div>')


_HOME_JS = """<script>
// 홈: 지표 띠 + 나스닥 100 히트맵(treemap.json, 매시 갱신) · 카드 누르면 해당 탭으로
(function(){
 var root=document.querySelector('.hm'); if(!root) return;
 var DATA=null, lastW=0;
 function esc(s){ return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
 function pad(n){ return (n<10?'0':'')+n; }
 root.addEventListener('click',function(ev){
   var b=ev.target.closest('[data-go]'); if(!b) return; var p=b.getAttribute('data-go'); if(!p) return;
   var nav=document.querySelector('.nav-t[data-p="'+p+'"]'); if(nav) nav.click();
   var panel=document.getElementById(p), t=b.getAttribute('data-t');
   if(panel && b.hasAttribute('data-t')){ var sub=panel.querySelector('.sub-tab[data-sub="os"]'); if(sub) sub.click();
     var q=t && panel.querySelector('.qtab[data-t="'+t+'"]'); if(q) q.click(); }
   var nw=document.querySelector('.navwrap'); if(nw) window.scrollTo(0, nw.offsetTop);
 });
 function d3ready(cb){ if(window.d3) return cb();
   var s=document.createElement('script'); s.src='https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js';
   s.onload=cb; s.onerror=function(){ var a=document.getElementById('hmAsof'); if(a) a.textContent='히트맵을 불러오지 못했습니다.'; };
   document.head.appendChild(s); }
 function num(x){ var a=Math.abs(x); return a>=1000?Math.round(x).toLocaleString('en-US'):a>=100?x.toFixed(1):x.toFixed(2); }
 function chips(){ var el=document.getElementById('hmIx'); if(!el||!DATA.idx) return;
   el.innerHTML=DATA.idx.map(function(i){ var up=i.chg>=0;
     return '<div class="hm-i"><span>'+esc(i.lab)+'</span><b>'+esc(i.pre)+num(i.px)+esc(i.suf)+'</b>'
       +'<em class="'+(up?'up':'dn')+'">'+(up?'▲':'▼')+Math.abs(i.chg).toFixed(2)+'%</em></div>'; }).join(''); }
 function draw(force){
   var el=document.getElementById('hmTm'); if(!DATA||!el||!el.offsetParent||!window.d3) return;
   var W=el.clientWidth; if(!W||(W===lastW&&!force)) return; lastW=W;
   var H=Math.round(W*(W<520?0.95:0.56)); el.innerHTML='';
   var dark=document.documentElement.getAttribute('data-theme')==='dark';
   var groups=d3.group(DATA.rows,function(x){return x.s;});
   var h=d3.hierarchy({children:Array.from(groups,function(g){return {name:g[0],children:g[1]};})})
     .sum(function(x){return x.m||0;}).sort(function(a,b){return b.value-a.value;});
   // paddingOuter는 위쪽 여백까지 덮어쓰므로 먼저 부르고, 섹터(깊이 1)만 위에 이름 띠 16px
   d3.treemap().size([W,H]).paddingInner(1.5).paddingOuter(1).paddingTop(function(d){ return d.depth===1?16:1; })(h);
   var col=d3.scaleLinear().domain([-3,-1.5,-0.4,0,0.4,1.5,3])
     .range(['#1d4ed8','#5b8def',dark?'#34507d':'#c7d6f2',dark?'#2b3443':'#e9edf2',dark?'#7a3a40':'#f3c6c8','#e5484d','#b4232a']).clamp(true);
   var svg=d3.select(el).append('svg').attr('width',W).attr('height',H).attr('role','img').attr('aria-label','나스닥 100 히트맵');
   h.children.forEach(function(s){            // 섹터 이름 띠: 어두운 바탕 + 흰 글자(어떤 타일 색 위에서도 읽히게)
     if(s.x1-s.x0<36) return;                // 이름이 안 들어가는 좁은 섹터는 띠 없이
     svg.append('rect').attr('x',s.x0).attr('y',s.y0).attr('width',s.x1-s.x0).attr('height',16).attr('class','hm-secbg');
     svg.append('text').attr('x',s.x0+5).attr('y',s.y0+11.5).attr('class','hm-sec').text(s.data.name); });
   h.leaves().forEach(function(l){ var w=l.x1-l.x0, hh=l.y1-l.y0, c=l.data.c, g=svg.append('g');
     g.append('rect').attr('x',l.x0).attr('y',l.y0).attr('width',w).attr('height',hh).attr('fill',col(c));
     g.append('title').text(l.data.t+' · '+l.data.n+' · '+(c>0?'+':'')+c.toFixed(2)+'%');
     var light=Math.abs(c)>1.2||dark;
     if(w>30&&hh>20){ var fs=Math.max(9,Math.min(20,Math.sqrt(w*hh)/5)), two=hh>fs*2.2;
       g.append('text').attr('x',l.x0+w/2).attr('y',l.y0+hh/2-(two?fs*0.25:0)).attr('class','hm-tt').attr('font-size',fs)
        .attr('fill',light?'#fff':'#0f1b2d').text(l.data.t);
       if(two) g.append('text').attr('x',l.x0+w/2).attr('y',l.y0+hh/2+fs*0.85).attr('class','hm-tc').attr('font-size',Math.max(8.5,fs*0.62))
        .attr('fill',light?'#fff':'#334155').text((c>0?'+':'')+c.toFixed(2)+'%'); }
   });
 }
 fetch('/stock_news_mailer/treemap.json?t='+Date.now()).then(function(r){ if(!r.ok) throw 0; return r.json(); })
  .then(function(d){ DATA=d; chips();
    // 'HH:MM 갱신 · 시세 HH:MM 기준' — 장이 닫혀 있으면 시세 시각은 마지막 거래 시각에 머문다
    var s=d.asof||'', b=d.built||'', a=document.getElementById('hmAsof');
    function md(x){ return (+x.slice(5,7))+'/'+(+x.slice(8,10)); }
    if(a&&b) a.textContent=md(b)+' '+b.slice(11,16)+' 갱신 · 시세 '+(s.slice(0,10)===b.slice(0,10)?'':md(s)+' ')+s.slice(11,16)+' 기준';
    else if(a&&s) a.textContent=md(s)+' '+s.slice(11,16)+' 기준 · 매시 갱신';
    d3ready(function(){ draw(true); }); })
  .catch(function(){ var a=document.getElementById('hmAsof'); if(a) a.textContent='히트맵 데이터를 불러오지 못했습니다.'; });
 var tm; window.addEventListener('resize',function(){ clearTimeout(tm); tm=setTimeout(function(){ draw(false); },150); });
 document.addEventListener('click',function(ev){       // 홈 탭으로 돌아오거나 테마를 바꾸면 다시 그림
   if(ev.target.closest('.nav-t,#theme')) setTimeout(function(){ draw(true); },0); });
})();
</script>"""
