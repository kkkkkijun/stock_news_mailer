
(function(){
 var root=document.getElementById('grRoot'); if(!root) return;
 var DEF=JSON.parse(root.getAttribute('data-default')||'[]'), VER=root.getAttribute('data-v')||'';
 var KEY='mb_watch_v1', DIRTY='mb_watch_dirty', PAGE=30, shown=PAGE, from='all';
 function lg(k){try{return localStorage.getItem(k);}catch(e){return null;}}
 function ls(k,v){try{ if(v==null) localStorage.removeItem(k); else localStorage.setItem(k,v);}catch(e){}}
 var fav=(function(){ try{ var a=JSON.parse(lg(KEY)); if(Array.isArray(a)) return a; }catch(e){} return DEF.slice(); })();
 var W=null;
 function isFav(t){ return fav.indexOf(t)>=0; }
 // ---- 즐겨찾기 저장: 로그인 시 Firestore(users/{uid}.watch, goal-app.js의 MBWatch), 아니면 이 브라우저 ----
 function persist(){ ls(KEY,JSON.stringify(fav));
   if(W&&W.uid){ W.set(fav).catch(function(){}); ls(DIRTY,null); } else ls(DIRTY,'1'); }
 function sync(){ W=window.MBWatch; if(!W||!W.ready) return;
   if(W.uid){
     if(W.list==null){ W.set(fav).catch(function(){}); ls(DIRTY,null); }
     else if(lg(DIRTY)){ var u=W.list.slice(); fav.forEach(function(t){ if(u.indexOf(t)<0) u.push(t); });
       fav=u; W.set(fav).catch(function(){}); ls(DIRTY,null); ls(KEY,JSON.stringify(fav)); }
     else { fav=W.list.slice(); ls(KEY,JSON.stringify(fav)); }
   }
   paint();
 }
 window.addEventListener('mbwatch', sync);
 var toastT=null, undo=null;
 function toast(msg,undoFn){ var t=document.getElementById('grToast'); if(!t) return;
   t.innerHTML=msg+(undoFn?' <button type="button" class="gr-undo">실행 취소</button>':''); t.hidden=false; undo=undoFn;
   clearTimeout(toastT); toastT=setTimeout(function(){ t.hidden=true; undo=null; },3000); }
 function name(t){ var r=root.querySelector('.gt-row[data-t="'+t+'"]')||root.querySelector('.gr-row[data-tk="'+t+'"]');
   return r?(r.getAttribute('data-nm')||t):t; }
 function toggle(t){ var on=!isFav(t), before=fav.slice();
   if(on) fav.push(t); else fav=fav.filter(function(x){return x!==t;});
   persist(); paint();
   toast(name(t)+(on?'을(를) 관심 목록에 추가했어요':'을(를) 관심 목록에서 뺐어요')+((W&&W.uid)?'':' · 로그인하면 계정에 저장돼요'),
         function(){ fav=before; persist(); paint(); }); }
 // ---- 탭 ----
 function view(v){ from=v;
   root.querySelectorAll('.gr-tab').forEach(function(b){ b.classList.toggle('on',b.getAttribute('data-v')===v); });
   document.getElementById('grAll').style.display=v==='all'?'':'none';
   document.getElementById('grScreener').style.display=v==='fav'?'':'none';
   document.getElementById('grBt').style.display=v==='bt'?'':'none';
   document.getElementById('grDeep').style.display='none'; }
 // ---- 전체 선별 표: 필터·정렬·더 보기 ----
 var tb=document.getElementById('gtBody'), sortK='yoy', sortDir=-1, gMin=-1e9, onlyProfit=false, onlyFav=false;
 function rows(){ return [].slice.call(tb.querySelectorAll('.gt-row')); }
 function applyTable(){ if(!tb) return;
   var q=(document.getElementById('gtSearch').value||'').trim().toLowerCase(), sec=document.getElementById('gtSector').value;
   var rs=rows();
   rs.sort(function(a,b){ var x=parseFloat(a.getAttribute('data-'+sortK)), y=parseFloat(b.getAttribute('data-'+sortK));
     if(isNaN(x)) return 1; if(isNaN(y)) return -1; return (x-y)*sortDir; });
   var n=0;
   rs.forEach(function(r){ tb.appendChild(r);
     var t=r.getAttribute('data-t'), ok=true;
     if(q && (t.toLowerCase()+' '+(r.getAttribute('data-nm')||'').toLowerCase()).indexOf(q)<0) ok=false;
     if(sec && r.getAttribute('data-sector')!==sec) ok=false;
     if(parseFloat(r.getAttribute('data-yoy'))<gMin) ok=false;
     if(onlyProfit && !(parseFloat(r.getAttribute('data-opm'))>0)) ok=false;
     if(onlyFav && !isFav(t)) ok=false;
     if(ok) n++;
     r.style.display=(ok && n<=shown)?'':'none';
     if(ok) r.querySelector('.n').textContent=n; });
   document.getElementById('gtCount').textContent=n;
   var m=document.getElementById('gtMore'); m.style.display=n>shown?'':'none';
   m.textContent=n+'개 중 '+Math.min(n,shown)+'개 표시 · 더 보기';
   root.querySelectorAll('.gt-th').forEach(function(h){ var k=h.getAttribute('data-k');
     h.classList.toggle('sorted',k===sortK); h.setAttribute('aria-sort',k===sortK?(sortDir<0?'descending':'ascending'):'none');
     h.querySelector('i').textContent=k===sortK?(sortDir<0?'▼':'▲'):''; }); }
 // ---- 관심 목록: 즐겨찾기 + 프리셋 + 정렬 ----
 var preset='all';
 function applyList(){ var list=document.getElementById('grList'); if(!list) return; var c=0;
   [].slice.call(list.querySelectorAll('.gr-row')).forEach(function(r){
     var ok=isFav(r.getAttribute('data-tk')), f=preset;
     if(ok && f!=='all') ok=(f==='profit'&&r.getAttribute('data-g0')==='g')||(f==='turn'&&r.getAttribute('data-turn')==='1')||(f==='cash'&&r.getAttribute('data-cash')==='g');
     r.style.display=ok?'flex':'none'; if(isFav(r.getAttribute('data-tk'))) c++; });
   var e=document.getElementById('grEmpty'); if(e) e.hidden=c>0; }
 function paint(){
   root.querySelectorAll('.gt-star').forEach(function(b){ var on=isFav(b.getAttribute('data-t'));
     b.classList.toggle('on',on); b.textContent=on?'★':'☆'; b.setAttribute('aria-pressed',on?'true':'false');
     b.setAttribute('aria-label',(on?'관심 목록에서 빼기: ':'관심 목록에 추가: ')+b.getAttribute('data-t')); });
   var c=document.getElementById('grFavN'); if(c) c.textContent=fav.filter(function(t){ return root.querySelector('.gr-row[data-tk="'+t+'"]'); }).length;
   applyList(); applyTable(); }
 // ---- 상세: 종목별 파일을 불러와 표시(페이지 용량 절약) ----
 var cache={};
 function openDeep(t){ var dp=document.getElementById('grDeep');
   document.getElementById('grAll').style.display='none'; document.getElementById('grScreener').style.display='none';
   document.getElementById('grBt').style.display='none'; dp.style.display='block'; dp.innerHTML='<div class="gr-none" style="padding:30px 0;text-align:center">불러오는 중…</div>'; window.scrollTo(0,root.getBoundingClientRect().top+window.scrollY-60);
   var p=cache[t]?Promise.resolve(cache[t]):fetch('/stock_news_mailer/growth/'+encodeURIComponent(t)+'.html?v='+VER).then(function(r){ if(!r.ok) throw 0; return r.text(); });
   p.then(function(h){ cache[t]=h; dp.innerHTML=h; }).catch(function(){ dp.innerHTML='<div class="gr-none" style="padding:30px 0;text-align:center">상세 정보를 불러오지 못했습니다. <button type="button" class="gr-back">← 목록</button></div>'; }); }
 root.addEventListener('click',function(ev){ var el=ev.target;
   var star=el.closest('.gt-star'); if(star){ ev.stopPropagation(); toggle(star.getAttribute('data-t')); return; }
   if(el.closest('.gr-undo')){ if(undo){ var u=undo; undo=null; u(); } document.getElementById('grToast').hidden=true; return; }
   var tab=el.closest('.gr-tab'); if(tab){ view(tab.getAttribute('data-v')); return; }
   if(el.closest('.gr-back')){ view(from); return; }
   var th=el.closest('.gt-th'); if(th){ var k=th.getAttribute('data-k'); if(k===sortK) sortDir=-sortDir; else { sortK=k; sortDir=-1; } applyTable(); return; }
   var g=el.closest('.gt-g'); if(g){ root.querySelectorAll('.gt-g').forEach(function(x){x.classList.toggle('on',x===g);}); gMin=parseFloat(g.getAttribute('data-g')); shown=PAGE; applyTable(); return; }
   var tg=el.closest('.gt-tog'); if(tg){ tg.classList.toggle('on'); var f=tg.getAttribute('data-f'); if(f==='profit') onlyProfit=tg.classList.contains('on'); else onlyFav=tg.classList.contains('on'); shown=PAGE; applyTable(); return; }
   if(el.closest('#gtMore')){ shown+=PAGE*10; applyTable(); return; }
   var pr=el.closest('.gr-preset'); if(pr){ root.querySelectorAll('.gr-preset').forEach(function(x){x.style.opacity='.55';}); pr.style.opacity='1'; preset=pr.getAttribute('data-f'); applyList(); return; }
   var sb=el.closest('.gr-sort button'); if(sb){ root.querySelectorAll('.gr-sort button').forEach(function(x){x.classList.toggle('on',x===sb);});
     var k=sb.getAttribute('data-k'), list=document.getElementById('grList'), rs=[].slice.call(list.querySelectorAll('.gr-row'));
     rs.sort(function(a,c){ if(k==='score') return (+c.getAttribute('data-score'))-(+a.getAttribute('data-score')); return (+a.getAttribute('data-'+k))-(+c.getAttribute('data-'+k)); });
     rs.forEach(function(r){ list.appendChild(r); }); return; }
   var row=el.closest('.gt-row,.gr-row'); if(row && row.getAttribute('data-has')!=='0'){ openDeep(row.getAttribute('data-t')||row.getAttribute('data-tk')); } });
 ['input','change'].forEach(function(e){ root.addEventListener(e,function(ev){ if(ev.target.id==='gtSearch'||ev.target.id==='gtSector'){ shown=PAGE; applyTable(); } }); });
 view('all'); sync(); paint();
})();
