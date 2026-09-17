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


def _render_ticker_groups(items, prev_sets):
    """뉴스 아이템을 티커별로 묶어 대표 1건만 펼치고 나머지는 접는다."""
    groups = []
    for it in items:
        lbl = it["label"] if it["kind"] == "ticker" else None
        if lbl and groups and groups[-1][0] == lbl:
            groups[-1][1].append(it)
        else:
            groups.append([lbl, [it]])
    out = ['<div class="tk-groups">']
    for lbl, gitems in groups:
        out.append('<div class="tk-group">')
        if lbl:
            key = lbl.split("-")[0]
            bg = _ticker_color(lbl)
            ko = _TICKER_KO.get(key.upper(), "")
            out.append(
                '<div class="tk-ghead">'
                f'<span class="tk-badge" style="background:{bg};color:{_text_on(bg)}">'
                f'{_e(key)}</span>'
                + (f'<span class="tk-name">{_e(ko)}</span>' if ko else "")
                + '</div>')
        rest_open = False
        for i, it in enumerate(gitems):
            new = ('<span class="badge-new">NEW</span>'
                   if (prev_sets is not None and _is_new(it["title"], prev_sets)) else "")
            tag = (f'<span class="tag">{_e(it["label"])}</span>'
                   if (it["kind"] == "tag" and it["label"]) else "")
            src = f'<span class="src">{_e(it["src"])}</span>' if it["src"] else ""
            meta = (f'<div class="news-meta">{new}{tag}{src}</div>'
                    if (new or tag or src) else "")
            desc = f'<p>{_e(it["desc"])}</p>' if it["desc"] else ""
            card = f'<div class="news tk-item">{meta}<h3>{_e(it["title"])}</h3>{desc}</div>'
            if i == 1:
                out.append('<div class="tk-rest">')
                rest_open = True
            out.append(card)
        if rest_open:
            out.append('</div>')
            out.append(f'<button class="tk-more" type="button" data-n="{len(gitems)-1}">'
                       f'뉴스 {len(gitems)-1}건 더 보기 '
                       f'<span class="tk-caret">▾</span></button>')
        out.append('</div>')
    out.append('</div>')
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
        h.append(_render_ticker_groups(items, prev_sets))
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
