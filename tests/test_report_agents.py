"""실적 보고서 4단계 에이전트(요약→번역→작성→최종 점검): 단계별 코드 관문, 재시도·되돌리기, 보류 시 미게시."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytz

import earnings as E
import report_agents as A
from render.earnings import _report_card_html

SRC = ("Redwire Reports Third Quarter 2026 Financial Results, Achieves Record Gross Margins. "
       "Revenues increased 5.4% year-over-year to $109.0 million for the third quarter of 2026. "
       "Year-over-year improvement in gross margins to a record 32.3% compared to 16.3%. "
       "Net Loss improved by $18.0 million year-over-year to $(23.2) million. "
       "Diluted EPS improved by $0.20 per share year-over-year to $(0.09) per share. "
       "Redwire reaffirms full year 2026 revenues of $450 million to $500 million.")

FACTS = {"facts": [
    {"id": "F1", "topic": "revenue", "key": True, "text": "Revenue increased 5.4% year-over-year to $109.0 million.",
     "quote": "Revenues increased 5.4% year-over-year to $109.0 million"},
    {"id": "F2", "topic": "margin", "key": True, "text": "Gross margin reached a record 32.3% vs 16.3%.",
     "quote": "gross margins to a record 32.3% compared to 16.3%"},
    {"id": "F3", "topic": "net_income", "key": True, "text": "Net loss improved by $18.0 million year-over-year to $(23.2) million.",
     "quote": "Net Loss improved by $18.0 million year-over-year to $(23.2) million"},
    {"id": "F4", "topic": "guidance", "key": True, "text": "Full year 2026 revenue guidance of $450 million to $500 million reaffirmed.",
     "quote": "reaffirms full year 2026 revenues of $450 million to $500 million"},
    {"id": "F6", "topic": "eps", "key": True, "text": "Diluted EPS improved by $0.20 year-over-year to $(0.09).",
     "quote": "Diluted EPS improved by $0.20 per share year-over-year to $(0.09) per share"},
    {"id": "F5", "topic": "other", "key": False, "text": "Backlog grew to $700.0 million.",       # 원문에 없는 인용
     "quote": "Backlog grew to a record $700.0 million"}],
    "actual": {"revenue_musd": 109.0, "eps": -0.09}}
KO_OK = {"facts": [{"id": "F1", "ko": "매출은 전년 대비 5.4% 증가한 $109.0M."},
                   {"id": "F2", "ko": "매출총이익률 사상 최고 32.3%(전년 16.3%)."},
                   {"id": "F3", "ko": "순손실은 전년 대비 $18.0M 축소된 $-23.2M."},
                   {"id": "F4", "ko": "2026년 연간 매출 가이던스 $450M~$500M 유지(재확인)."},
                   {"id": "F6", "ko": "희석 EPS는 전년 대비 $0.20 개선된 $-0.09."}]}
KO_BAD = {"facts": [dict(x) for x in KO_OK["facts"]]}
KO_BAD["facts"][2]["ko"] = "순손실은 $-23.2M로 $18.0M 증가."
REPORT = {"headline": {"text": "레드와이어, 사상 최고 마진·적자 축소·가이던스 유지", "src": ["F2", "F3", "F4"]},
          "metrics": [{"k": "매출", "v": "$109.0M", "dir": "up", "src": ["F1"]},
                      {"k": "순손실", "v": "$-23.2M", "dir": "up", "src": ["F3"]},
                      {"k": "EPS", "v": "$-0.09", "dir": "up", "src": ["F6"]}],
          "guidance": {"text": "2026년 매출 $450M~$500M 유지", "src": ["F4"]},
          "bullets": [{"text": "매출 $109.0M, 전년 대비 5.4% 증가.", "src": ["F1"]},
                      {"text": "매출총이익률 사상 최고 32.3%.", "src": ["F2"]},
                      {"text": "매출이 예상보다 13.9% 적음.", "src": ["C1"]}]}
NOISE = {"issues": [{"where": "x", "problem": "근거 없는 지적", "evidence": "this sentence is not in the source", "stage": "작성"}]}


class _Client:
    """프롬프트의 단계 표시('1단계'…'4단계')로 어느 에이전트인지 구분해 준비된 답을 차례로 준다."""
    def __init__(self, **answers):
        self.q = {k: list(v) for k, v in answers.items()}
        self.prompts = []

        def create(**kw):
            p = kw["messages"][0]["content"]
            self.prompts.append(p)
            st = next(s for s in ("1단계", "2단계", "3단계", "4단계") if s in p)
            body = self.q[{"1단계": "s", "2단계": "t", "3단계": "w", "4단계": "f"}[st]].pop(0)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(body, ensure_ascii=False)))])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def _cons(actual):
    from report_check import compare_text, consensus_compare
    cmp = consensus_compare(actual, "$126.56M", "$-0.09")
    return cmp, compare_text(cmp)


def _run(client):
    return A.run_pipeline(client, "m", "레드와이어", "RDW", "3분기", SRC, _cons)


def test_publishes_when_all_stages_pass_and_drops_fabricated_quote_and_ungrounded_issue():
    c = _Client(s=[FACTS], t=[KO_OK], w=[REPORT], f=[NOISE])
    r = _run(c)
    assert r["ok"] is True and [x["stage"] for x in r["stages"]] == list(A.STAGES)
    assert "F5" not in {f["id"] for f in r["facts"]}                       # 원문에 없는 인용 → 사실에서 제외
    assert "원문 불일치 1개 제외" in r["stages"][0]["note"]
    assert "원문 근거 없는 지적 1건 제외" in r["stages"][3]["note"]
    assert r["report"]["headline"].startswith("레드와이어") and r["cons_text"].startswith("매출 $109.0M")
    assert r["report"]["bullets"][2] == "매출이 예상보다 13.9% 적음."


def test_translation_gate_catches_reversed_loss_and_retries():
    c = _Client(s=[FACTS], t=[KO_BAD, KO_OK], w=[REPORT], f=[{"issues": []}])
    r = _run(c)
    assert r["ok"] is True
    retry = [p for p in c.prompts if "2단계" in p and "직전 시도에서 발견된 문제" in p]
    assert len(retry) == 1 and "순손실 방향 반대" in retry[0]


def test_write_gate_requires_sources_and_key_facts():
    no_guid = json.loads(json.dumps(REPORT))
    no_guid["guidance"] = {"text": "", "src": []}
    no_guid["headline"]["src"] = ["F2", "F3"]
    issues = A.gate_report(no_guid, [dict(f) for f in FACTS["facts"][:5]], {x["id"]: x["ko"] for x in KO_OK["facts"]}, "")
    assert any("핵심 사실 F4 누락" in i for i in issues)
    assert any("근거 사실 id" in i for i in issues)                     # C1 인용인데 예상 대비 문구 없음
    fake = json.loads(json.dumps(REPORT))
    fake["bullets"][0]["text"] = "매출 $119.0M, 전년 대비 5.4% 증가."
    assert any("119.0" in i for i in A.gate_report(fake, [dict(f) for f in FACTS["facts"][:5]],
                                                     {x["id"]: x["ko"] for x in KO_OK["facts"]}, "x 13.9%"))


def test_final_check_with_real_evidence_sends_back_then_holds():
    real = {"issues": [{"where": "레드와이어, 사상 최고 마진", "problem": "EPS 개선 누락",
                        "evidence": "Diluted EPS improved by $0.20 per share", "stage": "작성"}]}
    c = _Client(s=[FACTS], t=[KO_OK], w=[REPORT, REPORT], f=[real, real])
    r = _run(c)
    assert r["ok"] is False and r["rounds"] == A.MAX_ROUNDS
    assert [x["stage"] for x in r["stages"]] == ["요약", "번역", "작성", "최종 점검", "작성", "최종 점검"]
    assert "EPS 개선 누락" in [p for p in c.prompts if "3단계" in p][1]   # 두 번째 작성에 지적이 전달됨


def test_write_gate_rejects_ttm_revenue_empty_metric_and_company_voice():
    bad = json.loads(json.dumps(REPORT))
    bad["metrics"][0]["v"] = "$100B"                                    # TTM 매출을 분기 매출처럼
    bad["metrics"].append({"k": "영업이익", "v": "", "dir": "", "src": ["F1"]})
    bad["bullets"][1]["text"] = "우리는 강력한 대차대조표를 유지하겠습니다."
    iss = A.gate_report(bad, [dict(f) for f in FACTS["facts"][:5]], {x["id"]: x["ko"] for x in KO_OK["facts"]},
                        "x 13.9%", {"revenue_musd": 109.0, "eps": -0.09})
    assert any("이번 분기 매출 $109.0M과 다름" in i for i in iss)
    assert any("값(v)이 비어" in i for i in iss) and any("우리·당사" in i for i in iss)


def _er():
    return {"detail": {"cur": {"period": "26.09", "eps": "$-0.09", "rev": "$126.56M"},
                       "prev": {"period": "26.06"}, "quarters": [{"cq": "2026-2", "reported": True}]}}


def _patch(monkeypatch):
    press = {"text": SRC, "full": SRC, "acc": "A1", "url": "u", "accept": "2026-11-04T21:21:19.000Z"}
    monkeypatch.setattr(E, "_recent_press", lambda t, now, ex: (press, "261105", "2026-11-05"))
    monkeypatch.setattr(E, "_release_move", lambda t, a: {"text": "발표 직후 시간외 -2.9% (진행 중)", "final": False, "pct": -2.9})


def test_held_report_is_not_published(monkeypatch):
    _patch(monkeypatch)
    bad = {"issues": [{"where": "x", "problem": "EPS 누락", "evidence": "Diluted EPS improved by $0.20", "stage": "작성"}]}
    c = _Client(s=[FACTS], t=[KO_OK], w=[REPORT, REPORT], f=[bad, bad])
    rec = E._report_for_ticker("RDW", _er(), {}, c, datetime(2026, 11, 5, tzinfo=pytz.utc))
    assert rec["check"]["ok"] is False and rec["attempts"] == 1
    assert "headline" not in rec and "bullets" not in rec                  # 보류 → 요약 내용 미게시
    assert rec["verdict"] == "miss" and rec["move"]["final"] is False      # 코드 계산 값은 유지
    html = _report_card_html(rec)
    assert "검수 보류" in html and "요약을 싣지 않았습니다" in html and "원문과 다를 수 있는" not in html


def test_published_report_card(monkeypatch):
    _patch(monkeypatch)
    c = _Client(s=[FACTS], t=[KO_OK], w=[REPORT], f=[{"issues": []}])
    rec = E._report_for_ticker("RDW", _er(), {}, c, datetime(2026, 11, 5, tzinfo=pytz.utc))
    assert rec["check"]["ok"] is True and rec["bullets"][0].startswith("매출 $109.0M")
    html = _report_card_html(rec)
    assert "요약→번역→작성→최종 점검" in html and "사상 최고 32.3%" in html


def test_held_report_retried_until_limit(monkeypatch):
    monkeypatch.setattr(E, "_sec_8k_press", lambda t: {"acc": "A1", "accept": "2026-11-04T21:21:19.000Z", "text": "x", "url": "u"})
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    now = datetime(2026, 11, 6, tzinfo=pytz.utc)
    base = {"acc": "A1", "gen": E.REPORT_GEN, "model": E.REPORT_MODEL}
    assert E._recent_press("RDW", now, {"RDW": {**base, "check": {"ok": False}, "attempts": 1}}) is not None
    assert E._recent_press("RDW", now, {"RDW": {**base, "check": {"ok": False}, "attempts": E.MAX_ATTEMPTS}}) is None
    assert E._recent_press("RDW", now, {"RDW": {**base, "check": {"ok": True}}}) is None
