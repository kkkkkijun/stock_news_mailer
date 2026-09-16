
(function(){
 var sc=document.getElementById('grScreener'), dp=document.getElementById('grDeep');
 if(!sc||!dp) return;
 function show(tk){
   dp.querySelectorAll('.gr-card').forEach(function(c){c.style.display=c.getAttribute('data-tk')===tk?'block':'none';});
   sc.style.display='none'; dp.style.display='block'; window.scrollTo(0,0);
 }
 function back(){ dp.style.display='none'; sc.style.display='block'; }
 sc.querySelectorAll('.gr-row').forEach(function(r){
   r.addEventListener('click',function(){show(r.getAttribute('data-tk'));});
 });
 dp.querySelectorAll('.gr-back').forEach(function(b){b.addEventListener('click',back);});
 sc.querySelectorAll('.gr-preset').forEach(function(p){
   p.addEventListener('click',function(){
     sc.querySelectorAll('.gr-preset').forEach(function(x){x.style.opacity='.55';});
     p.style.opacity='1'; var f=p.getAttribute('data-f');
     sc.querySelectorAll('.gr-row').forEach(function(r){
       var ok=(f==='all')||(f==='profit'&&r.getAttribute('data-g0')==='g')||
              (f==='turn'&&r.getAttribute('data-turn')==='1')||
              (f==='cash'&&r.getAttribute('data-cash')==='g');
       r.style.display=ok?'flex':'none';
     });
   });
 });
})();
