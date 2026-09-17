# -*- coding: utf-8 -*-
"""render/common.py 순수 헬퍼 테스트(네트워크 호출 없음).

입력: 없음
출력: 없음(assert)
실행: pytest -q tests/test_common.py
관련: render/common.py, render/config.py(TICKER_COLORS)
"""
from datetime import date, datetime

from render import common
from render.common import _event_ddays, _text_on, _ticker_color
from render.config import TICKER_COLORS


def _events(monkeypatch, *days):
    monkeypatch.setattr(common, "EVENT_DDAYS", [(f"ev{i}", d) for i, d in enumerate(days)])


def test_event_ddays_counts_down_and_formats_date(monkeypatch):
    _events(monkeypatch, date(2026, 11, 3))
    assert _event_ddays(datetime(2026, 9, 18, 7)) == [("ev0", "D-46", "11.03(화)")]


def test_event_ddays_shows_dday_on_the_day_and_hides_after(monkeypatch):
    _events(monkeypatch, date(2026, 11, 3))
    assert _event_ddays(datetime(2026, 11, 3, 23))[0][1] == "D-DAY"
    assert _event_ddays(datetime(2026, 11, 4, 0)) == []


def test_event_ddays_keeps_config_order_and_skips_past(monkeypatch):
    _events(monkeypatch, date(2026, 12, 1), date(2026, 1, 1), date(2026, 10, 1))
    assert [e[0] for e in _event_ddays(datetime(2026, 9, 18))] == ["ev0", "ev2"]


def test_ticker_color_known_ticker_uses_brand_color():
    assert _ticker_color("NVDA") == TICKER_COLORS["NVDA"]


def test_ticker_color_unknown_ticker_is_deterministic_hsl():
    c1 = _ticker_color("ZZZQQQ")
    c2 = _ticker_color("ZZZQQQ")
    assert c1 == c2
    assert c1.startswith("hsl(")

    c3 = _ticker_color("QQQZZZ")
    assert c3 != c1


def test_ticker_color_strips_suffix_after_dash():
    assert _ticker_color("BTC-USD") == _ticker_color("BTC")


def test_text_on_white_is_dark_black_is_white():
    dark = _text_on("#FFFFFF")
    light = _text_on("#000000")
    assert dark == "#0f1b2d"
    assert light == "#fff"
    assert dark != light
