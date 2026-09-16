
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
