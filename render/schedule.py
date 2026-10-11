# -*- coding: utf-8 -*-
"""경제지표 일정 렌더링(publish_site.py 분리)."""
from __future__ import annotations

from render.common import _e
from render.config import _CUR_CC

# 이벤트명 한글 사전(반복되는 유한 집합). 미등록은 영문 유지 후 점차 보강.
_ECON_KO = {
    "Nonfarm Payrolls": "비농업 고용",
    "Unemployment Rate": "실업률",
    "Average Hourly Earnings (MoM)": "시간당 평균임금 (전월比)",
    "Average Hourly Earnings (YoY)": "시간당 평균임금 (전년比)",
    "Labor Force Participation Rate": "경제활동참가율",
    "U6 Underemployment Rate": "U6 불완전고용률",
    "ADP Employment Change": "ADP 민간고용",
    "ADP Employment Change 4-week average": "ADP 민간고용 4주평균",
    "JOLTS Job Openings": "JOLTS 구인건수",
    "Initial Jobless Claims": "신규 실업수당 청구",
    "Challenger Job Cuts": "챌린저 감원",
    "Nonfarm Productivity": "비농업 생산성",
    "Unit Labor Costs": "단위노동비용",
    "Consumer Price Index (MoM)": "소비자물가지수 CPI (전월比)",
    "Consumer Price Index (YoY)": "소비자물가지수 CPI (전년比)",
    "Consumer Price Index ex Food & Energy (MoM)": "근원 CPI (식품·에너지 제외, 전월比)",
    "Consumer Price Index ex Food & Energy (YoY)": "근원 CPI (식품·에너지 제외, 전년比)",
    "Producer Price Index (MoM)": "생산자물가지수 PPI (전월比)",
    "Producer Price Index (YoY)": "생산자물가지수 PPI (전년比)",
    "Producer Price Index ex Food & Energy (MoM)": "근원 PPI (전월比)",
    "Producer Price Index ex Food & Energy (YoY)": "근원 PPI (전년比)",
    "Personal Consumption Expenditures - Price Index (MoM)": "PCE 물가지수 (전월比)",
    "Personal Consumption Expenditures - Price Index (YoY)": "PCE 물가지수 (전년比)",
    "Core Personal Consumption Expenditures - Price Index (MoM)": "근원 PCE 물가지수 (전월比)",
    "Core Personal Consumption Expenditures - Price Index (YoY)": "근원 PCE 물가지수 (전년比)",
    "Core Personal Consumption Expenditures (QoQ)": "근원 PCE (전분기比)",
    "Personal Consumption Expenditures Prices (QoQ)": "PCE 물가 (전분기比)",
    "Personal Income (MoM)": "개인소득 (전월比)",
    "Personal Spending": "개인소비",
    "Retail Sales (MoM)": "소매판매 (전월比)",
    "Retail Sales (YoY)": "소매판매 (전년比)",
    "Retail Sales Control Group": "소매판매 코어(컨트롤그룹)",
    "Retail Sales ex Autos (MoM)": "소매판매 (자동차 제외, 전월比)",
    "ISM Manufacturing PMI": "ISM 제조업 PMI",
    "ISM Manufacturing Employment Index": "ISM 제조업 고용지수",
    "ISM Manufacturing New Orders Index": "ISM 제조업 신규주문지수",
    "ISM Manufacturing Prices Paid": "ISM 제조업 지불물가",
    "ISM Services PMI": "ISM 서비스업 PMI",
    "ISM Services Employment Index": "ISM 서비스업 고용지수",
    "ISM Services New Orders Index": "ISM 서비스업 신규주문지수",
    "ISM Services Prices Paid": "ISM 서비스업 지불물가",
    "S&P Global Composite PMI": "S&P글로벌 종합 PMI",
    "S&P Global Manufacturing PMI": "S&P글로벌 제조업 PMI",
    "S&P Global Services PMI": "S&P글로벌 서비스업 PMI",
    "HCOB Composite PMI": "HCOB 종합 PMI",
    "HCOB Manufacturing PMI": "HCOB 제조업 PMI",
    "HCOB Services PMI": "HCOB 서비스업 PMI",
    "RatingDog Manufacturing PMI": "제조업 PMI (RatingDog)",
    "RatingDog Services PMI": "서비스업 PMI (RatingDog)",
    "NBS Manufacturing PMI": "중국 국가통계국 제조업 PMI",
    "NBS Non-Manufacturing PMI": "중국 국가통계국 비제조업 PMI",
    "Chicago PMI": "시카고 PMI",
    "NY Empire State Manufacturing Index": "뉴욕 엠파이어스테이트 제조업지수",
    "Philadelphia Fed Manufacturing Survey": "필라델피아 연준 제조업지수",
    "Factory Orders (MoM)": "공장주문 (전월比)",
    "Durable Goods Orders": "내구재주문",
    "Durable Goods Orders ex Defense": "내구재주문 (국방 제외)",
    "Durable Goods Orders ex Transportation": "내구재주문 (운송 제외)",
    "Nondefense Capital Goods Orders ex Aircraft": "근원 자본재주문 (항공 제외)",
    "Industrial Production (MoM)": "산업생산 (전월比)",
    "Industrial Production (YoY)": "산업생산 (전년比)",
    "Industrial Production s.a. (MoM)": "산업생산 (계절조정, 전월比)",
    "Gross Domestic Product Annualized": "GDP 연율화",
    "Gross Domestic Product Price Index": "GDP 물가지수",
    "Gross Domestic Product (QoQ)": "GDP (전분기比)",
    "Gross Domestic Product s.a. (QoQ)": "GDP (계절조정, 전분기比)",
    "Gross Domestic Product s.a. (YoY)": "GDP (계절조정, 전년比)",
    "Gross Domestic Product Deflator (YoY)": "GDP 디플레이터 (전년比)",
    "Employment Change (QoQ)": "고용 변화 (전분기比)",
    "Michigan Consumer Sentiment Index": "미시간대 소비자심리지수",
    "Michigan Consumer Expectations Index": "미시간대 소비자기대지수",
    "UoM 1-year Consumer Inflation Expectations": "미시간대 1년 기대인플레이션",
    "UoM 5-year Consumer Inflation Expectation": "미시간대 5년 기대인플레이션",
    "Consumer Confidence": "소비자신뢰지수",
    "Consumer Sentiment Index": "소비자심리지수",
    "Business Climate": "기업환경지수",
    "Economic Sentiment Indicator": "경제심리지수",
    "ZEW Survey – Economic Sentiment": "ZEW 경기전망지수",
    "Sentix Investor Confidence": "Sentix 투자자신뢰지수",
    "Building Permits (MoM)": "건축허가 (전월比)",
    "Housing Starts (MoM)": "주택착공 (전월比)",
    "Existing Home Sales Change (MoM)": "기존주택판매 (전월比)",
    "New Home Sales Change (MoM)": "신규주택판매 (전월比)",
    "Pending Home Sales (MoM)": "잠정주택판매 (전월比)",
    "Housing Price Index (MoM)": "주택가격지수 (전월比)",
    "Monthly Budget Statement": "월간 재정수지",
    "Loan Officer Survey": "대출담당자 서베이",
    "Trade Balance": "무역수지",
    "Trade Balance USD": "무역수지 (달러)",
    "Trade Balance CNY": "무역수지 (위안)",
    "Exports (YoY)": "수출 (전년比)",
    "Exports (YoY) CNY": "수출 (전년比, 위안)",
    "Imports (YoY)": "수입 (전년比)",
    "Imports (YoY) CNY": "수입 (전년比, 위안)",
    "Current Account n.s.a.": "경상수지",
    "Adjusted Merchandise Trade Balance": "조정 상품무역수지",
    "Merchandise Trade Balance Total": "상품무역수지 총액",
    "Harmonized Index of Consumer Prices (MoM)": "조화소비자물가 HICP (전월比)",
    "Core Harmonized Index of Consumer Prices (MoM)": "근원 HICP (전월比)",
    "Core Harmonized Index of Consumer Prices (YoY)": "근원 HICP (전년比)",
    "Economic Bulletin": "ECB 경제전망 보고서",
    "National Consumer Price Index (YoY)": "전국 소비자물가 (전년比)",
    "National CPI ex Food, Energy (YoY)": "전국 근원 CPI (식품·에너지 제외, 전년比)",
    "National CPI ex Fresh Food (YoY)": "전국 근원 CPI (신선식품 제외, 전년比)",
    "Tokyo Consumer Price Index (YoY)": "도쿄 소비자물가 (전년比)",
    "Tokyo CPI ex Food, Energy (YoY)": "도쿄 근원 CPI (식품·에너지 제외, 전년比)",
    "Tokyo CPI ex Fresh Food (YoY)": "도쿄 근원 CPI (신선식품 제외, 전년比)",
    "Labor Cash Earnings (YoY)": "근로자 현금소득 (전년比)",
    "FOMC Minutes": "FOMC 의사록",
    "BoJ Monetary Policy Meeting Minutes": "일본은행 통화정책회의 의사록",
    "BoK Interest Rate Decision": "한국은행 기준금리 결정",
    "PBoC Interest Rate Decision": "중국인민은행 기준금리 결정",
    "Fed's Musalem speech": "연준 무살렘 연설",
    "Construction Spending (MoM)": "건설지출 (전월比)",
    "Consumer Price Index Growth (MoM)": "소비자물가 상승률 (전월比)",
    "Consumer Price Index Growth (YoY)": "소비자물가 상승률 (전년比)",
    "Goods and Services Trade Balance": "상품·서비스 무역수지",
    "Goods Trade Balance": "상품 무역수지",
    "Total Vehicle Sales": "총 차량판매",
    "Redbook Index (YoY)": "레드북 소매판매지수 (전년比)",
    "RealClearMarkets/TIPP Economic Optimism (MoM)": "TIPP 경제낙관지수 (전월比)",
    "API Weekly Crude Oil Stock": "API 주간 원유재고",
    "FX Reserves": "외환보유액",
    "3-Month Bill Auction": "3개월물 국채 입찰",
    "6-Month Bill Auction": "6개월물 국채 입찰",
    "52-Week Bill Auction": "52주물 국채 입찰",
    "4-Week Bill Auction": "4주물 국채 입찰",
    "2-Year Note Auction": "2년물 국채 입찰",
    "3-Year Note Auction": "3년물 국채 입찰",
    "5-Year Note Auction": "5년물 국채 입찰",
    "7-Year Note Auction": "7년물 국채 입찰",
    "10-Year Note Auction": "10년물 국채 입찰",
    "20-Year Bond Auction": "20년물 국채 입찰",
    "30-Year Bond Auction": "30년물 국채 입찰",
    "30-year TIPS Auction": "30년물 물가연동국채 입찰",
    "Continuing Jobless Claims": "연속 실업수당 청구",
    "Initial Jobless Claims 4-week average": "신규 실업수당 청구 4주평균",
    "MBA Mortgage Applications": "MBA 주택담보대출 신청",
    "EIA Crude Oil Stocks Change": "EIA 원유재고 변화",
    "EIA Natural Gas Storage Change": "EIA 천연가스 재고 변화",
    "Baker Hughes US Oil Rig Count": "베이커휴즈 원유 시추기 수",
    "Wholesale Inventories": "도매재고",
    "Business Inventories": "기업재고",
    "Building Permits Change": "건축허가 변화",
    "Housing Starts Change": "주택착공 변화",
    "Import Price Index (MoM)": "수입물가지수 (전월比)",
    "Import Price Index (YoY)": "수입물가지수 (전년比)",
    "Export Price Index (MoM)": "수출물가지수 (전월比)",
    "Export Price Index (YoY)": "수출물가지수 (전년比)",
    "New Home Sales (MoM)": "신규주택판매 건수 (전월比)",
    "Existing Home Sales (MoM)": "기존주택판매 건수 (전월比)",
    "Capacity Utilization": "설비가동률",
    "NAHB Housing Market Index": "NAHB 주택시장지수",
    "NFIB Business Optimism Index": "NFIB 중소기업 낙관지수",
    "Richmond Fed Manufacturing Index": "리치먼드 연준 제조업지수",
    "Kansas Fed Manufacturing Activity": "캔자스 연준 제조업활동",
    "Dallas Fed Manufacturing Business Index": "댈러스 연준 제조업지수",
    "Consumer Credit Change": "소비자신용 변화",
    "USDA WASDE Report": "USDA 세계 농산물 수급전망",
    "Money Supply Growth": "통화량 증가율",
    "Export Price Growth (YoY)": "수출물가 상승률 (전년比)",
    "Import Price Growth (YoY)": "수입물가 상승률 (전년比)",
    "Producer Price Index Growth (MoM)": "생산자물가 상승률 (전월比)",
    "Producer Price Index Growth (YoY)": "생산자물가 상승률 (전년比)",
    "Industrial Output (YoY)": "산업생산 (전년比)",
    "Service Sector Output": "서비스업 생산",
    "BOK Manufacturing BSI": "한국은행 제조업 BSI",
    "Current Account Balance": "경상수지",
    "Consumer Sentiment Index": "소비자심리지수",
    "IMF Meeting": "IMF 연차총회",
    "Large Retailer Sales": "대형소매점 판매",
    "Retail Trade (YoY)": "소매판매 (전년比)",
    "Retail Trade s.a (MoM)": "소매판매 계절조정 (전월比)",
    "BoJ Interest Rate Decision": "일본은행(BoJ) 기준금리 결정",
    "BoJ Monetary Policy Statement": "BoJ 통화정책 성명",
    "BoJ Press Conference": "BoJ 총재 기자회견",
    "BoJ Outlook Report": "BoJ 경제·물가 전망 보고서",
    "Fed Interest Rate Decision": "연준(Fed) 기준금리 결정",
    "Fed Monetary Policy Statement": "FOMC 통화정책 성명",
    "FOMC Press Conference": "FOMC 기자회견 (파월 의장)",
    "FOMC Economic Projections": "FOMC 경제전망 (SEP)",
    "Interest Rate Projections - Current": "점도표: 올해 금리 전망",
    "Interest Rate Projections - 1st year": "점도표: 1년 후 금리 전망",
    "Interest Rate Projections - 2nd year": "점도표: 2년 후 금리 전망",
    "Interest Rate Projections - 3rd year": "점도표: 3년 후 금리 전망",
    "Interest Rate Projections - Longer": "점도표: 장기 금리 전망",
    "Fed's Beige Book": "연준 베이지북",
    "Fed's Goolsbee speech": "굴스비 시카고 연은 총재 연설",
    "Employment Cost Index": "고용비용지수",
    "Gross Domestic Product Growth (QoQ)": "GDP 성장률 (전분기比)",
    "Tankan Large Manufacturing Index": "단칸 대형 제조업 업황지수",
    "Tankan Large Manufacturing Outlook": "단칸 대형 제조업 전망",
    "Tankan Large All Industry Capex": "단칸 대기업 전산업 설비투자",
    "US Midterm Elections": "미국 중간선거",
}


def _impact_gauge(imp):
    b = "var(--border)"
    seg = ({"HIGH": ["#e5484d", "#e5484d", "#e5484d"],
            "MEDIUM": ["#f59e0b", "#f59e0b", b]}
           .get(imp, ["#94a3b8", b, b]))   # LOW = 회색 1칸
    return ('<span class="igauge">'
            + "".join(f'<i style="background:{c}"></i>' for c in seg) + "</span>")


def _econ_row(e):
    t = e["dt"].strftime("%I:%M %p").lstrip("0")
    name = _ECON_KO.get(e["name"], e["name"])
    cc = _CUR_CC.get(e["cur"])
    # 국기는 사이트 자체(docs/flags/)에서 같은 출처로 로드(외부 의존 0).
    flag = (f'<img class="ev-flag" src="flags/{cc}.svg" '
            f'alt="{_e(e["cur"])}" title="{_e(e["cur"])}" '
            f'width="22" height="16" decoding="async">'
            if cc else '<span class="ev-flag"></span>')
    res, extra, badge, cls = e.get("res"), "", "", ""
    if res and e.get("past") and res.get("act"):
        # 발표 완료: 실제 + 예상 대비 방향(숫자 방향일 뿐, 좋다/나쁘다 판단 아님)
        a, c = res.get("act_n"), res.get("cons_n")
        vs = ""
        if a is not None and c is not None:
            k, tx = (("beat", "▲ 상회") if a > c else ("miss", "▼ 하회") if a < c
                     else ("inl", "= 부합"))
            vs = f'<span class="ev-vs {k}">{tx}</span>'
        parts = [f'<span class="k">실제</span><span class="act">{_e(res["act"])}</span>{vs}']
        if res.get("cons"):
            parts.append(f'<span><span class="k">예상</span>{_e(res["cons"])}</span>')
        if res.get("prev"):
            parts.append(f'<span><span class="k">이전</span>{_e(res["prev"])}</span>')
        extra = '<div class="ev-res">' + "".join(parts) + '</div>'
        badge = '<span class="ev-done">발표</span>'
        cls = " has-res"
    elif res and (res.get("cons") or res.get("prev")):
        pre = []
        if res.get("cons"):
            pre.append(f'<span>예상 <b>{_e(res["cons"])}</b></span>')
        if res.get("prev"):
            pre.append(f'<span>이전 <b>{_e(res["prev"])}</b></span>')
        extra = '<div class="ev-pre">' + "".join(pre) + '</div>'
        cls = " has-res"
    if e.get("past"):
        cls += " past"
    return (f'<div class="ev{cls}" data-imp="{e["impact"]}"><span class="ev-t">{t}</span>'
            f'{flag}<div class="ev-body"><span class="ev-n">{_e(name)}{badge}</span>'
            f'{extra}</div>{_impact_gauge(e["impact"])}</div>')


# 캘린더 칸에 넣을 높음 지표 '계열 약칭'. 전월比/전년比·근원 등 변형은 한 계열로 묶는다.
# (영문명에 포함된 문자열, 약칭) — 위에서부터 먼저 맞는 것을 쓴다(구체적인 것이 위).
_ECON_SHORT = (
    ("Tokyo", "도쿄CPI"), ("BoJ", "BoJ"), ("FOMC Minutes", "FOMC의사록"),
    ("Fed Interest Rate", "FOMC"), ("Fed Monetary", "FOMC"), ("FOMC", "FOMC"),
    ("Personal Consumption", "PCE"), ("Producer Price", "PPI"), ("Consumer Price", "CPI"),
    ("Retail Sales", "소매판매"), ("ISM", "ISM"), ("Michigan", "미시간"),
    ("S&P Global", "PMI"), ("Gross Domestic", "GDP"), ("Nonfarm", "고용"),
    ("Average Hourly", "고용"), ("Unemployment", "실업률"), ("ADP", "ADP"),
    ("JOLTS", "JOLTS"), ("Election", "선거"),
)


def _econ_short(name):
    """영문 지표명 → 캘린더 칸용 약칭. 미등록은 한글명(없으면 영문) 그대로(칸에서 말줄임)."""
    for key, short in _ECON_SHORT:
        if key in name:
            return short
    return _ECON_KO.get(name, name)


_SCHED_JS = """<script>
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
      c.classList.toggle('has', [].some.call(c.querySelectorAll('.lab,.cal-tk'), vis));
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
        on=[].some.call(x.querySelectorAll('.ev,.up-row,.rep-item'), vis); }
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
</script>"""
