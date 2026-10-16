# -*- coding: utf-8 -*-
"""RWA/고래 심리 지도 탭 렌더링(publish_site.py 분리)."""
from __future__ import annotations


def _render_rwa() -> str:
    head = ('<div class="sched-head" style="margin-bottom:8px"><span>'
            '<span class="sched-ico">🗺️</span>지도 '
            '<span class="sched-tz">Ostium · 온체인 RWA 심리</span></span></div>')
    legend = ('<div style="display:flex;gap:14px;flex-wrap:wrap;font-size:11px;'
              'color:var(--faint);margin:8px 2px 12px">'
              '<span style="display:inline-flex;align-items:center;gap:5px">'
              '<span style="width:9px;height:9px;border-radius:50%;background:#e5484d"></span>롱</span>'
              '<span style="display:inline-flex;align-items:center;gap:5px">'
              '<span style="width:9px;height:9px;border-radius:50%;background:#3b82f6"></span>숏</span>'
              '<span>가로=심리 · 세로=평균 레버리지 · 크기=명목가치</span></div>')
    return ('<div class="part">' + head
            + '<div id="rwaChips" style="display:flex;gap:7px;margin:2px 0 10px;flex-wrap:wrap"></div>'
            + '<div id="rwaAsof" style="font-size:11.5px;color:var(--muted-2);margin-bottom:4px">불러오는 중…</div>'
            + legend
            + '<div id="rwaMap"></div>'
            + '<div id="rwaTable" style="margin-top:18px"></div>'
            + '<div style="font-size:11px;color:var(--faint);margin-top:12px;line-height:1.6">'
            + 'Ostium(Arbitrum) 온체인 포지션 집계 · 전통 증시 전체가 아니라 온체인 RWA 트레이더 심리입니다. 투자 조언 아님.</div></div>')


_RWA_JS = """<script>
(function(){
 var RED="#e5484d",BLUE="#3b82f6",CATS=["암호화폐","주식","지수","원자재"],cur="주식",ALL=null;
 var SNAP=null,LIVE_AT=0,LIVE_BUSY=false,LIVE_EVERY=5*60*1000;
 function d3ready(cb){ if(window.d3)return cb();
   var s=document.createElement('script');
   s.src='https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js';
   s.onload=cb; s.onerror=fail; document.head.appendChild(s); }
 function fail(){ var a=document.getElementById('rwaAsof'); if(a)a.textContent='지도 데이터를 불러오지 못했습니다.'; }
 function fmt(m){ return m>=1?('$'+m.toFixed(2)+'M'):('$'+Math.round(m*1000)+'K'); }
 // 스냅샷은 절대경로: 지난 회차(archive/) 페이지에서도 같은 파일을 읽어 실시간 갱신까지 이어지게
 function init(){ d3ready(function(){
   Promise.all([
     fetch('/stock_news_mailer/rwamap.json?t='+Date.now()).then(function(r){return r.json();}).catch(function(){return null;}),
     fetch('/stock_news_mailer/whales.json?t='+Date.now()).then(function(r){return r.json();}).catch(function(){return null;})
   ]).then(function(res){
     var rwa=res[0]||{assets:[],asof:'',positions:0}, wh=res[1]||{coins:[],asof:'',whales:0};
     if(!SNAP){ SNAP={rwa:rwa,wh:wh}; build(rwaAssets(rwa),wh.coins,rwa.asof,wh.asof,rwa.positions,wh.whales,false,false); }
     chips(); render(); live();
   }).catch(fail); }); }
 function rwaAssets(rwa){ return (rwa.assets||[]).filter(function(a){return a.cat!=='암호화폐';}); }
 function build(rest,coins,asofR,asofC,pos,whales,liveR,liveC){
   var crypto=(coins||[]).map(function(c){return {t:c.t,disp:c.t,cat:'암호화폐',net:c.net,lev:c.lev,tot:(c.l+c.s),n:c.n};});
   ALL={assets:crypto.concat(rest),asofRwa:asofR,asofCrypto:asofC,positions:pos,whales:whales,liveR:liveR,liveC:liveC};
 }
 // ---- 실시간: 브라우저가 공개 API를 직접 조회(서버 cron 지연과 무관). 실패하면 스냅샷 유지 ----
 // 서버(rwa.py·whales.py)와 같은 반올림: 아주 작은 포지션은 0이 되어 화면에서 빠진다
 function r3(v){return Math.round(v*1000)/1000;} function r2(v){return Math.round(v*100)/100;}
 function kst(){ var d=new Date(Date.now()+9*3600e3); return d.toISOString().slice(0,16).replace('T',' '); }
 function post(url,body,ms){ var c=new AbortController(),t=setTimeout(function(){c.abort();},ms||15000);
   return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:c.signal})
     .then(function(r){clearTimeout(t); if(!r.ok) throw new Error('HTTP '+r.status); return r.json();}); }
 function liveRwa(cfg){
   // rwa.py build_rwa와 같은 규칙: 환·채권 제외, 명목 = 담보/1e6 × 레버리지/100
   var cr=new Set(cfg.crypto),ix=new Set(cfg.index),cm=new Set(cfg.commod),fx=new Set(cfg.forex),bd=new Set(cfg.bond);
   function cat(sym,to){ if(fx.has(sym)||to!=='USD'||bd.has(sym))return null; if(cr.has(sym))return '암호화폐';
     if(ix.has(sym))return '지수'; if(cm.has(sym))return '원자재'; return '주식'; }
   var all=[];
   function page(skip){ return post(cfg.url,{query:'{ trades(first:1000, skip:'+skip+', where:{isOpen:true}){ isBuy leverage collateral trader pair{ from to } } }'},20000)
     .then(function(j){ var t=(j.data&&j.data.trades)||[]; all=all.concat(t); return (t.length<1000||skip>8000)?all:page(skip+1000); }); }
   return page(0).then(function(trades){
     var agg={};
     trades.forEach(function(x){ var sym=x.pair.from,c=cat(sym,x.pair.to); if(!c)return;
       var lev=(+x.leverage)/100,usd=(+x.collateral)/1e6*lev; if(usd<=0)return;
       var a=agg[sym]||(agg[sym]={cat:c,lU:0,sU:0,levS:0,levC:0,tr:{}});
       if(x.isBuy)a.lU+=usd; else a.sU+=usd; a.levS+=lev; a.levC++; a.tr[x.trader]=1; });
     var assets=Object.keys(agg).map(function(sym){ var a=agg[sym],tot=a.lU+a.sU; if(tot<=0)return null;
       return {t:sym,disp:(cfg.disp||{})[sym]||sym,cat:a.cat,l:r3(a.lU/1e6),s:r3(a.sU/1e6),tot:r3(tot/1e6),n:Object.keys(a.tr).length,
               lev:a.levC?Math.round(a.levS/a.levC*10)/10:0,net:Math.round((a.lU-a.sU)/tot*1000)/1000}; })
       .filter(Boolean).sort(function(p,q){return q.tot-p.tot;});
     return {assets:assets.filter(function(a){return a.cat!=='암호화폐';}),positions:trades.length};
   });
 }
 function liveWhales(addrs){
   // whales.py build_whales와 같은 규칙: 명목 = |수량| × 현재가(없으면 진입가)
   return post('https://api.hyperliquid.xyz/info',{type:'allMids'}).then(function(mids){
     var agg={},ok=0,i=0;
     function one(a){ return post('https://api.hyperliquid.xyz/info',{type:'clearinghouseState',user:a}).then(function(r){ ok++;
       (r.assetPositions||[]).forEach(function(p){ var q=p.position,szi=+q.szi||0; if(!szi)return;
         var px=+(mids[q.coin]||q.entryPx||0),ntl=Math.abs(szi)*px; if(ntl<=0)return;
         var c=agg[q.coin]||(agg[q.coin]={lU:0,sU:0,lN:0,sN:0,levS:0,levC:0}), lev=+((q.leverage||{}).value||0);
         if(szi>0){c.lU+=ntl;c.lN++;}else{c.sU+=ntl;c.sN++;} if(lev){c.levS+=lev;c.levC++;} }); }).catch(function(){}); }
     function worker(){ return i<addrs.length ? one(addrs[i++]).then(worker) : Promise.resolve(); }
     var ws=[]; for(var k=0;k<6;k++) ws.push(worker());
     return Promise.all(ws).then(function(){
       var coins=Object.keys(agg).map(function(t){ var c=agg[t],tot=c.lU+c.sU; if(tot<=0)return null;
         return {t:t,n:c.lN+c.sN,l:r2(c.lU/1e6),s:r2(c.sU/1e6),lev:c.levC?Math.round(c.levS/c.levC*10)/10:0,net:Math.round((c.lU-c.sU)/tot*1000)/1000}; })
         .filter(Boolean).sort(function(p,q){return (q.l+q.s)-(p.l+p.s);});
       if(ok<addrs.length*0.5) throw new Error('whale coverage '+ok);
       return {coins:coins,whales:ok};
     });
   });
 }
 function live(){
   if(LIVE_BUSY||Date.now()-LIVE_AT<LIVE_EVERY||!SNAP)return;
   LIVE_BUSY=true; var a=document.getElementById('rwaAsof'); if(a)a.textContent+=' · 최신 데이터 불러오는 중…';
   var cfg=SNAP.rwa.cfg, addrs=SNAP.wh.addrs||[];
   var pR=cfg?liveRwa(cfg).catch(function(){return null;}):Promise.resolve(null);
   var pW=addrs.length?liveWhales(addrs).catch(function(){return null;}):Promise.resolve(null);
   Promise.all([pR,pW]).then(function(res){
     var r=res[0],w=res[1],now=kst();
     build(r?r.assets:rwaAssets(SNAP.rwa), w?w.coins:SNAP.wh.coins, r?now:SNAP.rwa.asof, w?now:SNAP.wh.asof,
           r?r.positions:SNAP.rwa.positions, w?w.whales:SNAP.wh.whales, !!r, !!w);
     LIVE_AT=Date.now(); LIVE_BUSY=false; render();
   });
 }
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
     ? ((ALL.liveC?'실시간 ':'기준 ')+(ALL.asofCrypto||'-')+(ALL.liveC?'':' 스냅샷')+' · 암호화폐 '+data.length+'종 · Hyperliquid 고래 '+(ALL.whales||0)+'명')
     : ((ALL.liveR?'실시간 ':'기준 ')+(ALL.asofRwa||'-')+(ALL.liveR?'':' 스냅샷')+' · '+cur+' '+data.length+'종 · Ostium 온체인 '+(ALL.positions||0)+'포지션');
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
</script>"""
