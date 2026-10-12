
// 월간 캘린더: 월 이동 · 중요도 필터(높음 고정, 중간/낮음 토글) · 날짜 선택 → 상세
document.querySelectorAll('.cal').forEach(function(cal){
  var months=[].slice.call(cal.querySelectorAll('.cal-month'));
  if(!months.length) return;
  var title=cal.querySelector('.cal-title'), navs=cal.querySelectorAll('.cal-nv');
  var dets=[].slice.call(cal.querySelectorAll('.cal-det'));
  var empty=cal.querySelector('.cal-empty'), today=cal.getAttribute('data-today');
  var WD=['일','월','화','수','목','금','토'], idx=0, sel=null;
  function vis(el){ return getComputedStyle(el).display!=='none'; }
  function mark(){   // 현재 필터에서 보이는 표시(라벨·티커)가 있는 칸만 '일정 있음'
    cal.querySelectorAll('.cal-c[data-d]').forEach(function(c){
      c.classList.toggle('has', [].some.call(c.querySelectorAll('.lab,.cal-tk,.hol'), vis));
    });
  }
  function label(d){ var t=new Date(d+'T00:00:00');
    return (t.getMonth()+1)+'월 '+t.getDate()+'일 ('+WD[t.getDay()]+')'; }
  function pick(d){
    sel=d;
    cal.querySelectorAll('.cal-c.sel').forEach(function(x){ x.classList.remove('sel'); });
    var c=cal.querySelector('.cal-c[data-d="'+d+'"]');
    if(c) c.classList.add('sel');
    var shown=false;
    dets.forEach(function(x){
      var on=x.getAttribute('data-d')===d;
      if(on){ x.hidden=false;
        on=[].some.call(x.querySelectorAll('.ev,.up-row,.rep-item,.hol-row'), vis); }
      x.hidden=!on; if(on) shown=true;
    });
    empty.hidden=shown;
    if(!shown) empty.querySelector('b').textContent=label(d);
  }
  function firstDay(m){
    var cells=[].slice.call(m.querySelectorAll('.cal-c[data-d]'));
    var t=cells.filter(function(c){ return c.getAttribute('data-d')===today; })[0];
    if(t){
      if(t.classList.contains('has')) return today;
      var nx=cells.filter(function(c){ return c.classList.contains('has') &&
        c.getAttribute('data-d')>today; })[0];
      return nx ? nx.getAttribute('data-d') : today;
    }
    var h=cells.filter(function(c){ return c.classList.contains('has'); })[0];
    return (h||cells[0]).getAttribute('data-d');
  }
  function show(i){
    idx=Math.max(0, Math.min(months.length-1, i));
    months.forEach(function(m,k){ m.style.display=(k===idx)?'':'none'; });
    title.textContent=months[idx].getAttribute('data-label');
    navs[0].disabled=(idx===0); navs[1].disabled=(idx===months.length-1);
    mark(); pick(firstDay(months[idx]));
  }
  navs.forEach(function(b){ b.addEventListener('click', function(){
    show(idx+parseInt(b.getAttribute('data-dir'),10)); }); });
  cal.querySelectorAll('.cal-c[data-d]').forEach(function(c){
    c.addEventListener('click', function(){ pick(c.getAttribute('data-d')); });
  });
  cal.querySelectorAll('.imp-chip[data-k]').forEach(function(ch){
    ch.addEventListener('click', function(){
      ch.classList.toggle('on');
      cal.classList.toggle('s-'+ch.getAttribute('data-k'), ch.classList.contains('on'));
      mark(); if(sel) pick(sel);
    });
  });
  var start=0; months.forEach(function(m,k){ if(m.style.display!=='none') start=k; });
  show(start);
});
document.querySelectorAll('.ern-item').forEach(function(item){
  var row=item.querySelector('.ern');
  if(!row || !item.querySelector('.ern-detail')) return;   // 상세 없으면 클릭 비활성
  row.addEventListener('click', function(){ item.classList.toggle('open'); });
});
document.querySelectorAll('.rep-head').forEach(function(h){
  h.addEventListener('click', function(){ h.parentNode.classList.toggle('open'); });
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
