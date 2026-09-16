# -*- coding: utf-8 -*-
"""지난 브리핑(캘린더/검색) 아카이브 인덱스 렌더링(publish_site.py 분리)."""
from __future__ import annotations

import json
import os
import re

from render import assets, config
from render.config import PARTS, SITE_TITLE
from render.files import _load_body
from render.layout import _shell
from render.parse import _parse_part, _split_sections

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
        files = sorted((f for f in os.listdir(config.DATA_DIR) if f.endswith(".txt")),
                       reverse=True)
    except OSError:
        return idx
    for fn in files:
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})-(am|pm)", fn[:-4])
        if not m:
            continue
        y, mo, d, ap = m.groups()
        _now, body = _load_body(os.path.join(config.DATA_DIR, fn))
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


def render_archive_index() -> str:
    """지난 브리핑 아카이브 인덱스(캘린더+검색) 페이지 HTML을 렌더링한다."""
    days: dict[str, dict[str, str]] = {}
    try:
        names = os.listdir(config.ARCHIVE_DIR)
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
    cal_js, _tail = assets._split_script(
        _CAL_JS.replace("__DATA__", json.dumps(days, ensure_ascii=False)))
    search_js, _tail = assets._split_script(
        _SEARCH_JS.replace("__SEARCH__", json.dumps(_search_index(), ensure_ascii=False)))
    tag = assets.write_archive_js(config, cal_js + "\n" + search_js, prefix="../")
    return _shell(SITE_TITLE, inner, script=tag, asset_prefix="../")
