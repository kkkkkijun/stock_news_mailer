# -*- coding: utf-8 -*-
"""성장주 가격 지표(render/growth._valuation)·점수 이력(fundamentals.update_score_history) 테스트.

입력: 없음
출력: 없음(assert)
실행: pytest -q tests/test_growth_valuation.py
관련: render/growth.py, fundamentals.py
"""
import json

from fundamentals import update_score_history
from render.growth import _gr_delta, _valuation


def _f(tk, shares, revs, netcash=0, yoy=20.0, fcf=100.0):
    return {"ticker": tk, "shares": shares, "netcash": netcash, "rev_yoy": yoy, "fcf": fcf,
            "series": {"rev": [{"v": v} for v in revs]}}


def test_valuation_computes_ev_sales_and_growth_adjusted_rank():
    funds = [_f("A", 10, [25, 25, 25, 25], netcash=100, yoy=50),   # 시총1000 EV900 EV/S 9 → 0.18
             _f("B", 10, [25, 25, 25, 25], netcash=0, yoy=10),     # EV/S 10 → 1.0
             _f("C", 10, [25, 25, 25, 25], yoy=-5)]                # 성장 음수 → 순위 제외
    v = _valuation(funds, {"A": 100, "B": 100, "C": 100})
    assert round(v["A"]["evs"], 2) == 9.0 and round(v["A"]["gadj"], 2) == 0.18
    assert v["A"]["rank"] == 1 and v["B"]["rank"] == 2 and v["B"]["label"] == "비쌈"
    assert v["C"]["gadj"] is None and "rank" not in v["C"]
    assert round(v["A"]["pfcf"]) == 10                              # 1000 / 100


def test_valuation_skips_missing_price_or_shares():
    v = _valuation([_f("A", None, [1, 1, 1, 1]), _f("B", 10, [1, 1, 1])], {"A": 10, "B": 10})
    assert v == {}


def test_score_history_appends_only_on_change_and_keeps_one_per_day(tmp_path):
    p = tmp_path / "h.json"
    update_score_history([{"ticker": "A", "cq": "2026-2", "score": 60}], "2026-10-15", str(p))
    update_score_history([{"ticker": "A", "cq": "2026-2", "score": 60}], "2026-10-16", str(p))  # 변화 없음
    update_score_history([{"ticker": "A", "cq": "2026-2", "score": 64}], "2026-10-16", str(p))
    update_score_history([{"ticker": "A", "cq": "2026-2", "score": 66}], "2026-10-16", str(p))  # 같은 날 덮어씀
    rows = json.loads(p.read_text(encoding="utf-8"))["A"]
    assert [(r["date"], r["score"]) for r in rows] == [("2026-10-15", 60), ("2026-10-16", 66)]
    assert "▲6" in _gr_delta(rows)
    assert "–" in _gr_delta(rows[:1])
