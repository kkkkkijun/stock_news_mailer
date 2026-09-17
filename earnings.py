# -*- coding: utf-8 -*-
"""Yahoo 실적 일정·컨센서스 수집(data/earnings.json)과 SEC 8-K 기반 실적 리포트 생성(data/reports.json).

입력: Yahoo quoteSummary(calendarEvents/earnings/earningsTrend/earningsHistory/financialData/recommendationTrend),
      sec._sec_8k_press(8-K 보도자료), quotes.fetch_quote(주가 반응), newsfeed.fetch_news_articles(관련 뉴스)
출력: data/earnings.json(실적 일정·컨센서스), data/reports.json(8-K 기반 AI 한글 요약)
실행: 별도 실행 없음 — main.py가 import해서 사용
관련: settings.py, sec.py, quotes.py, llm.py, newsfeed.py, netutil.py, main.py
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import netutil
from settings import EARNINGS_TICKERS, _EARN_KO, KST, SUMMARY_MODEL
from sec import _sec_8k_press, _report_kdate
from quotes import _QUOTE_UA, fetch_quote
from llm import get_openai_client
from newsfeed import fetch_news_articles

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


def _gen_report(client, name, sym, qlabel, numbers, press_text,
                price_move="", news_text=""):
    import json as _json
    if client is None:
        return {"headline": f"{name} {qlabel} 실적", "verdict": "",
                "metrics": [], "guidance": "", "bullets": ["(요약 생성 불가: API 키 없음)"]}
    pm = f"\n[발표 후 주가]\n{price_move}\n" if price_move else ""
    nx = f"\n[관련 뉴스(시장 반응)]\n{news_text}\n" if news_text else ""
    prompt = (
        f"{name}({sym})의 {qlabel} 실적 발표 자료다.\n"
        f"[확정 숫자]\n{numbers}\n{pm}{nx}"
        f"\n[발표문 원문 발췌]\n{press_text}\n\n"
        "위 정보로 '실적 보고서 요약'을 한국어로 작성해 JSON만 출력하라.\n"
        "규칙:\n"
        "- 확정 숫자·발표문에 있는 값만 사용. 없는 수치·주장 지어내지 말 것. 투자 조언 금지.\n"
        "- 회사 발표문은 호재(매출·백로그 등) 위주로 쓰였을 수 있다. 주가가 하락/약세면 "
        "그 배경이 되는 악재(순손실 규모·EPS 하회·마진·가이던스/일정 지연 등)를 반드시 찾아 "
        "호재와 균형 있게 담고, 왜 주가가 그렇게 움직였는지 드러나게 하라.\n"
        "- 주가 등락 '방향'과 서술을 일치시켜라: 상승이면 상승/긍정 반응으로, 하락이면 하락/부정 반응으로. "
        "상승했는데 '부진·약세', 하락했는데 '호조'처럼 방향과 어긋나게 쓰지 말 것.\n"
        "- bullets 3~4개: 호재+악재 함께. 주가 하락 시 최소 1~2개는 하락·유의 요인.\n"
        "- metrics.dir: 긍정 방향(증가·개선·상회·흑자·기록)=\"up\", 부정 방향(감소·손실·하회·부진·지연)=\"down\", 중립=\"\".\n"
        "- metrics 금액은 '$234M','$2.36B'처럼 축약. 백로그는 metrics에 넣지 말 것(필요하면 bullets에).\n"
        '형식: {"headline":"한 줄 핵심(<=42자, 호재·악재 균형)","verdict":"beat|miss|inline",'
        '"metrics":[{"k":"지표","v":"값","dir":"up|down|"}],'
        '"guidance":"가이던스 요지(없으면 빈문자열)",'
        '"bullets":["3~4개"]}'
    )
    try:
        resp = client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, max_tokens=850)
        data = _json.loads(resp.choices[0].message.content or "{}")
        return {"headline": data.get("headline", ""), "verdict": data.get("verdict", ""),
                "metrics": (data.get("metrics") or [])[:5],
                "guidance": data.get("guidance", ""),
                "bullets": (data.get("bullets") or [])[:4]}
    except Exception as e:
        log.exception(f"[reports] {sym} 요약 실패: {e}")
        return {"headline": f"{name} {qlabel} 실적", "verdict": "",
                "metrics": [], "guidance": "", "bullets": []}


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
    if existing.get(t, {}).get("acc") == press["acc"]:   # 캐시
        return None
    return press, kshort, kiso


def _resolve_report_quarter(cur: dict[str, Any], rq: list[dict[str, Any]],
                            kiso: str) -> tuple[str, str, bool] | None:
    """발표 분기 판정(8-K 접수일 기준): 접수일이 cur(0q) 분기말 이후면 Yahoo 실제치 미반영
    상태 → cur(0q)가 방금 발표분. 아니면 최신 실제분기(rq 마지막). 판정 불가면 None."""
    cur_cq, cur_label = (_period_cq(cur["period"]) if cur.get("period") else (None, None))
    yahoo_lag = bool(cur_cq and kiso and kiso > _period_qend(cur["period"]))
    if yahoo_lag:
        return cur_cq, cur_label, yahoo_lag
    if rq:
        return rq[-1].get("cq"), rq[-1].get("label", ""), yahoo_lag
    return None


def _report_numbers_text(cur: dict[str, Any], prev: dict[str, Any], yahoo_lag: bool) -> str:
    """LLM 프롬프트에 넘길 '확정 숫자' 문구."""
    if yahoo_lag:        # Yahoo 실제치 미반영 → 발표문 원문에서 실제 추출 유도
        return (f"이번 분기 시장 예상 EPS {cur.get('eps', '-')} 매출 {cur.get('rev', '-')}; "
                "실제 수치·서프라이즈는 발표문 원문 기준으로 추출할 것")
    return (f"EPS 실제 {prev.get('eps_act', '-')} / 예상 {prev.get('eps_est', '-')} "
            f"(서프라이즈 {prev.get('surprise', '-')})")


def _report_market_context(t: str) -> tuple[str, str]:
    """주가 반응 + 관련 뉴스(왜 올랐/내렸는지 근거 확보) → (price_move, news_text)."""
    q = fetch_quote(t)
    pm = ""
    if q and q.get("chg") is not None:
        c = q["chg"]
        pm = f"전일대비 {c:+.2f}% ({'상승' if c >= 0 else '하락'})"
    news_text = ""
    try:
        arts = fetch_news_articles(t)[:4]
        news_text = " / ".join(a.get("title") or "" for a in arts if a.get("title"))
    except Exception as e:
        log.warning(f"[reports] {t} 관련 뉴스 조회 실패: {e}")
    return pm, news_text


def _report_for_ticker(t: str, er: dict[str, Any] | None, existing: dict[str, Any],
                       client: Any, now: datetime) -> dict[str, Any] | None:
    """티커 하나의 실적 보고서 레코드를 만든다(발표 없음/캐시 히트 시 existing 재사용, 실패 시 None)."""
    if not er:
        return None
    det = er.get("detail") or {}
    cur, prev = det.get("cur") or {}, det.get("prev") or {}
    rq = [q for q in (det.get("quarters") or []) if q.get("reported")]
    if not rq and not cur.get("period"):
        return None
    press_info = _recent_press(t, now, existing)
    if press_info is None:
        return existing.get(t)
    press, kshort, kiso = press_info
    resolved = _resolve_report_quarter(cur, rq, kiso)
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
    numbers = _report_numbers_text(cur, prev, yahoo_lag)
    pm, news_text = _report_market_context(t)
    log.info(f"[reports] {t} 8-K 요약 생성… ({qlabel}, 주가 {pm or '-'})")
    summ = _gen_report(client, name, t, f"{qnum}분기", numbers, press["text"],
                       price_move=pm, news_text=news_text)
    rec = {"ticker": t, "name": name,
           "title": f"{kshort}_{name}_{qnum}분기_실적보고서",
           "date": kiso, "qnum": qnum, "quarter": qlabel, "cq": cq,
           "acc": press["acc"], "url": press["url"]}
    if not yahoo_lag:    # Yahoo 실제치 있을 때만 EPS/서프라이즈 첨부
        rec.update({"eps_act": prev.get("eps_act"), "eps_est": prev.get("eps_est"),
                    "surprise": prev.get("surprise"), "surprise_pos": prev.get("surprise_pos")})
    rec.update(summ)
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
