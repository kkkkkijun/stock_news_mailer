# -*- coding: utf-8 -*-
"""뉴스/시세 카드 렌더링(publish_site.py 분리)."""
from __future__ import annotations

import re

from render.common import _e, _spark_svg, _text_on, _ticker_color
from render.config import _TICKER_KO
from render.parse import _is_new, _parse_part


def _quote_card(q):
    """시세 dict → 카드 HTML. 한국식 색관례(상승 빨강 ▲ / 하락 파랑 ▼)."""
    sym = (q.get("ticker") or "").strip()
    disp = sym.split("-")[0] or sym
    chg = q.get("chg")
    if chg is None:
        color, chg_txt, sp_color = "var(--faint)", "—", "#9aa7b8"
    elif chg >= 0:
        color = sp_color = "#e5484d"
        chg_txt = f"▲ {chg:.2f}%"
    else:
        color = sp_color = "#3b82f6"
        chg_txt = f"▼ {abs(chg):.2f}%"
    bg = _ticker_color(sym)
    spark = _spark_svg(q.get("spark"), sp_color)
    price = q.get("price")
    price_txt = f"${price:,.2f}" if isinstance(price, (int, float)) else "—"
    return (f'<div class="qcard"><div class="qtop">'
            f'<span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
            f'{_e(disp)}</span>{spark}</div>'
            f'<div class="qprice">{price_txt}</div>'
            f'<div class="qchg" style="color:{color};">{chg_txt}</div></div>')


def _render_quotes(cards):
    cards = [c for c in (cards or []) if c]
    if not cards:
        return ""
    grid = ('<div class="quotes">'
            + "".join(_quote_card(c) for c in cards) + "</div>")
    asof = next((c.get("asof") for c in cards if c.get("asof")), "")
    if asof:
        grid += (f'<div class="quotes-asof">시세 기준 {_e(asof)} · '
                 'Yahoo Finance</div>')
    return grid


_SENT_LAB = {"g": "호재", "b": "악재", "n": "중립"}


def _nb_row(it, i, prev_sets):
    """기사 한 줄: [판정] 한글 헤드라인 / 매체·시각 — 누르면 요약·원문 제목·링크가 펼쳐진다(첫 기사는 펼친 채)."""
    s = it.get("sent")
    tag = f'<span class="nb-tag {s}">{_SENT_LAB[s]}</span>' if s in _SENT_LAB else ""
    new = ('<span class="badge-new">NEW</span>'
           if (prev_sets is not None and _is_new(it["title"], prev_sets)) else "")
    head = it.get("ko") or it["title"]
    meta = " · ".join(x for x in (it.get("src", ""), f'같은 내용 {it["dups"]}곳 더' if it.get("dups") else "") if x)
    why = f'<span class="nb-why">{_e(it["why"])}</span>' if it.get("why") else ""
    orig = (f'<div class="nb-orig">{_e(it["title"])}</div>' if it.get("ko") else "")
    link = (f'<a class="nb-link" href="{_e(it["link"])}" target="_blank" rel="noopener">원문 보기 ↗</a>'
            if it.get("link") else "")
    desc = f'<p>{_e(it["desc"])}</p>' if it.get("desc") else ""
    op = i == 0
    return (f'<div class="nb-row{" open" if op else ""}" data-s="{s or ""}">'
            f'<button type="button" class="nb-rh" aria-expanded="{"true" if op else "false"}">{tag}'
            f'<span class="nb-tx"><b>{_e(head)}</b><span class="nb-m">{new}{_e(meta)}</span></span>'
            '<i class="nb-car" aria-hidden="true">›</i></button>'
            f'<div class="nb-body">{why}{desc}{orig}{link}</div></div>')


def _render_ticker_groups(items, prev_sets, quotes=None):
    """주식 탭 뉴스(B안): 종목 카드마다 [배지·이름·현재가·등락·추이] + 한 줄 총평·호재/악재 비율 + 기사 한 줄 목록.

    판정(🏷)이 없는 예전 회차는 총평·비율·필터 없이 같은 카드 모양으로 원문 제목을 보여준다."""
    qmap = {q.get("ticker"): q for q in (quotes or []) if q}
    groups = []
    for it in items:
        lbl = it["label"] if it["kind"] == "ticker" else None
        if lbl and groups and groups[-1][0] == lbl:
            groups[-1][1].append(it)
        else:
            groups.append([lbl, [it]])
    tagged = any(it.get("sent") for it in items)
    out = []
    if tagged:
        out.append('<div class="nb-bar" role="group" aria-label="뉴스 필터">'
                   '<button type="button" class="nb-f on" data-f="">전체</button>'
                   '<button type="button" class="nb-f" data-f="g">호재</button>'
                   '<button type="button" class="nb-f" data-f="b">악재</button>'
                   '<select class="nb-sort" aria-label="정렬"><option value="">기본 순</option>'
                   '<option value="b">악재 많은 순</option><option value="g">호재 많은 순</option></select></div>')
    out.append('<div class="nb-list">')
    for gi, (lbl, gitems) in enumerate(groups):
        # 호재·악재 기사를 위로(같은 무리 안에서는 원래 순서), 기사 아닌 페이지는 숨김
        shown = sorted((it for it in gitems if it.get("sent") != "x"),
                       key=lambda it: 0 if it.get("sent") in ("g", "b") else 1)
        hidden = len(gitems) - len(shown)
        cnt = {k: sum(1 for it in shown if it.get("sent") == k) for k in "gbn"}
        out.append(f'<div class="nb-card" data-i="{gi}" data-g="{cnt["g"]}" data-b="{cnt["b"]}">')
        if lbl:
            key = lbl.split("-")[0]
            bg = _ticker_color(lbl)
            ko = _TICKER_KO.get(key.upper(), "")
            q = qmap.get(lbl) or {}
            chg, px = q.get("chg"), q.get("price")
            if isinstance(chg, (int, float)):
                up = chg >= 0
                pq = (f'<span class="nb-px">{f"${px:,.2f}" if isinstance(px, (int, float)) else ""}'
                      f' <em class="{"up" if up else "dn"}">{"▲" if up else "▼"} {abs(chg):.2f}%</em></span>')
                sp = _spark_svg(q.get("spark"), "#e5484d" if up else "#3b82f6", w=72, h=24)
            else:
                pq = sp = ""
            out.append('<div class="nb-head">'
                       f'<span class="tk-badge" style="background:{bg};color:{_text_on(bg)}">{_e(key)}</span>'
                       f'<span class="nb-nm"><b>{_e(ko or key)}</b>{pq}</span>{sp}</div>')
        brief = next((it.get("brief") for it in gitems if it.get("brief")), "")
        if brief or any(cnt.values()):
            mood = "".join(f'<i class="{k}" style="flex:{cnt[k]}"></i>' for k in "gnb" if cnt[k])
            out.append('<div class="nb-sum">'
                       + (f'<div class="nb-brief"><span class="nb-ai">한 줄</span>{_e(brief)}</div>' if brief else "")
                       + (f'<div class="nb-cnt"><span class="nb-mood" aria-hidden="true">{mood}</span>'
                          f'<small>호재 {cnt["g"]} · 악재 {cnt["b"]} · 중립 {cnt["n"]}</small></div>' if any(cnt.values()) else "")
                       + '</div>')
        for i, it in enumerate(shown):
            out.append(_nb_row(it, i, prev_sets))
        if hidden:
            out.append(f'<div class="nb-hid">기사 아닌 페이지 {hidden}건 숨김</div>')
        out.append('</div>')
    out.append('</div>')
    if tagged:
        out.append('<div class="nb-foot">호재·악재는 AI가 기사 내용을 보유자 관점에서 분류한 것 · 투자 판단용 아님</div>')
    return "".join(out)


def _render_part(pid, icon, name, lines, hero=False, quotes=None, prev_sets=None,
                 group_by_ticker=False):
    summary, items, blocks, note = _parse_part(lines)
    h = [f'<section class="part" id="{pid}">',
         f'<div class="part-head"><span class="part-icon">{icon}</span>'
         f'<h2>{_e(name)}</h2></div>']
    quotes_html = _render_quotes(quotes)
    if quotes_html:
        h.append(quotes_html)
    if summary:
        h.append('<div class="summary"><div class="summary-label">오늘 한눈에</div>'
                 f'<p>{_e(summary)}</p></div>')
    # 제목 없는 깨진 항목 제거(모델이 제목을 비우고 테마만 준 경우 등)
    # 예: '5. (성장)' → 파싱 시 제목이 '(성장)' 뿐이고 본문도 없음.
    items = [it for it in items if (it.get("title") or "").strip()
             and not (re.fullmatch(r"\(.*?\)", it["title"].strip())
                      and not (it.get("desc") or "").strip())]
    if items and group_by_ticker:
        h.append(_render_ticker_groups(items, prev_sets, quotes))
    elif items:
        h.append('<div class="news-list">')
        for i, it in enumerate(items):
            is_hero = hero and i == 0          # 섹션의 1번 뉴스만 핵심 강조
            if not it["label"]:
                badge = ""
            elif it["kind"] == "ticker":
                bg = _ticker_color(it["label"])
                badge = (f'<span class="ticker" style="background:{bg};'
                         f'color:{_text_on(bg)};">{_e(it["label"])}</span>')
            else:
                badge = f'<span class="tag">{_e(it["label"])}</span>'
            key = '<span class="badge-key">핵심</span>' if is_hero else ""
            new = ('<span class="badge-new">NEW</span>'
                   if (prev_sets is not None and _is_new(it["title"], prev_sets))
                   else "")
            src = f'<span class="src">{_e(it["src"])}</span>' if it["src"] else ""
            desc = f'<p>{_e(it["desc"])}</p>' if it["desc"] else ""
            cls = "news hero" if is_hero else "news"
            h.append(f'<div class="{cls}"><div class="news-meta">{key}{new}{badge}{src}'
                     f'</div><h3>{_e(it["title"])}</h3>{desc}</div>')
        h.append("</div>")
    for label, bullets in blocks:
        if not bullets:
            continue
        h.append(f'<div class="outlook"><div class="outlook-label">{_e(label)}</div>'
                 '<div class="outlook-list">')
        for o in bullets:
            h.append('<div class="outlook-item"><span class="arrow">›</span>'
                     f'<span>{_e(o)}</span></div>')
        h.append("</div></div>")
    if note:
        h.append(f'<div class="note">{_e(note)}</div>')
    h.append("</section>")
    return "".join(h)
