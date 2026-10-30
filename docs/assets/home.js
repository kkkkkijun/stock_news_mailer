
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
    var s=d.asof||'', a=document.getElementById('hmAsof');
    if(a&&s) a.textContent=(+s.slice(5,7))+'/'+(+s.slice(8,10))+' '+s.slice(11,16)+' 기준 · 매시 갱신';
    d3ready(function(){ draw(true); }); })
  .catch(function(){ var a=document.getElementById('hmAsof'); if(a) a.textContent='히트맵 데이터를 불러오지 못했습니다.'; });
 var tm; window.addEventListener('resize',function(){ clearTimeout(tm); tm=setTimeout(function(){ draw(false); },150); });
 document.addEventListener('click',function(ev){       // 홈 탭으로 돌아오거나 테마를 바꾸면 다시 그림
   if(ev.target.closest('.nav-t,#theme')) setTimeout(function(){ draw(true); },0); });
})();
