# -*- coding: utf-8 -*-
"""기업실적 일정·결과 렌더링(publish_site.py 분리)."""
import re
from datetime import date, datetime

from render.common import _e, _fmt_money, _hl, _mv_color, _rec_color, _rep_cq, _text_on, _ticker_color
from render.config import KST, _WD_KO
from render.files import _is_fresh, _load_reports


def _report_card_html(r, open_=False):
    """8-K 기반 실적 보고서 카드 1개."""
    bg = _ticker_color(r.get("ticker", ""))
    badge = (f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
             f'{_e((r.get("ticker") or "").split("-")[0])}</span>')
    v, sp = r.get("verdict"), r.get("surprise_pos")
    vcls = "beat" if (v == "beat" or sp) else ("miss" if (v == "miss" or sp is False) else "")
    vtxt = {"beat": "어닝 서프라이즈", "miss": "어닝 쇼크", "inline": "예상 부합"}.get(v, "")
    if r.get("surprise"):
        vtxt = (vtxt + " " + ("▲" if sp else "▼") + _e(r["surprise"])).strip()
    verdict = f'<span class="rep-verdict {vcls}">{vtxt}</span>' if vtxt else ""
    metrics = [m for m in (r.get("metrics") or [])
               if not re.search(r'백로그|backlog', m.get("k", ""), re.I)][:4]
    mets = "".join(
        f'<div class="rep-m"><div class="rep-mk">{_e(m.get("k",""))}</div>'
        f'<div class="rep-mv">'
        f'{_mv_color(_fmt_money(m.get("v",""), m.get("k","")), m.get("dir"))}</div></div>'
        for m in metrics)
    ms = f'<div class="rep-ms">{mets}</div>' if mets else ""
    guide = (f'<div class="rep-guide">📈 {_hl(r["guidance"])}</div>'
             if r.get("guidance") else "")
    bullets = "".join(f'<div class="rep-b"><span>•</span><span>{_hl(b)}</span></div>'
                      for b in (r.get("bullets") or []))
    title = f'<div class="rep-hd">{_e(r.get("title",""))}</div>'
    foot = ('<div class="rep-foot">'
            f'<a href="{_e(r.get("url",""))}" target="_blank" rel="noopener">🔗 SEC 8-K 원문</a>'
            '<span>AI 요약 · 참고용</span></div>')
    newb = '<span class="ev-new">NEW</span>' if open_ else ''
    header = (f'<div class="rep-head">{badge}'
              f'<span class="rep-name">{_e(r.get("name",""))} · {_e(r.get("quarter",""))}{newb}</span>'
              f'{verdict}<span class="rep-arrow">▾</span></div>')
    body = (f'<div class="rep-body">{title}{ms}{guide}'
            f'<div class="rep-bs">{bullets}</div>{foot}</div>')
    return f'<div class="rep-item{" open" if open_ else ""}">{header}{body}</div>'


def _render_earnings(evs, now):
    head = ('<div class="sched sched-earn"><div class="sched-head">'
            '<span><span class="sched-ico">🏢</span>기업실적'
            ' <span class="sched-tz">관심종목</span></span></div>')
    if not evs:
        return head + '<div class="ern-none">등록된 실적 일정이 없습니다.</div></div>'
    fresh = sorted((r for r in _load_reports() if _is_fresh(r, now)),
                   key=lambda r: r.get("date", ""), reverse=True)
    fresh_cq = (fresh[0].get("cq") or _rep_cq(fresh[0])) if fresh else None
    fresh_tk = {r.get("ticker") for r in fresh}
    auto = bool(fresh_cq)   # 최근 발표 있으면 '실적 결과'로 자동 진입
    nb = '<span class="ev-new">NEW</span>' if fresh else ''
    toggle = ('<div class="earn-views">'
              f'<button class="ev-view{"" if auto else " on"}" data-v="up">📅 예정</button>'
              f'<button class="ev-view{" on" if auto else ""}" data-v="r">📄 실적 결과{nb}</button></div>')
    return (head + toggle
            + _render_upcoming(evs, now, show=not auto, skip=fresh_tk)
            + _render_results(evs, now, show=auto, default_cq=fresh_cq, fresh_tk=fresh_tk)
            + '<div class="sched-src">데이터: Yahoo Finance · SEC EDGAR</div></div>')


def _render_upcoming(evs, now, show=True, skip=None):
    """예정 뷰: 분기별 그룹 + 컨센서스(예상 EPS/매출·목표주가·투자의견 색/비율)."""
    up, dn = "#e5484d", "#3b82f6"
    skip = skip or set()
    groups = {}
    for e in sorted(evs, key=lambda x: (x["date"] is None, x["date"] or date.max)):
        if e["ticker"] in skip:      # 최근 발표한 종목은 '실적 결과'로
            continue
        d = e["date"]
        gk = (d.year, (d.month - 1)//3 + 1) if d else (9999, 9)
        gl = f"{d.year} {(d.month-1)//3+1}Q" if d else "미정"
        groups.setdefault(gk, {"label": gl, "rows": []})["rows"].append(e)
    disp = "" if show else ' style="display:none"'
    out = [f'<div class="earn-up"{disp}>'
           '<div class="up-note">발표 예정일·시간 · 한국시간(KST) 기준</div>']
    for gk in sorted(groups):
        out.append(f'<div class="up-qh">{_e(groups[gk]["label"])}</div>')
        for e in groups[gk]["rows"]:
            d = e["date"]
            det = e.get("detail") or {}
            cur, tgt, rec = det.get("cur") or {}, det.get("target") or {}, det.get("rec") or {}
            bg = _ticker_color(e["ticker"])
            badge = (f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
                     f'{_e(e["ticker"].split("-")[0])}</span>')
            ts = e.get("ts")
            if d:
                dd = (d - now.date()).days
                dtxt = "D-DAY" if dd == 0 else (f"D+{-dd}" if dd < 0 else f"D-{dd}")
                md = f'{d.month}/{d.day}({_WD_KO[d.weekday()]})'
                if ts:
                    md += " " + datetime.fromtimestamp(ts, KST).strftime("%H:%M")
                    if e.get("est"):
                        md += " 예상"
            else:
                dtxt, md = "미정", "미정"
            parts = []
            if cur.get("eps") not in (None, "-"):
                parts.append(f'예상 EPS <b>{_e(cur["eps"])}</b>')
            if cur.get("rev") not in (None, "-"):
                gg = ""
                if cur.get("growth"):
                    gg = f' <b style="color:{up if cur.get("growth_pos") else dn}">{_e(cur["growth"])}</b>'
                parts.append(f'매출 <b>{_e(cur["rev"])}</b>{gg}')
            if tgt.get("mean") not in (None, "-"):
                uu = ""
                if tgt.get("upside"):
                    uu = f' <b style="color:{up if tgt.get("upside_pos") else dn}">{_e(tgt["upside"])}</b>'
                parts.append(f'목표 <b>{_e(tgt["mean"])}</b>{uu}')
            subline = " · ".join(parts) if parts else "컨센서스 없음"
            sub2 = ""
            if rec.get("label") not in (None, "-"):
                lab = rec.get("label") or ""
                cnt = (f' <span class="up-cnt">({rec.get("count")}명)</span>'
                       if rec.get("count") else "")
                b_, h_, s_ = rec.get("buy") or 0, rec.get("hold") or 0, rec.get("sell") or 0
                tot = b_ + h_ + s_
                bar = rt = ""
                if tot:
                    bar = ('<span class="rec-bar">'
                           f'<i style="width:{b_/tot*100:.0f}%;background:#e5484d"></i>'
                           f'<i style="width:{h_/tot*100:.0f}%;background:#f59e0b"></i>'
                           f'<i style="width:{s_/tot*100:.0f}%;background:#3b82f6"></i></span>')
                    rt = ('<span class="rec-ratio">'
                          f'<b style="color:#e5484d">매수 {round(b_/tot*100)}%</b> · '
                          f'<b style="color:#f59e0b">보유 {round(h_/tot*100)}%</b> · '
                          f'<b style="color:#3b82f6">매도 {round(s_/tot*100)}%</b></span>')
                sub2 = (f'<div class="up-rec">투자의견 '
                        f'<b style="color:{_rec_color(lab)}">{_e(lab)}</b>{cnt}{bar}{rt}</div>')
            out.append(
                f'<div class="up-row"><span class="up-dday">{dtxt}</span>{badge}'
                f'<div class="up-main"><div class="up-t"><b>{_e(e["name"])}</b>'
                f'<span class="up-date">{md}</span></div>'
                f'<div class="up-sub">{subline}</div>{sub2}</div></div>')
    out.append('</div>')
    return "".join(out)


def _render_results(evs, now, show=False, default_cq=None, fresh_tk=None):
    """실적 결과 뷰: 연/분기 필터 + 발표분(8-K 보고서 있으면 풀카드, 없으면 숫자줄)."""
    fresh_tk = fresh_tk or set()
    rep_list = _load_reports()
    reports = {}
    for r in rep_list:
        cq = r.get("cq") or _rep_cq(r)
        if cq:
            reports[(r.get("ticker"), cq)] = r
    buckets, labels = {}, {}
    for e in evs:
        for q in (e["detail"].get("quarters") or []):
            if not q.get("reported"):
                continue
            cq = q.get("cq")
            if not cq:
                continue
            labels[cq] = q.get("label") or cq
            buckets.setdefault(cq, []).append(
                {"ticker": e["ticker"], "name": e["name"], "q": q,
                 "report": reports.get((e["ticker"], cq))})
    # Yahoo가 아직 '예정'이어도 8-K 보고서가 있으면 결과에 노출(반영 지연 대응)
    ev_name = {e["ticker"]: e["name"] for e in evs}
    for r in rep_list:
        cq = r.get("cq") or _rep_cq(r)
        if not cq:
            continue
        labels.setdefault(cq, r.get("quarter") or cq)
        lst = buckets.setdefault(cq, [])
        ex = next((x for x in lst if x["ticker"] == r.get("ticker")), None)
        if ex:
            ex["report"] = r
        else:
            lst.append({"ticker": r.get("ticker"),
                        "name": r.get("name") or ev_name.get(r.get("ticker"), ""),
                        "q": None, "report": r})
    if not buckets:
        return ('<div class="earn-r" style="display:none">'
                '<div class="ern-none">발표된 실적이 없습니다.</div></div>')
    cqs = sorted(buckets, reverse=True)
    default = default_cq if default_cq in buckets else cqs[0]
    default_year = default.split("-")[0]
    years = sorted({cq.split("-")[0] for cq in cqs}, reverse=True)
    chips = ['<div class="q-years">']
    for y in years:
        chips.append(f'<button class="q-year{" on" if y==default_year else ""}" '
                     f'data-y="{y}">{y}년</button>')
    chips.append('</div><div class="q-quarters">')
    for cq in cqs:
        y, qn = cq.split("-")
        hide = "" if y == default_year else ' style="display:none"'
        on = " on" if cq == default else ""
        chips.append(f'<button class="q-q{on}" data-y="{y}" data-q="{cq}"{hide}>{qn}Q</button>')
    chips.append('</div>')

    def _prio(x):
        # 1) NEW(최근 발표) → 2) 발표 예정(미발표) → 3) 발표됨
        if x.get("report") and x["ticker"] in fresh_tk:
            return 0
        q = x.get("q") or {}
        return 2 if (x.get("report") or q.get("reported")) else 1
    panels = []
    for cq in cqs:
        nrep = sum(1 for x in buckets[cq] if x["report"])
        note = (f'<div class="rep-note">{_e(labels[cq])} · 발표 {len(buckets[cq])}종목'
                f'{f" · 보고서 {nrep}" if nrep else ""} · 출처 SEC 8-K/Yahoo · 참고용</div>')
        items = []
        ordered = sorted(buckets[cq],
                         key=lambda x: ((x.get("report") or {}).get("date") or ""),
                         reverse=True)          # 발표일 최근순
        ordered.sort(key=_prio)                 # NEW → 예정 → 발표됨 (안정 정렬)
        for it in ordered:
            if it["report"]:
                items.append(_report_card_html(it["report"],
                                               open_=it["ticker"] in fresh_tk))
                continue
            q = it["q"]
            bg = _ticker_color(it["ticker"])
            badge = (f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
                     f'{_e(it["ticker"].split("-")[0])}</span>')
            surp = (f'<span class="q-surp {"up" if q.get("surprise_pos") else "dn"}">'
                    f'{"▲" if q.get("surprise_pos") else "▼"} {_e(q.get("surprise") or "")}</span>'
                    if q.get("surprise") else '')
            items.append(
                f'<div class="res-row">{badge}'
                f'<div class="res-main"><b>{_e(it["name"])}</b>'
                f'<span class="q-sub">EPS 실제 {_e(q.get("eps_act","-"))} / '
                f'예상 {_e(q.get("eps_est","-"))}</span></div>{surp}</div>')
        hide = "" if cq == default else ' style="display:none"'
        panels.append(f'<div class="q-panel" data-q="{cq}"{hide}>'
                      + note + "".join(items) + '</div>')
    disp = "" if show else ' style="display:none"'
    return (f'<div class="earn-r"{disp}>'
            + "".join(chips) + "".join(panels) + '</div>')
