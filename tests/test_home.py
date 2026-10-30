"""메인 홈: 히트맵 데이터(treemap.py) + 일정 묶음 + 홈 렌더."""
from datetime import date, datetime

import treemap as TM
from render.home import home_events, render_home
from settings import KST


def test_parse_spark_uses_previous_close():
    j = {"spark": {"result": [
        {"symbol": "GOOGL", "response": [{"meta": {"regularMarketPrice": 283.82, "chartPreviousClose": 324.89,
                                                   "regularMarketTime": 1793304000}}]},
        {"symbol": "BAD", "response": [{"meta": {"regularMarketPrice": 1.0}}]}]}}
    q = TM.parse_spark(j)
    assert round(q["GOOGL"]["chg"], 2) == -12.64 and "BAD" not in q


def test_build_rows_dedups_share_class_and_scales_mcap():
    uni = {"rows": [{"t": "GOOGL", "name": "Alphabet", "px": 100.0, "mcap_nq": 2_000_000, "sector": "커뮤니케이션"},
                    {"t": "GOOG", "name": "Alphabet C", "px": 100.0, "mcap_nq": 2_000_000, "sector": "커뮤니케이션"},
                    {"t": "ASML", "name": "ASML", "px": 50.0, "mcap_nq": 300_000, "sector": ""}]}
    screen = {"rows": [{"t": "GOOGL"}], "miss": ["ASML"]}
    q = {"GOOGL": {"px": 90.0, "chg": -10.0}, "GOOG": {"px": 90.0, "chg": -10.0}, "ASML": {"px": 50.0, "chg": 1.234}}
    rows = TM.build_rows(uni, screen, q)
    assert [r["t"] for r in rows] == ["GOOGL", "ASML"]                  # GOOG(같은 회사) 제외
    assert rows[0]["m"] == 1800.0 and rows[1]["s"] == "기타" and rows[1]["c"] == 1.23


def _ev(dt, name, cur="USD", impact="HIGH", **res):
    return {"dt": dt, "name": name, "cur": cur, "impact": impact, "res": res}


def test_home_events_groups_and_orders():
    now = KST.localize(datetime(2026, 10, 30, 9, 0))
    t = lambda d, h, m=0: KST.localize(datetime(2026, 10, d, h, m))  # noqa: E731
    months = [("2026-10", "", [
        _ev(t(29, 21, 30), "Gross Domestic Product Annualized"),                       # 지난 것
        _ev(t(30, 21, 30), "Core Personal Consumption Expenditures - Price Index (MoM)", cons="0.3%"),
        _ev(t(30, 21, 30), "Core Personal Consumption Expenditures - Price Index (YoY)", cons="3.1%"),
        _ev(t(30, 22, 0), "Something Medium", impact="MEDIUM"),
        _ev(t(31, 12, 0), "BoJ Interest Rate Decision", cur="JPY", prev="1.25%"),
    ])]
    earn = [{"ticker": "AMZN", "date": date(2026, 10, 30)}, {"ticker": "AAPL", "date": date(2026, 11, 3)},
            {"ticker": "PLTR", "date": date(2026, 11, 3)}, {"ticker": "NVDA", "date": date(2026, 11, 18)}]
    ev = home_events(months, earn, now)
    labs = [(r["label"], r["note"]) for r in ev]
    assert labs[0] == ("미국 PCE", "예상 0.3%")                         # 같은 시각·약칭은 한 줄
    assert ("AMZN 실적", "") in labs and ("AAPL·PLTR 실적", "") in labs
    assert all("NVDA" not in r["label"] for r in ev)                    # 7일 밖
    assert not any(r["label"].endswith("GDP") for r in ev)              # 이미 지난 지표


def test_render_home_sections_and_links():
    body = ["💹 경제 PART", "[오늘 한눈에]", "금리가 동결됐다. 둘째 문장.",
            "📈 해외주식 PART", "🧭 [IREN] 자금 우려로 약세",
            "📰 [IREN] t1", "🏷 악재 | h | r | 0", "→ s", "📰 [IREN] t2", "🏷 악재 | h | r | 0", "→ s",
            "📰 [NVDA] t3", "🏷 호재 | h | r | 0", "→ s"]
    from render.parse import _split_sections
    sections = _split_sections("\n".join(body))
    now = KST.localize(datetime(2026, 10, 30, 9, 0))
    h = render_home(sections, {"os": [{"ticker": "IREN", "chg": -8.98}]}, now, [], [],
                    {"os": "tp1", "eco": "tp0"})
    assert h.index('data-t="IREN"') < h.index('data-t="NVDA"')          # 악재 많은 종목 먼저
    assert "자금 우려로 약세" in h and "▼8.98%" in h and 'data-go="tp1"' in h
    assert "금리가 동결됐다." in h and "둘째 문장" not in h and 'data-go="tp0"' in h
    assert 'id="hmTm"' in h and 'id="hmIx"' in h and "다가오는 일정" not in h   # 일정 없으면 카드 생략
