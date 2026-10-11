# -*- coding: utf-8 -*-
"""일정 탭 월간 캘린더(경제지표 + 기업실적 통합) 렌더링.

입력: 월별 경제지표(_load_econ_events), 실적 예정(_load_earnings), 8-K 실적 보고서(_load_reports)
출력: 월 그리드 HTML + 날짜별 상세(기존 지표 행·실적 행·보고서 카드). 동작은 sched.js
규칙: 칸에는 높음 지표 '계열 약칭'을 항상 표시, 중간·낮음은 필터 칩을 켠 경우에만(CSS 클래스 s-med/s-low).
관련: render/schedule.py(_econ_row·_econ_short), render/earnings.py(_upcoming_row·_report_card_html)
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from render.common import _e, _text_on, _ticker_color
from render.config import _WD_KO
from render.earnings import _report_card_html, _upcoming_row
from render.schedule import _econ_row, _econ_short

_CAL = calendar.Calendar(firstweekday=6)       # 일요일 시작(한국 달력 관례)
_DOW_HEAD = ["일", "월", "화", "수", "목", "금", "토"]


def _empty_day() -> dict[str, list]:
    return {"econ": [], "earn": [], "rep": []}


def _bucket_days(months: list, earnings: list[dict[str, Any]],
                 reports: list[dict[str, Any]]) -> dict[date, dict[str, list]]:
    """날짜 → {econ:[지표], earn:[실적 예정], rep:[8-K 보고서]}.

    같은 종목·같은 날짜에 예정과 보고서가 모두 있으면 보고서만 남긴다(발표 완료)."""
    days: dict[date, dict[str, list]] = defaultdict(_empty_day)
    for _ym, _label, evs in months:
        for e in evs:
            days[e["dt"].date()]["econ"].append(e)
    rep_keys = set()
    for r in reports:
        try:
            d = date.fromisoformat(r.get("date", ""))
        except (TypeError, ValueError):
            continue
        days[d]["rep"].append(r)
        rep_keys.add((r.get("ticker"), d))
    for e in earnings:
        if e.get("date") and (e["ticker"], e["date"]) not in rep_keys:
            days[e["date"]]["earn"].append(e)
    return days


def _tk_chip(ticker: str) -> str:
    t = (ticker or "").split("-")[0]
    bg = _ticker_color(t)
    return f'<span class="cal-tk" style="background:{bg};color:{_text_on(bg)}">{_e(t)}</span>'


def _cell(d: date, ym: str, info: dict[str, list] | None, today: date) -> str:
    """캘린더 칸 1개. 다른 달 날짜는 비활성 칸."""
    cls = ["cal-c"]
    if d.weekday() == 6:
        cls.append("sun")
    elif d.weekday() == 5:
        cls.append("sat")
    if d.strftime("%Y-%m") != ym:
        return f'<div class="{" ".join(cls + ["out"])}"><span class="cal-dn">{d.day}</span></div>'
    if d < today:
        cls.append("past")
    if d == today:
        cls.append("today")
    inner = [f'<span class="cal-dn">{d.day}</span>']
    if info:
        fams: list[str] = []
        for e in info["econ"]:
            if e["impact"] == "HIGH":
                f = _econ_short(e["name"])
                if f not in fams:
                    fams.append(f)
        for i, f in enumerate(fams[:2]):
            inner.append(f'<span class="lab hi{" h2" if i else ""}">{_e(f)}</span>')
        if len(fams) > 1:   # 모바일은 1개만 보이므로 '+N'도 두 벌(폭별 CSS로 하나만 노출)
            inner.append(f'<span class="lab-more mob">+{len(fams) - 1}</span>')
        if len(fams) > 2:
            inner.append(f'<span class="lab-more dsk">+{len(fams) - 2}</span>')
        n_md = sum(1 for e in info["econ"] if e["impact"] == "MEDIUM")
        n_lo = sum(1 for e in info["econ"] if e["impact"] == "LOW")
        if n_md:
            inner.append(f'<span class="lab md">중간 {n_md}</span>')
        if n_lo:
            inner.append(f'<span class="lab lo">낮음 {n_lo}</span>')
        tks = [r.get("ticker") for r in info["rep"]] + [e["ticker"] for e in info["earn"]]
        if tks:
            chips = "".join(_tk_chip(t) for t in tks[:3])
            more = f'<span class="lab-more">+{len(tks) - 3}</span>' if len(tks) > 3 else ""
            inner.append(f'<span class="cal-tks">{chips}{more}</span>')
    return (f'<button type="button" class="{" ".join(cls)}" data-d="{d.isoformat()}">'
            + "".join(inner) + '</button>')


def _detail(d: date, info: dict[str, list], now: datetime) -> str:
    """선택한 날짜의 상세: 헤더(건수) → 실적(보고서 카드/예정 행) → 지표 행(시간순)."""
    n = {k: sum(1 for e in info["econ"] if e["impact"] == k) for k in ("HIGH", "MEDIUM", "LOW")}
    n_earn = len(info["earn"]) + len(info["rep"])
    cnt = "".join(
        f'<span class="{c}">{t} {v}</span>'
        for c, t, v in (("n-hi", "높음", n["HIGH"]), ("n-md", "중간", n["MEDIUM"]),
                        ("n-lo", "낮음", n["LOW"]), ("n-er", "실적", n_earn)) if v)
    out = [f'<div class="cal-det" data-d="{d.isoformat()}" hidden>'
           f'<div class="cal-dh">{d.month}월 {d.day}일 ({_WD_KO[d.weekday()]})'
           f'<span class="cal-cnt">{cnt}</span></div>']
    out += [_report_card_html(r) for r in info["rep"]]
    out += [_upcoming_row(e, now) for e in info["earn"]]
    out += [_econ_row(e) for e in sorted(info["econ"], key=lambda e: e["dt"])]
    out.append('</div>')
    return "".join(out)


def _default_ym(yms: list[str], today: date) -> str:
    cur = today.strftime("%Y-%m")
    return cur if cur in yms else yms[0]


def _render_calendar(months: list, earnings: list[dict[str, Any]],
                     reports: list[dict[str, Any]], now: datetime) -> str:
    """months: [[ym, label, [events]], ...] 오름차순. 경제지표가 없는 달은 그리지 않는다."""
    if not months:
        return ""
    today = now.date()
    days = _bucket_days(months, earnings, reports)
    yms = [m[0] for m in months]
    default = _default_ym(yms, today)
    out = [f'<div class="sched cal s-high" data-today="{today.isoformat()}">'
           '<div class="cal-bar">'
           '<button type="button" class="cal-nv" data-dir="-1" aria-label="이전 달">‹</button>'
           '<b class="cal-title"></b>'
           '<button type="button" class="cal-nv" data-dir="1" aria-label="다음 달">›</button>'
           '<span class="cal-sp"></span>'
           '<div class="imp-filter">'
           '<span class="imp-chip on fixed" title="높음 지표는 항상 표시">'
           '<i style="background:#e5484d"></i>높음</span>'
           '<button type="button" class="imp-chip" data-k="med">'
           '<i style="background:#f59e0b"></i>중간</button>'
           '<button type="button" class="imp-chip" data-k="low">'
           '<i style="background:#94a3b8"></i>낮음</button>'
           '</div></div>'
           '<div class="cal-dow">'
           + "".join(f'<span class="{"sun" if i == 0 else "sat" if i == 6 else ""}">{w}</span>'
                     for i, w in enumerate(_DOW_HEAD))
           + '</div><div class="cal-months">']
    for ym, label, _evs in months:
        y, m = int(ym[:4]), int(ym[5:7])
        hide = "" if ym == default else ' style="display:none"'
        out.append(f'<div class="cal-month" data-ym="{ym}" data-label="{_e(label)}"{hide}>'
                   '<div class="cal-grid">')
        for week in _CAL.monthdatescalendar(y, m):
            out += [_cell(d, ym, days.get(d), today) for d in week]
        out.append('</div></div>')
    out.append('</div><div class="cal-dets">')
    in_range = set(yms)
    for d in sorted(days):
        if d.strftime("%Y-%m") in in_range:
            out.append(_detail(d, days[d], now))
    out.append('<div class="cal-empty" hidden><b></b><span>표시할 일정이 없습니다.</span>'
               '<em>중간·낮음 지표는 위 필터를 켜면 보입니다.</em></div>')
    out.append('</div><div class="sched-tz2">시간 기준 KST · 데이터 FXStreet · Yahoo Finance · '
               'SEC EDGAR · ▲상회/▼하회 = 예상치 대비 숫자 방향</div></div>')
    return "".join(out)
