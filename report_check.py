# -*- coding: utf-8 -*-
"""실적 보고서 신뢰성 장치(순수 함수 — 네트워크·LLM 없음, 테스트 대상).

① release_reaction: 8-K 접수 시각 기준 '발표 후' 주가 반응. 장 마감 후 발표면 다음 거래일, 장 전·장중이면
   그날 정규장 종가를 직전 종가와 비교한다. 그 거래일이 아직 안 끝났으면 발표 뒤 마지막 가격(시간외 포함)으로
   '진행 중' 표시. (예전엔 생성 시점의 '전일 대비'를 써서, 장 마감 후 발표 기업은 발표 '전' 하락을 반응으로 적었다.)
② unsupported_numbers: 보고서 문장의 수치가 발표문·확정 숫자·계산값에 실제로 있는지 대조.
③ consensus_compare / verdict: 시장 예상 대비 결과를 숫자로 계산하고 beat/miss/inline을 코드로 판정.
관련: earnings.py(_report_for_ticker), render/earnings.py(카드 표시)
"""
from __future__ import annotations

import re
from datetime import date, datetime, time as dtime
from typing import Any

_OPEN, _CLOSE = dtime(9, 30), dtime(16, 0)


# ---------------------------------------------------------------- ① 주가 반응
def release_reaction(daily: list[tuple[date, float]], intraday: list[tuple[datetime, float]],
                     rel_et: datetime, now_et: datetime) -> dict[str, Any] | None:
    """daily = [(거래일, 정규장 종가)] 오름차순, intraday = [(ET 시각, 가격)] 시간외 포함 오름차순.

    반환 {pct, base, last, label, final, text} — final=False면 반응 거래일이 아직 진행 중."""
    after_close = rel_et.time() >= _CLOSE
    sessions = [(d, c) for d, c in daily if c and (d > rel_et.date() if after_close else d >= rel_et.date())]
    if not sessions:
        return _in_progress(daily, intraday, rel_et, after_close)
    rd, rc = sessions[0]
    prior = [(d, c) for d, c in daily if c and d < rd]
    if not prior:
        return None
    base = prior[-1][1]
    done = now_et.date() > rd or (now_et.date() == rd and now_et.time() >= _CLOSE)
    if not done:
        return _in_progress(daily, intraday, rel_et, after_close, base=base)
    pct = (rc / base - 1) * 100
    when = "발표 다음 거래일" if after_close else "발표 당일"
    label = f"{when}({rd.month}/{rd.day}) 종가"
    return {"pct": round(pct, 2), "base": base, "last": rc, "label": label, "final": True,
            "text": f"{label} {pct:+.1f}% (${base:,.2f} → ${rc:,.2f})"}


def _in_progress(daily, intraday, rel_et, after_close, base=None):
    if base is None:
        prior = [c for d, c in daily if c and (d <= rel_et.date() if after_close else d < rel_et.date())]
        if not prior:
            return None
        base = prior[-1]
    after = [(t, p) for t, p in intraday if p and t >= rel_et]
    if not after:
        return None
    t, last = after[-1]
    regular = t.weekday() < 5 and _OPEN <= t.time() < _CLOSE
    label = "발표 후 장중" if regular else "발표 직후 시간외"
    pct = (last / base - 1) * 100
    return {"pct": round(pct, 2), "base": base, "last": last, "label": label, "final": False,
            "text": f"{label} {pct:+.1f}% (${base:,.2f} → ${last:,.2f}, 진행 중)"}


# ---------------------------------------------------------------- ② 수치 대조
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand|[BMK](?![a-z])|%)?", re.I)


def numbers_in(text: str) -> list[float]:
    """문장 속 수치(절댓값). 10억 단위는 백만 단위로도 함께 넣는다($2.36B ↔ 2,360 million)."""
    out: list[float] = []
    for m in _NUM.finditer(text or ""):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        u = (m.group(2) or "").lower()
        out.append(v)
        if u in ("billion", "b"):
            out.append(v * 1000)
        elif u in ("thousand", "k"):
            out.append(v / 1000)
    return out


def _trivial(v: float, raw: str) -> bool:
    """대조에서 뺄 수: 연도·분기·작은 정수(개수·순서)."""
    if v.is_integer() and 1990 <= v <= 2100:
        return True
    return v.is_integer() and v < 10 and not re.search(r"[$%]|million|billion|[BMK]\b", raw)


def unsupported_numbers(report: dict[str, Any], source: str, extra: list[float] | None = None) -> list[str]:
    """보고서(headline·metrics·guidance·bullets)의 수치 중 원문(+extra 계산값)에 없는 것."""
    src = numbers_in(source) + list(extra or [])
    texts = [report.get("headline", ""), report.get("guidance", "")] + list(report.get("bullets") or []) \
        + [str(m.get("v", "")) for m in report.get("metrics") or []]
    bad = []
    for t in texts:
        for m in _NUM.finditer(t or ""):
            raw = m.group(0)
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if _trivial(v, raw):
                continue
            cands = numbers_in(raw)
            ok = any(abs(c - s) <= max(0.051, 0.006 * abs(s)) for c in cands for s in src)
            if not ok:
                bad.append(raw.strip())
    return sorted(set(bad))


# ---------------------------------------------------------------- ③ 예상 대비 판정
def money_m(s: Any) -> float | None:
    """'$126.56M' · '$2.4B' · 126.56 → 백만 달러. 못 읽으면 None."""
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"(-?\d[\d,]*\.?\d*)\s*([BMK])?", str(s or "").replace("$", ""))
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    return v * {"B": 1000, "K": 0.001}.get(m.group(2) or "M", 1)


def eps_num(s: Any) -> float | None:
    if isinstance(s, (int, float)):
        return float(s)
    m = re.search(r"-?\d+\.?\d*", str(s or "").replace("$", "").replace("(", "-"))
    return float(m.group(0)) if m else None


def consensus_compare(actual: dict[str, Any], est_rev: Any, est_eps: Any) -> dict[str, Any]:
    """실제(발표문) vs 시장 예상. {rev:{act,est,pct}, eps:{act,est,diff}} — 둘 중 없는 쪽은 생략."""
    out: dict[str, Any] = {}
    ra, re_ = money_m(actual.get("revenue_musd")), money_m(est_rev)
    if ra and re_:
        out["rev"] = {"act": round(ra, 2), "est": round(re_, 2), "pct": round((ra / re_ - 1) * 100, 1)}
    ea, ee = eps_num(actual.get("eps")), eps_num(est_eps)
    if ea is not None and ee is not None:
        out["eps"] = {"act": ea, "est": ee, "diff": round(ea - ee, 3)}
    return out


def verdict(cmp: dict[str, Any]) -> str:
    """매출 ±1%·EPS ±0.5센트 밖이면 상회/하회. 합이 +면 beat, −면 miss, 0이면 inline. 비교 불가면 ''."""
    if not cmp:
        return ""
    s = 0
    if "rev" in cmp:
        s += 1 if cmp["rev"]["pct"] > 1 else -1 if cmp["rev"]["pct"] < -1 else 0
    if "eps" in cmp:
        s += 1 if cmp["eps"]["diff"] > 0.005 else -1 if cmp["eps"]["diff"] < -0.005 else 0
    return "beat" if s > 0 else "miss" if s < 0 else "inline"


def compare_text(cmp: dict[str, Any]) -> str:
    parts = []
    if "rev" in cmp:
        r = cmp["rev"]
        parts.append(f"매출 ${r['act']:,.1f}M vs 예상 ${r['est']:,.1f}M ({r['pct']:+.1f}%)")
    if "eps" in cmp:
        e = cmp["eps"]
        tag = "부합" if abs(e["diff"]) <= 0.005 else ("상회" if e["diff"] > 0 else "하회")
        parts.append(f"EPS ${e['act']:.2f} vs 예상 ${e['est']:.2f} ({tag})")
    return " · ".join(parts)


# ---------------------------------------------------------------- ④ 방향 모순(코드 규칙)
# 발표문의 "Net Loss improved…" 같은 비교 문장과 보고서의 "순손실 증가" 같은 서술이 반대인지 본다.
# (지표, 발표문 정규식, 보고서 한글 키워드, 손실류 여부) — 손실류는 'increased'가 나쁜 쪽.
_METRICS = (
    ("순손실", r"net loss", r"순손실|당기순손실|순손실액", True),
    ("매출", r"(?:total )?revenues?", r"매출(?!총)", False),
    ("EPS", r"(?:diluted |basic )?eps|earnings per share", r"EPS|주당순이익", False),
    ("조정 EBITDA", r"adjusted ebitda", r"조정\s?EBITDA", False),
    ("매출총이익률", r"gross margins?", r"매출총이익률|총이익률|마진", False),
    ("백로그", r"backlog", r"백로그|수주잔고", False),
)
_EN_UP = r"improved|increased|increase|grew|rose|expanded"
_EN_DOWN = r"decreased|decrease|declined|fell|worsened"   # contracted·higher·lower는 형용사로도 쓰여 제외
_KO_UP = r"증가|늘|확대|상승|성장|개선|높아"
_KO_DOWN = r"감소|줄|축소|하락|악화|낮아"


def _press_dir(name, pat, is_loss, press):
    # 지표 이름 뒤 같은 문장(소수점 허용) 안의 첫 비교어. 'a nearly 75% increase' 같은 명사형도 인정
    # 'would have increased'(일회성 비용 제외 시 가정) 같은 가정문은 실제 방향이 아니므로 건너뜀
    m = next((x for x in re.finditer(rf"\b(?:{pat})\b(?:[^.;]|\.(?=\d)){{0,48}}?\b({_EN_UP}|{_EN_DOWN})\b",
                                     press or "", re.I) if not re.search(r"\bwould\b", x.group(0), re.I)), None)
    if not m:
        return None
    w = m.group(1).lower()
    if w == "improved":
        return "better"
    up = re.fullmatch(_EN_UP, w) is not None
    return ("worse" if up else "better") if is_loss else ("better" if up else "worse")


def _report_dir(kpat, is_loss, text):
    # 지표 이름 뒤 같은 구(소수점은 허용, 구분점·쉼표·마침표에서 끊음) 안의 첫 증감어
    m = re.search(rf"(?:{kpat})((?:[^·,;.]|\.(?=\d)){{0,26}}?)({_KO_UP}|{_KO_DOWN})", text or "")
    if not m or re.search(r"주가|예상|컨센서스|하회|상회", m.group(1)):
        return None                     # '매출 하회로 주가 하락'처럼 다른 주어·예상 대비는 판단 안 함
    w = m.group(2)
    if w in ("개선",):
        return "better"
    if w in ("악화",):
        return "worse"
    up = re.fullmatch(_KO_UP, w) is not None
    return ("worse" if up else "better") if is_loss else ("better" if up else "worse")


def direction_conflicts(report: dict[str, Any], press: str) -> list[str]:
    """보고서 문장·metrics 방향이 발표문의 전년 대비 비교 문장과 반대인 곳."""
    out = []
    texts = [report.get("headline", "")] + list(report.get("bullets") or [])
    mets = {str(m.get("k", "")): m.get("dir") for m in report.get("metrics") or []}
    for name, pat, kpat, is_loss in _METRICS:
        pd = _press_dir(name, pat, is_loss, press)
        if not pd:
            continue
        for t in texts:
            rd = _report_dir(kpat, is_loss, t)
            if rd and rd != pd:
                out.append(f"{name} 방향 반대: 보고서 '{t[:40]}' ↔ 발표문은 {'개선' if pd == 'better' else '악화'}")
        if is_loss or name in ("EPS", "매출총이익률"):        # 매출 dir은 예상 대비일 수 있어 제외
            for k, d in mets.items():
                if re.search(kpat, k) and d in ("up", "down") and (d == "up") != (pd == "better"):
                    out.append(f"{name} 지표 화살표({d})가 발표문({'개선' if pd == 'better' else '악화'})과 반대")
    return out
