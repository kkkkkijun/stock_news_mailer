"""보고서 보류 사례(2026-10~11) 재발 방지: NVDA 분기·월 오탐, TSLA Non-GAAP, PLTR 어림 매출, HIMS 잘린 JSON,
AMZN·GOOGL·META 경미한 지적 과잉 보류, 재생성 실패 시 기존 게시본 유지, 수동 재시도."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytz

import earnings as E
import report_agents as A
from test_report_agents import FACTS, KO_OK, REPORT, SRC, _Client, _er, _patch, _run


def test_calendar_quarter_uses_middle_month():
    assert E.cal_quarter(2026, 9) == (2026, 3) and E.cal_quarter(2026, 12) == (2026, 4)      # 일반 결산 그대로
    assert E.cal_quarter(2026, 10) == (2026, 3)                                              # NVDA 8~10월 → 3Q
    assert E.cal_quarter(2027, 1) == (2026, 4) and E.cal_quarter(2026, 4) == (2026, 1)
    assert E._earn_cq("26.10") == ("2026-3", "2026 3Q") and E._period_cq("27.01") == ("2026-4", "2026 4Q")


def test_ask_retries_truncated_json_with_bigger_limit():
    seen = []

    def create(**kw):
        seen.append(kw["max_tokens"])
        if len(seen) == 1:
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason="length",
                                                            message=SimpleNamespace(content='{"issues": [{"where": "x'))])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
                                                        message=SimpleNamespace(content='{"issues": []}'))])
    c = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert A._ask(c, "m", "p", 1200) == {"issues": []} and seen == [1200, 2400]


def test_non_gaap_eps_metric_is_not_compared_to_gaap():
    act = {"revenue_musd": 28046, "eps": 0.22}
    assert A._metric_mismatch({"k": "Non-GAAP EPS", "v": "$0.48"}, act) == ""
    assert A._metric_mismatch({"k": "조정 EPS", "v": "$0.48"}, act) == ""
    assert "다름" in A._metric_mismatch({"k": "EPS", "v": "$0.48"}, act)


def test_final_gate_ignores_minor_and_self_admitted_issues():
    out = {"issues": [
        {"where": "a", "problem": "표현이 모호함", "evidence": "Revenues increased 5.4% year-over-year", "severity": "minor"},
        {"where": "b", "problem": "수치와 방향 자체는 맞으나 비교 기준을 더 밝히면 좋음",
         "evidence": "Revenues increased 5.4% year-over-year"},
        {"where": "c", "problem": "원문과 일치.", "evidence": "Revenues increased 5.4% year-over-year", "severity": "error"},
        {"where": "d", "problem": "순손실 방향 반대", "evidence": "Net Loss improved by $18.0 million", "severity": "error"}]}
    found, noise, minor = A.gate_final(out, SRC)
    assert [x["where"] for x in found] == ["d"] and noise == 0 and minor == 3


def test_minor_only_final_check_publishes():
    minor = {"issues": [{"where": "x", "problem": "더 자세히", "evidence": "Revenues increased 5.4%", "severity": "minor"}]}
    r = _run(_Client(s=[FACTS], t=[KO_OK], w=[REPORT], f=[minor]))
    assert r["ok"] is True and "경미한 지적 1건 제외" in r["stages"][-1]["note"]


def test_approximate_revenue_fact_triggers_soft_retry_and_write_failure_goes_back_to_summary():
    approx = json.loads(json.dumps(FACTS))
    approx["facts"][0] = {"id": "F1", "topic": "revenue", "key": True, "text": "Revenue increased 5.4% year-over-year.",
                          "quote": "Revenues increased 5.4% year-over-year"}
    _, _, retry = A.gate_summary(approx, SRC)
    assert retry and all(x.startswith(A.SOFT) for x in retry) and A.hard(retry) == []
    wrong = json.loads(json.dumps(REPORT))
    wrong["metrics"][0]["v"] = "$100.0M"
    ko_approx = json.loads(json.dumps(KO_OK))
    ko_approx["facts"][0]["ko"] = "매출은 전년 대비 5.4% 증가."
    c = _Client(s=[approx, approx, FACTS], t=[ko_approx, KO_OK], w=[wrong, wrong, REPORT], f=[{"issues": []}])
    r = _run(c)
    assert r["ok"] is True and [x["stage"] for x in r["stages"]] == ["요약", "번역", "작성", "요약", "번역", "작성", "최종 점검"]
    assert "이번 분기 매출" in [p for p in c.prompts if "1단계" in p][2]          # 2회차 요약에 작성 지적이 전달됨


def test_actual_not_in_source_is_dropped():
    assert A.verified_actual({"revenue_musd": 109.0, "eps": -0.09}, SRC) == {"revenue_musd": 109.0, "eps": -0.09}
    assert A.verified_actual({"revenue_musd": 999.0, "eps": None}, SRC) == {}


def test_failed_regeneration_keeps_published_report(monkeypatch):
    _patch(monkeypatch)
    bad = {"issues": [{"where": "x", "problem": "EPS 누락", "evidence": "Diluted EPS improved by $0.20", "stage": "작성"}]}
    old = {"ticker": "RDW", "acc": "A1", "gen": E.REPORT_GEN - 1, "model": E.REPORT_MODEL, "headline": "기존 게시본",
           "check": {"ok": True, "by": "agents"}}
    c = _Client(s=[FACTS], t=[KO_OK], w=[REPORT, REPORT], f=[bad, bad])
    rec = E._report_for_ticker("RDW", _er(), {"RDW": old}, c, datetime(2026, 11, 5, tzinfo=pytz.utc))
    assert rec["headline"] == "기존 게시본" and rec["check"]["ok"] is True and rec["gen"] == E.REPORT_GEN


def test_manual_retry_tickers_from_env(monkeypatch):
    monkeypatch.setenv("REPORT_RETRY", "nvda, hims")
    assert E.retry_tickers() == {"NVDA", "HIMS"}


def test_report_status_table_and_warnings():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from datetime import date
    from report_status import status_markdown
    reps = [{"ticker": "NVDA", "date": "2026-11-18", "quarter": "2026 3Q", "attempts": 1, "check": {"ok": True}},
            {"ticker": "HIMS", "date": "2026-11-10", "quarter": "2026 3Q", "attempts": 3,
             "check": {"ok": False, "issues": ["[오류] a|b"]}},
            {"ticker": "META", "date": "2026-08-01", "quarter": "2026 2Q", "check": {"ok": False, "issues": []}}]
    md, warns = status_markdown(reps, date(2026, 11, 18))
    assert "게시 1 / 전체 3" in md and "| NVDA | 2026-11-18 | 2026 3Q | ✅ 게시 |" in md and "a/b" in md
    assert len(warns) == 1 and warns[0].startswith("HIMS")


def test_korean_large_units_match_english_scale():
    import report_check as R
    en = "Produced and delivered our 10 millionth vehicle."
    ko = "누적 1,000만 번째 차량을 생산·인도했다."
    assert R.unsupported_numbers({"bullets": [ko]}, en) == []
    assert R.unsupported_numbers({"bullets": [en]}, ko) == []
    assert R.unsupported_numbers({"bullets": ["누적 2,000만 번째 차량"]}, en) == ["2,000만"]
    assert R.unsupported_numbers({"bullets": ["매출 $1,158억"]}, "revenue of $115.8 billion") == []


def test_english_number_words_match_digits():
    import report_check as R
    en = "Operating cash flow increased 29% to $168.3 billion for the trailing twelve months."
    assert R.unsupported_numbers({"bullets": ["최근 12개월 영업현금흐름은 29% 증가한 $168.3B."]}, en) == []
    assert R.unsupported_numbers({"bullets": ["최근 13개월 영업현금흐름 $168.3B."]}, en) == ["13"]
