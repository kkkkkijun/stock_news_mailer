# -*- coding: utf-8 -*-
"""fundamentals.py의 순수 함수(_pick/_fill_q4/_axes) 단위 테스트. 네트워크 없음.

입력: 없음
출력: 없음(pytest 결과)
실행: pytest tests/test_fundamentals_pure.py
관련: fundamentals.py
"""
from fundamentals import REV, _pick, _fill_q4, _axes


def test_pick_chooses_tag_with_most_recent_end_date():
    # SEC companyfacts 형태: {태그: {"units": {"USD": [{start,end,val}, ...]}}}
    older_tag, newer_tag = REV[0], REV[1]
    gaap = {
        older_tag: {"units": {"USD": [
            {"start": "2022-01-01", "end": "2022-03-31", "val": 100},
            {"start": "2022-04-01", "end": "2022-06-30", "val": 110},
        ]}},
        newer_tag: {"units": {"USD": [
            {"start": "2022-07-01", "end": "2022-09-30", "val": 120},
            {"start": "2022-10-01", "end": "2022-12-31", "val": 130},
        ]}},
    }
    picked = _pick(gaap, REV)
    assert picked == gaap[newer_tag]["units"]["USD"]


def test_fill_q4_derives_q4_from_annual_minus_three_quarters():
    q = {"2023-03-31": 10.0, "2023-06-30": 20.0, "2023-09-30": 30.0}
    ann = {"2023-12-31": ("2023-01-01", 100.0)}
    out = _fill_q4(q, ann)
    assert out["2023-12-31"] == 40.0
    assert out == {"2023-03-31": 10.0, "2023-06-30": 20.0,
                   "2023-09-30": 30.0, "2023-12-31": 40.0}


def _profile(yoy):
    """_axes()가 기대하는 최소 필드를 가진 합성 프로파일(다른 축은 최대한 우호적으로)."""
    return {"rev_yoy": yoy, "opm": 50, "opm_delta": 10,
            "netcash": 100, "fcf": 50, "dilution": 0}


def test_axes_caps_score_at_50_when_yoy_below_12():
    result = _axes(_profile(5))
    assert result["score"] <= 50


def test_axes_caps_score_at_72_when_yoy_below_22():
    result = _axes(_profile(20))
    assert result["score"] <= 72
