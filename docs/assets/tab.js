
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
