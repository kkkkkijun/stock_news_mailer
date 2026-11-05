# -*- coding: utf-8 -*-
"""Yahoo 실적 일정·컨센서스 수집(data/earnings.json)과 SEC 8-K 기반 실적 리포트 생성(data/reports.json).

입력: Yahoo quoteSummary(calendarEvents/earnings/earningsTrend/earningsHistory/financialData/recommendationTrend),
      sec._sec_8k_press(8-K 보도자료·접수 시각), Yahoo chart(발표 전후 주가), newsfeed.fetch_news_articles(관련 뉴스)
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


REPORT_GEN = 2          # 보고서 생성 규칙 버전. 올리면 최근 보고서를 새 규칙으로 다시 만든다.


def _gen_report(client, name, sym, qlabel, numbers, press_text,
                price_move="", news_text="", fix_notes=None):
    """8-K 발표문 → 보고서 JSON(LLM). fix_notes가 있으면 직전 결과의 오류를 고쳐 다시 쓰게 한다."""
    import json as _json
    if client is None:
        return {"headline": f"{name} {qlabel} 실적", "verdict": "",
                "metrics": [], "guidance": "", "bullets": ["(요약 생성 불가: API 키 없음)"]}
    pm = f"\n[발표 후 주가 — 시점 포함]\n{price_move}\n" if price_move else ""
    nx = f"\n[관련 뉴스 제목(참고, 사실 근거로 쓰지 말 것)]\n{news_text}\n" if news_text else ""
    fx = ("\n[직전 결과에서 발견된 오류 — 반드시 고칠 것]\n- " + "\n- ".join(fix_notes) + "\n") if fix_notes else ""
    prompt = (
        f"{name}({sym})의 {qlabel} 실적 발표 자료다.\n"
        f"[확정 숫자(시장 예상 포함)]\n{numbers}\n{pm}{nx}"
        f"\n[발표문 원문]\n{press_text}\n{fx}\n"
        "위 정보로 '실적 보고서 요약'을 한국어로 작성해 JSON만 출력하라.\n"
        "규칙:\n"
        "1) 수치는 발표문·확정 숫자·발표 후 주가에 있는 것만 쓴다. 없는 수치·주장·인과관계를 지어내지 말 것. 투자 조언 금지.\n"
        "2) 증가·감소·개선·악화 방향은 발표문의 비교 문장(year-over-year, improved, increased, decreased 등)을 그대로 따른다.\n"
        "   손실(순손실·영업손실·조정 EBITDA 적자)은 금액이 줄면 '개선/축소', 늘면 '악화/확대'다. '손실'이라는 단어만 보고 악화로 쓰지 말 것.\n"
        "3) 비교 기준을 정확히: 발표문이 전년 동기 대비면 '전년 대비', 전분기 대비면 '전분기 대비'. '올해 대비' 같은 말을 만들지 말 것.\n"
        "4) 시장 예상 대비 결과는 확정 숫자의 예상치와 발표문 실제치를 비교해 숫자로 쓴다(예: 매출 $109.0M, 예상 $126.6M 하회).\n"
        "5) 발표문 제목·첫 문단이 강조한 핵심 성과(예: 사상 최고 마진, 수주 기록)는 반드시 넣고, "
        "악재(예상 하회, 비용 증가, 적자 등)도 함께 넣어 균형을 맞춘다.\n"
        "6) 주가는 [발표 후 주가]의 시점 표현 그대로 쓴다. 시점이 없거나 '진행 중'이면 주가를 확정적 결과처럼 쓰지 말 것.\n"
        "7) 가이던스는 상향·하향·유지(재확인) 여부를 발표문 표현대로 쓴다.\n"
        "8) metrics.dir은 회사에 좋은 방향이면 \"up\"(매출 증가, 손실 축소, 마진 개선), 나쁜 방향이면 \"down\", 애매하면 \"\". "
        "금액은 '$109.0M','$2.36B'처럼 축약. 백로그는 metrics에 넣지 말 것(필요하면 bullets).\n"
        "9) actual에는 발표문에 적힌 이번 분기 실제 매출(백만 달러 숫자)과 희석 EPS(숫자)를 넣고, 없으면 null.\n"
        '형식: {"headline":"한 줄 핵심(<=42자, 호재·악재 균형)",'
        '"metrics":[{"k":"지표","v":"값","dir":"up|down|"}],'
        '"guidance":"가이던스 요지(없으면 빈문자열)",'
        '"bullets":["3~4개"],"actual":{"revenue_musd":숫자|null,"eps":숫자|null}}'
    )
    try:
        resp = client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, max_tokens=900)
        data = _json.loads(resp.choices[0].message.content or "{}")
        return {"headline": data.get("headline", ""),
                "metrics": (data.get("metrics") or [])[:5],
                "guidance": data.get("guidance", ""),
                "bullets": (data.get("bullets") or [])[:4],
                "actual": data.get("actual") or {}}
    except Exception as e:
        log.exception(f"[reports] {sym} 요약 실패: {e}")
        return {"headline": f"{name} {qlabel} 실적", "verdict": "",
                "metrics": [], "guidance": "", "bullets": []}


def _fact_check(client, rep: dict[str, Any], numbers: str, press_text: str, price_move: str) -> list[str]:
    """보고서를 발표문과 대조(LLM 검수자). 문제 문장 목록, 문제가 없거나 검수 실패면 []."""
    import json as _json
    if client is None:
        return []
    body = _json.dumps({k: rep.get(k) for k in ("headline", "metrics", "guidance", "bullets")}, ensure_ascii=False)
    prompt = (
        "너는 실적 보고서 검수자다. [발표문 원문]·[확정 숫자]·[발표 후 주가]만 근거로 [보고서]를 한 문장씩 점검하고 "
        'JSON {"issues":["..."]}만 출력하라. 문제로 볼 것:\n'
        "① 증가·감소·개선·악화 방향이 원문과 반대(예: 원문은 순손실 improved인데 보고서는 '손실 증가')\n"
        "② 비교 기준 오류(전년 대비를 '올해 대비'·'전분기 대비'로 쓰는 등)\n"
        "③ 원문·확정 숫자·주가에 없는 수치나 주장, 근거 없는 인과(예: '이 때문에 주가 하락')\n"
        "④ 시장 예상 대비 상회·하회 판단 오류\n"
        "⑤ 발표문 제목·첫 문단이 강조한 핵심 성과의 누락\n"
        "⑥ 주가 움직임의 시점 오류(발표 전 움직임을 발표 반응처럼 서술)\n"
        "각 issue는 '보고서의 어느 표현이 왜 틀렸고 원문은 무엇인지' 한 문장. 문제가 없으면 빈 배열.\n\n"
        f"[확정 숫자]\n{numbers}\n[발표 후 주가]\n{price_move or '(없음)'}\n[발표문 원문]\n{press_text}\n\n[보고서]\n{body}"
    )
    try:
        resp = client.chat.completions.create(
            model=SUMMARY_MODEL, messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, max_tokens=600)
        issues = _json.loads(resp.choices[0].message.content or "{}").get("issues") or []
        return [str(i).strip() for i in issues if str(i).strip()][:6]
    except Exception as e:
        log.warning(f"[reports] 검수 실패(건너뜀): {e}")
        return []


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
    if ex.get("acc") == press["acc"] and ex.get("gen") == REPORT_GEN:   # 캐시(같은 발표·같은 생성 규칙)
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


def _report_market_context(t: str, accept: str | None = None) -> tuple[str, str, dict[str, Any] | None]:
    """발표 후 주가 반응(시점 포함) + 관련 뉴스 제목 → (price_move 문구, news_text, move dict)."""
    move = _release_move(t, accept)
    pm = move["text"] if move else ""
    news_text = ""
    try:
        arts = fetch_news_articles(t)[:4]
        news_text = " / ".join(a.get("title") or "" for a in arts if a.get("title"))
    except Exception as e:
        log.warning(f"[reports] {t} 관련 뉴스 조회 실패: {e}")
    return pm, news_text, move


def _check_report(rep: dict[str, Any], numbers: str, press_text: str, pm: str, cmp: dict[str, Any],
                  client: Any) -> list[str]:
    """방향 모순·수치 대조(코드 규칙) + 원문 대조(LLM 검수) → 문제 목록."""
    from report_check import direction_conflicts, unsupported_numbers
    extra = []
    for k in ("rev", "eps"):
        for v in (cmp.get(k) or {}).values():
            extra.append(abs(float(v)))
    issues = direction_conflicts(rep, press_text)
    issues += [f"원문에 없는 수치: {n}" for n in unsupported_numbers(rep, f"{numbers}\n{pm}\n{press_text}", extra)]
    return issues + _fact_check(client, rep, numbers, press_text, pm)


def _report_for_ticker(t: str, er: dict[str, Any] | None, existing: dict[str, Any],
                       client: Any, now: datetime) -> dict[str, Any] | None:
    """티커 하나의 실적 보고서 레코드를 만든다(발표 없음/캐시 히트 시 existing 재사용, 실패 시 None).

    생성 → 예상 대비 계산·판정(코드) → 수치·원문 대조 → 문제가 있으면 그 내용을 주고 한 번 다시 생성 → 재대조.
    대조 결과는 check {ok, issues}로 남겨 화면에 표시한다."""
    from report_check import compare_text, consensus_compare, verdict
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
    est_rev, est_eps = (cur.get("rev"), cur.get("eps")) if yahoo_lag else (None, prev.get("eps_est"))
    pm, news_text, move = _report_market_context(t, press.get("accept"))
    log.info(f"[reports] {t} 8-K 요약 생성… ({qlabel}, 주가 {pm or '-'})")
    summ = _gen_report(client, name, t, f"{qnum}분기", numbers, press["text"], price_move=pm, news_text=news_text)

    def finish(s):
        act = dict(s.get("actual") or {})
        if not yahoo_lag and prev.get("eps_act"):
            act.setdefault("eps", prev.get("eps_act"))
        cmp = consensus_compare(act, est_rev, est_eps)
        return cmp, _check_report(s, numbers, press["text"], pm, cmp, client)

    cmp, issues = finish(summ)
    if issues and client is not None:
        log.info(f"[reports] {t} 대조 문제 {len(issues)}건 → 다시 생성")
        summ = _gen_report(client, name, t, f"{qnum}분기", numbers, press["text"],
                           price_move=pm, news_text=news_text, fix_notes=issues)
        cmp, issues = finish(summ)
    rec = {"ticker": t, "name": name,
           "title": f"{kshort}_{name}_{qnum}분기_실적보고서",
           "date": kiso, "qnum": qnum, "quarter": qlabel, "cq": cq,
           "acc": press["acc"], "url": press["url"], "accept": press.get("accept"), "gen": REPORT_GEN}
    if not yahoo_lag:    # Yahoo 실제치 있을 때만 EPS/서프라이즈 첨부
        rec.update({"eps_act": prev.get("eps_act"), "eps_est": prev.get("eps_est"),
                    "surprise": prev.get("surprise"), "surprise_pos": prev.get("surprise_pos")})
    summ.pop("actual", None)
    rec.update(summ)
    rec.update({"verdict": verdict(cmp), "cons": cmp, "cons_text": compare_text(cmp), "move": move,
                "check": {"ok": not issues, "issues": issues, "by": "auto"}})
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
