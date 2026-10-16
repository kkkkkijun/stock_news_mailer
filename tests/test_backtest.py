"""점수 검증(backtest.py) 순수 함수 + 화면 렌더."""
from datetime import date

import backtest as B
import fundamentals as F
from render.growth import _render_backtest


def test_eval_dates_only_with_known_forward_return():
    ds = B.eval_dates(date(2026, 10, 16))
    assert ds[0] == date(2023, 2, 15) and ds[-1] == date(2026, 5, 15)   # 8/15+91일은 아직 미래
    assert all(d.month in (2, 5, 8, 11) and d.day == 15 for d in ds)


def test_filter_facts_drops_later_filings():
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"end": "2024-03-31", "val": 1, "filed": "2024-05-01"},
                                       {"end": "2024-06-30", "val": 2, "filed": "2024-08-01"}]}},
        "Later": {"units": {"USD": [{"end": "2024-06-30", "val": 3, "filed": "2024-08-01"}]}}}}}
    g = B.filter_facts(facts, date(2024, 5, 15))["facts"]["us-gaap"]
    assert [r["val"] for r in g["Revenues"]["units"]["USD"]] == [1]
    assert "Later" not in g                       # 그 시점에 값이 하나도 없던 태그는 빠짐


def test_close_at_uses_last_trading_day_before():
    s = [("2024-05-13", 10.0), ("2024-05-14", 11.0), ("2024-05-16", 12.0)]
    assert B.close_at(s, date(2024, 5, 15)) == 11.0
    assert B.close_at(s, date(2024, 5, 1)) is None


def test_spearman_handles_ties_and_direction():
    assert B.spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]) == 1.0
    assert B.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == -1.0
    assert B.spearman([1, 1, 2, 3, 4], [1, 2, 3, 4, 5]) > 0.9
    assert B.spearman([1, 2], [1, 2]) is None     # 표본 부족


def _obs(d, t, score, r3, ax=50):
    return {"d": d, "t": t, "score": score, "r3": r3,
            "ax": {"growth": score, "path": ax, "balance": ax, "shareholder": 100 - score}}


def test_summarize_halves_and_axes():
    obs = [_obs("2025-05-15", t, s, r) for t, s, r in
           (("A", 90, 20), ("B", 80, 10), ("C", 30, -5), ("D", 20, 0))]
    obs += [_obs("2025-08-15", t, s, r) for t, s, r in
            (("A", 90, -10), ("B", 80, 0), ("C", 30, 5), ("D", 20, 15))]
    r = B.summarize(obs)
    p0 = r["per"][0]
    assert (p0["hi3"], p0["lo3"]) == (15.0, -2.5) and p0["top"][:2] == ["A", "B"]
    assert r["h3"] == {"dates": 2, "hi": 5.0, "lo": round((-2.5 + 10) / 2, 1), "wins": 1, "ic": None}
    assert r["axes"]["growth"]["wins"] == 1 and r["axes"]["shareholder"]["spread"] == -r["axes"]["growth"]["spread"]
    assert "h6" not in r                          # 6개월 수익률이 없으면 요약도 없음


def test_year_ago_leap_day():
    assert F._year_ago(date(2024, 2, 29)) == date(2023, 2, 28)
    assert F._yoy(["2023-02-28"], {"2023-02-28": 5}, "2024-02-29") == 5


def test_render_backtest_verdict_and_empty():
    bt = {"built": "2026-10-16", "universe": 4, "n": 8, "first": "2025-05-15", "last": "2025-08-15",
          "skipped": [], **B.summarize([_obs("2025-05-15", t, s, r) for t, s, r in
                                        (("A", 90, -20), ("B", 80, -10), ("C", 30, 5), ("D", 20, 0))])}
    h = _render_backtest(bt)
    assert 'id="grBt"' in h and "맞히지 못했습니다" in h and "그날까지 SEC에 공시된 재무만" in h
    assert "<svg" in h and "시점별 자세히" in h
    assert "아직 없습니다" in _render_backtest({})


def test_universe_note_counts_from_data():
    from render.growth import _gr_universe_note
    uni = {"rows": [{"t": t} for t in ("NVDA", "GOOGL", "GOOG", "ASML", "MSFT")]}
    scr = {"rows": [{"t": t} for t in ("NVDA", "GOOGL", "MSFT")], "miss": ["ASML"]}
    funds = [{"ticker": t} for t in ("NVDA", "GOOGL", "MSFT", "HIMS")]
    h = _gr_universe_note(funds, scr, uni)
    assert "분석 대상 4종목" in h and "목록 5개" in h and "(GOOG)" in h and "4개 회사" in h
    assert "1개 제외 → 3개" in h and "(ASML)" in h and "1개 추가 → 4개" in h and "(HIMS)" in h
    assert _gr_universe_note(funds, {}, uni) == ""
