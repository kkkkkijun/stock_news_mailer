# -*- coding: utf-8 -*-
"""render/common.py 순수 헬퍼 테스트(네트워크 호출 없음).

입력: 없음
출력: 없음(assert)
실행: pytest -q tests/test_common.py
관련: render/common.py, render/config.py(TICKER_COLORS)
"""
from render.common import _text_on, _ticker_color
from render.config import TICKER_COLORS


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
