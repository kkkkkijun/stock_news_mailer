
(function(){
  var t=document.getElementById('top');
  if(!t)return;
  function s(){ t.classList.toggle('show', window.pageYOffset>200); }
  window.addEventListener('scroll',s,{passive:true}); s();
  t.addEventListener('click',function(){ window.scrollTo({top:0,behavior:'smooth'}); });
})();


(function(){
  var b=document.getElementById('theme'); if(!b)return;
  function ic(){ b.textContent =
    document.documentElement.getAttribute('data-theme')==='dark' ? '☀️' : '🌙'; }
  ic();
  b.addEventListener('click', function(){
    var n = document.documentElement.getAttribute('data-theme')==='dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', n);
    try{ localStorage.setItem('theme', n); }catch(e){}
    ic();
  });
})();


if('serviceWorker' in navigator){
  window.addEventListener('load', function(){
    navigator.serviceWorker.register('/stock_news_mailer/sw.js').catch(function(){});
  });
}
