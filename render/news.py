# -*- coding: utf-8 -*-
"""뉴스/시세 카드 렌더링(publish_site.py 분리)."""
from __future__ import annotations

import re

from render.common import _e, _spark_svg, _text_on, _ticker_color
from render.config import _TICKER_KO
from render.parse import _is_new, _parse_part


def _quote_inner(q):
    """시세 카드 내용(배지·추이·가격·등락). 버튼 안에도 들어가므로 span만 쓴다. 한국식 색관례(상승 빨강 ▲ / 하락 파랑 ▼)."""
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
    return (f'<span class="qtop"><span class="ticker" style="background:{bg};color:{_text_on(bg)};">'
            f'{_e(disp)}</span>{spark}</span>'
            f'<span class="qprice">{price_txt}</span>'
            f'<span class="qchg" style="color:{color};">{chg_txt}</span>')


def _quote_card(q):
    return f'<div class="qcard">{_quote_inner(q)}</div>'


def _quotes_asof(cards):
    asof = next((c.get("asof") for c in cards if c.get("asof")), "")
    return (f'<div class="quotes-asof">시세 기준 {_e(asof)} · Yahoo Finance</div>' if asof else "")


def _render_quotes(cards):
    cards = [c for c in (cards or []) if c]
    if not cards:
        return ""
    return ('<div class="quotes">' + "".join(_quote_card(c) for c in cards) + "</div>") + _quotes_asof(cards)


_SENT_LAB = {"g": "호재", "b": "악재", "n": "중립"}
_EMPTY_NEWS = "수집된 뉴스가 없습니다"


def _nb_row(it, open_=False):
    """기사 한 줄: ● 한글 헤드라인 / 판정 · 매체 · 시각 — 누르면 요약·근거·원문 제목·링크."""
    s = it.get("sent")
    dot = f'<i class="nb-dot {s}" aria-hidden="true"></i>' if s in _SENT_LAB else ""
    lab = f'<em class="{s}">{_SENT_LAB[s]}</em> · ' if s in _SENT_LAB else ""
    pub, _sep, when = (it.get("src") or "").rpartition(" · ")
    if not pub:
        pub, when = when, ""
    if re.fullmatch(r"\d{2}/\d{2} \d{2}:\d{2}", when):        # 보는 시점 기준 'N시간 전'으로 바꿈(tab.js)
        tm = f' · <time data-at="{_e(when)}">{_e(when)}</time>'
    else:
        tm = f" · {_e(when)}" if when else ""
    head = it.get("ko") or it["title"]
    body = "".join([
        f'<p>{_e(it["desc"])}</p>' if it.get("desc") else "",
        f'<span class="nb-why">판정 근거 · {_e(it["why"])}</span>' if it.get("why") else "",
        f'<span class="nb-orig">{_e(it["title"])}' + (f' · 같은 내용 {it["dups"]}곳 더 보도' if it.get("dups") else "")
        + '</span>' if it.get("ko") else "",
        f'<a class="nb-link" href="{_e(it["link"])}" target="_blank" rel="noopener">원문 보기 ↗</a>' if it.get("link") else "",
    ])
    return (f'<div class="nb-row{" open" if open_ else ""}{"" if dot else " nd"}">'
            f'<button type="button" class="nb-rh" aria-expanded="{"true" if open_ else "false"}">{dot}'
            f'<span class="nb-tx"><b>{_e(head)}</b><span class="nb-m">{lab}{_e(pub)}{tm}</span></span></button>'
            f'<div class="nb-body">{body}</div></div>')


def _render_ticker_tabs(pid, quotes, items):
    """주식·코인 뉴스(1안): 시세 카드 = 종목 선택 탭, 아래엔 고른 종목의 뉴스만.

    카드 아래 '악재 2'처럼 판정 요약을 붙이고, 처음엔 악재가 가장 많은 종목(같으면 호재, 그다음 앞 순서)을 고른다.
    판정이 없는 예전 회차는 '뉴스 3'만 붙이고 첫 종목을 고른다. 시세가 없는 종목도 배지만 있는 카드로 둔다."""
    groups: dict[str, list] = {}
    for it in items:
        if it["kind"] == "ticker":
            groups.setdefault(it["label"], []).append(it)
    cards = [c for c in (quotes or []) if c]
    seen = {c.get("ticker") for c in cards}
    cards += [{"ticker": t} for t in groups if t not in seen]
    tagged = any(it.get("sent") for it in items)
    info = {}
    for c in cards:
        t = c.get("ticker")
        g = [it for it in groups.get(t, []) if it.get("sent") != "x"
             and not (it["title"].startswith(_EMPTY_NEWS) and not it.get("desc"))]
        g.sort(key=lambda it: 0 if it.get("sent") in ("g", "b") else 1)      # 호재·악재를 위로
        cnt = {k: sum(1 for it in g if it.get("sent") == k) for k in "gbn"}
        info[t] = (g, cnt)
    order = [c.get("ticker") for c in cards]
    sel = max(order, key=lambda t: (info[t][1]["b"], info[t][1]["g"], -order.index(t))) if order else None

    def flag(t):
        g, cnt = info[t]
        if not g:
            return '<span class="qflag n">뉴스 없음</span>'
        if not tagged:
            return f'<span class="qflag n">뉴스 {len(g)}</span>'
        parts = [f'<span class="qflag {k}">{_SENT_LAB[k]} {cnt[k]}</span>' for k in "bg" if cnt[k]]
        return "".join(parts) or f'<span class="qflag n">중립 {cnt["n"]}</span>'

    out = ['<div class="quotes qtabs" role="tablist" aria-label="종목 선택">']
    for c in cards:
        t = c.get("ticker")
        on = t == sel
        out.append(f'<button type="button" class="qcard qtab{" sel" if on else ""}" role="tab" data-t="{_e(t)}" '
                   f'aria-selected="{"true" if on else "false"}" aria-controls="{pid}-nb-{_e(t)}">'
                   f'{_quote_inner(c)}<span class="qflags">{flag(t)}</span></button>')
    out.append('</div>' + _quotes_asof(cards))
    for c in cards:
        t = c.get("ticker")
        g, _cnt = info[t]
        key = t.split("-")[0]
        ko = _TICKER_KO.get(key.upper(), "") or key
        brief = next((it.get("brief") for it in groups.get(t, []) if it.get("brief")), "")
        rows = "".join(_nb_row(it, i == 0) for i, it in enumerate(g)) or f'<div class="nb-empty">{_EMPTY_NEWS}</div>'
        out.append(f'<div class="nb-pane" id="{pid}-nb-{_e(t)}" role="tabpanel" data-t="{_e(t)}"{"" if t == sel else " hidden"}>'
                   f'<div class="nb-ph"><b>{_e(ko)}</b>' + (f'<span>{_e(brief)}</span>' if brief else "") + '</div>'
                   f'{rows}</div>')
    if tagged:
        out.append('<div class="nb-foot">● 빨강 호재 · 파랑 악재 · 회색 중립 — AI가 기사 내용을 보유자 관점에서 분류 · 투자 판단용 아님</div>')
    return "".join(out)


def _render_part(pid, icon, name, lines, hero=False, quotes=None, prev_sets=None,
                 group_by_ticker=False):
    summary, items, blocks, note = _parse_part(lines)
    h = [f'<section class="part" id="{pid}">',
         f'<div class="part-head"><span class="part-icon">{icon}</span>'
         f'<h2>{_e(name)}</h2></div>']
    if group_by_ticker:                  # 시세 카드가 종목 선택 탭을 겸한다(뉴스는 아래에서 함께 그림)
        quotes_html = ""
    else:
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
    if group_by_ticker:
        h.append(_render_ticker_tabs(pid, quotes, items) if (items or quotes) else "")
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
