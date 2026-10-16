# -*- coding: utf-8 -*-
"""성장주 스크리너·심층 카드 렌더링(publish_site.py 분리)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from render.common import _e, _ticker_color
from render.config import KST, _GR_SIG, _GR_SIGTXT, _WD_KO


# 가격 온도계 구간: 성장 대비 EV/매출의 종목 내 순위 위치(0=가장 저렴 ~ 1=가장 비쌈)
_TH_BANDS = ((1 / 3, "저렴", "cheap"), (2 / 3, "보통", "mid"), (1.01, "비쌈", "rich"))


def _valuation(funds: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, dict[str, Any]]:
    """종목별 가격 지표. 품질 점수와 분리해 '지금 비싼가'만 본다.

    시가총액 = 주가 × 희석주식수, EV = 시총 − 순현금, EV/매출 = EV ÷ 최근 4분기 매출,
    성장 대비 EV/매출 = EV/매출 ÷ 매출 YoY(%) — 적자 성장주와 흑자 대형주를 한 줄로 비교하려고 쓴다.
    성장률이 0 이하이거나 입력이 빠지면 그 종목은 순위에서 뺀다. 단위: 백만 달러."""
    out: dict[str, dict[str, Any]] = {}
    for d in funds:
        tk, px, sh = d["ticker"], prices.get(d["ticker"]), d.get("shares")
        revs = [q.get("v") for q in d.get("series", {}).get("rev", [])][-4:]
        if not px or not sh or len(revs) < 4 or any(v is None for v in revs) or sum(revs) <= 0:
            continue
        mcap = px * sh
        ev = mcap - (d.get("netcash") or 0)
        evs = ev / sum(revs)
        yoy, fcf = d.get("rev_yoy"), d.get("fcf")
        out[tk] = {"mcap": mcap, "ev": ev, "evs": evs,
                   "gadj": evs / yoy if (yoy and yoy > 0) else None,
                   "pfcf": mcap / fcf if (fcf and fcf > 0) else None}
    ranked = sorted((t for t, v in out.items() if v["gadj"] is not None), key=lambda t: out[t]["gadj"])
    n = len(ranked)
    for i, t in enumerate(ranked):
        pos = i / (n - 1) if n > 1 else 0.5
        lab, cls = next((lab, cls) for cut, lab, cls in _TH_BANDS if pos < cut)
        out[t].update(pos=pos, rank=i + 1, n=n, label=lab, cls=cls)
    return out


def _gr_thermo(v: dict[str, Any] | None, wide: bool = False) -> str:
    """가격 온도계: 파랑(저렴)~빨강(비쌈) 막대 위 현재 위치 + 구간 라벨."""
    if not v or v.get("pos") is None:
        why = "성장 음수 · 산출 불가" if v else "가격 정보 없음"
        return f'<span class="gr-th na">{why}</span>'
    return (f'<span class="gr-th{" wide" if wide else ""}" title="성장 대비 EV/매출 {v["gadj"]:.2f} · '
            f'{v["n"]}종목 중 {v["rank"]}번째로 저렴"><span class="gr-th-bar">'
            f'<i style="left:{v["pos"] * 100:.0f}%"></i></span>'
            f'<span class="gr-th-lab {v["cls"]}">{v["label"]}</span></span>')


def _gr_dday(d: date | None, today: date) -> tuple[str, int | None]:
    if not d:
        return "", None
    n = (d - today).days
    return ("D-DAY" if n == 0 else f"D-{n}" if n > 0 else f"D+{-n}"), n


def _gr_delta(hist: list[dict[str, Any]]) -> str:
    """직전 기록 대비 종합점수 변화. 이력이 1개 이하면 '–'."""
    if len(hist) < 2:
        return '<span class="gr-dl eq" title="점수 이력을 쌓는 중">–</span>'
    dv = (hist[-1].get("score") or 0) - (hist[-2].get("score") or 0)
    if dv == 0:
        return '<span class="gr-dl eq">–</span>'
    return (f'<span class="gr-dl {"up" if dv > 0 else "dn"}" title="{_e(hist[-2].get("date", ""))} 대비">'
            f'{"▲" if dv > 0 else "▼"}{abs(dv)}</span>')


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


def _gr_deep_head(d: dict[str, Any], tk: str, col: str, sc: int, sc_col: str, px_asof: str = "") -> str:
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
        f'매출 {_gr_money(d.get("rev"))} · SEC XBRL'
        + (f' · 주가 {_e(px_asof)}' if px_asof else '') + '</div></div>'
        f'<div style="margin-left:auto;text-align:center"><div style="font-size:30px;font-weight:800;'
        f'line-height:1;color:{sc_col}">{sc}</div>'
        '<div style="font-size:10px;color:var(--faint)">품질 점수/100</div></div></div>')


def _gr_deep_verdict(d: dict[str, Any], ax: dict[str, Any], sc_col: str,
                     q_phrase: str = "", p_phrase: str = "") -> str:
    """한 줄 총평(태그 + 4축 라벨 요약)."""
    return (
        '<div style="background:var(--chip);border-radius:12px;padding:12px 14px;margin-bottom:16px;'
        'font-size:13px;line-height:1.6;color:var(--ink)">'
        f'<b style="color:{sc_col}">{_e(d.get("tag",""))}</b> · '
        f'{_e(ax.get("growth",{}).get("lab",""))}, {_e(ax.get("path",{}).get("lab",""))}, '
        f'{_e(ax.get("balance",{}).get("lab",""))}. '
        f'주주가치: {_e(ax.get("shareholder",{}).get("lab",""))}.'
        + (f'<div style="margin-top:4px;font-weight:700">품질은 {_e(q_phrase)}, '
           f'가격은 <span style="color:#b42318">{_e(p_phrase)}</span></div>' if q_phrase else '')
        + '</div>')


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


def _gr_quality_phrase(rank: int, n: int) -> str:
    if rank <= 3:
        return "최상위"
    return "상위권" if rank <= n / 2 else "중하위권"


def _gr_price_phrase(v: dict[str, Any] | None) -> str:
    if not v:
        return "산출 불가 (주가·주식수 없음)"
    if v.get("rank") is None:
        return "비교 불가 (매출 성장률 0 이하)"
    if v["rank"] == v["n"]:
        return f'{v["n"]}종목 중 가장 비쌈'
    if v["rank"] == 1:
        return f'{v["n"]}종목 중 가장 저렴'
    return f'{v["label"]} 구간 ({v["n"]}종목 중 {v["rank"]}번째로 저렴)'


def _gr_kv(label, val):
    return f'<div class="gr-kv"><small>{_e(label)}</small><b>{_e(val)}</b></div>'


def _gr_price_card(tk: str, vals: dict[str, dict[str, Any]]) -> str:
    v = vals.get(tk)
    ranked = sorted((t for t, x in vals.items() if x.get("rank")), key=lambda t: vals[t]["rank"])
    top = max([vals[t]["gadj"] for t in ranked] or [1]) or 1
    bars = "".join(
        f'<div class="gr-rk{" me" if t == tk else ""}"><span>{_e(t)}</span>'
        f'<span class="gr-rk-bar"><i style="width:{max(2, vals[t]["gadj"] / top * 100):.0f}%"></i></span>'
        f'<span>{vals[t]["gadj"]:.2f}</span></div>' for t in ranked)
    kv = ("".join([
        _gr_kv("시가총액", _gr_money(v["mcap"])),
        _gr_kv("EV / 매출(TTM)", f'{v["evs"]:.1f}배'),
        _gr_kv("성장 대비 EV/매출", f'{v["gadj"]:.2f}' if v.get("gadj") is not None else "산출 불가"),
        _gr_kv("시총 / FCF", f'{v["pfcf"]:.0f}배' if v.get("pfcf") else "FCF 적자"),
    ]) if v else '<div class="gr-none">주가·주식수 정보가 없어 계산하지 못했습니다.</div>')
    return ('<div class="gr-box"><div class="gr-box-h"><span>가격은?<small>품질 점수와 별개</small></span>'
            f'{_gr_thermo(v, wide=True)}</div><div class="gr-kvs">{kv}</div>'
            '<div class="gr-rk-t">성장 대비 EV/매출 · 종목 비교<small>낮을수록 성장에 비해 싸다</small></div>'
            f'<div class="gr-rks">{bars}</div></div>')


def _gr_earn_card(earn: dict[str, Any] | None, hist: list[dict[str, Any]], today: date) -> str:
    if not earn:
        return ('<div class="gr-box"><div class="gr-box-h"><span>다음 실적</span></div>'
                '<div class="gr-none">실적 일정이 등록되지 않은 종목입니다.</div></div>')
    det = earn.get("detail") or {}
    cur, rec = det.get("cur") or {}, det.get("rec") or {}
    d, ts = earn.get("date"), earn.get("ts")
    ed_txt, ed_n = _gr_dday(d, today)
    when = "미정"
    if d:
        when = f'{d.month}/{d.day}({_WD_KO[d.weekday()]})'
        if ts:
            when += " " + datetime.fromtimestamp(ts, KST).strftime("%H:%M")
        if earn.get("est"):
            when += " 예상"
    tot = (rec.get("buy") or 0) + (rec.get("hold") or 0) + (rec.get("sell") or 0)
    rec_txt = f'매수 {round((rec.get("buy") or 0) / tot * 100)}%' if tot else (rec.get("label") or "—")
    sp = (det.get("surprises") or [])[-4:]
    qs = [q.get("label", "") for q in (det.get("quarters") or []) if q.get("reported")][-len(sp):] if sp else []
    qs = [""] * (len(sp) - len(qs)) + qs
    bars = "".join(
        f'<div class="gr-sp"><span class="gr-sp-bar"><i class="{"beat" if x.get("pos") else "miss"}" '
        f'style="height:{min(100, abs(x.get("v") or 0) * 3 + 12):.0f}%"></i></span>'
        f'<em class="{"beat" if x.get("pos") else "miss"}">{_e(x.get("fmt", ""))}</em>'
        f'<small>{_e(q.replace("20", "", 1).replace(" ", "."))}</small></div>' for x, q in zip(sp, qs))
    chip = (f'<span class="gr-dday">{ed_txt}</span>' if ed_txt and ed_n is not None and ed_n >= 0 else "")
    pts = [h.get("score") for h in hist[-8:] if h.get("score") is not None]
    if len(pts) >= 2:
        trend = (_gr_spark(pts, "#16a37f", h=40)
                 + '<div class="gr-hl">' + "".join(f'<span>{_e(h.get("date","")[5:])} {h.get("score")}</span>'
                                                   for h in hist[-8:][::max(1, len(pts) // 3)]) + '</div>')
    else:
        trend = '<div class="gr-none">점수 이력을 쌓는 중입니다. 다음 점수 변화부터 추이가 표시됩니다.</div>'
    return ('<div class="gr-box"><div class="gr-box-h"><span>다음 실적<small>일정 탭과 같은 데이터</small></span>'
            f'{chip}</div><div class="gr-kvs">'
            + _gr_kv("발표 예정", when) + _gr_kv("예상 EPS", cur.get("eps") or "—")
            + _gr_kv("예상 매출", cur.get("rev") or "—") + _gr_kv("투자의견", rec_txt)
            + '</div>'
            + (f'<div class="gr-rk-t">지난 {len(sp)}분기 EPS 서프라이즈<small>예상 대비</small></div>'
               f'<div class="gr-sps">{bars}</div>' if sp else "")
            + f'<div class="gr-hist"><div class="gr-rk-t">점수 이력</div>{trend}</div></div>')


def _gr_deep(d, ctx=None):
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

    ctx = ctx or {}
    vals, today = ctx.get("vals") or {}, ctx.get("today") or date.today()
    head = _gr_deep_head(d, tk, col, sc, sc_col, ctx.get("asof", ""))
    verdict = _gr_deep_verdict(d, ax, sc_col,
                               _gr_quality_phrase(ctx.get("qrank", {}).get(d["ticker"], 99), ctx.get("n", 0)),
                               _gr_price_phrase(vals.get(d["ticker"])))
    extra = ('<div class="gr-2">' + _gr_price_card(d["ticker"], vals)
             + _gr_earn_card((ctx.get("earn") or {}).get(d["ticker"]),
                             (ctx.get("hist") or {}).get(d["ticker"], []), today) + '</div>')
    cards = _gr_deep_cards(ax, revs, opms)
    story = _gr_deep_story(d, revs, revsr, opms)
    bridge = _gr_deep_bridge(d)
    metrics = _gr_deep_metrics(d)

    note = ('<div style="font-size:11.5px;color:var(--faint);margin-top:12px">'
            '수치는 SEC 공시(XBRL·10-K) 원본 기반이며 정성 요약은 AI가 작성했습니다. '
            '투자 판단의 책임은 본인에게 있습니다.</div>')

    return (f'<div class="gr-card" data-tk="{tk}" style="display:none">'
            + head + verdict + extra + cards + story + bridge + metrics
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


def _gr_row(d, val=None, earn=None, hist=None, today=None):
    tk = _e(d["ticker"])
    col = _ticker_color(d["ticker"])
    sc = d.get("score", 0)
    sc_col = "#16a37f" if sc >= 78 else "#e0930a" if sc >= 55 else "#e5484d"
    yoy = d.get("rev_yoy")
    sub = [f'EV/매출 {val["evs"]:.1f}배' if val else _e(d.get("tag", ""))]
    if yoy is not None:
        sub.append(f'성장 {yoy:+.0f}%')
    ed_txt, ed_n = _gr_dday((earn or {}).get("date"), today or date.today())
    ed = f'<span class="gr-ed">실적 {ed_txt}</span>' if ed_txt and ed_n is not None and ed_n >= 0 else ""
    gadj = (val or {}).get("gadj")
    return (
        f'<div class="gr-row" data-tk="{tk}" data-score="{sc}" '
        f'data-val="{gadj if gadj is not None else 999:.4f}" data-ed="{ed_n if ed_n is not None and ed_n >= 0 else 9999}" '
        'style="display:flex;align-items:center;gap:10px;padding:11px 12px;background:var(--card);'
        'border:1px solid var(--border);border-radius:12px;cursor:pointer">'
        f'<div style="width:34px;height:34px;border-radius:8px;background:{col}22;color:{col};'
        'display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;'
        f'flex-shrink:0">{tk}</div>'
        '<div style="min-width:0;flex:1">'
        f'<div style="font-size:13px;font-weight:700;color:var(--ink)">{_e(d["name"])}</div>'
        f'<div style="font-size:11px;color:var(--muted-2);white-space:nowrap;overflow:hidden;'
        f'text-overflow:ellipsis" title="{_e(d.get("tag",""))}">{" · ".join(sub)}</div></div>'
        f'{ed}{_gr_thermo(val)}'
        f'<div style="font-size:20px;font-weight:800;color:{sc_col};flex-shrink:0;width:32px;'
        f'text-align:right">{sc}</div>{_gr_delta(hist or [])}</div>')


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
 var list=document.getElementById('grList');
 sc.querySelectorAll('.gr-sort button').forEach(function(b){
   b.addEventListener('click',function(){
     sc.querySelectorAll('.gr-sort button').forEach(function(x){x.classList.toggle('on',x===b);});
     var k=b.getAttribute('data-k'), rows=[].slice.call(list.querySelectorAll('.gr-row'));
     rows.sort(function(a,c){
       if(k==='score') return (+c.getAttribute('data-score'))-(+a.getAttribute('data-score'));
       return (+a.getAttribute('data-'+k))-(+c.getAttribute('data-'+k));
     });
     rows.forEach(function(r){list.appendChild(r);});
   });
 });
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


def _render_growth(funds, now, earnings=None, prices=None, prices_asof="", history=None):
    """earnings: _load_earnings 결과(list), prices: {티커: 현재가}, history: 점수 이력 dict."""
    funds = sorted(funds, key=lambda x: -x.get("score", 0))
    vals = _valuation(funds, prices or {})
    earn = {e["ticker"]: e for e in (earnings or [])}
    hist = history or {}
    today = now.date()
    ctx = {"vals": vals, "earn": earn, "hist": hist, "today": today, "asof": prices_asof,
           "qrank": {d["ticker"]: i + 1 for i, d in enumerate(funds)}, "n": len(funds)}
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
        r = _gr_row(d, vals.get(d["ticker"]), earn.get(d["ticker"]), hist.get(d["ticker"], []), today)
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
        + '<span>점수 = 품질(성장·수익성경로·재무건전성·주주가치) · 온도계 = 성장 대비 EV/매출의 종목 내 위치 · '
          '▲▼ = 직전 기록 대비 점수 변화</span></div>')
    head = ('<div class="sched-head" style="margin-bottom:12px"><span>'
            '<span class="sched-ico">🔎</span>성장주 '
            f'<span class="sched-tz">SEC 재무 · {len(funds)}종목'
            + (f' · 주가 {_e(prices_asof)}' if prices_asof else '') + '</span></span>'
            '<div class="gr-sort" role="group" aria-label="정렬">'
            '<button type="button" class="on" data-k="score">품질순</button>'
            '<button type="button" data-k="val">가격순</button>'
            '<button type="button" data-k="ed">실적 임박순</button></div></div>')
    screener = (f'<div id="grScreener">{head}{presets}'
                f'<div id="grList" style="display:flex;flex-direction:column;gap:7px">{"".join(rows)}</div>'
                f'{legend}</div>')
    deep = ('<div id="grDeep" style="display:none">'
            + "".join(_gr_deep(d, ctx) for d in funds) + '</div>')
    return f'<div class="part">{screener}{deep}</div>'
