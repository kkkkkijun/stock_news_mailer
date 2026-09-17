# -*- coding: utf-8 -*-
"""성장주 스크리너·심층 카드 렌더링(publish_site.py 분리)."""
from __future__ import annotations

from typing import Any

from render.common import _e, _ticker_color
from render.config import _GR_SIG, _GR_SIGTXT


def _gr_money(m):
    if m is None:
        return "—"
    a, s = abs(m), ("-" if m < 0 else "")
    return f"{s}${a/1000:.1f}B" if a >= 1000 else f"{s}${a:.0f}M"


def _gr_spark(vals, color, zero=False, w=118, h=28):
    pts = [v for v in vals if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(pts), max(pts)
    if zero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    rng = (hi - lo) or 1.0
    n = len(vals)
    coords = []
    for i, v in enumerate(vals):
        if v is None:
            continue
        x = round(i * w / (n - 1), 1)
        y = round(h - 3 - (v - lo) / rng * (h - 6), 1)
        coords.append(f"{x},{y}")
    base = ""
    if zero:
        zy = round(h - 3 - (0 - lo) / rng * (h - 6), 1)
        base = (f'<line x1="0" y1="{zy}" x2="{w}" y2="{zy}" stroke="var(--border)" '
                f'stroke-width="1" stroke-dasharray="2 2"/>')
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:{h}px;margin-top:6px" '
            f'preserveAspectRatio="none">{base}<polyline points="{" ".join(coords)}" '
            f'fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/></svg>')


def _gr_axis_card(title, ax, spark_svg):
    sig = ax.get("sig", "y")
    col = _GR_SIG[sig]
    return (
        '<div style="background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:12px;flex:1;min-width:132px">'
        '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{col}"></span>'
        f'<span style="font-size:12px;color:var(--muted)">{title}</span>'
        f'<span style="margin-left:auto;font-size:11px;color:{col};font-weight:700">'
        f'{_GR_SIGTXT[sig]}</span></div>'
        f'<div style="font-size:13.5px;font-weight:700;color:var(--ink)">{_e(ax.get("lab",""))}</div>'
        f'{spark_svg}</div>')


def _gr_deep_head(d: dict[str, Any], tk: str, col: str, sc: int, sc_col: str) -> str:
    """심층 카드 상단: 뒤로가기 버튼·티커 배지·종목명·기준일·종합점수."""
    return (
        '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px">'
        f'<button class="gr-back" style="border:1px solid var(--border);background:var(--card);'
        'color:var(--muted);border-radius:8px;padding:5px 9px;font:inherit;font-size:12px;'
        'cursor:pointer">← 목록</button>'
        f'<div style="width:40px;height:40px;border-radius:10px;background:{col}22;color:{col};'
        'display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px">'
        f'{tk}</div><div><div style="font-size:16px;font-weight:800;color:var(--ink)">'
        f'{_e(d["name"])} <span style="font-size:12px;font-weight:600;color:var(--faint)">'
        f'{_e(d.get("sector",""))}</span></div>'
        f'<div style="font-size:11.5px;color:var(--muted-2)">기준 {_e(d.get("asof",""))} · '
        f'매출 {_gr_money(d.get("rev"))} · SEC XBRL</div></div>'
        f'<div style="margin-left:auto;text-align:center"><div style="font-size:30px;font-weight:800;'
        f'line-height:1;color:{sc_col}">{sc}</div>'
        '<div style="font-size:10px;color:var(--faint)">종합점수/100</div></div></div>')


def _gr_deep_verdict(d: dict[str, Any], ax: dict[str, Any], sc_col: str) -> str:
    """한 줄 총평(태그 + 4축 라벨 요약)."""
    return (
        '<div style="background:var(--chip);border-radius:12px;padding:12px 14px;margin-bottom:16px;'
        'font-size:13px;line-height:1.6;color:var(--ink)">'
        f'<b style="color:{sc_col}">{_e(d.get("tag",""))}</b> · '
        f'{_e(ax.get("growth",{}).get("lab",""))}, {_e(ax.get("path",{}).get("lab",""))}, '
        f'{_e(ax.get("balance",{}).get("lab",""))}. '
        f'주주가치: {_e(ax.get("shareholder",{}).get("lab",""))}.</div>')


def _gr_deep_cards(ax: dict[str, Any], revs: list[float | None],
                   opms: list[float | None]) -> str:
    """4축(성장/수익성경로/재무건전성/주주가치) 카드 행."""
    return (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">'
        + _gr_axis_card("① 성장", ax.get("growth", {}), _gr_spark(revs, "#3a6fd8"))
        + _gr_axis_card("② 수익성 경로", ax.get("path", {}), _gr_spark(opms, "#e0930a", zero=True))
        + _gr_axis_card("③ 재무 건전성", ax.get("balance", {}), "")
        + _gr_axis_card("④ 주주가치", ax.get("shareholder", {}), "")
        + '</div>')


def _gr_deep_story(d: dict[str, Any], revs: list[float | None],
                   revsr: list[dict[str, Any]], opms: list[float | None]) -> str:
    """매출 성장 막대그래프 + 적자 갭(영업이익률) 스파크라인 2단 카드."""
    rmax = max([v for v in revs if v is not None] or [1])
    bars = ""
    for q in revsr:
        v = q.get("v")
        hpct = round((v or 0) / rmax * 100)
        last = q is revsr[-1]
        bg = "#3a6fd8" if last else "#3a6fd855"
        bars += (f'<div title="{_e(q.get("cq",""))}: {_gr_money(v)}" style="flex:1;background:{bg};'
                 f'border-radius:3px 3px 0 0;height:{max(hpct,3)}%"></div>')
    return (
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px">'
        '<div style="flex:1;min-width:240px;background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:14px">'
        '<div style="font-size:12px;color:var(--muted);margin-bottom:10px">매출 성장 (분기)</div>'
        f'<div style="display:flex;align-items:flex-end;gap:5px;height:80px">{bars}</div>'
        f'<div style="font-size:12px;color:var(--ink);margin-top:8px">최근 {_gr_money(d.get("rev"))}'
        + (f' · <span style="color:#e5484d">YoY {d["rev_yoy"]:+.0f}%</span>' if d.get("rev_yoy") is not None else "")
        + '</div></div>'
        '<div style="flex:1;min-width:240px;background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:14px">'
        '<div style="font-size:12px;color:var(--muted);margin-bottom:10px">적자 갭 (영업이익률 %)</div>'
        f'{_gr_spark(opms, "#e0930a", zero=True, h=70)}'
        f'<div style="font-size:12px;color:var(--ink);margin-top:8px">현재 '
        + (f'{d["opm"]:+.0f}%' if d.get("opm") is not None else "—")
        + (f' · Δ{d["opm_delta"]:+.0f}%p (전년비)' if d.get("opm_delta") is not None else "")
        + '</div></div></div>')


def _gr_deep_bridge(d: dict[str, Any]) -> str:
    """부채→자산(CapEx) 브릿지 바. 데이터 없으면 빈 문자열."""
    br = d.get("bridge")
    if not (br and br.get("d_debt") and br.get("capex")):
        return ""
    dd, cx = br["d_debt"], br["capex"]
    ratio = min(100, round(cx / dd * 100)) if dd else 0
    good = ratio >= 60
    msg = (f'늘어난 부채의 {ratio}%가 설비투자(CapEx)로 유입 → '
           + ("<b style=\"color:#16a37f\">투자형 성장</b>" if good
              else "<b style=\"color:#e5484d\">일부만 투자·점검 필요</b>"))
    return (
        '<div style="background:var(--card);border:1px solid var(--border);border-radius:12px;'
        'padding:14px;margin-bottom:14px">'
        f'<div style="font-size:12px;color:var(--muted);margin-bottom:8px">부채 → 자산 브릿지 · '
        f'지난 1년 부채 {_gr_money(dd)} 증가</div>'
        '<div style="display:flex;height:26px;border-radius:6px;overflow:hidden;gap:2px;margin-bottom:8px">'
        f'<div style="width:{ratio}%;background:#16a37f;min-width:2px"></div>'
        f'<div style="width:{100-ratio}%;background:#cbd5e1"></div></div>'
        f'<div style="font-size:12px;color:var(--ink);line-height:1.5">CapEx {_gr_money(cx)} · {msg}</div></div>')


def _gr_deep_metrics(d: dict[str, Any]) -> str:
    """커스텀 지표(런웨이·룰40·R&D/매출·FCF) 정량 자동 계산 카드 행."""
    runway = "흑자" if (d.get("fcf") or 0) > 0 else (
        f'{round(d["cash"]/(abs(d["fcf"])/12))}개월'
        if (d.get("cash") and d.get("fcf")) else "—")
    rule40 = (round((d.get("rev_yoy") or 0) + (d.get("opm") or 0))
              if (d.get("rev_yoy") is not None and d.get("opm") is not None) else None)
    rnd_txt = f'{d["rnd_pct"]:.0f}%' if d.get("rnd_pct") is not None else "—"
    return (
        '<div style="font-size:12px;font-weight:700;color:var(--muted);margin:6px 0 8px">내 지표(정량 자동)</div>'
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">'
        f'{_gr_kpi("런웨이(현금÷소진)", runway)}'
        f'{_gr_kpi("룰40(성장+마진)", (str(rule40)+"pt") if rule40 is not None else "—")}'
        f'{_gr_kpi("R&D/매출", rnd_txt)}'
        f'{_gr_kpi("FCF(TTM)", _gr_money(d.get("fcf")))}'
        '</div>')


def _gr_deep(d):
    tk = _e(d["ticker"])
    col = _ticker_color(d["ticker"])
    ax = d.get("axes", {})
    sc = d.get("score", 0)
    sc_col = "#16a37f" if sc >= 78 else "#e0930a" if sc >= 55 else "#e5484d"
    revs = [q.get("v") for q in d.get("series", {}).get("rev", [])]
    opis = d.get("series", {}).get("opi", [])
    revsr = d.get("series", {}).get("rev", [])
    opms = []
    for r, o in zip(revsr, opis):
        rv, ov = r.get("v"), o.get("v")
        opms.append(round(ov / rv * 100, 1) if (rv and ov is not None) else None)

    head = _gr_deep_head(d, tk, col, sc, sc_col)
    verdict = _gr_deep_verdict(d, ax, sc_col)
    cards = _gr_deep_cards(ax, revs, opms)
    story = _gr_deep_story(d, revs, revsr, opms)
    bridge = _gr_deep_bridge(d)
    metrics = _gr_deep_metrics(d)

    note = ('<div style="font-size:11.5px;color:var(--faint);margin-top:12px">'
            '수치는 SEC 공시(XBRL·10-K) 원본 기반이며 정성 요약은 AI가 작성했습니다. '
            '투자 판단의 책임은 본인에게 있습니다.</div>')

    return (f'<div class="gr-card" data-tk="{tk}" style="display:none">'
            + head + verdict + cards + story + bridge + metrics
            + _gr_qual(d) + note + '</div>')


def _gr_qual(d):
    q = d.get("qual")
    if not q:
        return ('<div style="font-size:11.5px;color:var(--faint);margin-top:14px">'
                '해자·산업 필연성 등 정성 분석은 10-K 수집 후 표시됩니다.</div>')
    ms = d.get("moat_score")
    cards = (("경쟁 우위 (해자)", q.get("moat", "")),
             ("산업 필연성", q.get("necessity", "")),
             ("확장 시나리오", q.get("expansion", "")))
    inner = "".join(
        '<div style="flex:1;min-width:180px;background:var(--card);border:1px solid var(--border);'
        'border-radius:12px;padding:13px">'
        f'<div style="font-size:12px;color:var(--accent);margin-bottom:5px;font-weight:700">{_e(t)}</div>'
        f'<div style="font-size:12.5px;color:var(--ink);line-height:1.6">{_e(v)}</div></div>'
        for t, v in cards if v)
    risk = ""
    if q.get("risk_note"):
        risk = ('<div style="background:var(--chip);border-radius:10px;padding:10px 12px;'
                'margin-top:10px;font-size:12px;color:var(--ink);line-height:1.55">'
                f'<b style="color:#e5484d">핵심 리스크</b> · {_e(q["risk_note"])}</div>')
    head = ('<div style="display:flex;align-items:center;gap:8px;margin:18px 0 9px;flex-wrap:wrap">'
            '<span style="font-size:12px;font-weight:700;color:var(--muted)">정성 분석</span>'
            + (f'<span style="font-size:11px;color:var(--muted-2)">해자 {ms}점</span>'
               if ms is not None else "")
            + '<span style="margin-left:auto;font-size:10.5px;color:var(--faint)">'
            + f'10-K {_e(q.get("src",""))} · AI 요약</span></div>')
    return head + '<div style="display:flex;gap:10px;flex-wrap:wrap">' + inner + '</div>' + risk


def _gr_kpi(label, val):
    return ('<div style="flex:1;min-width:120px;background:var(--chip);border-radius:9px;padding:10px 12px">'
            f'<div style="font-size:11px;color:var(--muted-2)">{_e(label)}</div>'
            f'<div style="font-size:18px;font-weight:800;color:var(--ink)">{_e(str(val))}</div></div>')


def _gr_row(d):
    tk = _e(d["ticker"])
    col = _ticker_color(d["ticker"])
    sc = d.get("score", 0)
    sc_col = "#16a37f" if sc >= 78 else "#e0930a" if sc >= 55 else "#e5484d"
    ax = d.get("axes", {})
    dots = "".join(
        f'<span style="width:8px;height:8px;border-radius:50%;background:{_GR_SIG[ax.get(k,{}).get("sig","y")]}"></span>'
        for k in ("growth", "path", "balance", "shareholder"))
    yoy = d.get("rev_yoy")
    yoy_txt = (f'{yoy:+.0f}%' if yoy is not None else "—")
    return (
        f'<div class="gr-row" data-tk="{tk}" data-score="{sc}" '
        'style="display:flex;align-items:center;gap:10px;padding:11px 12px;background:var(--card);'
        'border:1px solid var(--border);border-radius:12px;cursor:pointer">'
        f'<div style="width:34px;height:34px;border-radius:8px;background:{col}22;color:{col};'
        'display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;'
        f'flex-shrink:0">{tk}</div>'
        '<div style="min-width:0;flex:1">'
        f'<div style="font-size:13px;font-weight:700;color:var(--ink)">{_e(d["name"])}</div>'
        f'<div style="font-size:11px;color:var(--muted-2);white-space:nowrap;overflow:hidden;'
        f'text-overflow:ellipsis">{_e(d.get("tag",""))}</div></div>'
        f'<div style="font-size:20px;font-weight:800;color:{sc_col};flex-shrink:0;width:32px;'
        'text-align:center">' + str(sc) + '</div>'
        f'<div style="display:flex;gap:4px;flex-shrink:0">{dots}</div>'
        f'<div style="font-size:13px;font-weight:700;color:#e5484d;width:48px;text-align:right;'
        f'flex-shrink:0">{yoy_txt}</div></div>')


_GROWTH_JS = """<script>
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
</script>"""


def _render_growth(funds, now):
    funds = sorted(funds, key=lambda x: -x.get("score", 0))
    presets = (
        '<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px">'
        '<span class="gr-preset" data-f="all" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--ink);cursor:pointer;opacity:1">전체</span>'
        '<span class="gr-preset" data-f="profit" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--muted-2);cursor:pointer;opacity:.55">고성장·흑자</span>'
        '<span class="gr-preset" data-f="turn" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--muted-2);cursor:pointer;opacity:.55">적자 갭 축소</span>'
        '<span class="gr-preset" data-f="cash" style="font-size:12px;padding:6px 11px;'
        'border-radius:99px;background:var(--chip);color:var(--muted-2);cursor:pointer;opacity:.55">순현금</span></div>')
    rows = []
    for d in funds:
        r = _gr_row(d)
        ax = d.get("axes", {})
        g0 = ax.get("growth", {}).get("sig")
        turn = "1" if (d.get("opm_delta") or 0) >= 3 and (d.get("opm") or 0) < 0 else "0"
        cashsig = ax.get("balance", {}).get("sig")
        r = r.replace('data-score="', f'data-g0="{g0}" data-turn="{turn}" data-cash="{cashsig}" data-score="', 1)
        rows.append(r)
    legend = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:11px;'
        'color:var(--faint)">'
        + "".join(f'<span style="display:inline-flex;align-items:center;gap:5px">'
                  f'<span style="width:8px;height:8px;border-radius:50%;background:{_GR_SIG[s]}"></span>'
                  f'{_GR_SIGTXT[s]}</span>' for s in ("g", "y", "r"))
        + '<span>4축 = 성장·수익성경로·재무건전성·주주가치 · 점수순</span></div>')
    head = ('<div class="sched-head" style="margin-bottom:12px"><span>'
            '<span class="sched-ico">🔎</span>성장주 '
            f'<span class="sched-tz">SEC 재무 · {len(funds)}종목</span></span></div>')
    screener = (f'<div id="grScreener">{head}{presets}'
                f'<div style="display:flex;flex-direction:column;gap:7px">{"".join(rows)}</div>'
                f'{legend}</div>')
    deep = ('<div id="grDeep" style="display:none">'
            + "".join(_gr_deep(d) for d in funds) + '</div>')
    return f'<div class="part">{screener}{deep}</div>'
