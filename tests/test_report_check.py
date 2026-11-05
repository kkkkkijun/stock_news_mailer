"""실적 보고서 신뢰성 장치: 발표 후 주가 시점 · 수치 대조 · 예상 대비 판정 · 방향 모순 · 재생성 파이프라인."""
from datetime import date, datetime

import pytz

import earnings as E
import report_check as R

NY = pytz.timezone("America/New_York")
PRESS = ("Redwire Reports Third Quarter 2026 Financial Results, Achieves Record Gross Margins. "
         "• Revenues increased 5.4% year-over-year to $109.0 million for the third quarter of 2026. "
         "• Year-over-year improvement in gross margins to a record 32.3% compared to 16.3%. "
         "• Net Loss improved by $18.0 million year-over-year to $(23.2) million. "
         "• Diluted EPS improved by $0.20 per share year-over-year to $(0.09) per share. "
         "• Adjusted EBITDA decreased by $2.7 million year-over-year to $(5.3) million. "
         "record Backlog of $619.7 million, a nearly 75% increase year-over-year. "
         "The following table presents our contracted backlog. "
         "Diluted EPS of $3.83 would have increased by $3.57 to $7.40.")


def _ny(*a):
    return NY.localize(datetime(*a))


def test_reaction_after_close_in_progress_uses_post_release_price():
    daily = [(date(2026, 11, 3), 8.12), (date(2026, 11, 4), 7.72)]           # 11/4 하락은 발표 '전'
    intra = [(_ny(2026, 11, 4, 15, 55), 7.70), (_ny(2026, 11, 4, 16, 25), 7.13), (_ny(2026, 11, 4, 19, 55), 7.50)]
    r = R.release_reaction(daily, intra, _ny(2026, 11, 4, 16, 21), _ny(2026, 11, 5, 3, 0))
    assert r["final"] is False and r["base"] == 7.72 and r["last"] == 7.50
    assert r["text"].startswith("발표 직후 시간외 -2.8%") and "진행 중" in r["text"]


def test_reaction_after_close_final_uses_next_session_close():
    daily = [(date(2026, 11, 4), 7.72), (date(2026, 11, 5), 7.40)]
    r = R.release_reaction(daily, [], _ny(2026, 11, 4, 16, 21), _ny(2026, 11, 5, 17, 0))
    assert r["final"] and r["label"] == "발표 다음 거래일(11/5) 종가" and r["pct"] == round((7.40 / 7.72 - 1) * 100, 2)


def test_reaction_premarket_release_uses_same_day_close():
    daily = [(date(2026, 10, 29), 100.0), (date(2026, 10, 30), 90.0)]
    r = R.release_reaction(daily, [], _ny(2026, 10, 30, 7, 0), _ny(2026, 10, 31, 9, 0))
    assert r["label"] == "발표 당일(10/30) 종가" and r["pct"] == -10.0


def test_numbers_and_units():
    rep = {"headline": "", "metrics": [{"k": "매출", "v": "$109.0M"}, {"k": "x", "v": "$2.36B"}],
           "bullets": ["순손실 $23.2M, 2026년 3분기", "가짜 수치 $77.7M"]}
    bad = R.unsupported_numbers(rep, "revenue $109.0 million, net loss $(23.2) million, 2,360 million")
    assert bad == ["77.7M"]                                     # 연도·분기·B↔M 환산은 통과


def test_consensus_compare_and_verdict():
    cmp = R.consensus_compare({"revenue_musd": 109.0, "eps": -0.09}, "$126.56M", "$-0.09")
    assert cmp["rev"]["pct"] == -13.9 and cmp["eps"]["diff"] == 0.0
    assert R.verdict(cmp) == "miss"
    assert "예상 $126.6M (-13.9%)" in R.compare_text(cmp) and "(부합)" in R.compare_text(cmp)
    assert R.verdict(R.consensus_compare({"revenue_musd": 130, "eps": 0.1}, "$126.56M", "$0.05")) == "beat"
    assert R.verdict({}) == ""


def test_direction_conflicts_catches_reversed_loss_only():
    bad = {"headline": "레드와이어, EPS 개선에도 매출 하회로 주가 하락",
           "metrics": [{"k": "순손실", "v": "$-23.2M", "dir": "down"}, {"k": "EPS", "v": "$-0.09", "dir": "up"}],
           "bullets": ["순손실이 $23.2M로 증가하여 우려.", "백로그는 $619.7M으로 전년 대비 75% 증가."]}
    c = R.direction_conflicts(bad, PRESS)
    assert any("순손실 방향 반대" in x for x in c) and any("순손실 지표 화살표" in x for x in c)
    assert not any("매출" in x or "백로그" in x or "EPS" in x for x in c)   # 예상 하회·contracted·would have는 무시
    good = {"headline": "", "metrics": [{"k": "순손실", "v": "$-23.2M", "dir": "up"}],
            "bullets": ["순손실 $23.2M로 전년보다 $18.0M 축소.", "조정 EBITDA $-5.3M로 $2.7M 악화."]}
    assert R.direction_conflicts(good, PRESS) == []


def test_cached_report_refreshes_unfinished_move(monkeypatch):
    old = {"ticker": "RDW", "acc": "A1", "gen": E.REPORT_GEN, "accept": "2026-11-04T21:21:19.000Z",
           "move": {"final": False, "text": "진행 중"}}
    monkeypatch.setattr(E, "_recent_press", lambda t, now, ex: None)
    monkeypatch.setattr(E, "_release_move", lambda t, a: {"final": True, "text": "발표 다음 거래일(11/5) 종가 -4.1%"})
    er = {"detail": {"cur": {"period": "26.09"}, "prev": {}, "quarters": []}}
    rec = E._report_for_ticker("RDW", er, {"RDW": old}, None, datetime(2026, 11, 6, tzinfo=pytz.utc))
    assert rec["move"]["final"] is True and "종가" in rec["move"]["text"]


def test_segment_metric_not_compared_with_total():
    press = "Revenue was $92.3 billion and increased 19%. XBOX content and services revenue decreased 2%."
    rep = {"headline": "", "metrics": [], "bullets": ["XBOX 콘텐츠 및 서비스 매출은 2% 감소", "총 매출 $92.3B로 19% 감소"]}
    c = R.direction_conflicts(rep, press)
    assert len(c) == 1 and "총 매출" in c[0]


def test_consensus_uses_reported_quarter_when_yahoo_already_updated():
    # 회계연도 어긋난 종목(AAPL): cur는 다음 분기 예상인데 period가 같게 찍힘 → prev에 이번 실제치가 있으면 lag 아님
    cur = {"period": "26.09", "eps": "$2.90", "rev": "$155.57B"}
    prev = {"period": "26.09", "eps_act": "$2.10", "eps_est": "$1.99"}
    rq = [{"cq": "2026-3", "label": "2026 3Q", "reported": True}]
    assert E._resolve_report_quarter(cur, rq, "2026-11-03", prev) == ("2026-3", "2026 3Q", False)
    # 발표 직후 Yahoo 미반영(RDW 11/5 전): prev가 직전 분기(6월말, 128일 전) → lag, cur 예상치 사용
    cur2, prev2 = {"period": "26.09", "eps": "$-0.09", "rev": "$126.56M"}, {"period": "26.06", "eps_act": "$-0.11"}
    assert E._resolve_report_quarter(cur2, rq, "2026-11-05", prev2)[2] is True


def test_manual_report_is_not_regenerated(monkeypatch):
    monkeypatch.setattr(E, "_sec_8k_press", lambda t: {"acc": "A1", "accept": "2026-11-04T21:21:19.000Z", "text": "x", "url": "u"})
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    now = datetime(2026, 11, 6, tzinfo=pytz.utc)
    manual = {"RDW": {"acc": "A1", "gen": 2, "check": {"by": "manual"}}}
    assert E._recent_press("RDW", now, manual) is None
    stale = {"RDW": {"acc": "A1", "gen": 2, "check": {"by": "auto"}}}
    assert E._recent_press("RDW", now, stale) is not None
