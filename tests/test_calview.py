# -*- coding: utf-8 -*-
"""일정 캘린더(render/calview.py)·지표 약칭(render/schedule._econ_short) 테스트(네트워크 없음).

입력: 없음
출력: 없음(assert)
실행: pytest -q tests/test_calview.py
관련: render/calview.py, render/schedule.py
"""
from datetime import date, datetime

from render.calview import _bucket_days, _cell, _render_calendar
from render.config import KST
from render.schedule import _econ_short

TODAY = date(2026, 10, 12)


def _ev(day, name, imp="HIGH"):
    return {"dt": datetime(2026, 10, day, 21, 30, tzinfo=KST), "name": name,
            "impact": imp, "cur": "USD", "past": day < TODAY.day, "res": None}


def test_econ_short_groups_variants_into_one_family():
    assert _econ_short("Consumer Price Index (MoM)") == "CPI"
    assert _econ_short("Consumer Price Index ex Food & Energy (YoY)") == "CPI"
    assert _econ_short("Tokyo Consumer Price Index (YoY)") == "도쿄CPI"
    assert _econ_short("Fed Interest Rate Decision") == "FOMC"
    assert _econ_short("FOMC Minutes") == "FOMC의사록"
    assert _econ_short("Some Unknown Index") == "Some Unknown Index"


def test_bucket_days_prefers_report_over_upcoming_same_ticker_same_day():
    months = [["2026-10", "2026년 10월", [_ev(14, "Retail Sales (MoM)")]]]
    earn = [{"ticker": "TSLA", "date": date(2026, 10, 22)},
            {"ticker": "MSFT", "date": date(2026, 10, 29)}]
    reps = [{"ticker": "TSLA", "date": "2026-10-22"}, {"ticker": "X", "date": "bad"}]
    days = _bucket_days(months, earn, reps)
    assert [e["name"] for e in days[date(2026, 10, 14)]["econ"]] == ["Retail Sales (MoM)"]
    assert days[date(2026, 10, 22)]["earn"] == []
    assert [r["ticker"] for r in days[date(2026, 10, 22)]["rep"]] == ["TSLA"]
    assert [e["ticker"] for e in days[date(2026, 10, 29)]["earn"]] == ["MSFT"]


def test_cell_shows_high_families_once_and_hides_medium_by_class():
    info = {"econ": [_ev(14, "Consumer Price Index (MoM)"), _ev(14, "Consumer Price Index (YoY)"),
                     _ev(14, "Retail Sales (MoM)"), _ev(14, "Nonfarm Payrolls"),
                     _ev(14, "IMF Meeting", "MEDIUM")],
            "earn": [], "rep": []}
    html = _cell(date(2026, 10, 14), "2026-10", info, TODAY)
    assert html.count('class="lab hi') == 2          # CPI·소매판매 (3번째 계열은 +1)
    assert ">CPI<" in html and ">소매판매<" in html
    assert 'lab-more dsk">+1<' in html and 'lab-more mob">+2<' in html
    assert 'class="lab md">중간 1<' in html           # 표시 여부는 CSS(s-med)가 결정
    assert 'data-d="2026-10-14"' in html


def test_cell_outside_month_is_inert():
    html = _cell(date(2026, 9, 30), "2026-10", None, TODAY)
    assert "data-d" not in html and "out" in html


def test_render_calendar_defaults_to_current_month_and_only_details_in_range():
    months = [["2026-09", "2026년 9월", [_ev(1, "ISM Services PMI")]],
              ["2026-10", "2026년 10월", [_ev(14, "Consumer Price Index (MoM)")]]]
    months[0][2][0]["dt"] = datetime(2026, 9, 3, 23, 0, tzinfo=KST)
    earn = [{"ticker": "NVDA", "name": "엔비디아", "date": date(2027, 2, 25), "detail": {}}]
    html = _render_calendar(months, earn, [], datetime(2026, 10, 12, 9, tzinfo=KST))
    assert 'data-ym="2026-09" data-label="2026년 9월" style="display:none"' in html
    assert 'data-ym="2026-10" data-label="2026년 10월">' in html
    assert 'class="cal-det" data-d="2026-10-14"' in html
    assert 'data-d="2027-02-25"' not in html          # 그려진 달 밖의 실적은 상세도 없음
    assert 'class="cal-c today" data-d="2026-10-12"' in html


def test_us_holidays_merge_csv_names_with_nyse_status():
    from render.calview import _us_holidays
    h = _us_holidays({date(2026, 10, 12): "Columbus Day", date(2026, 11, 26): "Thanksgiving Day"})
    assert h[date(2026, 10, 12)] == {"name": "콜럼버스의 날", "status": "open"}
    assert h[date(2026, 11, 26)]["status"] == "closed"
    assert h[date(2026, 11, 27)] == {"name": "추수감사절 다음 날", "status": "early"}  # NYSE표에만 있음


def test_hol_note_converts_early_close_to_kst():
    from render.calview import _hol_note
    note = _hol_note(date(2026, 11, 27), {"name": "x", "status": "early"})
    assert note == "미국 증시 조기 폐장 · 13:00 ET (한국시간 다음 날 03:00)"   # EST(UTC-5)
    assert _hol_note(date(2026, 10, 12), {"name": "x", "status": "open"}) == "미국 증시 정상 개장"


def test_holiday_cell_and_detail_render_status():
    from render.calview import _detail
    info = {"econ": [], "earn": [], "rep": [], "hol": {"name": "추수감사절", "status": "closed"}}
    cell = _cell(date(2026, 11, 26), "2026-11", info, TODAY)
    assert 'class="t-dsk">휴장<' in cell and 'hol-tag closed' in cell and "hol-closed" in cell and "추수감사절" in cell
    det = _detail(date(2026, 11, 26), info, datetime(2026, 10, 12, tzinfo=KST))
    assert 'class="hol-row closed"' in det and "미국 증시 휴장" in det
