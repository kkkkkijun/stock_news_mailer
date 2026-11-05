# -*- coding: utf-8 -*-
"""실적 보고서 4단계 에이전트 파이프라인 — 원문과 다른 보고서는 게시하지 않는다.

  ① 요약 에이전트   : 8-K 보도자료 원문(영문) → 사실 목록(영문). 사실마다 원문 그대로의 인용(quote)을 붙인다.
                      [코드 관문] 인용이 원문에 실제로 있는지, 사실의 수치가 인용 안에 있는지 → 아니면 그 사실을 버림.
  ② 번역 에이전트   : 사실 목록 → 한국어. 수치·비교 기준·증감 방향을 그대로 옮긴다.
                      [코드 관문] 영문에 없는 수치가 생겼는지, 증감 방향이 뒤집혔는지.
  ③ 보고서 작성 에이전트: 한국어 사실만으로 headline·metrics·guidance·bullets 작성, 문장마다 근거 사실 ID(src).
                      [코드 관문] 근거 ID가 실제 있는지, 수치가 근거 사실에 있는지, 방향이 근거와 같은지, 핵심 사실 누락.
  ④ 최종 점검 에이전트: 보고서를 '원문'과 직접 대조. 문제마다 원문 인용(evidence)을 요구하고, 원문에 없는 인용을 단
                      지적은 버린다(근거 없는 지적 = 잡음). 문제가 남으면 책임 단계부터 다시(최대 MAX_ROUNDS회).
                      코드 관문과 최종 점검을 모두 통과해야 게시(ok=True). 끝내 못 통과하면 보류(ok=False) — 화면엔
                      요약을 싣지 않고 원문 링크만 둔다.

순수 로직 + client.chat.completions 호출만 한다(네트워크·파일 없음). 관련: earnings._report_for_ticker, report_check
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from report_check import direction_conflicts, unsupported_numbers

log = logging.getLogger(__name__)

STAGES = ("요약", "번역", "작성", "최종 점검")
MAX_ROUNDS = 2          # 최종 점검 실패 시 책임 단계부터 다시 도는 횟수(첫 회 포함)


# ---------------------------------------------------------------- 공통
def _norm(s: str) -> str:
    s = (s or "").lower()
    s = s.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}))
    return re.sub(r"\s+", "", s)


def quote_in_source(quote: str, source_norm: str) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in source_norm


def _ask(client, model: str, prompt: str, max_tokens: int) -> dict[str, Any]:
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}, max_tokens=max_tokens)
    return json.loads(resp.choices[0].message.content or "{}")


def _notes(notes: list[str] | None) -> str:
    return ("\n[직전 시도에서 발견된 문제 — 반드시 고칠 것]\n- " + "\n- ".join(notes) + "\n") if notes else ""


_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4}


def period_pairs(text: str) -> list[tuple[int, int]]:
    """문장 속 (연도, 분기) — 나온 순서대로. '2026년 3분기'·'Q3 2026'·'third quarter of 2026'·'2026 third quarter'."""
    found = []
    pats = [(r"(\d{4})\s*년\s*(?:제\s*)?([1-4])\s*분기", lambda m: (m.group(1), m.group(2))),
            (r"\bQ([1-4])[\s'\-]*(?:FY\s*)?(\d{4})\b", lambda m: (m.group(2), m.group(1))),
            (r"\b(\d{4})\s*Q([1-4])\b", lambda m: (m.group(1), m.group(2))),
            (r"\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(?:fiscal\s+(?:year\s+)?)?(\d{4})\b",
             lambda m: (m.group(2), _ORD[m.group(1).lower()])),
            (r"\b(\d{4})\s+(first|second|third|fourth)\s+quarter\b", lambda m: (m.group(1), _ORD[m.group(2).lower()]))]
    for pat, get in pats:
        for m in re.finditer(pat, text or "", re.I):
            y, q = get(m)
            found.append((m.start(), (int(y), int(q))))
    return [p for _, p in sorted(found)]


def period_conflict(ko: str, en_texts: list[str]) -> str:
    """한국어 문장의 첫 기간(주어 기간)이 근거 영문 문장들의 첫 기간 중 하나와 같은지. 다르면 설명 문자열."""
    kp = period_pairs(ko)
    firsts = [pp[0] for pp in (period_pairs(e) for e in en_texts) if pp]
    if not kp or not firsts or kp[0] in firsts:
        return ""
    y, q = kp[0]
    want = ", ".join(f"{a}년 {b}분기" for a, b in firsts)
    return f"기간 오류: '{y}년 {q}분기' ↔ 근거는 {want}"


# ---------------------------------------------------------------- ① 요약
def summarize(client, model, name, sym, qlabel, source, notes=None) -> dict[str, Any]:
    prompt = (
        f"너는 실적 보고서 파이프라인의 1단계 '요약 에이전트'다. 아래는 {name}({sym}) {qlabel} 실적 보도자료 원문이다.\n"
        "원문에 적힌 사실만 영어로 뽑아 JSON만 출력하라.\n"
        "규칙:\n"
        "1) 각 사실은 영어 한 문장(text)과, 그 사실이 적힌 원문 구간을 한 글자도 바꾸지 않고 복사한 quote(8~220자)를 가진다. "
        "text의 모든 수치는 quote 안에 있어야 한다. 원문에 없는 해석·인과·전망을 넣지 말 것.\n"
        "2) 비교 기준을 원문 그대로 적는다(year-over-year, sequential, fiscal year 등). 증감 방향 단어도 원문 그대로"
        "(improved, increased, decreased …). 표에만 있는 수치는 표의 두 기간 값을 그대로 적고 방향은 값으로 판단한다.\n"
        "3) 반드시 포함: 매출, 희석 EPS(GAAP, 조정 EPS가 있으면 따로), 순이익/순손실, 마진, 원문 제목·첫 문단이 강조한 성과(기록·최초 등), "
        "가이던스(상향/하향/유지/신규와 정확한 범위), 일회성 비용·이익, 주요 부문 실적. 6~14개.\n"
        "4) key=true: 제목·첫 문단 강조 항목, 가이던스, 실적을 크게 바꾼 일회성 항목, 매출·EPS.\n"
        "5) actual: 이번 분기 실제 매출(백만 달러 숫자)과 희석 EPS(GAAP, 숫자). 없으면 null.\n"
        'JSON: {"facts":[{"id":"F1","topic":"revenue|eps|net_income|margin|guidance|segment|one_time|cash|other",'
        '"text":"...","quote":"...","key":true}],"actual":{"revenue_musd":숫자|null,"eps":숫자|null}}\n'
        f"{_notes(notes)}\n[원문]\n{source}"
    )
    return _ask(client, model, prompt, 2200)


def gate_summary(out: dict[str, Any], source: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """원문에 없는 인용·인용에 없는 수치를 가진 사실은 버린다 → (남은 사실, 버린 이유, 다시 할 이유)."""
    sn = _norm(source)
    kept, dropped = [], []
    for i, f in enumerate(out.get("facts") or []):
        fid = str(f.get("id") or f"F{i + 1}")
        text, quote = str(f.get("text") or ""), str(f.get("quote") or "")
        if not text.strip():
            continue
        if not quote_in_source(quote, sn):
            dropped.append(f"{fid}: quote가 원문과 글자 그대로 일치하지 않음")
            continue
        bad = unsupported_numbers({"bullets": [text]}, quote)
        if bad:
            dropped.append(f"{fid}: text의 수치 {', '.join(bad)}가 quote에 없음")
            continue
        topic = f.get("topic") or "other"
        kept.append({"id": fid, "topic": topic, "text": text, "quote": quote,     # 가이던스·일회성 항목은 항상 핵심
                     "key": bool(f.get("key")) or topic in ("guidance", "one_time")})
    retry = []
    if len(kept) < 3:
        retry.append(f"원문과 일치하는 사실이 {len(kept)}개뿐 — quote를 원문에서 그대로 복사할 것")
    if not any(f["key"] for f in kept):
        retry.append("핵심(key) 사실이 없음 — 매출·EPS·가이던스·제목 강조 항목을 key로 표시할 것")
    topics = {f["topic"] for f in kept}
    for tp, label in (("revenue", "이번 분기 매출"), ("eps", "이번 분기 희석 EPS")):
        if tp not in topics and re.search(r"revenue" if tp == "revenue" else r"per share|EPS", source, re.I):
            retry.append(f"{label} 사실(topic={tp})이 없음 — 원문(표 포함)에서 이번 분기 값을 인용해 넣을 것")
    return kept, dropped, retry


# ---------------------------------------------------------------- ② 번역
def translate(client, model, facts, notes=None) -> dict[str, Any]:
    src = json.dumps([{"id": f["id"], "text": f["text"]} for f in facts], ensure_ascii=False)
    prompt = (
        "너는 실적 보고서 파이프라인의 2단계 '번역 에이전트'다. 아래 영어 사실 목록을 자연스러운 한국어로 번역해 JSON만 출력하라.\n"
        "규칙:\n"
        "1) 정보를 더하거나 빼지 말 것. 문장 하나당 번역 하나, id 유지.\n"
        "2) 수치·단위는 그대로. $109.0 million → $109.0M, $2.36 billion → $2.36B 처럼만 줄일 수 있다(억·조로 바꾸지 말 것). "
        "괄호 음수 $(23.2) million → $-23.2M.\n"
        "3) 비교 기준: year-over-year → 전년 대비, sequential/quarter-over-quarter → 전분기 대비, fiscal year → 회계연도. "
        "다른 표현을 만들지 말 것.\n"
        "4) 방향: increased → 증가, decreased → 감소, improved → 개선. 손실이 improved/decreased면 '순손실 축소(개선)', "
        "손실이 increased면 '순손실 확대'. raised guidance → 가이던스 상향, reaffirmed → 유지(재확인).\n"
        "5) 회사·제품·부문 이름은 원어 그대로 둬도 된다.\n"
        'JSON: {"facts":[{"id":"F1","ko":"..."}]}\n'
        f"{_notes(notes)}\n[사실 목록]\n{src}"
    )
    return _ask(client, model, prompt, 2000)


def gate_translation(facts, out) -> tuple[dict[str, str], list[str]]:
    ko = {str(x.get("id")): str(x.get("ko") or "") for x in out.get("facts") or []}
    issues = []
    for f in facts:
        k = ko.get(f["id"], "")
        if not k.strip():
            issues.append(f"{f['id']}: 번역 누락")
            continue
        bad = unsupported_numbers({"bullets": [k]}, f["text"])
        if bad:
            issues.append(f"{f['id']}: 영문에 없는 수치 {', '.join(bad)}")
        missing = unsupported_numbers({"bullets": [f["text"]]}, k)
        if missing:
            issues.append(f"{f['id']}: 영문 수치 {', '.join(missing)}가 번역에서 빠짐")
        for c in direction_conflicts({"bullets": [k]}, f["text"]):
            issues.append(f"{f['id']}: {c}")
        pc = period_conflict(k, [f["text"]])
        if pc:
            issues.append(f"{f['id']}: {pc}")
    return ko, issues


# ---------------------------------------------------------------- ③ 보고서 작성
def write(client, model, name, sym, qlabel, facts, ko, cons_text, notes=None) -> dict[str, Any]:
    rows = [{"id": f["id"], "key": f["key"], "ko": ko.get(f["id"], "")} for f in facts if ko.get(f["id"])]
    if cons_text:
        rows.append({"id": "C1", "key": False, "ko": f"시장 예상 대비(코드 계산): {cons_text}"})
    prompt = (
        f"너는 실적 보고서 파이프라인의 3단계 '보고서 작성 에이전트'다. {name}({sym}) {qlabel} 실적 보고서를 쓴다.\n"
        "아래 한국어 사실 목록만 근거로 쓰고, 모든 항목에 근거 사실 id(src)를 단다. JSON만 출력.\n"
        "규칙:\n"
        "1) 사실 목록에 없는 수치·주장·인과관계·평가를 쓰지 말 것. 비교 기준·증감 방향은 근거 사실의 표현 그대로.\n"
        "2) key=true 사실은 모두 어딘가(headline/metrics/guidance/bullets)에 반영한다.\n"
        "3) headline: 42자 이하, 핵심 호재와 악재를 함께(근거 사실에 있는 것만).\n"
        "4) metrics 2~4개: 매출·EPS·순이익(손실)·마진 등. v는 '$109.0M','$-0.09','32.3%'처럼. "
        "dir은 회사에 좋은 변화면 up(매출 증가, 손실 축소, 마진 개선), 나쁜 변화면 down, 비교 근거가 없으면 빈문자열.\n"
        "5) guidance: 가이던스 사실이 있으면 그 내용(상향·하향·유지와 범위), 없으면 빈문자열과 src [].\n"
        "6) bullets 3~4개, 각 1문장. 주가는 쓰지 말 것(화면에 따로 표시됨).\n"
        'JSON: {"headline":{"text":"...","src":["F1"]},"metrics":[{"k":"매출","v":"$109.0M","dir":"up","src":["F1"]}],'
        '"guidance":{"text":"...","src":["F7"]},"bullets":[{"text":"...","src":["F2","F3"]}]}\n'
        f"{_notes(notes)}\n[사실 목록]\n{json.dumps(rows, ensure_ascii=False)}"
    )
    return _ask(client, model, prompt, 1500)


def _items(out: dict[str, Any]) -> list[tuple[str, str, list[str], dict[str, Any] | None]]:
    """(위치, 문장, src, metric) 목록으로 평탄화."""
    def src(x):
        return [str(s) for s in (x.get("src") or [])] if isinstance(x, dict) else []

    def txt(x):
        return str(x.get("text") or "") if isinstance(x, dict) else str(x or "")
    items = [("headline", txt(out.get("headline")), src(out.get("headline")), None)]
    g = out.get("guidance")
    if txt(g).strip():
        items.append(("guidance", txt(g), src(g), None))
    for m in out.get("metrics") or []:
        items.append((f"metric {m.get('k', '')}", f"{m.get('k', '')} {m.get('v', '')}", src(m), m))
    for b in out.get("bullets") or []:
        items.append(("bullet", txt(b), src(b), None))
    return items


def _metric_mismatch(met: dict[str, Any], actual: dict[str, Any]) -> str:
    """매출·EPS 지표 값이 요약 단계가 뽑은 이번 분기 실제치와 다른지(TTM·연간 값을 분기 매출로 쓰는 실수 방지)."""
    from report_check import eps_num, money_m
    k, v = str(met.get("k") or ""), str(met.get("v") or "")
    if re.fullmatch(r"\s*(총\s*)?매출(액)?\s*", k) and actual.get("revenue_musd") is not None:
        got, want = money_m(v), float(actual["revenue_musd"])
        if got is None or abs(abs(got) - abs(want)) > max(0.6, 0.006 * abs(want)):
            return f"매출 지표 {v}가 이번 분기 매출 ${want:,.1f}M과 다름(누적·연간 값이면 지표 이름에 밝힐 것)"
    if re.search(r"EPS|주당순이익", k) and actual.get("eps") is not None and "조정" not in k:
        got = eps_num(v)
        if got is None or abs(got - float(actual["eps"])) > 0.0051:
            return f"EPS 지표 {v}가 이번 분기 희석 EPS {actual['eps']}와 다름"
    return ""


def gate_report(out, facts, ko, cons_text, actual=None) -> list[str]:
    by_id = {f["id"]: f for f in facts}
    issues, cited = [], set()
    if len([b for b in out.get("bullets") or [] if (b.get("text") if isinstance(b, dict) else b)]) < 3:
        issues.append("bullets가 3개 미만 — 핵심 사실로 3~4개 작성할 것")
    for where, text, src, met in _items(out):
        if not text.strip():
            issues.append(f"{where}: 비어 있음")
            continue
        if re.search(r"주가", text):
            issues.append(f"{where} '{text[:30]}': 주가는 쓰지 말 것")
        if re.search(r"우리|당사", text):
            issues.append(f"{where} '{text[:30]}': 회사 입장 문장(우리·당사)을 옮기지 말고 사실만 쓸 것")
        if met is not None:
            if not re.search(r"\d", str(met.get("v") or "")):
                issues.append(f"{where}: 값(v)이 비어 있거나 숫자가 없음")
            mm = _metric_mismatch(met, actual or {})
            if mm:
                issues.append(f"{where}: {mm}")
        refs = [s for s in src if s in by_id or (s == "C1" and cons_text)]
        if not refs:
            issues.append(f"{where} '{text[:30]}': 근거 사실 id(src)가 없거나 목록에 없음")
            continue
        cited.update(refs)
        basis = " ".join(f"{by_id[s]['text']} {ko.get(s, '')}" for s in refs if s in by_id)
        if "C1" in refs:
            basis += " " + cons_text
        bad = unsupported_numbers({"bullets": [text]}, basis)
        if bad:
            issues.append(f"{where} '{text[:30]}': 근거 사실에 없는 수치 {', '.join(bad)}")
        en = " ".join(by_id[s]["text"] for s in refs if s in by_id)
        pc = period_conflict(text, [by_id[s]["text"] for s in refs if s in by_id])
        if pc:
            issues.append(f"{where} '{text[:30]}': {pc}")
        rep = {"bullets": [text]} if met is None else {"metrics": [met]}
        for c in direction_conflicts(rep, en):
            issues.append(f"{where}: {c}")
    for f in facts:
        if f["key"] and f["id"] not in cited:
            issues.append(f"핵심 사실 {f['id']} 누락: {f['text'][:60]}")
    return issues


# ---------------------------------------------------------------- ④ 최종 점검
def final_check(client, model, name, sym, report: dict[str, Any], source: str) -> dict[str, Any]:
    body = json.dumps(report, ensure_ascii=False)
    prompt = (
        f"너는 실적 보고서 파이프라인의 4단계 '최종 점검 에이전트'다. {name}({sym}) 보고서를 [원문]과 직접 대조한다. "
        "기준은 원문뿐이다. JSON만 출력.\n"
        "문제로 볼 것: ① 증가·감소·개선·악화 방향이 원문과 반대 ② 비교 기준 오류(전년/전분기/회계연도) "
        "③ 수치 오류나 지표 이름 오류(예: EPS를 순손실로) ④ 원문에 없는 주장·인과 "
        "⑤ 원문 제목·첫 문단의 핵심 성과, 가이던스, 실적을 크게 바꾼 일회성 항목의 누락 ⑥ 가이던스 상향/하향/유지 오류.\n"
        "문체·표현 취향은 문제가 아니다. 각 문제는 where(보고서의 해당 문장 그대로), problem(무엇이 틀렸는지), "
        "evidence(그 판단의 근거가 되는 원문 구간을 한 글자도 바꾸지 않고 복사), stage(원인 단계: 요약|번역|작성)를 가진다. "
        "evidence를 원문에서 그대로 복사할 수 없다면 그 지적은 쓰지 말 것. 문제가 없으면 빈 배열.\n"
        'JSON: {"issues":[{"where":"...","problem":"...","evidence":"...","stage":"작성"}]}\n'
        f"[보고서]\n{body}\n\n[원문]\n{source}"
    )
    return _ask(client, model, prompt, 1200)


def gate_final(out: dict[str, Any], source: str) -> tuple[list[dict[str, str]], int]:
    """원문 인용(evidence)이 원문에 실제로 있는 지적만 남긴다 → (지적, 버린 수)."""
    sn = _norm(source)
    kept, dropped = [], 0
    for x in out.get("issues") or []:
        if not isinstance(x, dict) or not quote_in_source(str(x.get("evidence") or ""), sn):
            dropped += 1
            continue
        stage = x.get("stage") if x.get("stage") in STAGES[:3] else "작성"
        kept.append({"where": str(x.get("where") or ""), "problem": str(x.get("problem") or ""),
                     "evidence": str(x.get("evidence") or ""), "stage": stage})
    return kept, dropped


# ---------------------------------------------------------------- 지휘(오케스트레이터)
def _flatten(out: dict[str, Any]) -> dict[str, Any]:
    """작성 결과(src 포함) → 화면용 레코드 필드."""
    def txt(x):
        return str(x.get("text") or "") if isinstance(x, dict) else str(x or "")
    mets = [{"k": m.get("k", ""), "v": m.get("v", ""), "dir": m.get("dir", "") if m.get("dir") in ("up", "down") else ""}
            for m in (out.get("metrics") or [])[:4]]
    return {"headline": txt(out.get("headline")), "metrics": mets, "guidance": txt(out.get("guidance")),
            "bullets": [txt(b) for b in (out.get("bullets") or [])[:4] if txt(b).strip()]}


def run_pipeline(client, model: str, name: str, sym: str, qlabel: str, source: str,
                 cons_fn: Callable[[dict[str, Any]], tuple[dict[str, Any], str]]) -> dict[str, Any]:
    """4단계 실행. cons_fn(actual) → (cmp, cons_text): 요약이 뽑은 실제치로 예상 대비를 코드가 계산한다.

    반환 {ok, report, cmp, cons_text, facts, stages, issues, rounds} — ok=False면 게시하지 않는다."""
    stages: list[dict[str, Any]] = []
    notes: dict[str, list[str]] = {}
    start = "요약"
    facts: list[dict[str, Any]] = []
    ko: dict[str, str] = {}
    cmp: dict[str, Any] = {}
    cons_text = ""
    report: dict[str, Any] = {}
    actual: dict[str, Any] = {}
    issues: list[str] = []
    rnd = 0
    for rnd in range(1, MAX_ROUNDS + 1):
        try:
            if start == "요약":
                s = summarize(client, model, name, sym, qlabel, source, notes.get("요약"))
                facts, dropped, retry = gate_summary(s, source)
                if retry:
                    s = summarize(client, model, name, sym, qlabel, source, retry + dropped)
                    facts, dropped, retry = gate_summary(s, source)
                stages.append({"stage": "요약", "round": rnd, "ok": not retry,
                               "note": f"사실 {len(facts)}개" + (f", 원문 불일치 {len(dropped)}개 제외" if dropped else "")})
                if retry:
                    issues = [f"[요약] {x}" for x in retry]
                    break
                actual = s.get("actual") or {}
                cmp, cons_text = cons_fn(actual)
            if start in ("요약", "번역"):
                t = translate(client, model, facts, notes.get("번역"))
                ko, tiss = gate_translation(facts, t)
                if tiss:
                    t = translate(client, model, facts, tiss)
                    ko, tiss = gate_translation(facts, t)
                stages.append({"stage": "번역", "round": rnd, "ok": not tiss, "note": f"{len(ko)}개 번역"})
                if tiss:
                    issues = [f"[번역] {x}" for x in tiss]
                    break
            w = write(client, model, name, sym, qlabel, facts, ko, cons_text, notes.get("작성"))
            wiss = gate_report(w, facts, ko, cons_text, actual)
            if wiss:
                w = write(client, model, name, sym, qlabel, facts, ko, cons_text, wiss)
                wiss = gate_report(w, facts, ko, cons_text, actual)
            stages.append({"stage": "작성", "round": rnd, "ok": not wiss, "note": f"항목 {len(_items(w))}개"})
            if wiss:
                issues = [f"[작성] {x}" for x in wiss]
                break
            report = _flatten(w)
            f = final_check(client, model, name, sym, report, source)
            found, noise = gate_final(f, source)
            stages.append({"stage": "최종 점검", "round": rnd, "ok": not found,
                           "note": f"지적 {len(found)}건" + (f"(원문 근거 없는 지적 {noise}건 제외)" if noise else "")})
            if not found:
                return {"ok": True, "report": report, "cmp": cmp, "cons_text": cons_text, "facts": facts,
                        "stages": stages, "issues": [], "rounds": rnd}
            issues = [f"[최종 점검·{x['stage']}] {x['where'][:40]} — {x['problem']} (원문: {x['evidence'][:80]})"
                      for x in found]
            order = {s: i for i, s in enumerate(STAGES)}
            start = min((x["stage"] for x in found), key=order.get)
            for x in found:
                notes.setdefault(x["stage"], []).append(f"{x['where'][:60]} — {x['problem']} (원문: {x['evidence'][:160]})")
        except Exception as e:                       # LLM·JSON 실패 → 보류
            log.warning(f"[reports] {sym} 파이프라인 오류: {e}")
            issues = [f"[오류] {e}"]
            break
    return {"ok": False, "report": report, "cmp": cmp, "cons_text": cons_text, "facts": facts,
            "stages": stages, "issues": issues, "rounds": rnd}
