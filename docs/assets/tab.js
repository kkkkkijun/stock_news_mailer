
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
/* 주식·코인 뉴스: 시세 카드(종목 탭) 선택 · 기사 펼침 · 상대 시각 */
function nbCenter(){ document.querySelectorAll('.quotes.qtabs').forEach(function(c){
  var s=c.querySelector('.qtab.sel'); if(s && c.scrollWidth>c.clientWidth && c.offsetParent)
    c.scrollLeft=s.offsetLeft-(c.clientWidth-s.offsetWidth)/2; }); }
document.addEventListener('click', function(ev){
  var q=ev.target.closest('.qtab');
  if(q){ var part=q.closest('.part'), t=q.getAttribute('data-t');
    part.querySelectorAll('.qtab').forEach(function(x){ var on=x===q; x.classList.toggle('sel',on); x.setAttribute('aria-selected',on?'true':'false'); });
    part.querySelectorAll('.nb-pane').forEach(function(p){ p.hidden=p.getAttribute('data-t')!==t; });
    nbCenter(); return; }
  var rh=ev.target.closest('.nb-rh');
  if(rh){ var r=rh.parentNode, o=r.classList.toggle('open'); rh.setAttribute('aria-expanded', o?'true':'false'); return; }
  if(ev.target.closest('.nav-t,.sub-tab')) setTimeout(nbCenter,0);
});
(function(){ var now=new Date();
  document.querySelectorAll('time[data-at]').forEach(function(el){
    var a=el.getAttribute('data-at')||'';       /* 'MM/DD HH:MM' (KST) */
    var m=[0, +a.slice(0,2), +a.slice(3,5), +a.slice(6,8), +a.slice(9,11)];
    if(a.length!==11 || m.slice(1).some(isNaN)) return;
    var d=new Date(now.getFullYear(), m[1]-1, m[2], m[3], m[4]);
    if(d-now>864e5) d.setFullYear(d.getFullYear()-1);
    var h=(now-d)/36e5, days=Math.floor((new Date(now.toDateString())-new Date(d.toDateString()))/864e5);
    el.title=el.getAttribute('data-at');
    el.textContent = h<1 ? '방금' : (days===0 ? Math.floor(h)+'시간 전' : days===1 ? '어제' : days<7 ? days+'일 전' : el.title);
  });
  nbCenter();
})();
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
