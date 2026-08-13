import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, GoogleAuthProvider, signInWithPopup, signOut, onAuthStateChanged }
  from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getFirestore, doc, setDoc, onSnapshot }
  from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const firebaseConfig = {
  apiKey: "AIzaSyCIsIbniZhAc4mdSCdtwgvafwRC0nuetl4",
  authDomain: "stock-news-mailer-6f86b.firebaseapp.com",
  projectId: "stock-news-mailer-6f86b",
  storageBucket: "stock-news-mailer-6f86b.firebasestorage.app",
  messagingSenderId: "14914685187",
  appId: "1:14914685187:web:3cfc508ab0f6abc1ad4136"
};
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const provider = new GoogleAuthProvider();

const ROOT = document.getElementById("goalRoot");
const SLOT = document.getElementById("authSlot");
if (ROOT) { init(); }

function init(){
  injectStyle();
  let uid = null, unsub = null, built = false;
  let editCash = null, editTrade = null;
  let journalMonth = "all", lastReal = [], tradeTicker = "all";
  const defState = () => ({ goal:{name:"",target:0,start:"",end:"",cur:"$",fx:0}, cash:[], trades:[], prices:{} });
  let S = defState();

  const $ = id => document.getElementById(id);
  const num = v => { const n = parseFloat(v); return isFinite(n) ? n : 0; };
  const curSym = () => "$";   // 입력·기준 통화는 달러 고정 (원화는 환율 환산 표시)
  const wonN = n => "₩" + Math.round(n).toLocaleString();
  const decs = () => (curSym()==="₩" ? 0 : 2);
  const money = n => curSym() + Number(n).toLocaleString(undefined,{minimumFractionDigits:decs(),maximumFractionDigits:decs()});
  const money2 = n => curSym() + Number(n).toLocaleString(undefined,{maximumFractionDigits:2});
  const px = n => curSym() + Number(n).toLocaleString(undefined,{maximumFractionDigits:4});
  const pctf = n => (n>=0?"+":"") + (Math.round(n*10)/10) + "%";
  const signMoney = n => (n>=0?"+":"−") + curSym() + Math.abs(Number(n)).toLocaleString(undefined,{minimumFractionDigits:decs(),maximumFractionDigits:decs()});
  const dayDiff = (a,b) => a&&b ? Math.round((new Date(b)-new Date(a))/86400000) : 0;
  const todayStr = () => { const d=new Date();
    return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0")+"-"+String(d.getDate()).padStart(2,"0"); };
  const mmdd = s => s ? (+s.slice(5,7))+"/"+(+s.slice(8,10)) : "";
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : "id"+Math.random().toString(36).slice(2)+Date.now());
  const esc = s => (s==null?"":String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

  /* ---------- auth ---------- */
  async function doLogin(btn){
    try { await signInWithPopup(auth, provider); }
    catch(e){
      const msg = "로그인 실패: " + (e.code||e.message) + " · 팝업 차단이면 허용 후 재시도.";
      const el = $("g_loginErr"); if(el){ el.textContent = msg; el.style.display=""; } else alert(msg);
    }
  }
  if (SLOT) SLOT.onclick = () => { if(uid) signOut(auth); else doLogin(); };

  onAuthStateChanged(auth, user => {
    if (unsub){ unsub(); unsub=null; }
    if (user){
      uid = user.uid;
      if (SLOT){ SLOT.textContent = (user.displayName||user.email||"로그인됨").split(" ")[0] + " · 로그아웃"; }
      buildShell(); subscribe(user.uid);
    } else {
      uid = null; S = defState(); built = false;
      if (SLOT) SLOT.textContent = "로그인";
      renderLogin();
    }
  });

  function subscribe(u){
    unsub = onSnapshot(doc(db,"users",u), snap => {
      const er=$("g_ruleErr"); if(er) er.style.display="none";
      S = snap.exists() ? Object.assign(defState(), snap.data()) : defState();
      renderData();
    }, err => {
      const er=$("g_ruleErr");
      if(er){ er.textContent = "DB 접근 오류: "+(err.code||err.message)+" · Firestore 규칙을 게시했는지 확인하세요."; er.style.display=""; }
    });
  }
  async function save(){
    if(!uid) return;
    if(built) renderData();   // 변경 즉시 대시보드·목록 재계산(로컬 반영, Firestore 왕복 대기 X)
    try { await setDoc(doc(db,"users",uid), Object.assign({}, S, {updatedAt: Date.now()})); }
    catch(e){ alert("저장 실패: "+(e.code||e.message)); }
  }

  /* ---------- views ---------- */
  function renderLogin(){
    ROOT.innerHTML =
      '<div class="g-login"><div class="g-login-ic">🔒</div>'+
      '<div class="g-login-t">내 목표 · 매매일지</div>'+
      '<div class="g-login-p">목표·자산·매매 기록은 <b>본인 계정에만</b> 저장되며<br>다른 사람은 절대 볼 수 없습니다.</div>'+
      '<button class="g-btn pri" id="g_loginBtn">Google로 로그인</button>'+
      '<div id="g_loginErr" class="g-err" style="display:none;margin-top:14px;text-align:left;"></div></div>';
    $("g_loginBtn").onclick = () => doLogin();
  }

  function buildShell(){
    if (built) return;
    ROOT.innerHTML = SHELL_HTML();
    built = true;
    $("g_cDate").value = todayStr(); $("g_tDate").value = todayStr();

    ROOT.querySelectorAll(".g-subtab").forEach(b=>{
      b.onclick = () => {
        ROOT.querySelectorAll(".g-subtab").forEach(x=>x.classList.remove("on"));
        b.classList.add("on");
        const t=b.getAttribute("data-t");
        $("g_asset").style.display = t==="asset"?"":"none";
        $("g_journal").style.display = t==="journal"?"":"none";
      };
    });
    $("g_cAdd").onclick = addCash;
    $("g_tAdd").onclick = addTrade;
    $("g_tFilter").onchange = () => { tradeTicker=$("g_tFilter").value; renderData(); };
    $("g_editGoal").onclick = openGoalEdit;
    $("ge_save").onclick = saveGoalEdit;
    $("ge_cancel").onclick = () => { $("g_goalEdit").style.display="none"; };
    $("g_fx").onchange = () => { S.goal.fx = num($("g_fx").value); renderData(); save(); };
    $("g_fxAuto").onclick = fetchFx;
    $("g_priceAuto").onclick = fetchPrices;
    $("g_csv").onclick = exportCSV;
    $("g_jMonth").onchange = () => { journalMonth=$("g_jMonth").value; renderJournal(compute()); };
    ROOT.querySelectorAll(".g-cal").forEach(b=>{
      b.onclick = () => { const el=$(b.getAttribute("data-for"));
        if(el){ try{ el.showPicker(); }catch(e){ el.focus(); } } };
    });
  }

  /* ---------- compute (연동) ---------- */
  function compute(){
    let dep=0, wd=0;
    for(const c of S.cash){ if(c.type==="in") dep+=num(c.amount); else wd+=num(c.amount); }
    const principal = dep - wd;
    const trades = [...S.trades].sort((a,b)=> (a.date<b.date?-1:a.date>b.date?1:0));
    // 평균단가·실현손익은 '체결가' 기준(수수료 제외) — 증권사(미래에셋) 표기와 일치.
    // 수수료는 현금/원금에서만 차감하고 별도 합계로 관리.
    const lots = {}; const realized = []; let buySpent=0, sellGot=0, fees=0;
    for(const t of trades){
      const q=num(t.qty), p=num(t.price), fee=num(t.fee), tk=(t.ticker||"").toUpperCase();
      if(q<=0) continue;
      fees += fee;
      if(!lots[tk]) lots[tk]=[];
      if(t.side==="buy"){ buySpent += q*p+fee; lots[tk].push({qty:q, cost:p, date:t.date}); }
      else {
        sellGot += q*p-fee; const sps=p; let rem=q;
        while(rem>1e-9 && lots[tk] && lots[tk].length){
          const L=lots[tk][0], m=Math.min(rem,L.qty);
          realized.push({ticker:tk, qty:m, buyDate:L.date, sellDate:t.date, buyPrice:L.cost, sellPrice:sps,
            pnl:(sps-L.cost)*m, pnlPct:L.cost?(sps/L.cost-1)*100:0, holdDays:dayDiff(L.date,t.date)});
          L.qty-=m; rem-=m; if(L.qty<=1e-9) lots[tk].shift();
        }
      }
    }
    const open=[]; let posVal=0, unreal=0;
    for(const tk in lots){
      let q=0, cs=0; for(const L of lots[tk]){ q+=L.qty; cs+=L.qty*L.cost; }
      if(q>1e-9){
        const avg=cs/q, hasP = S.prices[tk]!=null && S.prices[tk]!=="";
        const cp = hasP? num(S.prices[tk]) : avg;
        posVal += q*cp; unreal += (cp-avg)*q;
        open.push({ticker:tk, qty:q, avg, hasP, unreal:(cp-avg)*q});
      }
    }
    const cash = principal - buySpent + sellGot;
    const equity = cash + posVal, pnl = equity - principal;
    const realizedPnl = realized.reduce((s,r)=>s+r.pnl,0);
    const wins = realized.filter(r=>r.pnl>0).length;
    return { principal, cash, equity, pnl, realizedPnl, unreal, posVal, fees, realized, open,
      wins, winRate: realized.length? wins/realized.length*100:0,
      avgRet: realized.length? realized.reduce((s,r)=>s+r.pnlPct,0)/realized.length:0,
      avgHold: realized.length? realized.reduce((s,r)=>s+r.holdDays,0)/realized.length:0,
      nClosed: realized.length };
  }

  /* ---------- render ---------- */
  function renderData(){
    if(!built) return;
    const m = compute(), g = S.goal;
    $("g_fx").value = g.fx ? g.fx : "";
    $("g_gName").textContent = g.name || "목표를 설정하세요";
    $("g_gDates").textContent = (g.start||"—")+" → "+(g.end||"—");
    $("g_gDday").textContent = g.end ? (dayDiff(todayStr(),g.end)>=0? "D-"+dayDiff(todayStr(),g.end) : "D+"+Math.abs(dayDiff(todayStr(),g.end))) : "D-—";
    const target=num(g.target), prog = target>0? Math.max(0,m.equity/target*100):0;
    $("g_ringArc").setAttribute("stroke-dashoffset", (251.3*(1-Math.min(prog,100)/100)).toFixed(1));
    $("g_ringPct").textContent = Math.round(prog)+"%";
    $("g_equity").textContent = money(m.equity);
    $("g_target").textContent = money(target);
    const retPct = m.principal>0 ? m.pnl/m.principal*100 : 0;
    const badge=$("g_pnlBadge");
    badge.className="g-pnlbadge "+(m.pnl>=0?"pos":"neg");
    badge.textContent=(m.pnl>=0?"▲ ":"▼ ")+signMoney(m.pnl)+" · "+pctf(retPct);
    $("g_gRemain").textContent = target>0 ? "남은 "+money(Math.max(0,target-m.equity))+(g.end?" · "+Math.max(0,dayDiff(todayStr(),g.end))+"일":"") : "";
    $("g_kPrin").textContent = money(m.principal);
    const kr=$("g_kReal"); kr.textContent=signMoney(m.realizedPnl); kr.className="g-v "+(m.realizedPnl>=0?"up":"dn");
    const ku=$("g_kUnreal"); ku.textContent=signMoney(m.unreal); ku.className="g-v "+(m.unreal>=0?"up":"dn");
    const fx = num(g.fx);
    $("g_won").innerHTML = fx>0
      ? "≈ <b>"+wonN(m.equity*fx)+"</b> <span class='g-fxhint'>원화환산 · 평가손익 "+(m.pnl>=0?"+":"−")+wonN(Math.abs(m.pnl)*fx)+"</span>"
      : "<span class='g-fxhint'>환율 입력/↻ 자동 시 원화 환산 표시</span>";

    const cr=$("g_cashRows"); cr.innerHTML="";
    if(!S.cash.length) cr.innerHTML="<div class='g-empty'>입출금 내역이 없습니다.</div>";
    [...S.cash].sort((a,b)=>a.date<b.date?1:-1).forEach(c=>{
      const d=document.createElement("div"); d.className="g-row";
      d.innerHTML="<div class='g-grow'><b>"+mmdd(c.date)+"</b> · "+(c.type==="in"?"입금":"출금")+
        (c.memo?" <span class='g-sub'>"+esc(c.memo)+"</span>":"")+"</div>"+
        "<span class='g-amtc "+(c.type==="in"?"up":"dn")+"'>"+(c.type==="in"?"+":"−")+money(num(c.amount))+"</span>"+
        "<span class='g-acts'></span>";
      const a=d.querySelector(".g-acts");
      a.appendChild(mkBtn("✎",()=>startEditCash(c)));
      a.appendChild(mkBtn("🗑",()=>{ if(confirm("삭제할까요?")){ S.cash=S.cash.filter(x=>x.id!==c.id); save(); }}));
      cr.appendChild(d);
    });

    // 티커 필터 옵션(거래에 있는 종목만)
    const tks=[...new Set(S.trades.map(t=>(t.ticker||"").toUpperCase()).filter(Boolean))].sort();
    const tf=$("g_tFilter");
    if(tf){
      tf.innerHTML="<option value='all'>전체</option>"+
        tks.map(k=>"<option value='"+esc(k)+"'>"+esc(k)+"</option>").join("");
      tf.value=(tradeTicker==="all"||tks.includes(tradeTicker))?tradeTicker:"all";
      tradeTicker=tf.value;
    }
    const tr=$("g_tradeRows"); tr.innerHTML="";
    const tlist=[...S.trades]
      .filter(t=>tradeTicker==="all"||(t.ticker||"").toUpperCase()===tradeTicker)
      .sort((a,b)=>a.date<b.date?1:-1);
    if(!tlist.length) tr.innerHTML="<div class='g-empty'>거래 내역이 없습니다.</div>";
    tlist.forEach(t=>{
      const d=document.createElement("div"); d.className="g-row";
      d.innerHTML="<div class='g-grow'><b>"+mmdd(t.date)+"</b> · "+
        "<b style='color:"+(t.side==="buy"?"#16a34a":"#3b82f6")+"'>"+(t.side==="buy"?"매수":"매도")+"</b> "+
        "<b>"+esc((t.ticker||"").toUpperCase())+"</b> <span class='g-sub'>"+num(t.qty)+"주 @ "+money2(num(t.price))+
        (num(t.fee)?" · 수수료 "+money2(num(t.fee)):"")+"</span></div><span class='g-acts'></span>";
      const a=d.querySelector(".g-acts");
      a.appendChild(mkBtn("✎",()=>startEditTrade(t)));
      a.appendChild(mkBtn("🗑",()=>{ if(confirm("삭제할까요?")){ S.trades=S.trades.filter(x=>x.id!==t.id); save(); }}));
      tr.appendChild(d);
    });

    renderJournal(m);
  }

  function renderJournal(m){
    // 월별 필터 옵션(청산 시점 기준)
    const months=[...new Set(m.realized.map(r=>r.sellDate.slice(0,7)))].sort().reverse();
    const sel=$("g_jMonth");
    if(sel){
      sel.innerHTML="<option value='all'>전체</option>"+months.map(mo=>
        "<option value='"+mo+"'>"+mo.slice(0,4)+"년 "+(+mo.slice(5,7))+"월</option>").join("");
      sel.value=(journalMonth==="all"||months.includes(journalMonth))?journalMonth:"all";
      journalMonth=sel.value;
    }
    let real=m.realized;
    if(journalMonth!=="all") real=real.filter(r=>r.sellDate.slice(0,7)===journalMonth);
    lastReal=real;

    // 통계(필터 반영) + 손익비
    const n=real.length;
    const realizedPnl=real.reduce((s,r)=>s+r.pnl,0);
    const wins=real.filter(r=>r.pnl>0).length;
    const winRate=n?wins/n*100:0;
    const avgRet=n?real.reduce((s,r)=>s+r.pnlPct,0)/n:0;
    const avgHold=n?real.reduce((s,r)=>s+r.holdDays,0)/n:0;
    const wA=real.filter(r=>r.pnl>0).map(r=>r.pnl), lA=real.filter(r=>r.pnl<0).map(r=>-r.pnl);
    const avgWin=wA.length?wA.reduce((a,b)=>a+b,0)/wA.length:0;
    const avgLoss=lA.length?lA.reduce((a,b)=>a+b,0)/lA.length:0;
    const payoff=avgLoss>0?avgWin/avgLoss:(avgWin>0?Infinity:0);

    $("g_jReal").textContent=signMoney(realizedPnl); $("g_jReal").className="g-sv "+(realizedPnl>=0?"up":"dn");
    $("g_jWin").innerHTML=Math.round(winRate)+"% <span class='g-faint'>("+wins+"/"+n+")</span>";
    $("g_jPayoff").textContent=n?(payoff===Infinity?"∞":payoff.toFixed(2)):"—";
    $("g_jAvg").textContent=n?pctf(avgRet):"—"; $("g_jAvg").className="g-sv "+(avgRet>=0?"up":"dn");
    $("g_jHold").textContent=n?(Math.round(avgHold)+"일"):"—";

    const cl=$("g_closedRows"); cl.innerHTML="";
    if(!real.length) cl.innerHTML="<div class='g-empty'>청산된 매매가 없습니다.</div>";
    [...real].sort((a,b)=>a.sellDate<b.sellDate?1:-1).forEach(r=>{
      const pos=r.pnl>=0, d=document.createElement("div");
      d.className="g-closed "+(pos?"pos":"neg");
      d.innerHTML="<div class='g-closed-top'><b>"+esc(r.ticker)+"</b>"+
        "<span class='"+(pos?"up":"dn")+"' style='font-weight:800'>"+signMoney(r.pnl)+" · "+pctf(r.pnlPct)+"</span></div>"+
        "<div class='g-sub'>"+mmdd(r.buyDate)+" 매수 "+money2(r.buyPrice)+" → "+mmdd(r.sellDate)+" 매도 "+money2(r.sellPrice)+
        " · "+(Math.round(r.qty*100)/100)+"주 · 보유 "+r.holdDays+"일</div>";
      cl.appendChild(d);
    });

    const op=$("g_openRows"); op.innerHTML="";
    if(!m.open.length) op.innerHTML="<div class='g-empty'>보유중 종목이 없습니다.</div>";
    m.open.forEach(o=>{
      const d=document.createElement("div"); d.className="g-row";
      d.innerHTML="<div class='g-grow'><b>"+esc(o.ticker)+"</b> <span class='g-sub'>"+(Math.round(o.qty*100)/100)+"주 · 평단 "+px(o.avg)+
        (o.hasP? " · 손익 <b class='"+(o.unreal>=0?"up":"dn")+"'>"+signMoney(o.unreal)+"</b>":"")+"</span></div>";
      const inp=document.createElement("input"); inp.className="g-price"; inp.type="number";
      inp.placeholder="현재가"; inp.inputMode="decimal";
      inp.value = (S.prices[o.ticker]!=null? S.prices[o.ticker] : "");
      inp.onchange = ()=>{ if(inp.value==="") delete S.prices[o.ticker]; else S.prices[o.ticker]=num(inp.value); save(); };
      d.appendChild(inp); op.appendChild(d);
    });
    // 종목별 성과 (실현손익 막대그래프, 필터 반영)
    const tk={}; real.forEach(r=>{ const o=tk[r.ticker]=tk[r.ticker]||{pnl:0,w:0,n:0};
      o.pnl+=r.pnl; o.n++; if(r.pnl>0)o.w++; });
    const tkr=$("g_tkRows"); tkr.innerHTML="";
    const tks=Object.keys(tk).sort((a,b)=>tk[b].pnl-tk[a].pnl);
    if(!tks.length){ tkr.innerHTML="<div class='g-empty'>청산된 매매가 없습니다.</div>"; }
    const maxAbs=Math.max(1,...tks.map(k=>Math.abs(tk[k].pnl)));
    tks.forEach(k=>{ const t=tk[k], pos=t.pnl>=0, w=Math.round(Math.abs(t.pnl)/maxAbs*100);
      const d=document.createElement("div"); d.className="g-barrow";
      d.title=t.n+"건 · "+t.w+"승 "+(t.n-t.w)+"패";
      d.innerHTML="<span class='g-bartk'>"+esc(k)+"</span>"+
        "<div class='g-bartrack'><div class='g-barfill' style='width:"+w+"%;background:"+(pos?"#16a34a":"#3b82f6")+"'></div></div>"+
        "<span class='g-baramt "+(pos?"up":"dn")+"'>"+signMoney(t.pnl)+"</span>";
      tkr.appendChild(d); });
  }

  function mkBtn(t,fn){ const b=document.createElement("button"); b.className="g-ico"; b.textContent=t; b.onclick=fn; return b; }

  /* ---------- add / edit ---------- */
  function addCash(){
    const amt=num($("g_cAmt").value); if(amt<=0){ alert("금액을 입력하세요."); return; }
    const o={ date:$("g_cDate").value||todayStr(), type:$("g_cType").value, amount:amt, memo:$("g_cMemo").value.trim() };
    if(editCash){ o.id=editCash; S.cash=S.cash.map(x=>x.id===editCash?o:x); editCash=null; $("g_cAdd").textContent="추가"; }
    else { o.id=uuid(); S.cash.push(o); }
    $("g_cAmt").value=""; $("g_cMemo").value=""; save();
  }
  function startEditCash(c){ editCash=c.id; $("g_cDate").value=c.date; $("g_cType").value=c.type;
    $("g_cAmt").value=c.amount; $("g_cMemo").value=c.memo||""; $("g_cAdd").textContent="수정 완료";
    ROOT.querySelector('[data-t="asset"]').click(); }
  function addTrade(){
    const tk=$("g_tTk").value.trim().toUpperCase(), q=num($("g_tQty").value), p=num($("g_tPrice").value);
    if(!tk){ alert("티커를 입력하세요."); return; }
    if(q<=0||p<=0){ alert("수량·단가를 입력하세요."); return; }
    const o={ date:$("g_tDate").value||todayStr(), side:$("g_tSide").value, ticker:tk, qty:q, price:p, fee:num($("g_tFee").value) };
    if(editTrade){ o.id=editTrade; S.trades=S.trades.map(x=>x.id===editTrade?o:x); editTrade=null; $("g_tAdd").textContent="추가"; }
    else { o.id=uuid(); S.trades.push(o); }
    $("g_tTk").value=""; $("g_tQty").value=""; $("g_tPrice").value=""; $("g_tFee").value=""; save();
  }
  function startEditTrade(t){ editTrade=t.id; $("g_tDate").value=t.date; $("g_tSide").value=t.side;
    $("g_tTk").value=(t.ticker||"").toUpperCase(); $("g_tQty").value=t.qty; $("g_tPrice").value=t.price;
    $("g_tFee").value=t.fee||""; $("g_tAdd").textContent="수정 완료";
    ROOT.querySelector('[data-t="journal"]').click(); }
  function openGoalEdit(){
    const g=S.goal;
    $("ge_name").value=g.name||""; $("ge_target").value=g.target||"";
    $("ge_start").value=g.start||todayStr(); $("ge_end").value=g.end||"";
    $("g_goalEdit").style.display="";
  }
  function saveGoalEdit(){
    S.goal={ name:$("ge_name").value.trim(), cur:"$", fx:S.goal.fx||0,
      target:num($("ge_target").value), start:$("ge_start").value, end:$("ge_end").value };
    $("g_goalEdit").style.display="none"; save();
  }
  async function fetchFx(){
    const btn=$("g_fxAuto"), old=btn.textContent; btn.textContent="…";
    try{
      const r=await fetch("https://open.er-api.com/v6/latest/USD");
      const j=await r.json();
      const rate=j && j.rates && j.rates.KRW;
      if(!rate) throw new Error("환율 데이터 없음");
      S.goal.fx=Math.round(rate*100)/100;
      if($("g_fxAt")) $("g_fxAt").textContent="("+((j.time_last_update_utc||"").slice(0,16))+" 기준)";
      renderData(); save();
    }catch(e){ alert("환율 자동조회 실패: "+(e.message||e)+"\n직접 입력해 주세요."); }
    finally{ btn.textContent=old; }
  }
  async function fetchPrices(){
    const btn=$("g_priceAuto"), old=btn.textContent; btn.textContent="…";
    try{
      const r=await fetch("prices.json?t="+Date.now());
      if(!r.ok) throw new Error("prices.json 없음("+r.status+")");
      const j=await r.json(); const pr=j.prices||{}; let n=0; const miss=[];
      compute().open.forEach(o=>{ if(pr[o.ticker]!=null){ S.prices[o.ticker]=pr[o.ticker]; n++; } else miss.push(o.ticker); });
      if($("g_priceNote")) $("g_priceNote").textContent =
        "시세 기준 "+(j.asof||"?")+" · "+n+"개 반영"+(miss.length? " · 미포함(수동): "+miss.join(", "):"");
      renderData(); save();
    }catch(e){ alert("현재가 불러오기 실패: "+(e.message||e)); }
    finally{ btn.textContent=old; }
  }
  function exportCSV(){
    if(!lastReal.length){ alert("내보낼 청산 매매가 없습니다."); return; }
    const rows=[["종목","매수일","매수단가","매도일","매도단가","수량","실현손익","수익률(%)","보유일"]];
    [...lastReal].sort((a,b)=>a.sellDate<b.sellDate?1:-1).forEach(r=>rows.push([
      r.ticker, r.buyDate, r.buyPrice.toFixed(4), r.sellDate, r.sellPrice.toFixed(4),
      r.qty, r.pnl.toFixed(2), r.pnlPct.toFixed(2), r.holdDays]));
    const csv=rows.map(row=>row.map(c=>'"'+String(c).replace(/"/g,'""')+'"').join(",")).join("\n");
    const blob=new Blob(["﻿"+csv],{type:"text/csv;charset=utf-8"});
    const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
    a.download="매매일지_"+(journalMonth==="all"?"전체":journalMonth)+".csv";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }
}

/* ---------- shell HTML ---------- */
function SHELL_HTML(){ return ''+
  '<div class="g-lock">🔒 이 데이터는 나만 볼 수 있어요 · 실시간 동기화</div>'+
  '<div id="g_ruleErr" class="g-err" style="display:none"></div>'+
  '<div class="g-subtabs"><button class="g-subtab on" data-t="asset">자산·목표</button>'+
  '<button class="g-subtab" data-t="journal">매매일지</button></div>'+
  '<div id="g_asset">'+
    '<div class="g-card"><div class="g-ghead"><div>'+
      '<div class="g-gname" id="g_gName">목표를 설정하세요</div>'+
      '<div class="g-gdates" id="g_gDates">—</div></div>'+
      '<div class="g-hactions"><span class="g-dday" id="g_gDday">D-—</span>'+
      '<button type="button" class="g-gear" id="g_editGoal" title="목표 수정">⚙</button></div></div>'+
    '<div class="g-ringrow">'+
      '<svg class="g-ring" width="98" height="98" viewBox="0 0 98 98">'+
        '<circle cx="49" cy="49" r="40" fill="none" stroke="var(--nav-track)" stroke-width="11"/>'+
        '<circle id="g_ringArc" cx="49" cy="49" r="40" fill="none" stroke="#16a34a" stroke-width="11" stroke-linecap="round" stroke-dasharray="251.3" stroke-dashoffset="251.3" transform="rotate(-90 49 49)"/>'+
        '<text id="g_ringPct" x="49" y="45" text-anchor="middle" font-size="21" font-weight="800" fill="#16a34a">0%</text>'+
        '<text x="49" y="62" text-anchor="middle" font-size="9" fill="var(--faint)">달성률</text>'+
      '</svg>'+
      '<div class="g-ringside">'+
        '<div class="g-rlabel">평가액 / 목표</div>'+
        '<div class="g-rmain"><span id="g_equity">$0</span> <span class="g-rtarget">/ <span id="g_target">$0</span></span></div>'+
        '<div id="g_pnlBadge" class="g-pnlbadge pos">▲ +$0 · +0%</div>'+
        '<div class="g-note" id="g_gRemain"></div>'+
      '</div></div>'+
    '<div class="g-kpis">'+
      '<div class="g-kpi"><div class="g-l">원금(순입금)</div><div class="g-v" id="g_kPrin">0</div></div>'+
      '<div class="g-kpi"><div class="g-l">실현손익</div><div class="g-v" id="g_kReal">0</div></div>'+
      '<div class="g-kpi"><div class="g-l">미실현손익</div><div class="g-v" id="g_kUnreal">0</div></div></div>'+
    '<div class="g-won" id="g_won"></div>'+
    '<div class="g-fx"><span>$1 =</span>'+
      '<input id="g_fx" class="g-fxin" inputmode="decimal" placeholder="환율">'+
      '<span>원</span><button type="button" class="g-btn sm" id="g_fxAuto">↻ 자동</button>'+
      '<span class="g-fxat" id="g_fxAt"></span></div>'+
    '<div id="g_goalEdit" class="g-gedit" style="display:none">'+
      '<div class="g-frm"><input id="ge_name" class="g-memo" placeholder="목표 이름"></div>'+
      '<div class="g-frm"><span class="g-gelabel">목표금액 $</span>'+
        '<input id="ge_target" class="g-amt" inputmode="decimal" placeholder="예: 40000"></div>'+
      '<div class="g-frm"><span class="g-gelabel">시작</span>'+
        '<input type="date" id="ge_start" class="g-date"><button type="button" class="g-cal" data-for="ge_start" aria-label="달력">📅</button>'+
        '<span class="g-gelabel">목표일</span>'+
        '<input type="date" id="ge_end" class="g-date"><button type="button" class="g-cal" data-for="ge_end" aria-label="달력">📅</button></div>'+
      '<div style="display:flex;gap:6px;justify-content:flex-end;margin-top:4px">'+
        '<button class="g-btn sm" id="ge_cancel">취소</button>'+
        '<button class="g-btn pri sm" id="ge_save">저장</button></div>'+
    '</div></div>'+
    '<div class="g-card"><div class="g-sect">입출금</div>'+
      '<div class="g-frm"><input type="date" class="g-date" id="g_cDate">'+
      '<button type="button" class="g-cal" data-for="g_cDate" aria-label="달력 열기">📅</button>'+
      '<select id="g_cType"><option value="in">입금</option><option value="out">출금</option></select>'+
      '<input type="number" class="g-amt" id="g_cAmt" placeholder="금액" inputmode="decimal">'+
      '<input type="text" class="g-memo" id="g_cMemo" placeholder="메모(선택)">'+
      '<button class="g-btn pri" id="g_cAdd">추가</button></div>'+
      '<div id="g_cashRows"></div></div>'+
  '</div>'+
  '<div id="g_journal" style="display:none">'+
    '<div class="g-card"><div class="g-sect">거래 입력 (티커: AAPL, NVDA …)</div>'+
      '<div class="g-frm"><input type="date" class="g-date" id="g_tDate">'+
      '<button type="button" class="g-cal" data-for="g_tDate" aria-label="달력 열기">📅</button>'+
      '<select id="g_tSide"><option value="buy">매수</option><option value="sell">매도</option></select>'+
      '<input type="text" class="g-tk" id="g_tTk" placeholder="티커">'+
      '<input type="number" class="g-num" id="g_tQty" placeholder="수량" inputmode="decimal">'+
      '<input type="number" class="g-num" id="g_tPrice" placeholder="단가" inputmode="decimal">'+
      '<input type="number" class="g-num" id="g_tFee" placeholder="수수료" inputmode="decimal">'+
      '<button class="g-btn pri" id="g_tAdd">추가</button></div>'+
      '<div class="g-tfilter">종목별 보기 '+
        '<select id="g_tFilter"><option value="all">전체</option></select></div>'+
      '<div id="g_tradeRows"></div></div>'+
    '<div class="g-jbar"><div class="g-jfilter"><span>월별</span>'+
      '<select id="g_jMonth"><option value="all">전체</option></select></div>'+
      '<button type="button" class="g-btn sm" id="g_csv">⤓ CSV 내보내기</button></div>'+
    '<div class="g-stats">'+
      '<div class="g-stat"><div class="g-sl">실현손익</div><div class="g-sv" id="g_jReal">0</div></div>'+
      '<div class="g-stat"><div class="g-sl">승률</div><div class="g-sv" id="g_jWin">0%</div></div>'+
      '<div class="g-stat"><div class="g-sl">손익비</div><div class="g-sv" id="g_jPayoff">—</div></div>'+
      '<div class="g-stat"><div class="g-sl">평균수익</div><div class="g-sv" id="g_jAvg">0%</div></div>'+
      '<div class="g-stat"><div class="g-sl">평균보유</div><div class="g-sv" id="g_jHold">0일</div></div></div>'+
    '<div class="g-card"><div class="g-sect">종목별 성과 (실현손익)</div><div id="g_tkRows"></div></div>'+
    '<div class="g-card"><div class="g-sect">청산 매매 (자동 매칭)</div><div id="g_closedRows"></div></div>'+
    '<div class="g-card"><div class="g-sect" style="display:flex;justify-content:space-between;align-items:center;gap:8px">'+
      '<span>보유중 (미청산)</span>'+
      '<button type="button" class="g-btn sm" id="g_priceAuto">↻ 현재가 불러오기</button></div>'+
      '<div id="g_openRows"></div>'+
      '<div class="g-note" id="g_priceNote">현재가 비우면 평단가로 계산. ↻로 추적 종목 현재가 자동 반영(언제든 갱신 · 시세는 수시 자동 갱신).</div></div>'+
  '</div>';
}

/* ---------- styles (사이트 변수 재사용 → 다크모드 자동) ---------- */
function injectStyle(){
  if (document.getElementById("g_style")) return;
  const s = document.createElement("style"); s.id="g_style";
  s.textContent = `
  #goalRoot .up{color:#e5484d}#goalRoot .dn{color:#3b82f6}#goalRoot .g-faint{color:var(--faint);font-size:11px;font-weight:600}
  #goalRoot .g-login{max-width:390px;margin:7vh auto;text-align:center;padding:24px 20px;
    background:var(--card);border:1px solid var(--border);border-radius:16px;box-shadow:0 2px 12px rgba(15,27,45,.06)}
  #goalRoot .g-login-ic{font-size:30px}#goalRoot .g-login-t{font-size:18px;font-weight:800;margin:8px 0 4px}
  #goalRoot .g-login-p{color:var(--muted);font-size:12.5px;line-height:1.65;margin-bottom:20px}
  #goalRoot .g-btn{font:inherit;font-size:12.5px;font-weight:700;border-radius:9px;padding:8px 13px;
    border:1px solid var(--border);background:var(--chip);color:var(--ink);cursor:pointer}
  #goalRoot .g-btn:active{transform:translateY(1px)}
  #goalRoot .g-btn.pri{background:var(--accent);color:#fff;border-color:var(--accent);font-size:13.5px;padding:9px 17px}
  #goalRoot .g-btn.dark{background:var(--ink);color:var(--page);border-color:var(--ink)}
  #goalRoot .g-btn.sm{font-size:11px;padding:5px 11px}
  #goalRoot .g-subtabs{display:flex;gap:5px;background:var(--nav-track);border:1px solid var(--border);
    border-radius:12px;padding:5px;margin-bottom:13px}
  #goalRoot .g-subtab{flex:1;text-align:center;font:inherit;font-size:12.5px;font-weight:700;color:var(--muted-2);
    background:transparent;border:0;border-radius:8px;padding:9px;cursor:pointer;transition:color .12s}
  #goalRoot .g-subtab.on{background:var(--accent);color:#fff;box-shadow:0 1px 4px rgba(58,111,216,.4)}
  #goalRoot .g-lock{display:flex;align-items:center;gap:6px;background:var(--chip);border:1px solid var(--border);
    border-radius:10px;padding:8px 11px;margin-bottom:12px;font-size:11px;color:var(--muted);font-weight:600}
  #goalRoot .g-card{background:var(--card);border:1px solid var(--border);border-radius:16px;
    padding:15px 16px;margin-bottom:11px;box-shadow:0 1px 5px rgba(15,27,45,.05)}
  #goalRoot .g-sect{font-size:11px;font-weight:800;color:var(--muted-2);margin-bottom:11px;letter-spacing:.02em}
  #goalRoot .g-ghead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
  #goalRoot .g-gname{font-size:16px;font-weight:800}#goalRoot .g-gdates{font-size:11px;color:var(--muted);margin-top:3px}
  #goalRoot .g-dday{font-size:11px;font-weight:800;color:var(--accent);background:var(--chip);
    border:1px solid var(--border);border-radius:999px;padding:4px 11px;white-space:nowrap}
  #goalRoot .g-ghr{display:flex;flex-direction:column;align-items:flex-end;gap:6px}
  #goalRoot .g-cursel{font:inherit;font-size:11px;font-weight:700;border:1px solid var(--border);
    border-radius:8px;padding:5px 8px;background:var(--card);color:var(--ink);cursor:pointer}
  #goalRoot .g-prog{margin:15px 0 6px;display:flex;align-items:baseline;justify-content:space-between}
  #goalRoot .g-pct{font-size:27px;font-weight:800;color:#16a34a;letter-spacing:-.01em}
  #goalRoot .g-psub{font-size:12px;color:var(--muted);font-weight:600}
  #goalRoot .g-bar{height:14px;border-radius:9px;background:var(--nav-track);overflow:hidden;border:1px solid var(--border)}
  #goalRoot .g-bar>i{display:block;height:100%;border-radius:9px;background:#16a34a;transition:width .4s ease}
  #goalRoot .g-note{font-size:10.5px;color:var(--faint);margin-top:6px}
  #goalRoot .g-kpis{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:14px}
  #goalRoot .g-kpi{background:var(--nav-track);border-radius:12px;padding:11px 12px}
  #goalRoot .g-l{font-size:10px;color:var(--muted);font-weight:600}
  #goalRoot .g-v{font-size:16px;font-weight:800;margin-top:3px;letter-spacing:-.01em}
  #goalRoot .g-break{margin-top:12px;background:var(--nav-track);border:1px dashed var(--border);border-radius:12px;
    padding:11px 13px;font-size:11px;color:var(--muted);line-height:1.75}
  #goalRoot .g-fx{display:flex;align-items:center;gap:7px;margin-top:12px;font-size:12px;
    color:var(--muted);font-weight:600;flex-wrap:wrap}
  #goalRoot .g-fxin{width:92px;font:inherit;font-size:12.5px;border:1px solid var(--border);
    border-radius:8px;padding:6px 9px;background:var(--card);color:var(--ink)}
  #goalRoot .g-fxat{font-size:10px;color:var(--faint);font-weight:500}
  #goalRoot .g-won{margin-top:11px;padding-top:10px;border-top:1px solid var(--border);
    font-size:11.5px;color:var(--muted);line-height:1.65}
  #goalRoot .g-fxhint{color:var(--faint);font-size:11px}
  #goalRoot .g-gedit{margin-top:12px;padding:12px;background:var(--nav-track);
    border:1px solid var(--border);border-radius:12px}
  #goalRoot .g-gelabel{font-size:11px;color:var(--muted);font-weight:700;align-self:center;white-space:nowrap}
  #goalRoot .g-hactions{display:flex;align-items:center;gap:8px}
  #goalRoot .g-gear{font:inherit;font-size:16px;line-height:1;border:0;background:none;color:var(--faint);cursor:pointer;padding:2px}
  #goalRoot .g-gear:hover{color:var(--accent)}
  #goalRoot .g-ringrow{display:flex;align-items:center;gap:16px;margin:14px 0 4px}
  #goalRoot .g-ring{flex-shrink:0}
  #goalRoot .g-ringside{flex:1;min-width:0}
  #goalRoot .g-rlabel{font-size:11px;color:var(--muted)}
  #goalRoot .g-rmain{font-size:20px;font-weight:800;letter-spacing:-.02em;margin-top:1px}
  #goalRoot .g-rtarget{font-size:13px;color:var(--faint);font-weight:600}
  #goalRoot .g-pnlbadge{display:inline-flex;align-items:center;gap:4px;font-size:13px;font-weight:800;border-radius:8px;padding:3px 9px;margin-top:6px}
  #goalRoot .g-pnlbadge.pos{color:#e5484d;background:rgba(229,72,77,.12)}
  #goalRoot .g-pnlbadge.neg{color:#3b82f6;background:rgba(59,130,246,.12)}
  #goalRoot .g-stats{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin-bottom:11px}
  @media(max-width:430px){#goalRoot .g-stats{grid-template-columns:repeat(3,1fr)}}
  #goalRoot .g-stat{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:10px 5px;text-align:center}
  #goalRoot .g-jbar{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}
  #goalRoot .g-jfilter{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);font-weight:600}
  #goalRoot .g-jfilter select{font:inherit;font-size:12px;border:1px solid var(--border);border-radius:8px;
    padding:5px 8px;background:var(--card);color:var(--ink);cursor:pointer}
  #goalRoot .g-sl{font-size:9px;color:var(--muted)}
  #goalRoot .g-sv{font-size:15px;font-weight:800;margin-top:2px}
  #goalRoot .g-barrow{display:flex;align-items:center;gap:9px;margin-bottom:9px}
  #goalRoot .g-barrow:last-child{margin-bottom:0}
  #goalRoot .g-bartk{width:46px;font-size:12px;font-weight:800;flex-shrink:0}
  #goalRoot .g-bartrack{flex:1;height:16px;background:var(--nav-track);border-radius:5px;overflow:hidden}
  #goalRoot .g-barfill{height:100%;border-radius:5px;transition:width .4s ease}
  #goalRoot .g-baramt{width:56px;text-align:right;font-size:12px;font-weight:800;flex-shrink:0}
  #goalRoot .g-closed{border-left:3px solid var(--border);padding:3px 0 3px 10px;margin-bottom:10px}
  #goalRoot .g-closed:last-child{margin-bottom:0}
  #goalRoot .g-closed.pos{border-left-color:#16a34a}
  #goalRoot .g-closed.neg{border-left-color:#3b82f6}
  #goalRoot .g-closed-top{display:flex;justify-content:space-between;align-items:baseline;font-size:13px}
  #goalRoot .g-frm{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
  #goalRoot .g-frm input,#goalRoot .g-frm select{font:inherit;font-size:12.5px;border:1px solid var(--border);
    border-radius:8px;padding:8px 9px;background:var(--card);color:var(--ink);min-width:0}
  #goalRoot .g-tfilter{display:flex;align-items:center;gap:6px;font-size:11.5px;
    color:var(--muted);font-weight:600;margin-bottom:8px}
  #goalRoot .g-tfilter select{font:inherit;font-size:12px;border:1px solid var(--border);
    border-radius:8px;padding:5px 9px;background:var(--card);color:var(--ink);cursor:pointer}
  #goalRoot .g-date{width:118px}#goalRoot .g-tk{width:82px;text-transform:uppercase}
  #goalRoot .g-date::-webkit-calendar-picker-indicator{display:none}
  #goalRoot .g-date::-webkit-inner-spin-button{display:none}
  #goalRoot .g-cal{font-size:15px;line-height:1;border:1px solid var(--border);background:var(--chip);
    border-radius:8px;padding:6px 9px;cursor:pointer;flex-shrink:0}
  #goalRoot .g-cal:active{transform:translateY(1px)}
  #goalRoot .g-num{width:74px}#goalRoot .g-amt{width:122px}#goalRoot .g-memo{flex:1;min-width:90px}
  #goalRoot .g-row{display:flex;align-items:center;gap:9px;padding:9px 2px;border-top:1px solid var(--border);font-size:12.5px}
  #goalRoot .g-row:first-child{border-top:0}#goalRoot .g-grow{flex:1;min-width:0}
  #goalRoot .g-sub{font-size:11px;color:var(--muted)}#goalRoot .g-amtc{font-weight:800;white-space:nowrap}
  #goalRoot .g-acts{display:flex;gap:5px;flex-shrink:0}
  #goalRoot .g-ico{font:inherit;font-size:12px;border:1px solid var(--border);background:var(--card);
    border-radius:7px;padding:4px 8px;cursor:pointer;color:var(--muted)}
  #goalRoot .g-empty{font-size:11.5px;color:var(--faint);padding:10px 0;text-align:center}
  #goalRoot .g-price{width:92px;font:inherit;font-size:12.5px;border:1px solid var(--border);border-radius:8px;
    padding:6px 8px;background:var(--card);color:var(--ink)}
  #goalRoot .g-err{background:#fdeeee;border:1px solid #f5cccc;color:#b91c1c;border-radius:10px;
    padding:10px 12px;font-size:11.5px;margin-bottom:11px;line-height:1.5}
  @media (max-width:440px){#goalRoot .g-kpis{grid-template-columns:1fr 1fr}}
  `;
  document.head.appendChild(s);
}
