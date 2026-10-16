# -*- coding: utf-8 -*-
"""성장주 스크리너·심층 카드 렌더링(publish_site.py 분리)."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

from render.common import _e, _ticker_color
from render.config import KST, _GR_SIG, _GR_SIGTXT, _WD_KO


# 가격 온도계 구간: 성장 대비 EV/매출의 종목 내 순위 위치(0=가장 저렴 ~ 1=가장 비쌈)
_TH_BANDS = ((1 / 3, "저렴", "cheap"), (2 / 3, "보통", "mid"), (1.01, "비쌈", "rich"))


def _valuation(funds: list[dict[str, Any]], prices: dict[str, float],
               nq_mcap: dict[str, float] | None = None) -> dict[str, dict[str, Any]]:
    """종목별 가격 지표. 품질 점수와 분리해 '지금 비싼가'만 본다.

    시가총액 = 주가 × 희석주식수, EV = 시총 − 순현금, EV/매출 = EV ÷ 최근 4분기 매출,
    성장 대비 EV/매출 = EV/매출 ÷ 매출 YoY(%) — 적자 성장주와 흑자 대형주를 한 줄로 비교하려고 쓴다.
    성장률이 0 이하이거나 입력이 빠지면 그 종목은 순위에서 뺀다. 단위: 백만 달러.
    nq_mcap(나스닥 표기 시총)과 20% 넘게 어긋나면 주식분할·상장 직후로 보고 나스닥 값을 쓴다
    (희석주식수는 분기 평균이라 분할·상장 직후엔 현재와 다르다)."""
    nq_mcap = nq_mcap or {}
    out: dict[str, dict[str, Any]] = {}
    for d in funds:
        tk, px, sh = d["ticker"], prices.get(d["ticker"]), d.get("shares")
        revs = [q.get("v") for q in d.get("series", {}).get("rev", [])][-4:]
        if not px or not sh or len(revs) < 4 or any(v is None for v in revs) or sum(revs) <= 0:
            continue
        mcap, basis = px * sh, "희석"
        nq = nq_mcap.get(tk)
        if nq and abs(mcap / nq - 1) > 0.20:
            mcap, basis = nq, "분할·상장 보정"
        ev = mcap - (d.get("netcash") or 0)
        evs = ev / sum(revs)
        yoy, fcf = d.get("rev_yoy"), d.get("fcf")
        out[tk] = {"mcap": mcap, "basis": basis, "ev": ev, "evs": evs,
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
    if a >= 1e6:                       # 백만 달러 단위 → 1조 달러 이상은 T
        return f"{s}${a/1e6:.2f}T"
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
    if tk in ranked:                       # 내 순위 주변 7개(앞뒤 3)만
        i = ranked.index(tk)
        lo = max(0, min(i - 3, len(ranked) - 7))
        ranked = ranked[lo:lo + 7]
    else:
        ranked = ranked[:7]
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
            '<div class="gr-rk-t">성장 대비 EV/매출 · 내 주변 순위'
            + (f'<small>{v["n"]}종목 중 {v["rank"]}번째로 저렴 · 낮을수록 성장에 비해 싸다</small>'
               if v and v.get("rank") else '<small>낮을수록 성장에 비해 싸다</small>') + '</div>'
            f'<div class="gr-rks">{bars}</div></div>')


def _gr_earn_card(earn: dict[str, Any] | None, hist: list[dict[str, Any]], today: date) -> str:
    if not earn:
        return ('<div class="gr-box"><div class="gr-box-h"><span>다음 실적</span></div>'
                '<div class="gr-none">실적 일정·컨센서스는 관심 종목(기본 12개)만 제공합니다.</div></div>')
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

    return (f'<div class="gr-card" data-tk="{tk}">'
            + head + verdict + extra + cards + story + bridge + metrics
            + _gr_qual(d) + note + '</div>')


def _gr_qual(d):
    q = d.get("qual")
    if not q:
        msg = ("해자·산업 필연성 등 정성 분석은 10-K 수집 후 표시됩니다." if d.get("watch", True)
               else "AI 정성 분석(해자·산업 필연성)은 관심 종목(기본 12개)만 제공합니다.")
        return f'<div style="font-size:11.5px;color:var(--faint);margin-top:14px">{msg}</div>'
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
 var root=document.getElementById('grRoot'); if(!root) return;
 var DEF=JSON.parse(root.getAttribute('data-default')||'[]'), VER=root.getAttribute('data-v')||'';
 var KEY='mb_watch_v1', DIRTY='mb_watch_dirty', PAGE=30, shown=PAGE, from='all';
 function lg(k){try{return localStorage.getItem(k);}catch(e){return null;}}
 function ls(k,v){try{ if(v==null) localStorage.removeItem(k); else localStorage.setItem(k,v);}catch(e){}}
 var fav=(function(){ try{ var a=JSON.parse(lg(KEY)); if(Array.isArray(a)) return a; }catch(e){} return DEF.slice(); })();
 var W=null;
 function isFav(t){ return fav.indexOf(t)>=0; }
 // ---- 즐겨찾기 저장: 로그인 시 Firestore(users/{uid}.watch, goal-app.js의 MBWatch), 아니면 이 브라우저 ----
 function persist(){ ls(KEY,JSON.stringify(fav));
   if(W&&W.uid){ W.set(fav).catch(function(){}); ls(DIRTY,null); } else ls(DIRTY,'1'); }
 function sync(){ W=window.MBWatch; if(!W||!W.ready) return;
   if(W.uid){
     if(W.list==null){ W.set(fav).catch(function(){}); ls(DIRTY,null); }
     else if(lg(DIRTY)){ var u=W.list.slice(); fav.forEach(function(t){ if(u.indexOf(t)<0) u.push(t); });
       fav=u; W.set(fav).catch(function(){}); ls(DIRTY,null); ls(KEY,JSON.stringify(fav)); }
     else { fav=W.list.slice(); ls(KEY,JSON.stringify(fav)); }
   }
   paint();
 }
 window.addEventListener('mbwatch', sync);
 var toastT=null, undo=null;
 function toast(msg,undoFn){ var t=document.getElementById('grToast'); if(!t) return;
   t.innerHTML=msg+(undoFn?' <button type="button" class="gr-undo">실행 취소</button>':''); t.hidden=false; undo=undoFn;
   clearTimeout(toastT); toastT=setTimeout(function(){ t.hidden=true; undo=null; },3000); }
 function name(t){ var r=root.querySelector('.gt-row[data-t="'+t+'"]')||root.querySelector('.gr-row[data-tk="'+t+'"]');
   return r?(r.getAttribute('data-nm')||t):t; }
 function toggle(t){ var on=!isFav(t), before=fav.slice();
   if(on) fav.push(t); else fav=fav.filter(function(x){return x!==t;});
   persist(); paint();
   toast(name(t)+(on?'을(를) 관심 목록에 추가했어요':'을(를) 관심 목록에서 뺐어요')+((W&&W.uid)?'':' · 로그인하면 계정에 저장돼요'),
         function(){ fav=before; persist(); paint(); }); }
 // ---- 탭 ----
 function view(v){ from=v;
   root.querySelectorAll('.gr-tab').forEach(function(b){ b.classList.toggle('on',b.getAttribute('data-v')===v); });
   document.getElementById('grAll').style.display=v==='all'?'':'none';
   document.getElementById('grScreener').style.display=v==='fav'?'':'none';
   document.getElementById('grBt').style.display=v==='bt'?'':'none';
   document.getElementById('grDeep').style.display='none'; }
 // ---- 전체 선별 표: 필터·정렬·더 보기 ----
 var tb=document.getElementById('gtBody'), sortK='yoy', sortDir=-1, gMin=-1e9, onlyProfit=false, onlyFav=false;
 function rows(){ return [].slice.call(tb.querySelectorAll('.gt-row')); }
 function applyTable(){ if(!tb) return;
   var q=(document.getElementById('gtSearch').value||'').trim().toLowerCase(), sec=document.getElementById('gtSector').value;
   var rs=rows();
   rs.sort(function(a,b){ var x=parseFloat(a.getAttribute('data-'+sortK)), y=parseFloat(b.getAttribute('data-'+sortK));
     if(isNaN(x)) return 1; if(isNaN(y)) return -1; return (x-y)*sortDir; });
   var n=0;
   rs.forEach(function(r){ tb.appendChild(r);
     var t=r.getAttribute('data-t'), ok=true;
     if(q && (t.toLowerCase()+' '+(r.getAttribute('data-nm')||'').toLowerCase()).indexOf(q)<0) ok=false;
     if(sec && r.getAttribute('data-sector')!==sec) ok=false;
     if(parseFloat(r.getAttribute('data-yoy'))<gMin) ok=false;
     if(onlyProfit && !(parseFloat(r.getAttribute('data-opm'))>0)) ok=false;
     if(onlyFav && !isFav(t)) ok=false;
     if(ok) n++;
     r.style.display=(ok && n<=shown)?'':'none';
     if(ok) r.querySelector('.n').textContent=n; });
   document.getElementById('gtCount').textContent=n;
   var m=document.getElementById('gtMore'); m.style.display=n>shown?'':'none';
   m.textContent=n+'개 중 '+Math.min(n,shown)+'개 표시 · 더 보기';
   root.querySelectorAll('.gt-th').forEach(function(h){ var k=h.getAttribute('data-k');
     h.classList.toggle('sorted',k===sortK); h.setAttribute('aria-sort',k===sortK?(sortDir<0?'descending':'ascending'):'none');
     h.querySelector('i').textContent=k===sortK?(sortDir<0?'▼':'▲'):''; }); }
 // ---- 관심 목록: 즐겨찾기 + 프리셋 + 정렬 ----
 var preset='all';
 function applyList(){ var list=document.getElementById('grList'); if(!list) return; var c=0;
   [].slice.call(list.querySelectorAll('.gr-row')).forEach(function(r){
     var ok=isFav(r.getAttribute('data-tk')), f=preset;
     if(ok && f!=='all') ok=(f==='profit'&&r.getAttribute('data-g0')==='g')||(f==='turn'&&r.getAttribute('data-turn')==='1')||(f==='cash'&&r.getAttribute('data-cash')==='g');
     r.style.display=ok?'flex':'none'; if(isFav(r.getAttribute('data-tk'))) c++; });
   var e=document.getElementById('grEmpty'); if(e) e.hidden=c>0; }
 function paint(){
   root.querySelectorAll('.gt-star').forEach(function(b){ var on=isFav(b.getAttribute('data-t'));
     b.classList.toggle('on',on); b.textContent=on?'★':'☆'; b.setAttribute('aria-pressed',on?'true':'false');
     b.setAttribute('aria-label',(on?'관심 목록에서 빼기: ':'관심 목록에 추가: ')+b.getAttribute('data-t')); });
   var c=document.getElementById('grFavN'); if(c) c.textContent=fav.filter(function(t){ return root.querySelector('.gr-row[data-tk="'+t+'"]'); }).length;
   applyList(); applyTable(); }
 // ---- 상세: 종목별 파일을 불러와 표시(페이지 용량 절약) ----
 var cache={};
 function openDeep(t){ var dp=document.getElementById('grDeep');
   document.getElementById('grAll').style.display='none'; document.getElementById('grScreener').style.display='none';
   document.getElementById('grBt').style.display='none'; dp.style.display='block'; dp.innerHTML='<div class="gr-none" style="padding:30px 0;text-align:center">불러오는 중…</div>'; window.scrollTo(0,root.getBoundingClientRect().top+window.scrollY-60);
   var p=cache[t]?Promise.resolve(cache[t]):fetch('/stock_news_mailer/growth/'+encodeURIComponent(t)+'.html?v='+VER).then(function(r){ if(!r.ok) throw 0; return r.text(); });
   p.then(function(h){ cache[t]=h; dp.innerHTML=h; }).catch(function(){ dp.innerHTML='<div class="gr-none" style="padding:30px 0;text-align:center">상세 정보를 불러오지 못했습니다. <button type="button" class="gr-back">← 목록</button></div>'; }); }
 root.addEventListener('click',function(ev){ var el=ev.target;
   var star=el.closest('.gt-star'); if(star){ ev.stopPropagation(); toggle(star.getAttribute('data-t')); return; }
   if(el.closest('.gr-undo')){ if(undo){ var u=undo; undo=null; u(); } document.getElementById('grToast').hidden=true; return; }
   var tab=el.closest('.gr-tab'); if(tab){ view(tab.getAttribute('data-v')); return; }
   if(el.closest('.gr-back')){ view(from); return; }
   var th=el.closest('.gt-th'); if(th){ var k=th.getAttribute('data-k'); if(k===sortK) sortDir=-sortDir; else { sortK=k; sortDir=-1; } applyTable(); return; }
   var g=el.closest('.gt-g'); if(g){ root.querySelectorAll('.gt-g').forEach(function(x){x.classList.toggle('on',x===g);}); gMin=parseFloat(g.getAttribute('data-g')); shown=PAGE; applyTable(); return; }
   var tg=el.closest('.gt-tog'); if(tg){ tg.classList.toggle('on'); var f=tg.getAttribute('data-f'); if(f==='profit') onlyProfit=tg.classList.contains('on'); else onlyFav=tg.classList.contains('on'); shown=PAGE; applyTable(); return; }
   if(el.closest('#gtMore')){ shown+=PAGE*10; applyTable(); return; }
   var pr=el.closest('.gr-preset'); if(pr){ root.querySelectorAll('.gr-preset').forEach(function(x){x.style.opacity='.55';}); pr.style.opacity='1'; preset=pr.getAttribute('data-f'); applyList(); return; }
   var sb=el.closest('.gr-sort button'); if(sb){ root.querySelectorAll('.gr-sort button').forEach(function(x){x.classList.toggle('on',x===sb);});
     var k=sb.getAttribute('data-k'), list=document.getElementById('grList'), rs=[].slice.call(list.querySelectorAll('.gr-row'));
     rs.sort(function(a,c){ if(k==='score') return (+c.getAttribute('data-score'))-(+a.getAttribute('data-score')); return (+a.getAttribute('data-'+k))-(+c.getAttribute('data-'+k)); });
     rs.forEach(function(r){ list.appendChild(r); }); return; }
   var row=el.closest('.gt-row,.gr-row'); if(row && row.getAttribute('data-has')!=='0'){ openDeep(row.getAttribute('data-t')||row.getAttribute('data-tk')); } });
 ['input','change'].forEach(function(e){ root.addEventListener(e,function(ev){ if(ev.target.id==='gtSearch'||ev.target.id==='gtSector'){ shown=PAGE; applyTable(); } }); });
 view('all'); sync(); paint();
})();
</script>"""


_BT_AXES = (("growth", "성장"), ("path", "수익성 경로"), ("balance", "재무 건전성"), ("shareholder", "주주 가치"))


def _bt_verdict(h3: dict[str, Any]) -> str:
    """3개월 결과 한 줄 판정(숫자에서 기계적으로)."""
    hi, lo, w, n = h3["hi"], h3["lo"], h3["wins"], h3["dates"]
    if hi > lo and w * 2 > n:
        return "점수 상위 절반이 대체로 더 올랐습니다"
    if hi < lo and w * 2 < n:
        return "지금 점수는 3개월 수익률을 맞히지 못했습니다"
    return "점수와 3개월 수익률 사이에 뚜렷한 관계가 보이지 않습니다"


def _bt_ic(x: float | None) -> str:
    return "" if x is None else f"{x:+.2f}"


def _bt_chart(per: list[dict[str, Any]]) -> str:
    """시점별 (상위 절반 − 하위 절반) 3개월 수익률 차이 막대(SVG)."""
    rows = [r for r in per if "hi3" in r]
    if not rows:
        return ""
    W, H, top, bot = 560, 200, 22, 30
    diffs = [r["hi3"] - r["lo3"] for r in rows]
    m = max(5.0, max(abs(x) for x in diffs))
    zero = top + (H - top - bot) / 2
    sc = (H - top - bot) / 2 / m
    bw = (W - 20) / len(rows)
    out = [f'<svg viewBox="0 0 {W} {H}" class="bt-svg" role="img" aria-label="시점별 점수 상위 절반과 하위 절반의 3개월 수익률 차이">'
           f'<line x1="10" x2="{W - 10}" y1="{zero:.1f}" y2="{zero:.1f}" class="ax"/>']
    for i, (r, x) in enumerate(zip(rows, diffs)):
        cx = 10 + bw * (i + .5)
        h = max(abs(x) * sc, 1)
        y = zero - h if x >= 0 else zero
        out.append(f'<rect x="{cx - bw * .32:.1f}" y="{y:.1f}" width="{bw * .64:.1f}" height="{h:.1f}" rx="3" '
                   f'class="{"w" if x > 0 else "l"}"><title>{r["d"]} 상위 {r["hi3"]:+.1f}% · 하위 {r["lo3"]:+.1f}%</title></rect>')
        ly = (y - 5) if x >= 0 else (y + h + 11)
        out.append(f'<text x="{cx:.1f}" y="{ly:.1f}" class="v">{x:+.0f}</text>')
        out.append(f'<text x="{cx:.1f}" y="{H - 10}" class="dt">{r["d"][2:4]}.{r["d"][5:7]}</text>')
    out.append("</svg>")
    return "".join(out)


def _render_backtest(bt: dict[str, Any] | None) -> str:
    """성장주 '점수 검증' 탭: data/backtest.json(backtest.py) 요약."""
    if not bt or not bt.get("h3"):
        return ('<div id="grBt" style="display:none"><div class="gr-none" style="padding:24px 0;text-align:center">'
                '점수 검증 결과가 아직 없습니다.</div></div>')
    h3, h6 = bt["h3"], bt.get("h6")
    def pct(x):
        return f'{x:+.1f}%'
    six = (f' · 6개월: 상위 <em class="hi">{pct(h6["hi"])}</em> / 하위 <em>{pct(h6["lo"])}</em> '
           f'({h6["wins"]}/{h6["dates"]}회)' if h6 else "")
    verdict = (f'<div class="bt-verdict"><b>{_bt_verdict(h3)}</b>'
               f'<span>3개월 평균 수익률: 점수 상위 절반 <em class="hi">{pct(h3["hi"])}</em> · 하위 절반 <em>{pct(h3["lo"])}</em> · '
               f'상위가 이긴 시점 {h3["wins"]}/{h3["dates"]}{six}</span>'
               + (f'<span>점수 순위와 수익률 순위의 상관(평균): {h3["ic"]:+.2f} <small>(0이면 무관, +1이면 완전히 일치)</small></span>'
                  if h3.get("ic") is not None else "")
               + '<span class="bt-warn">⚠ 지금 나스닥 100에 남아 있는 종목만으로 계산해, 그사이 빠진 종목이 없는 만큼 '
                 '실제보다 좋게 나왔을 수 있습니다.</span></div>')
    axes = bt.get("axes") or {}
    ax_rows = "".join(
        f'<div class="bt-ax"><span>{lab}</span><span class="bt-ax-bar"><i class="{"w" if a["spread"] > 0 else "l"}" '
        f'style="{"left:50%" if a["spread"] > 0 else "right:50%"};width:{min(abs(a["spread"]) / 10 * 50, 50):.0f}%"></i></span>'
        f'<b class="{"w" if a["spread"] > 0 else "l"}">{a["spread"]:+.1f}%p</b><small>{a["wins"]}/{a["dates"]}</small></div>'
        for k, lab in _BT_AXES if (a := axes.get(k)))
    ax_box = (f'<div class="bt-box"><div class="bt-h">축별로 나눠 보면 <small>그 축 점수 상위 절반 − 하위 절반, 3개월 · 이긴 시점</small></div>'
              f'{ax_rows}</div>') if ax_rows else ""
    trs = "".join(
        f'<tr><td>{_e(r["d"])}</td><td class="c">{r["n"]}</td><td class="tops">{_e(", ".join(r["top"]))}</td>'
        f'<td class="num{" w" if r["hi3"] > r["lo3"] else ""}">{pct(r["hi3"])}</td>'
        f'<td class="num{" w" if r["lo3"] > r["hi3"] else ""}">{pct(r["lo3"])}</td>'
        f'<td class="num">{_bt_ic(r.get("ic3"))}</td></tr>'
        for r in reversed(bt.get("per", [])) if "hi3" in r)
    table = ('<details class="bt-det"><summary>시점별 자세히</summary><div class="gt-wrap"><table class="gt bt-t"><thead><tr>'
             '<th>시점</th><th>종목 수</th><th>그때 점수 상위 5</th><th>상위 절반</th><th>하위 절반</th><th>순위 상관</th>'
             f'</tr></thead><tbody>{trs}</tbody></table></div></details>')
    skipped = bt.get("skipped") or []
    how = ('<div class="bt-how"><b>어떻게 계산했나</b><ul>'
           f'<li>{_e(bt["first"])}~{_e(bt["last"])}, 실적 시즌 직후(2·5·8·11월 15일) {h3["dates"]}개 시점마다 '
           '<b>그날까지 SEC에 공시된 재무만</b>으로 그때의 품질 점수를 다시 계산(공시일 기준 · 미래 정보 차단)</li>'
           '<li>그 시점 점수로 종목을 반으로 나눠 이후 91일(3개월)·182일(6개월) 주가 수익률 평균을 비교(배당 제외)</li>'
           f'<li>대상: 지금 정밀 분석 중인 {bt["universe"]}종목 · 관측 {bt["n"]}건'
           + (f' · 계산 불가 {len(skipped)}개' if skipped else "") + '</li>'
           '<li><b>한계</b>: 종목을 <b>지금</b> 기준으로 골라(지금 나스닥 100 + 관심 종목) 그사이 탈락·상장폐지된 종목이 빠져 있고, '
           '같은 시점의 수익률은 시장 전체 흐름에 함께 움직여 시점 수가 적으면 우연의 영향이 큼. 투자 판단용 아님</li>'
           f'<li>{_e(bt["built"])} 계산 · 4주마다 다시 계산</li></ul></div>')
    legend = ('<div class="bt-legend"><span><i class="w"></i>상위 절반이 더 오름</span><span><i class="l"></i>하위 절반이 더 오름</span>'
              '<span>막대 = 시점별 3개월 수익률 차이(%p)</span></div>')
    return (f'<div id="grBt" style="display:none">{verdict}{legend}{_bt_chart(bt.get("per", []))}'
            f'{ax_box}{table}{how}</div>')


_SECTOR_ORDER = ("정보기술", "커뮤니케이션", "경기소비재", "헬스케어", "산업재", "필수소비재",
                 "금융", "에너지", "유틸리티", "부동산", "소재", "기타")


def _num_attr(v):
    return "" if v is None else f"{v:.4f}"


def _gt_row(r: dict[str, Any], d: dict[str, Any] | None, v: dict[str, Any] | None,
            u: dict[str, Any]) -> str:
    """전체 선별 표 1행. r=1차 선별, d=정밀 분석(없을 수 있음), v=가격, u=나스닥 목록 행."""
    t = r["t"]
    name = (d or {}).get("name") or u.get("name") or t
    sec = u.get("sector") or (d or {}).get("sector") or ""
    mcap, basis = None, ""
    if v:
        mcap, basis = v["mcap"], v.get("basis", "")
    elif u.get("px") and r.get("shares_dil"):
        mcap, basis = u["px"] * r["shares_dil"], "희석" if r.get("shares_basis") != "기본" else "기본 주식수"
        if u.get("mcap_nq") and abs(mcap / u["mcap_nq"] - 1) > 0.20:
            mcap, basis = u["mcap_nq"], "분할·상장 보정"
    elif u.get("mcap_nq"):
        mcap, basis = u["mcap_nq"], "나스닥 기준"
    note = f'<small class="gt-sub warn">{basis}</small>' if basis in ("분할·상장 보정", "나스닥 기준", "기본 주식수") else ""
    chips = []
    if r.get("gw") is not None and r["gw"] >= 30 and r["yoy"] >= 25:
        chips.append(f'<span class="gt-chip m" title="영업권 1년 {r["gw"]:+.0f}%">인수 영향 확인</span>')
    if r.get("gap") is not None and r["gap"] > 10:
        chips.append(f'<span class="gt-chip d" title="총매출·고객계약 매출 성장률 차 {r["gap"]}%p">매출 정의 확인</span>')
    if r.get("per") and r["per"][-1] != "2":
        chips.append('<span class="gt-chip q" title="회계연도가 달라 직전 분기끼리 비교">직전 분기 기준</span>')
    sc = (d or {}).get("score")
    q = (f'<b class="gt-sc {"g" if sc >= 78 else "y" if sc >= 55 else "r"}">{sc}</b>' if sc is not None
         else '<span class="gt-na">—</span>')
    th = _gr_thermo(v) if v else '<span class="gt-na">—</span>'
    yoy, opm = r["yoy"], r.get("opm")
    return (f'<tr class="gt-row" data-t="{_e(t)}" data-nm="{_e(name)}" data-sector="{_e(sec)}" '
            f'data-yoy="{yoy:.2f}" data-opm="{_num_attr(opm)}" data-mcap="{_num_attr(mcap)}" '
            f'data-rev="{r["rev"]:.2f}" data-score="{sc if sc is not None else ""}" '
            f'data-val="{_num_attr((v or {}).get("gadj"))}" data-has="{1 if d else 0}">'
            f'<td class="st"><button type="button" class="gt-star" data-t="{_e(t)}" aria-pressed="false">☆</button></td>'
            f'<td class="n"></td>'
            f'<td><div class="gt-tk"><span class="gt-sym">{_e(t)}</span><span class="gt-nm">{_e(name)}'
            f'<small title="{_e(u.get("sector_src", ""))}"><span class="gt-tk-in">{_e(t)} · </span>{_e(sec)}</small></span></div></td>'
            f'<td class="num">{_gr_money(mcap)}{note}</td>'
            f'<td class="num c-rev">{_gr_money(r["rev"])}<small class="gt-sub">{_e(r.get("tag", ""))}</small></td>'
            f'<td class="num {"up" if yoy >= 0 else "dn"}">{yoy:+.0f}%</td>'
            f'<td class="num c-opm">{"—" if opm is None else f"{opm:+.0f}%"}</td>'
            f'<td class="num">{q}</td><td class="c-th">{th}</td><td class="c-chips">{"".join(chips)}</td></tr>')


def _growth_ctx(funds, now, earnings=None, prices=None, prices_asof="", history=None, universe=None):
    """목록·표·상세가 함께 쓰는 계산 결과. 가격은 나스닥 현재가 우선(전체 선별과 같은 기준)."""
    funds = sorted(funds, key=lambda x: -x.get("score", 0))
    uni = {r["t"]: r for r in (universe or {}).get("rows", [])}
    px = dict(prices or {})
    for t, u in uni.items():
        if u.get("px"):
            px[t] = u["px"]
    vals = _valuation(funds, px, {t: u["mcap_nq"] for t, u in uni.items() if u.get("mcap_nq")})
    asof = (f'나스닥 {universe.get("asof")} 종가' if universe and universe.get("asof") else prices_asof)
    return {"funds": funds, "vals": vals, "earn": {e["ticker"]: e for e in (earnings or [])},
            "hist": history or {}, "today": now.date(), "asof": asof, "uni": uni,
            "qrank": {d["ticker"]: i + 1 for i, d in enumerate(funds)}, "n": len(funds)}


def _gr_universe_note(funds, screen, universe) -> str:
    """'분석 대상 N종목은 어떻게 정했나' 접이식 설명. 숫자·티커는 데이터에서 계산(갱신 시 자동 반영)."""
    u_rows = (universe or {}).get("rows") or []
    s_rows = (screen or {}).get("rows") or []
    if not u_rows or not s_rows:
        return ""
    s_set = {r["t"] for r in s_rows}
    miss = list((screen or {}).get("miss") or [])
    dup = [r["t"] for r in u_rows if r["t"] not in s_set and r["t"] not in miss]
    extra = [d["ticker"] for d in funds if d["ticker"] not in s_set]
    n_co = len(u_rows) - len(dup)
    li = [f'<li><b>나스닥 100 목록 {len(u_rows)}개</b>(나스닥 공식 데이터)'
          + (f' — 같은 회사의 다른 종류 주식({_e(", ".join(dup))})은 빼서 <b>{n_co}개 회사</b>' if dup else "")
          + '</li>']
    if miss:
        li.append(f'<li><b>{len(miss)}개 제외 → {len(s_rows)}개</b>: SEC 표준 재무 데이터로 분기 매출을 계산할 수 없는 종목'
                  f'({_e(", ".join(miss))}). 대부분 해외 기업이라 미국 분기 보고서(10-Q) 대신 해외 양식으로 공시하고, '
                  '일부는 매출 항목 이름이 달라 자동 계산에서 빠집니다</li>')
    if extra:
        li.append(f'<li><b>관심 종목 중 나스닥 100 밖 {len(extra)}개 추가 → {len(funds)}개</b> ({_e(", ".join(extra))})</li>')
    li.append('<li><b>왜 나스닥 100인가</b>: 성장 기업 비중이 높은 지수이고, 무료 공식 데이터(나스닥·SEC)만으로 매일 갱신할 수 있는 범위라서 먼저 이 범위로 시작했습니다. '
              'S&amp;P 500 등으로 넓히는 것은 보류 중</li>')
    return (f'<details class="gr-uni"><summary>분석 대상 {len(funds)}종목은 어떻게 정했나</summary>'
            f'<ol>{"".join(li)}</ol></details>')


def _render_growth(funds, now, earnings=None, prices=None, prices_asof="", history=None,
                   screen=None, universe=None, default_watch=None, backtest=None):
    """성장주 탭: [전체 선별 · 나스닥 100] 표 / [관심 목록] 목록 / [점수 검증]. 상세는 growth/<티커>.html을 불러온다.

    screen: data/screen.json(1차 선별), universe: data/universe.json, default_watch: 로그인 전 기본 관심 종목,
    backtest: data/backtest.json(점수 검증 · 시점 기준 백테스트)."""
    ctx = _growth_ctx(funds, now, earnings, prices, prices_asof, history, universe)
    funds, vals, earn, hist, uni = ctx["funds"], ctx["vals"], ctx["earn"], ctx["hist"], ctx["uni"]
    by = {d["ticker"]: d for d in funds}
    default_watch = default_watch or [d["ticker"] for d in funds if d.get("watch", True)]
    # 관심 목록 탭(기존 목록 화면): 정밀 분석된 모든 종목 행을 두고, 즐겨찾기만 보이게(JS)
    presets = (
        '<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:14px">'
        + "".join(f'<span class="gr-preset" data-f="{k}" style="font-size:12px;padding:6px 11px;'
                  f'border-radius:99px;background:var(--chip);color:var(--{"ink" if k == "all" else "muted-2"});'
                  f'cursor:pointer;opacity:{1 if k == "all" else .55}">{lab}</span>'
                  for k, lab in (("all", "전체"), ("profit", "고성장·흑자"), ("turn", "적자 갭 축소"), ("cash", "순현금")))
        + '</div>')
    rows = []
    for d in funds:
        r = _gr_row(d, vals.get(d["ticker"]), earn.get(d["ticker"]), hist.get(d["ticker"], []), ctx["today"])
        ax = d.get("axes", {})
        turn = "1" if (d.get("opm_delta") or 0) >= 3 and (d.get("opm") or 0) < 0 else "0"
        r = r.replace('data-score="', f'data-nm="{_e(d.get("name", ""))}" data-g0="{ax.get("growth", {}).get("sig")}" '
                      f'data-turn="{turn}" data-cash="{ax.get("balance", {}).get("sig")}" data-score="', 1)
        rows.append(r)
    legend = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:11px;color:var(--faint)">'
        + "".join(f'<span style="display:inline-flex;align-items:center;gap:5px">'
                  f'<span style="width:8px;height:8px;border-radius:50%;background:{_GR_SIG[s_]}"></span>'
                  f'{_GR_SIGTXT[s_]}</span>' for s_ in ("g", "y", "r"))
        + f'<span>점수 = 품질(성장·수익성경로·재무건전성·주주가치) · 온도계 = 성장 대비 EV/매출의 {len([v for v in vals.values() if v.get("rank")])}종목 내 위치 · '
          '▲▼ = 직전 기록 대비 점수 변화 · 관심 종목 편집은 전체 선별 표의 ☆</span></div>')
    fav_view = ('<div id="grScreener" style="display:none">'
                '<div class="gr-sub-h"><div class="gr-sort" role="group" aria-label="정렬">'
                '<button type="button" class="on" data-k="score">품질순</button>'
                '<button type="button" data-k="val">가격순</button>'
                '<button type="button" data-k="ed">실적 임박순</button></div></div>'
                f'{presets}<div id="grList" style="display:flex;flex-direction:column;gap:7px">{"".join(rows)}</div>'
                '<div id="grEmpty" class="gr-none" style="padding:24px 0;text-align:center" hidden>'
                '관심 종목이 없습니다. 전체 선별 표에서 ☆를 눌러 추가하세요.</div>'
                f'{legend}</div>')
    # 전체 선별 탭(나스닥 100)
    sc_rows = (screen or {}).get("rows", [])
    all_view = ""
    if sc_rows:
        secs = sorted({uni.get(r["t"], {}).get("sector", "") for r in sc_rows} - {""},
                      key=lambda x: _SECTOR_ORDER.index(x) if x in _SECTOR_ORDER else 99)
        trs = "".join(_gt_row(r, by.get(r["t"]), vals.get(r["t"]), uni.get(r["t"], {})) for r in sc_rows)
        ths = "".join(f'<th class="gt-th{c}" data-k="{k}" role="columnheader" aria-sort="none" tabindex="0">{lab} <i></i></th>'
                      for k, lab, c in (("mcap", "시가총액", ""), ("rev", "분기 매출", " c-rev"), ("yoy", "매출 성장", ""),
                                        ("opm", "영업이익률", " c-opm"), ("score", "품질 점수", ""), ("val", "가격", " c-th")))
        miss = (screen or {}).get("miss") or []
        all_view = (
            '<div id="grAll"><div class="gt-filters">'
            '<input id="gtSearch" type="search" placeholder="종목·티커 검색" aria-label="종목 검색">'
            '<select id="gtSector" aria-label="섹터"><option value="">섹터: 전체</option>'
            + "".join(f'<option value="{_e(x)}">{_e(x)}</option>' for x in secs) + '</select>'
            '<span class="gt-grp" role="group" aria-label="매출 성장">매출 성장'
            '<button type="button" class="gt-g on" data-g="-1e9">전체</button><button type="button" class="gt-g" data-g="15">+15%</button>'
            '<button type="button" class="gt-g" data-g="25">+25%</button><button type="button" class="gt-g" data-g="50">+50%</button></span>'
            '<button type="button" class="gt-tog" data-f="profit">흑자만</button>'
            '<button type="button" class="gt-tog" data-f="fav">★ 관심만</button></div>'
            '<div class="gt-wrap"><table class="gt"><thead><tr><th class="st" title="관심 목록">★</th><th class="n">#</th>'
            f'<th>종목</th>{ths}<th class="c-chips">표시</th></tr></thead><tbody id="gtBody">{trs}</tbody></table></div>'
            '<button type="button" id="gtMore" class="gt-more"></button>'
            f'<div class="gt-foot">조건에 맞는 <b id="gtCount">{len(sc_rows)}</b>개 · 매출 = 최근 분기 SEC 공시(총매출 우선) · '
            '시총 = 주가 × 희석주식수 · '
            + (f'계산 불가 {len(miss)}개: {_e(", ".join(miss))}' if miss else "")
            + '</div></div>')
    n_all = len(sc_rows)
    tabs = ('<div class="gr-tabs" role="tablist">'
            + (f'<button type="button" class="gr-tab on" data-v="all" role="tab">전체 선별<span class="gr-tab-x"> · 나스닥 100</span><small>{n_all}</small></button>' if sc_rows else "")
            + f'<button type="button" class="gr-tab{"" if sc_rows else " on"}" data-v="fav" role="tab">관심 목록<small id="grFavN">{len(default_watch)}</small></button>'
            + ('<button type="button" class="gr-tab" data-v="bt" role="tab">점수 검증</button>' if backtest else "")
            + '</div>')
    head = ('<div class="sched-head" style="margin-bottom:10px"><span>'
            '<span class="sched-ico">🔎</span>성장주 '
            f'<span class="sched-tz">SEC 재무 · 정밀 분석 {len(funds)}종목'
            + (f' · 주가 {_e(ctx["asof"])}' if ctx["asof"] else '') + '</span></span></div>')
    ver = now.strftime("%Y%m%d%H%M")
    if not sc_rows:                 # 1차 선별 데이터가 없으면 관심 목록만(이전과 같은 화면)
        fav_view = fav_view.replace('id="grScreener" style="display:none"', 'id="grScreener"', 1)
        all_view = '<div id="grAll" style="display:none"></div>'
    return (f'<div class="part" id="grRoot" data-default=\'{_e(json.dumps(default_watch))}\' data-v="{ver}">'
            f'{head}{tabs}{_gr_universe_note(funds, screen, universe)}<div id="grToast" class="gr-toast" role="status" hidden></div>'
            f'{all_view}{fav_view}{_render_backtest(backtest)}<div id="grDeep" style="display:none"></div></div>')


def write_growth_fragments(funds, now, out_dir, earnings=None, prices=None, prices_asof="",
                           history=None, universe=None) -> int:
    """종목별 상세 카드를 out_dir/<티커>.html로 쓴다(메인·지난 회차 페이지가 필요할 때 불러옴).

    반환: 쓴 파일 수. 더 이상 정밀 분석 대상이 아닌 종목의 옛 파일은 지운다."""
    ctx = _growth_ctx(funds, now, earnings, prices, prices_asof, history, universe)
    os.makedirs(out_dir, exist_ok=True)
    keep = set()
    for d in ctx["funds"]:
        fn = f'{d["ticker"]}.html'
        keep.add(fn)
        html = _gr_deep(d, ctx)
        p = os.path.join(out_dir, fn)
        try:
            if open(p, encoding="utf-8").read() == html:
                continue
        except OSError:
            pass
        with open(p, "w", encoding="utf-8") as f:
            f.write(html)
    for fn in os.listdir(out_dir):
        if fn.endswith(".html") and fn not in keep:
            os.remove(os.path.join(out_dir, fn))
    return len(keep)
