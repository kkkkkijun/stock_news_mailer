
(function(){
 var RED="#e5484d",BLUE="#3b82f6",CATS=["암호화폐","주식","지수","원자재"],cur="주식",ALL=null;
 function d3ready(cb){ if(window.d3)return cb();
   var s=document.createElement('script');
   s.src='https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js';
   s.onload=cb; s.onerror=fail; document.head.appendChild(s); }
 function fail(){ var a=document.getElementById('rwaAsof'); if(a)a.textContent='지도 데이터를 불러오지 못했습니다.'; }
 function fmt(m){ return m>=1?('$'+m.toFixed(2)+'M'):('$'+Math.round(m*1000)+'K'); }
 function init(){ d3ready(function(){
   Promise.all([
     fetch('rwamap.json?t='+Date.now()).then(function(r){return r.json();}).catch(function(){return null;}),
     fetch('whales.json?t='+Date.now()).then(function(r){return r.json();}).catch(function(){return null;})
   ]).then(function(res){
     var rwa=res[0]||{assets:[],asof:'',positions:0}, wh=res[1]||{coins:[],asof:'',whales:0};
     var crypto=(wh.coins||[]).map(function(c){return {t:c.t,disp:c.t,cat:'암호화폐',net:c.net,lev:c.lev,tot:(c.l+c.s),n:c.n};});
     var rest=(rwa.assets||[]).filter(function(a){return a.cat!=='암호화폐';});
     ALL={assets:crypto.concat(rest),asofRwa:rwa.asof,asofCrypto:wh.asof,positions:rwa.positions,whales:wh.whales};
     chips(); render();
   }).catch(fail); }); }
 document.querySelectorAll('.nav-t').forEach(function(b){
   if(b.getAttribute('data-p')==='tpMap') b.addEventListener('click',init); });
 function chips(){
   document.getElementById('rwaChips').innerHTML=CATS.map(function(c){ var on=c===cur;
     return '<span class="rwac" data-c="'+c+'" style="cursor:pointer;font-size:12.5px;font-weight:700;padding:6px 14px;border-radius:99px;'+
       (on?'background:var(--ink);color:var(--page)':'background:var(--chip);color:var(--muted-2)')+'">'+c+'</span>'; }).join('');
   document.querySelectorAll('.rwac').forEach(function(el){ el.addEventListener('click',function(){ cur=el.getAttribute('data-c'); chips(); render(); }); });
 }
 function render(){
   if(!ALL)return;
   var data=(ALL.assets||[]).filter(function(a){return a.cat===cur && (a.tot||0)>0;});
   var isC=cur==='암호화폐';
   document.getElementById('rwaAsof').textContent = isC
     ? ('기준 '+(ALL.asofCrypto||'-')+' · 암호화폐 '+data.length+'종 · Hyperliquid 고래 '+(ALL.whales||0)+'명')
     : ('기준 '+(ALL.asofRwa||'-')+' · '+cur+' '+data.length+'종 · Ostium 온체인 '+(ALL.positions||0)+'포지션');
   var W=680,H=400;
   var x=d3.scaleLinear([-1.05,1.05],[54,W-54]);
   var maxLev=Math.max(8,d3.max(data,function(d){return d.lev;})||8);
   var y=d3.scaleLinear([1,maxLev],[H-44,42]);
   var r=d3.scaleSqrt([0,d3.max(data,function(d){return d.tot;})||1],[13,42]);
   var nodes=data.map(function(d){return {d:d,x:x(d.net),y:y(d.lev||1),r:Math.max(13,r(d.tot))};});
   var sim=d3.forceSimulation(nodes)
     .force('x',d3.forceX(function(o){return x(o.d.net);}).strength(0.6))
     .force('y',d3.forceY(function(o){return y(o.d.lev||1);}).strength(0.55))
     .force('c',d3.forceCollide(function(o){return o.r+2.2;}).iterations(4)).stop();
   for(var i=0;i<300;i++)sim.tick();
   nodes.forEach(function(o){o.x=Math.max(o.r+4,Math.min(W-o.r-4,o.x));o.y=Math.max(o.r+4,Math.min(H-o.r-4,o.y));});
   var cx=x(0),cyLev=y(maxLev/2),col=function(n){return n>=0?RED:BLUE;};
   var s='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;display:block">';
   s+='<rect x="'+cx+'" y="0" width="'+(W-cx)+'" height="'+cyLev+'" fill="'+RED+'" opacity="0.05"/>';
   s+='<rect x="0" y="0" width="'+cx+'" height="'+cyLev+'" fill="'+BLUE+'" opacity="0.05"/>';
   s+='<line x1="'+cx+'" y1="20" x2="'+cx+'" y2="'+(H-18)+'" stroke="var(--border-strong)" stroke-width="1" stroke-dasharray="4 5"/>';
   s+='<line x1="18" y1="'+cyLev+'" x2="'+(W-18)+'" y2="'+cyLev+'" stroke="var(--border)" stroke-width="1" stroke-dasharray="3 5"/>';
   s+='<text x="18" y="26" fill="'+BLUE+'" font-size="12" font-weight="700">◀ 고레버·숏</text>';
   s+='<text x="'+(W-18)+'" y="26" text-anchor="end" fill="'+RED+'" font-size="12" font-weight="700">고레버·롱 ▶</text>';
   s+='<text x="'+(W/2)+'" y="'+(H-6)+'" text-anchor="middle" fill="var(--faint)" font-size="10.5">▼ 저레버</text>';
   nodes.forEach(function(o){ var fz=Math.max(9,Math.min(13,o.r*0.44));
     s+='<circle cx="'+o.x.toFixed(1)+'" cy="'+o.y.toFixed(1)+'" r="'+o.r.toFixed(1)+'" fill="var(--card)" stroke="'+col(o.d.net)+'" stroke-width="'+(1.6+Math.abs(o.d.net)*5).toFixed(1)+'"/>';
     s+='<text x="'+o.x.toFixed(1)+'" y="'+(o.y+fz*0.35).toFixed(1)+'" text-anchor="middle" font-size="'+fz.toFixed(1)+'" font-weight="700" fill="var(--ink)">'+o.d.disp+'</text>';});
   s+='</svg>';
   document.getElementById('rwaMap').innerHTML=s;
   var rows=data.slice(0,20).map(function(d){
     var lp=Math.round((d.net+1)/2*100), nt=d.net>=0?'순롱':'순숏', nc=col(d.net);
     return '<div style="display:flex;align-items:center;gap:8px;padding:9px 4px;border-top:1px solid var(--border)">'+
       '<div style="width:64px;font-size:13px;font-weight:700;color:var(--ink);overflow:hidden;text-overflow:ellipsis">'+d.disp+'</div>'+
       '<div style="flex:1;min-width:60px"><div style="display:flex;height:13px;border-radius:4px;overflow:hidden;gap:1px">'+
         '<div style="width:'+lp+'%;background:'+RED+'"></div><div style="width:'+(100-lp)+'%;background:'+BLUE+'"></div></div></div>'+
       '<div style="width:56px;text-align:right;font-size:12px;font-weight:700;color:'+nc+'">'+nt+' '+Math.abs(Math.round(d.net*100))+'%</div>'+
       '<div style="width:54px;text-align:right;font-size:12px;color:var(--ink)">'+fmt(d.tot)+'</div>'+
       '<div style="width:34px;text-align:right;font-size:11.5px;color:var(--muted-2)">'+(d.lev||'-')+'x</div>'+
       '<div style="width:40px;text-align:right;font-size:11px;color:var(--faint)">'+d.n+'지갑</div></div>';
   }).join('');
   document.getElementById('rwaTable').innerHTML=
     '<div style="display:flex;font-size:10.5px;color:var(--faint);padding:0 4px 2px"><span style="width:64px">종목</span><span style="flex:1">롱/숏</span><span style="width:56px;text-align:right">심리</span><span style="width:54px;text-align:right">명목</span><span style="width:34px;text-align:right">레버</span><span style="width:40px;text-align:right">참여</span></div>'+rows;
 }
})();
