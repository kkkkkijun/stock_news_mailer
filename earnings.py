# -*- coding: utf-8 -*-
"""Yahoo 실적 일정·컨센서스 수집(data/earnings.json)과 SEC 8-K 기반 실적 리포트 생성(data/reports.json).

입력: Yahoo quoteSummary(calendarEvents/earnings/earningsTrend/earningsHistory/financialData/recommendationTrend),
      sec._sec_8k_press(8-K 보도자료·접수 시각), Yahoo chart(발표 전후 주가), report_agents(4단계 보고서 파이프라인)
출력: data/earnings.json(실적 일정·컨센서스), data/reports.json(8-K 기반 AI 한글 요약)
실행: 별도 실행 없음 — main.py가 import해서 사용
관련: settings.py, sec.py, quotes.py, llm.py, newsfeed.py, netutil.py, main.py
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from typing import Any

import netutil
from settings import EARNINGS_TICKERS, _EARN_KO, KST, SUMMARY_MODEL
from sec import _sec_8k_press, _report_kdate
from quotes import _QUOTE_UA
from llm import get_openai_client

log = logging.getLogger(__name__)

# =========================================================
# 기업 실적 일정 (M7 + 관심종목) → data/earnings.json (일정 탭 우측)
#   Yahoo quoteSummary calendarEvents(crumb 방식, 무키)로 종목별 '다음 실적일'.
#   전부 실패 시 기존 파일 유지(덮어쓰지 않음).
# =========================================================
def _yahoo_earn_session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": _QUOTE_UA["User-Agent"]})
    try:
        s.get("https://fc.yahoo.com", timeout=8)  # 의도된 404(쿠키 설정용) → 상태 무시
    except Exception as e:
        log.debug("[earnings] Yahoo 쿠키 워밍업 예외(계속 진행): %s", e)
    crumb = netutil.get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                        timeout=8, session=s).text.strip()
    return s, crumb


def _g(node, *keys):
    for k in keys:
        node = node.get(k) if isinstance(node, dict) else None
    return node


def _num(node):
    return node.get("raw") if isinstance(node, dict) else None


def _pctval(fmt):
    try:
        return float(str(fmt).replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _signfmt(fmt):
    """'5.54%' → ('+5.54%', True) / '-3%' → ('-3%', False)."""
    if fmt is None:
        return None, None
    f = str(fmt).strip()
    neg = f.startswith("-")
    if not neg and not f.startswith("+"):
        f = "+" + f
    return f, (not neg)


def _ym_ts(ts):
    if not ts:
        return ""
    from datetime import datetime as _dt
    x = _dt.utcfromtimestamp(ts)
    return f"{x.year % 100:02d}.{x.month:02d}"


def _ym_str(s):
    return f"{s[2:4]}.{s[5:7]}" if s and len(s) >= 7 else ""


def _earn_prev_block(hist):
    """직전 실적(EPS 실측/예상/서프라이즈) + 분기별 서프라이즈 목록. hist 없으면 빈 dict."""
    if not hist:
        return {}
    last = hist[-1]
    ea, ee = _num(last.get("epsActual")), _num(last.get("epsEstimate"))
    sfmt, spos = _signfmt(_g(last, "surprisePercent", "fmt"))
    out = {"prev": {"period": _ym_ts(_num(last.get("quarter"))),
                    "eps_act": f"${ea:.2f}" if ea is not None else "-",
                    "eps_est": f"${ee:.2f}" if ee is not None else "-",
                    "surprise": sfmt, "surprise_pos": spos}}
    sp = []
    for q in hist:
        v = _pctval(_g(q, "surprisePercent", "fmt"))
        if v is not None:
            sf, sposq = _signfmt(_g(q, "surprisePercent", "fmt"))
            sp.append({"fmt": sf, "v": v, "pos": sposq})
    out["surprises"] = sp
    return out


def _earn_trend_blocks(res):
    """이번/다음 분기 컨센서스(cur/next)와 최근 30일 EPS 리비전(rev) 블록."""
    out = {}
    for t in res.get("earningsTrend", {}).get("trend", []) or []:
        per = t.get("period")
        if per not in ("0q", "+1q"):
            continue
        avg = _num(_g(t, "earningsEstimate", "avg"))
        lo = _num(_g(t, "earningsEstimate", "low"))
        hi = _num(_g(t, "earningsEstimate", "high"))
        gfmt, gpos = _signfmt(_g(t, "growth", "fmt"))
        rev = _g(t, "revenueEstimate", "avg", "fmt")
        blk = {"period": _ym_str(t.get("endDate")),
               "eps": f"${avg:.2f}" if avg is not None else "-",
               "eps_range": (f"${lo:.2f}~${hi:.2f}"
                             if lo is not None and hi is not None else ""),
               "rev": f"${rev}" if rev else "-",
               "growth": gfmt, "growth_pos": gpos}
        if per == "0q":          # 곧 발표할 그 분기 = '이번 발표 예상'
            out["cur"] = blk
            out["rev"] = {"up": _num(_g(t, "epsRevisions", "upLast30days")),
                          "down": _num(_g(t, "epsRevisions", "downLast30days"))}
        else:                    # +1q = 그 다음 분기
            out["next"] = blk
    return out


def _earn_cq(per):
    """'26.06' → ('2026-2','2026 2Q'): 회계분기를 캘린더 분기(1Q~4Q) 키로."""
    try:
        y = 2000 + int(per[:2]); mo = int(per[3:5]); q = (mo - 1) // 3 + 1
        return f"{y}-{q}", f"{y} {q}Q"
    except (ValueError, TypeError):
        return None, None


def _earn_quarters(hist, res, date):
    """분기별(과거 실제 + 다가올 예상) 목록 → 기업실적 '분기별' 토글용.
    회계분기 종료월의 '캘린더 분기(1Q~4Q)'로 그룹핑(NVDA 등 오프셋 흡수)."""
    qmap = {}
    for q in hist:
        per = _ym_ts(_num(q.get("quarter")))
        cq, cql = _earn_cq(per)
        if not cq:
            continue
        ea, ee = _num(q.get("epsActual")), _num(q.get("epsEstimate"))
        sfmt, spos = _signfmt(_g(q, "surprisePercent", "fmt"))
        qmap[cq] = {"cq": cq, "label": cql, "reported": True,
                    "eps_act": f"${ea:.2f}" if ea is not None else "-",
                    "eps_est": f"${ee:.2f}" if ee is not None else "-",
                    "surprise": sfmt, "surprise_pos": spos}
    for t in res.get("earningsTrend", {}).get("trend", []) or []:
        if t.get("period") not in ("0q", "+1q"):
            continue
        cq, cql = _earn_cq(_ym_str(t.get("endDate")))
        if not cq or cq in qmap:
            continue
        avg = _num(_g(t, "earningsEstimate", "avg"))
        rev = _g(t, "revenueEstimate", "avg", "fmt")
        e = {"cq": cq, "label": cql, "reported": False,
             "eps_est": f"${avg:.2f}" if avg is not None else "-",
             "rev": f"${rev}" if rev else None}
        if t.get("period") == "0q":
            e["date"] = date
        qmap[cq] = e
    return [qmap[k] for k in sorted(qmap)]


def _earn_target_and_rec(fd, rt):
    """목표주가(target)와 애널리스트 의견(rec) 블록."""
    pr, mn = _num(fd.get("currentPrice")), _num(fd.get("targetMeanPrice"))
    lo2, hi2 = _num(fd.get("targetLowPrice")), _num(fd.get("targetHighPrice"))
    up = round((mn - pr) / pr * 100) if pr and mn else None
    target = {"price": f"${pr:,.2f}" if pr else "-",
              "mean": f"${mn:,.2f}" if mn else "-",
              "range": (f"${lo2:,.0f}~${hi2:,.0f}" if lo2 and hi2 else ""),
              "upside": (f"{'+' if up >= 0 else ''}{up}%" if up is not None else None),
              "upside_pos": (up is not None and up >= 0)}
    _rk = {"strong_buy": "적극 매수", "buy": "매수", "hold": "보유",
           "underperform": "비중 축소", "sell": "매도"}
    key = fd.get("recommendationKey")
    rec = {"label": _rk.get(key, key or "-"),
           "count": _num(fd.get("numberOfAnalystOpinions"))}
    if rt:
        t0 = rt[0]
        rec.update({"buy": (t0.get("strongBuy", 0) or 0) + (t0.get("buy", 0) or 0),
                    "hold": t0.get("hold", 0) or 0,
                    "sell": (t0.get("sell", 0) or 0) + (t0.get("strongSell", 0) or 0)})
    return {"target": target, "rec": rec}


def _fetch_earning(session, crumb, sym):
    """종목 다음 실적일 + 상세(직전실적·컨센서스·목표주가·의견·리비전·서프라이즈)."""
    from datetime import datetime as _dt
    mods = ("calendarEvents,earnings,earningsTrend,earningsHistory,"
            "financialData,recommendationTrend")
    r = netutil.get(f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                    f"{sym}?modules={mods}&crumb={crumb}", timeout=12, session=session)
    if r.status_code != 200:
        return None
    res = r.json()["quoteSummary"]["result"][0]

    ce = res.get("calendarEvents", {}).get("earnings", {})
    raws = [x["raw"] for x in ce.get("earningsDate", []) if "raw" in x]
    date = (_dt.fromtimestamp(min(raws), KST).strftime("%Y-%m-%d")
            if raws else None)   # 실적 발표일: 한국시간(KST) 기준
    est = bool(ce.get("isEarningsDateEstimate"))
    hist = res.get("earningsHistory", {}).get("history", []) or []

    d = {}
    d.update(_earn_prev_block(hist))
    d.update(_earn_trend_blocks(res))
    d["quarters"] = _earn_quarters(hist, res, date)
    d.update(_earn_target_and_rec(res.get("financialData", {}) or {},
                                  res.get("recommendationTrend", {}).get("trend", []) or []))
    return {"date": date, "ts": (min(raws) if raws else None),
            "est": est, "detail": d}


def build_earnings(path: str | None = None) -> None:
    import json
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "earnings.json")
    try:
        session, crumb = _yahoo_earn_session()
    except Exception as e:  # noqa
        log.exception(f"[earnings] 세션 실패: {e}")
        return
    if not crumb:
        log.warning("[earnings] crumb 없음 → 기존 파일 유지")
        return
    out, ok = [], False
    for t in EARNINGS_TICKERS:
        try:
            info = _fetch_earning(session, crumb, t)
        except Exception as e:
            log.warning(f"[earnings] {t} 조회 실패: {e}")
            info = None
        if info is not None:
            ok = True
        out.append({"ticker": t, "name": _EARN_KO.get(t, t),
                    "date": info["date"] if info else None,
                    "ts": info.get("ts") if info else None,
                    "est": bool(info["est"]) if info else False,
                    "detail": info.get("detail") if info else None})
    if not ok:
        log.warning("[earnings] 전부 실패 → 기존 파일 유지")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log.info(f"[earnings] 저장: {sum(1 for r in out if r['date'])}/{len(out)}개 실적일")


# =========================================================
# 실적 보고서 (SEC 8-K 원문 → AI 한글 요약) → data/reports.json
#   기업실적 '보고서' 탭. 최근(50일 내) 발표만, accession 캐시로 재생성 최소화.
# =========================================================
def _period_cq(per):
    """'26.06' → ('2026-2', '2026 2Q')."""
    try:
        y = 2000 + int(per[:2])
        q = (int(per[3:5]) - 1) // 3 + 1
        return f"{y}-{q}", f"{y} {q}Q"
    except (ValueError, TypeError, IndexError):
        return None, None


def _period_qend(per):
    """'26.06' → '2026-06-30' (해당 분기말 날짜, 문자열 비교용)."""
    try:
        y = 2000 + int(per[:2])
        mo = int(per[3:5])
        last = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}[mo]
        return f"{y}-{mo:02d}-{last:02d}"
    except (ValueError, TypeError, KeyError, IndexError):
        return "9999-99-99"


REPORT_GEN = 5          # 보고서 생성 규칙 버전. 올리면 최근 보고서를 새 규칙으로 다시 만든다.
# 실적 보고서 생성·검수 모델(뉴스 요약과 분리). 바꾸면 캐시가 무효화돼 다시 만든다.
REPORT_MODEL = os.getenv("OPENAI_REPORT_MODEL") or SUMMARY_MODEL
MAX_ATTEMPTS = 3        # 최종 점검을 통과 못 한(보류) 보고서를 다음 실행에서 다시 시도하는 총 횟수


def _recent_press(t: str, now: datetime, existing: dict[str, Any]) -> tuple[dict[str, Any], str, str] | None:
    """최근(130일 내)·미캐시 8-K 보도자료를 가져온다. 해당 없으면 None(호출부가 existing 재사용)."""
    from datetime import datetime as _dt
    time.sleep(0.3)                     # SEC 레이트리밋 여유
    press = _sec_8k_press(t)
    if not press:
        return None
    kshort, kiso = _report_kdate(press.get("accept"))
    try:
        days = (now.date() - _dt.strptime(kiso, "%Y-%m-%d").date()).days
    except (ValueError, TypeError):
        days = 999
    if days > 130:                      # 최근 한 분기(약 130일) 내 발표만 카드화
        return None
    ex = existing.get(t, {})
    if ex.get("acc") == press["acc"]:
        chk = ex.get("check") or {}
        if chk.get("by") == "manual":    # 사람이 원문 대조로 고친 보고서는 덮어쓰지 않음
            return None
        same = ex.get("gen") == REPORT_GEN and ex.get("model", SUMMARY_MODEL) == REPORT_MODEL
        if same and (chk.get("ok") or ex.get("attempts", 1) >= MAX_ATTEMPTS):   # 게시됐거나 재시도 한도
            return None
    return press, kshort, kiso


def _prev_is_reported(prev: dict[str, Any] | None, kiso: str) -> bool:
    """Yahoo prev(최근 실제 분기)가 이번 발표분인가 — 실제 EPS가 있고 그 분기말이 발표일 전 95일 이내."""
    from datetime import datetime as _dt
    if not (prev and prev.get("eps_act") and prev.get("period") and kiso):
        return False
    try:
        gap = (_dt.strptime(kiso, "%Y-%m-%d") - _dt.strptime(_period_qend(prev["period"]), "%Y-%m-%d")).days
    except ValueError:
        return False
    return 0 <= gap <= 95       # 직전 분기분이면 간격이 한 분기(90일)+보고 지연이라 95일을 넘는다


def _resolve_report_quarter(cur: dict[str, Any], rq: list[dict[str, Any]],
                            kiso: str, prev: dict[str, Any] | None = None) -> tuple[str, str, bool] | None:
    """발표 분기 판정(8-K 접수일 기준): 접수일이 cur(0q) 분기말 이후이고 Yahoo prev에 이번 분기 실제치가
    아직 없으면 Yahoo 미반영 상태 → cur(0q)가 방금 발표분. 아니면 최신 실제분기(rq 마지막). 판정 불가면 None.
    (회계연도가 어긋난 종목은 cur가 이미 다음 분기 예상인데 period가 같게 찍혀, prev로 반영 여부를 확인한다.)"""
    cur_cq, cur_label = (_period_cq(cur["period"]) if cur.get("period") else (None, None))
    yahoo_lag = (bool(cur_cq and kiso and kiso > _period_qend(cur["period"]))
                 and not _prev_is_reported(prev, kiso))
    if yahoo_lag:
        return cur_cq, cur_label, yahoo_lag
    if rq:
        return rq[-1].get("cq"), rq[-1].get("label", ""), yahoo_lag
    return None


def _price_series(t: str) -> tuple[list, list]:
    """(일봉 [(ET 날짜, 정규장 종가)], 5분봉 [(ET 시각, 가격)] 시간외 포함) — Yahoo chart. 실패 시 빈 목록."""
    import pytz
    ny = pytz.timezone("America/New_York")
    base = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
    daily, intra = [], []
    try:
        r = netutil.get_json(base, params={"range": "3mo", "interval": "1d"}, headers=_QUOTE_UA, timeout=15)
        res = r["chart"]["result"][0]
        daily = [(datetime.fromtimestamp(ts, ny).date(), c)
                 for ts, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0]["close"]) if c]
        r = netutil.get_json(base, params={"range": "5d", "interval": "5m", "includePrePost": "true"},
                             headers=_QUOTE_UA, timeout=15)
        res = r["chart"]["result"][0]
        intra = [(datetime.fromtimestamp(ts, ny), c)
                 for ts, c in zip(res.get("timestamp") or [], res["indicators"]["quote"][0]["close"]) if c]
    except Exception as e:
        log.warning(f"[reports] {t} 주가 시계열 실패: {e}")
    return daily, intra


def _release_move(t: str, accept: str | None) -> dict[str, Any] | None:
    """8-K 접수 시각(SEC acceptanceDateTime, UTC) 기준 발표 후 주가 반응(report_check.release_reaction)."""
    import pytz
    from report_check import release_reaction
    if not accept:
        return None
    try:
        rel = datetime.fromisoformat(re.sub(r"\.\d+", "", accept).replace("Z", "+00:00"))
    except ValueError:
        return None
    ny = pytz.timezone("America/New_York")
    daily, intra = _price_series(t)
    return release_reaction(daily, intra, rel.astimezone(ny), datetime.now(ny))


def _report_for_ticker(t: str, er: dict[str, Any] | None, existing: dict[str, Any],
                       client: Any, now: datetime) -> dict[str, Any] | None:
    """티커 하나의 실적 보고서 레코드를 만든다(발표 없음/캐시 히트 시 existing 재사용, 실패 시 None).

    report_agents.run_pipeline(요약→번역→작성→최종 점검)을 돌려, 최종 점검까지 통과하면 게시(check.ok=True),
    아니면 보류(요약 내용 없이 원문 링크만 표시, 다음 실행에서 MAX_ATTEMPTS까지 재시도)."""
    from report_check import compare_text, consensus_compare, verdict
    from report_agents import run_pipeline
    if not er:
        return None
    det = er.get("detail") or {}
    cur, prev = det.get("cur") or {}, det.get("prev") or {}
    rq = [q for q in (det.get("quarters") or []) if q.get("reported")]
    if not rq and not cur.get("period"):
        return None
    press_info = _recent_press(t, now, existing)
    if press_info is None:
        rec = existing.get(t)
        if rec and rec.get("accept") and not (rec.get("move") or {}).get("final"):
            mv = _release_move(t, rec["accept"])          # 반응 거래일이 끝나면 확정치로 갱신(LLM 없이)
            if mv:
                rec = {**rec, "move": mv}
        return rec
    press, kshort, kiso = press_info
    resolved = _resolve_report_quarter(cur, rq, kiso, prev)
    if resolved is None:
        return existing.get(t)
    cq, qlabel, yahoo_lag = resolved
    if not cq:
        return existing.get(t)
    try:
        qnum = int(cq.split("-")[1])
    except (ValueError, IndexError):
        qnum = 0
    name = _EARN_KO.get(t, t)
    est_rev, est_eps = (cur.get("rev"), cur.get("eps")) if yahoo_lag else (None, prev.get("eps_est"))
    move = _release_move(t, press.get("accept"))          # 발표 시각 기준 주가 반응(코드)

    def cons_fn(actual):
        act = dict(actual or {})
        if not yahoo_lag and prev.get("eps_act"):
            act["eps"] = prev.get("eps_act")     # 예상치와 같은 기준(Yahoo 실제치)으로 비교
        cmp = consensus_compare(act, est_rev, est_eps)
        return cmp, compare_text(cmp)

    if client is None:
        return existing.get(t)
    log.info(f"[reports] {t} 4단계 파이프라인 시작… ({qlabel}, 모델 {REPORT_MODEL})")
    res = run_pipeline(client, REPORT_MODEL, name, t, f"{qnum}분기", press.get("full") or press["text"], cons_fn)
    log.info(f"[reports] {t} {'게시' if res['ok'] else '보류'} — "
             + " → ".join(f"{x['stage']}({'✓' if x['ok'] else '✗'})" for x in res["stages"])
             + ("" if res["ok"] else f" | {res['issues'][:3]}"))
    ex = existing.get(t) or {}
    attempts = ex.get("attempts", 0) + 1 if ex.get("acc") == press["acc"] and ex.get("gen") == REPORT_GEN else 1
    rec = {"ticker": t, "name": name,
           "title": f"{kshort}_{name}_{qnum}분기_실적보고서",
           "date": kiso, "qnum": qnum, "quarter": qlabel, "cq": cq,
           "acc": press["acc"], "url": press["url"], "accept": press.get("accept"), "gen": REPORT_GEN,
           "model": REPORT_MODEL, "attempts": attempts}
    if not yahoo_lag:    # Yahoo 실제치 있을 때만 EPS/서프라이즈 첨부
        rec.update({"eps_act": prev.get("eps_act"), "eps_est": prev.get("eps_est"),
                    "surprise": prev.get("surprise"), "surprise_pos": prev.get("surprise_pos")})
    if res["ok"]:
        rec.update(res["report"])
    rec.update({"verdict": verdict(res["cmp"]), "cons": res["cmp"], "cons_text": res["cons_text"], "move": move,
                "check": {"ok": res["ok"], "by": "agents", "stages": res["stages"], "issues": res["issues"]}})
    return rec


def _save_reports(path: str, reports: list[dict[str, Any]], prev: dict[str, Any]) -> None:
    """생성된 보고서를 저장한다. 전부 실패(reports 비어있음)면 기존 파일을 그대로 둔다."""
    import json as _json
    if not reports:
        log.warning("[reports] 생성된 보고서 없음")
        return
    reports.sort(key=lambda r: r.get("date", ""), reverse=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(reports, f, ensure_ascii=False, indent=1)
    log.info(f"[reports] 저장: {len(reports)}개")


def build_reports(path: str | None = None, client: Any = None) -> None:
    import json as _json
    edir = os.path.dirname(os.path.abspath(__file__))
    path = path or os.path.join(edir, "data", "reports.json")
    try:
        earns = {r["ticker"]: r for r in
                 _json.load(open(os.path.join(edir, "data", "earnings.json"), encoding="utf-8"))}
    except (OSError, ValueError):
        log.warning("[reports] earnings.json 없음 → 중단")
        return
    try:
        existing = {r["ticker"]: r for r in _json.load(open(path, encoding="utf-8"))}
    except (OSError, ValueError):
        existing = {}
    if client is None:
        client = get_openai_client()
    now = datetime.now(KST)
    out = []
    for t in EARNINGS_TICKERS:
        rec = _report_for_ticker(t, earns.get(t), existing, client, now)
        if rec is not None:
            out.append(rec)
    _save_reports(path, out, existing)
