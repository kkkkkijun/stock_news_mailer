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
  const defState = () => ({ goal:{name:"",target:0,start:"",end:"",cur:"$"}, cash:[], trades:[], prices:{} });
  let S = defState();

  const $ = id => document.getElementById(id);
  const num = v => { const n = parseFloat(v); return isFinite(n) ? n : 0; };
  const curSym = () => S.goal.cur || "$";
  const money = n => curSym() + Math.round(n).toLocaleString();
  const money2 = n => curSym() + (Math.round(n*100)/100).toLocaleString(undefined,{maximumFractionDigits:2});
  const pctf = n => (n>=0?"+":"") + (Math.round(n*10)/10) + "%";
  const signMoney = n => (n>=0?"+":"−") + curSym() + Math.abs(Math.round(n)).toLocaleString();
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
    $("g_editGoal").onclick = editGoal;
    $("g_cur").onchange = () => { S.goal.cur = $("g_cur").value; renderData(); save(); };
    $("g_genBtn").onclick = () => { renderJournal(compute());
      $("g_genBtn").textContent="✓ 갱신됨"; setTimeout(()=>$("g_genBtn").textContent="⚙ 매매일지 생성 / 새로고침",1200); };
  }

  /* ---------- compute (연동) ---------- */
  function compute(){
    let dep=0, wd=0;
    for(const c of S.cash){ if(c.type==="in") dep+=num(c.amount); else wd+=num(c.amount); }
    const principal = dep - wd;
    const trades = [...S.trades].sort((a,b)=> (a.date<b.date?-1:a.date>b.date?1:0));
    const lots = {}; const realized = []; let buySpent=0, sellGot=0;
    for(const t of trades){
      const q=num(t.qty), p=num(t.price), fee=num(t.fee), tk=(t.ticker||"").toUpperCase();
      if(q<=0) continue;
      if(!lots[tk]) lots[tk]=[];
      if(t.side==="buy"){ buySpent += q*p+fee; lots[tk].push({qty:q, cost:p+fee/q, date:t.date}); }
      else {
        sellGot += q*p-fee; const sps=p-fee/q; let rem=q;
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
    return { principal, cash, equity, pnl, realizedPnl, unreal, posVal, realized, open,
      wins, winRate: realized.length? wins/realized.length*100:0,
      avgRet: realized.length? realized.reduce((s,r)=>s+r.pnlPct,0)/realized.length:0,
      avgHold: realized.length? realized.reduce((s,r)=>s+r.holdDays,0)/realized.length:0,
      nClosed: realized.length };
  }

  /* ---------- render ---------- */
  function renderData(){
    if(!built) return;
    const m = compute(), g = S.goal;
    $("g_cur").value = curSym();
    $("g_gName").textContent = g.name || "목표를 설정하세요";
    $("g_gDates").textContent = (g.start||"—")+" → "+(g.end||"—");
    $("g_gDday").textContent = g.end ? (dayDiff(todayStr(),g.end)>=0? "D-"+dayDiff(todayStr(),g.end) : "D+"+Math.abs(dayDiff(todayStr(),g.end))) : "D-—";
    const target=num(g.target), prog = target>0? Math.max(0,m.equity/target*100):0;
    $("g_gPct").textContent = (Math.round(prog*10)/10)+"%";
    $("g_gBar").style.width = Math.min(100,prog)+"%";
    $("g_gProgSub").textContent = money(m.equity)+" / "+money(target);
    $("g_gRemain").textContent = target>0 ? "남은 "+money(Math.max(0,target-m.equity))+(g.end?" · "+Math.max(0,dayDiff(todayStr(),g.end))+"일 남음":"") : "";
    $("g_kPrin").textContent = money(m.principal);
    $("g_kEquity").textContent = money(m.equity);
    const pe=$("g_kPnl"); pe.textContent=signMoney(m.pnl); pe.className="g-v "+(m.pnl>=0?"up":"dn");
    $("g_gBreak").innerHTML =
      "평가손익 <b class='"+(m.pnl>=0?"up":"dn")+"'>"+signMoney(m.pnl)+"</b> = "+
      "<b class='dn'>실현 "+signMoney(m.realizedPnl)+"</b> + "+
      "<b class='"+(m.unreal>=0?"up":"dn")+"'>미실현 "+signMoney(m.unreal)+"</b><br>"+
      "현금 <b>"+money(m.cash)+"</b> + 보유 포지션 <b>"+money(m.posVal)+"</b> = 평가액 <b>"+money(m.equity)+"</b>";

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

    const tr=$("g_tradeRows"); tr.innerHTML="";
    if(!S.trades.length) tr.innerHTML="<div class='g-empty'>거래 내역이 없습니다.</div>";
    [...S.trades].sort((a,b)=>a.date<b.date?1:-1).forEach(t=>{
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
    $("g_jReal").textContent = signMoney(m.realizedPnl);
    $("g_jReal").className = "g-v "+(m.realizedPnl>=0?"up":"dn");
    $("g_jWin").innerHTML = Math.round(m.winRate)+"% <span class='g-faint'>("+m.wins+"/"+m.nClosed+")</span>";
    $("g_jAvg").textContent = m.nClosed? pctf(m.avgRet):"—";
    $("g_jAvg").className = "g-v "+(m.avgRet>=0?"up":"dn");
    $("g_jHold").textContent = m.nClosed? (Math.round(m.avgHold)+"일"):"—";

    const cl=$("g_closedRows"); cl.innerHTML="";
    if(!m.realized.length) cl.innerHTML="<div class='g-empty'>청산된 매매가 없습니다.</div>";
    [...m.realized].sort((a,b)=>a.sellDate<b.sellDate?1:-1).forEach(r=>{
      const d=document.createElement("div"); d.className="g-row"; const cls=r.pnl>=0?"up":"dn";
      d.innerHTML="<div class='g-grow'><b>"+esc(r.ticker)+"</b>"+
        "<span class='g-amtc "+cls+"' style='float:right'>"+signMoney(r.pnl)+" · "+pctf(r.pnlPct)+"</span>"+
        "<div class='g-sub'>"+mmdd(r.buyDate)+" 매수 "+money2(r.buyPrice)+" → "+mmdd(r.sellDate)+" 매도 "+money2(r.sellPrice)+
        " · "+(Math.round(r.qty*100)/100)+"주 · 보유 "+r.holdDays+"일</div></div>";
      cl.appendChild(d);
    });

    const op=$("g_openRows"); op.innerHTML="";
    if(!m.open.length) op.innerHTML="<div class='g-empty'>보유중 종목이 없습니다.</div>";
    m.open.forEach(o=>{
      const d=document.createElement("div"); d.className="g-row";
      d.innerHTML="<div class='g-grow'><b>"+esc(o.ticker)+"</b> <span class='g-sub'>"+(Math.round(o.qty*100)/100)+"주 · 평단 "+money2(o.avg)+
        (o.hasP? " · 손익 <b class='"+(o.unreal>=0?"up":"dn")+"'>"+signMoney(o.unreal)+"</b>":"")+"</span></div>";
      const inp=document.createElement("input"); inp.className="g-price"; inp.type="number";
      inp.placeholder="현재가"; inp.inputMode="decimal";
      inp.value = (S.prices[o.ticker]!=null? S.prices[o.ticker] : "");
      inp.onchange = ()=>{ if(inp.value==="") delete S.prices[o.ticker]; else S.prices[o.ticker]=num(inp.value); save(); };
      d.appendChild(inp); op.appendChild(d);
    });
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
  function editGoal(){
    const name=prompt("목표 이름", S.goal.name||"3개월 목표"); if(name===null) return;
    const target=prompt("목표 금액(숫자만)", S.goal.target||""); if(target===null) return;
    const start=prompt("시작일 (YYYY-MM-DD)", S.goal.start||todayStr()); if(start===null) return;
    const end=prompt("목표일 (YYYY-MM-DD)", S.goal.end||""); if(end===null) return;
    S.goal={ name:name.trim(), cur:S.goal.cur||"$", target:num(target), start:start.trim(), end:end.trim() }; save();
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
      '<div class="g-ghr"><span class="g-dday" id="g_gDday">D-—</span>'+
      '<select id="g_cur" class="g-cursel"><option value="$">$ 달러</option>'+
      '<option value="₩">₩ 원</option></select></div></div>'+
    '<div class="g-prog"><span class="g-pct" id="g_gPct">0%</span><span class="g-psub" id="g_gProgSub">0 / 0</span></div>'+
    '<div class="g-bar"><i id="g_gBar" style="width:0%"></i></div>'+
    '<div class="g-note" id="g_gRemain"></div>'+
    '<div class="g-kpis">'+
      '<div class="g-kpi"><div class="g-l">원금(순입금)</div><div class="g-v" id="g_kPrin">0</div></div>'+
      '<div class="g-kpi"><div class="g-l">평가액</div><div class="g-v" id="g_kEquity">0</div></div>'+
      '<div class="g-kpi"><div class="g-l">평가손익</div><div class="g-v" id="g_kPnl">0</div></div></div>'+
    '<div class="g-break" id="g_gBreak"></div>'+
    '<div style="margin-top:12px;text-align:right"><button class="g-btn sm" id="g_editGoal">✎ 목표 수정</button></div></div>'+
    '<div class="g-card"><div class="g-sect">입출금</div>'+
      '<div class="g-frm"><input type="date" class="g-date" id="g_cDate">'+
      '<select id="g_cType"><option value="in">입금</option><option value="out">출금</option></select>'+
      '<input type="number" class="g-amt" id="g_cAmt" placeholder="금액" inputmode="decimal">'+
      '<input type="text" class="g-memo" id="g_cMemo" placeholder="메모(선택)">'+
      '<button class="g-btn pri" id="g_cAdd">추가</button></div>'+
      '<div id="g_cashRows"></div></div>'+
  '</div>'+
  '<div id="g_journal" style="display:none">'+
    '<div class="g-card"><div class="g-sect">거래 입력 (티커: AAPL, NVDA …)</div>'+
      '<div class="g-frm"><input type="date" class="g-date" id="g_tDate">'+
      '<select id="g_tSide"><option value="buy">매수</option><option value="sell">매도</option></select>'+
      '<input type="text" class="g-tk" id="g_tTk" placeholder="티커">'+
      '<input type="number" class="g-num" id="g_tQty" placeholder="수량" inputmode="decimal">'+
      '<input type="number" class="g-num" id="g_tPrice" placeholder="단가" inputmode="decimal">'+
      '<input type="number" class="g-num" id="g_tFee" placeholder="수수료" inputmode="decimal">'+
      '<button class="g-btn pri" id="g_tAdd">추가</button></div>'+
      '<div id="g_tradeRows"></div></div>'+
    '<button class="g-btn dark" id="g_genBtn" style="width:100%;padding:11px;font-size:13.5px;margin-bottom:11px">⚙ 매매일지 생성 / 새로고침</button>'+
    '<div class="g-kpis" style="margin-bottom:11px">'+
      '<div class="g-kpi"><div class="g-l">총 실현손익</div><div class="g-v" id="g_jReal">0</div></div>'+
      '<div class="g-kpi"><div class="g-l">승률</div><div class="g-v" id="g_jWin">0%</div></div>'+
      '<div class="g-kpi"><div class="g-l">평균 수익률</div><div class="g-v" id="g_jAvg">0%</div></div>'+
      '<div class="g-kpi"><div class="g-l">평균 보유</div><div class="g-v" id="g_jHold">0일</div></div></div>'+
    '<div class="g-card"><div class="g-sect">청산 매매 (자동 매칭)</div><div id="g_closedRows"></div></div>'+
    '<div class="g-card"><div class="g-sect">보유중 (미청산) · 현재가 입력 시 손익 반영</div><div id="g_openRows"></div>'+
      '<div class="g-note">현재가를 비워두면 평단가로 계산(손익 0)됩니다.</div></div>'+
  '</div>';
}

/* ---------- styles (사이트 변수 재사용 → 다크모드 자동) ---------- */
function injectStyle(){
  if (document.getElementById("g_style")) return;
  const s = document.createElement("style"); s.id="g_style";
  s.textContent = `
  #goalRoot .up{color:#e5484d}#goalRoot .dn{color:#3b82f6}#goalRoot .g-faint{color:var(--faint);font-size:11px}
  #goalRoot .g-login{max-width:380px;margin:6vh auto;text-align:center;padding:0 12px}
  #goalRoot .g-login-ic{font-size:26px}#goalRoot .g-login-t{font-size:18px;font-weight:800;margin:6px 0}
  #goalRoot .g-login-p{color:var(--muted);font-size:12.5px;line-height:1.6;margin-bottom:18px}
  #goalRoot .g-btn{font:inherit;font-size:12.5px;font-weight:700;border-radius:8px;padding:7px 12px;
    border:1px solid var(--border);background:var(--chip);color:var(--ink);cursor:pointer}
  #goalRoot .g-btn.pri{background:var(--accent);color:#fff;border-color:var(--accent);font-size:14px;padding:10px 18px}
  #goalRoot .g-btn.dark{background:var(--ink);color:var(--page);border-color:var(--ink)}
  #goalRoot .g-btn.sm{font-size:11px;padding:4px 9px}
  #goalRoot .g-lock{display:flex;align-items:center;gap:6px;background:var(--chip);border:1px solid var(--border);
    border-radius:8px;padding:7px 10px;margin-bottom:11px;font-size:11px;color:var(--muted)}
  #goalRoot .g-card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:14px 15px;margin-bottom:11px}
  #goalRoot .g-sect{font-size:11px;font-weight:800;color:var(--faint);margin-bottom:9px}
  #goalRoot .g-ghead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
  #goalRoot .g-gname{font-size:15px;font-weight:800}#goalRoot .g-gdates{font-size:11px;color:var(--muted);margin-top:2px}
  #goalRoot .g-dday{font-size:11px;font-weight:700;color:var(--accent);background:var(--chip);
    border:1px solid var(--border);border-radius:999px;padding:3px 9px;white-space:nowrap}
  #goalRoot .g-ghr{display:flex;flex-direction:column;align-items:flex-end;gap:6px}
  #goalRoot .g-cursel{font:inherit;font-size:11px;font-weight:700;border:1px solid var(--border);
    border-radius:8px;padding:4px 7px;background:var(--card);color:var(--ink);cursor:pointer}
  #goalRoot .g-prog{margin:13px 0 4px;display:flex;align-items:baseline;justify-content:space-between}
  #goalRoot .g-pct{font-size:22px;font-weight:800;color:#16a34a}#goalRoot .g-psub{font-size:12px;color:var(--muted)}
  #goalRoot .g-bar{height:12px;border-radius:7px;background:var(--nav-track);overflow:hidden}
  #goalRoot .g-bar>i{display:block;height:100%;border-radius:7px;background:#16a34a}
  #goalRoot .g-note{font-size:10px;color:var(--faint);margin-top:5px}
  #goalRoot .g-kpis{display:grid;grid-template-columns:1fr 1fr 1fr;gap:7px;margin-top:12px}
  #goalRoot .g-kpi{background:var(--nav-track);border-radius:9px;padding:9px 10px}
  #goalRoot .g-l{font-size:9.5px;color:var(--muted)}#goalRoot .g-v{font-size:14px;font-weight:800;margin-top:1px}
  #goalRoot .g-break{margin-top:10px;background:var(--nav-track);border:1px dashed var(--border);border-radius:9px;
    padding:9px 11px;font-size:10.5px;color:var(--muted);line-height:1.7}
  #goalRoot .g-frm{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:9px}
  #goalRoot .g-frm input,#goalRoot .g-frm select{font:inherit;font-size:12px;border:1px solid var(--border);
    border-radius:7px;padding:6px 8px;background:var(--card);color:var(--ink);min-width:0}
  #goalRoot .g-date{width:130px}#goalRoot .g-tk{width:78px;text-transform:uppercase}
  #goalRoot .g-num{width:72px}#goalRoot .g-amt{width:108px}#goalRoot .g-memo{flex:1;min-width:80px}
  #goalRoot .g-row{display:flex;align-items:center;gap:8px;padding:7px 0;border-top:1px solid var(--border);font-size:12px}
  #goalRoot .g-row:first-child{border-top:0}#goalRoot .g-grow{flex:1;min-width:0}
  #goalRoot .g-sub{font-size:10.5px;color:var(--muted)}#goalRoot .g-amtc{font-weight:800;white-space:nowrap}
  #goalRoot .g-acts{display:flex;gap:4px;flex-shrink:0}
  #goalRoot .g-ico{font:inherit;font-size:11px;border:1px solid var(--border);background:var(--card);
    border-radius:6px;padding:3px 7px;cursor:pointer;color:var(--muted)}
  #goalRoot .g-empty{font-size:11.5px;color:var(--faint);padding:8px 0}
  #goalRoot .g-price{width:88px;font:inherit;font-size:12px;border:1px solid var(--border);border-radius:7px;
    padding:5px 7px;background:var(--card);color:var(--ink)}
  #goalRoot .g-err{background:#fdeeee;border:1px solid #f5cccc;color:#b91c1c;border-radius:8px;
    padding:9px 11px;font-size:11.5px;margin-bottom:11px;line-height:1.5}
  @media (max-width:440px){#goalRoot .g-kpis{grid-template-columns:1fr 1fr}}
  `;
  document.head.appendChild(s);
}
