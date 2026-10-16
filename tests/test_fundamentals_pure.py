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


# ---- 1단계 신뢰도 수정(2026-10-16): 현금흐름 YTD 차분 · TTM 연속성 · 단기투자 포함 ----
from fundamentals import CAPEX, OCF, _flow_quarters, _liquid_cash, _ttm  # noqa: E402


def _usd(rows):
    return {"units": {"USD": [{"start": s, "end": e, "val": v} for s, e, v in rows]}}


def test_flow_quarters_derives_quarters_from_ytd_cumulative():
    # 10-Q 현금흐름은 연초 누적: 3개월 10, 6개월 25, 9개월 45, 연간 70 → 분기 10/15/20/25
    g = {OCF[0]: _usd([("2025-01-01", "2025-03-31", 10), ("2025-01-01", "2025-06-30", 25),
                       ("2025-01-01", "2025-09-30", 45), ("2025-01-01", "2025-12-31", 70)])}
    assert _flow_quarters(g, OCF) == {"2025-03-31": 10, "2025-06-30": 15,
                                      "2025-09-30": 20, "2025-12-31": 25}


def test_flow_quarters_ignores_trailing_twelve_month_facts():
    # AMZN처럼 TTM 값이 같은 start로 섞여도 분기로 오인하지 않는다
    g = {OCF[0]: _usd([("2025-07-01", "2025-09-30", 30), ("2025-07-01", "2026-06-30", 160)])}
    assert _flow_quarters(g, OCF) == {"2025-09-30": 30}


def test_capex_picks_the_tag_with_latest_data():
    old_tag, new_tag = CAPEX[0], CAPEX[1]
    g = {old_tag: _usd([("2016-01-01", "2016-03-31", 1)]),
         new_tag: _usd([("2026-01-01", "2026-03-31", 9)])}
    assert _flow_quarters(g, CAPEX) == {"2026-03-31": 9}


def test_ttm_requires_four_consecutive_quarters():
    q = {"2025-03-31": 1, "2025-06-30": 2, "2025-09-30": 3, "2025-12-31": 4}
    assert _ttm(q) == 10
    gappy = {"2022-03-31": 1, "2023-03-31": 2, "2024-03-31": 3, "2025-03-31": 4}  # 매년 1분기만
    assert _ttm(gappy) is None


def test_liquid_cash_adds_same_date_short_term_investments_only():
    cash = {"2026-06-30": 100}
    assert _liquid_cash(cash, {}, [{"2026-06-30": 50}]) == (150, True)
    assert _liquid_cash(cash, {}, [{"2025-10-26": 50}]) == (100, False)      # 끊긴 태그는 섞지 않음
    assert _liquid_cash(cash, {"2026-06-30": 180}, [{"2026-06-30": 80}]) == (180, True)  # 합산 태그 우선


def test_rev_quarters_prefers_tag_with_latest_quarterly_data_over_annual_only():
    # IREN 사례: Revenues는 연간값만(분기 없음), 고객계약 매출에 분기값 → 분기 시계열은 고객계약 매출
    from fundamentals import _rev_quarters
    g = {REV[0]: _usd([("2025-07-01", "2026-06-30", 700)]),
         REV[1]: _usd([("2026-01-01", "2026-03-31", 145), ("2026-04-01", "2026-06-30", 137)])}
    assert max(_rev_quarters(g)) == "2026-06-30" and _rev_quarters(g)["2026-06-30"] == 137


def test_rev_quarters_tie_goes_to_total_revenues():
    from fundamentals import _rev_quarters
    g = {REV[0]: _usd([("2026-04-01", "2026-06-30", 120)]), REV[1]: _usd([("2026-04-01", "2026-06-30", 100)])}
    assert _rev_quarters(g)["2026-06-30"] == 120
