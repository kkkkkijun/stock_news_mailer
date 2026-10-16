"""성장주 발굴 — SEC XBRL companyfacts 기반 재무 파이프라인.
sec.py의 _sec_cik / _SEC_UA 재사용. build_fundamentals()가 data/fundamentals.json 생성.

입력: SEC XBRL companyfacts API, 10-K 원문, sec.py의 _sec_cik/_SEC_UA, llm.py의 get_openai_client
출력: data/fundamentals.json(성장주 스코어), data/qual_cache.json(10-K 정성 분석 캐시)
실행: python fundamentals.py (지정된 몇 개 티커로 fundamentals_test.json 생성, 단독 테스트용). 평소엔 main.py가 build_fundamentals()/build_qualitative() 호출
관련: settings.py, sec.py, llm.py, netutil.py, main.py, publish_site.py
"""
from __future__ import annotations

import json
import logging
import os
import statistics
import time
from datetime import date, timedelta
from typing import Any

import netutil
from settings import EARNINGS_TICKERS, SUMMARY_MODEL
from sec import _sec_cik, _SEC_UA
from llm import get_openai_client

log = logging.getLogger(__name__)

# 총매출(Revenues) 우선: 두 태그의 최신 날짜가 같으면 앞의 것을 쓴다(_pick). 1차 선별(screen.py)과 같은 규칙
REV = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
GP = ["GrossProfit"]
OPINC = ["OperatingIncomeLoss"]
NI = ["NetIncomeLoss"]
OCF = ["NetCashProvidedByUsedInOperatingActivities"]
# 설비투자: 기업마다 태그가 다르다(AMZN·NVDA=ProductiveAssets). _pick이 최신 데이터 태그를 고른다.
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
         "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets"]
RND = ["ResearchAndDevelopmentExpense"]
ASSETS = ["Assets"]
LIAB = ["Liabilities"]
CASH = ["CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
# 현금+단기투자 합산 태그(있으면 우선) / 단기투자자산 후보(NVDA=DebtSecuritiesCurrent 등)
CASH_STI = ["CashCashEquivalentsAndShortTermInvestments"]
STI = ["ShortTermInvestments", "MarketableSecuritiesCurrent", "DebtSecuritiesCurrent",
       "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]
DEBT_LT = ["LongTermDebtNoncurrent", "LongTermDebt"]
DEBT_CUR = ["LongTermDebtCurrent", "DebtCurrent"]
SHARES = ["WeightedAverageNumberOfDilutedSharesOutstanding",
          "WeightedAverageNumberOfSharesOutstandingBasic"]

NAMES = {"NVDA": "엔비디아", "MSFT": "마이크로소프트", "AAPL": "애플",
         "GOOGL": "알파벳", "AMZN": "아마존", "META": "메타", "TSLA": "테슬라",
         "HIMS": "힘스", "RDW": "레드와이어", "IREN": "아이렌", "PLTR": "팔란티어",
         "RKLB": "로켓랩"}
SECTORS = {"RKLB": "우주·발사체", "IREN": "데이터센터·비트코인", "HIMS": "원격의료",
           "RDW": "우주 인프라", "PLTR": "AI·데이터", "NVDA": "반도체",
           "TSLA": "전기차", "MSFT": "SW·클라우드", "AAPL": "하드웨어",
           "GOOGL": "인터넷·AI", "AMZN": "이커머스·클라우드", "META": "소셜·AI"}


def _cq(end):
    y, m = int(end[:4]), int(end[5:7])
    return f"{y}-{(m - 1) // 3 + 1}"


def _pick(gaap, tags, dur=True):
    """후보 태그 중 '가장 최신 데이터가 있는' 태그의 units를 반환.
    기업이 태그를 갈아타도(예: NVDA RevenueFromContract→Revenues) 최신 걸 잡는다."""
    best, best_end = None, ""
    for t in tags:
        if t not in gaap:
            continue
        u = gaap[t]["units"]
        usd = u.get("USD") or u.get("shares") or next(iter(u.values()))
        if dur:
            ends = [e["end"] for e in usd if e.get("start") and e.get("end")]
        else:
            ends = [e["end"] for e in usd if e.get("end")]
        mx = max(ends) if ends else ""
        if mx > best_end:
            best, best_end = usd, mx
    return best


def _quarters(gaap, tags, lo=80, hi=100):
    """단일 분기(~90일) flow 값. {end: val} (end 오름차순)."""
    usd = _pick(gaap, tags)
    if not usd:
        return {}
    seen = {}
    for e in usd:
        s, en = e.get("start"), e.get("end")
        if not s or not en:
            continue
        d = (date.fromisoformat(en) - date.fromisoformat(s)).days
        if lo <= d <= hi:
            seen[en] = e["val"]
    return dict(sorted(seen.items()))


def _annuals(gaap, tags, lo=350, hi=380):
    usd = _pick(gaap, tags)
    if not usd:
        return {}
    seen = {}
    for e in usd:
        s, en = e.get("start"), e.get("end")
        if not s or not en:
            continue
        d = (date.fromisoformat(en) - date.fromisoformat(s)).days
        if lo <= d <= hi:
            seen[en] = (s, e["val"])
    return seen


def _fill_q4(q, ann):
    """연간값 − 그 해 내 3개 분기 = Q4. 누락 Q4 보간."""
    out = dict(q)
    for aend, (astart, aval) in ann.items():
        if aend in out:
            continue
        parts = [v for en, v in q.items() if astart < en < aend
                 and (date.fromisoformat(aend) - date.fromisoformat(en)).days < 300]
        if len(parts) == 3:
            out[aend] = aval - sum(parts)
    return dict(sorted(out.items()))


def _flow_quarters(gaap, tags):
    """현금흐름처럼 10-Q에 '연초 누적(YTD)'으로만 공시되는 flow의 단일 분기 값. {end: val}.

    같은 회계연도 시작일(start)의 누적값을 끝 날짜순으로 차분해 분기를 만든다
    (Q2=6개월−3개월, Q3=9개월−6개월, Q4=연간−9개월). 직접 공시된 ~90일 값이 있으면 그것을 쓴다.
    차분 구간이 80~100일이 아니면(예: TTM 값과 섞인 경우) 버린다."""
    usd = _pick(gaap, tags)
    if not usd:
        return {}
    direct, cum = {}, {}
    for e in usd:
        s, en = e.get("start"), e.get("end")
        if not s or not en:
            continue
        days = (date.fromisoformat(en) - date.fromisoformat(s)).days
        if 80 <= days <= 100:
            direct[en] = e["val"]
        if 80 <= days <= 380:
            cum.setdefault(s, {})[en] = e["val"]
    derived = {}
    for s, by_end in cum.items():
        prev_end, prev_val = date.fromisoformat(s) - timedelta(days=1), 0
        for en in sorted(by_end):
            span = (date.fromisoformat(en) - prev_end).days
            if 80 <= span <= 100:
                derived.setdefault(en, by_end[en] - prev_val)
            prev_end, prev_val = date.fromisoformat(en), by_end[en]
    out = {**derived, **direct}
    return dict(sorted(out.items()))


def _ttm(d):
    """최근 4개 분기 합. 4개가 연속된 분기(첫~끝 250~300일)가 아니면 None."""
    ends = sorted(d)[-4:]
    if len(ends) < 4:
        return None
    span = (date.fromisoformat(ends[-1]) - date.fromisoformat(ends[0])).days
    if not 250 <= span <= 300:
        return None
    return sum(d[en] for en in ends)


def _liquid_cash(cash, cash_sti, sti_tags):
    """현금성자산 + 단기투자자산(같은 결산일 값만). 합산 태그가 같은 날짜에 있으면 그것을 쓴다.

    cash, cash_sti: {end: val}. sti_tags: [{end: val}, ...] 후보 태그별 시계열.
    반환 (총액, 단기투자 포함 여부). 오래 끊긴 태그(다른 날짜)는 섞지 않는다."""
    if not cash:
        return None, False
    last = max(cash)
    if cash_sti.get(last) is not None and cash_sti[last] >= cash[last]:
        return cash_sti[last], cash_sti[last] > cash[last]
    for series in sti_tags:
        if series.get(last):
            return cash[last] + series[last], True
    return cash[last], False


def _rev_quarters(gaap):
    """매출 분기 시계열. 후보 태그마다 분기값(+Q4 보간)을 만들어 '가장 최근 분기'가 있는 태그를 쓰고,
    같으면 REV 순서(총매출 우선). 태그 단위 _pick만 쓰면 연간값만 있는 태그(IREN의 Revenues)가
    날짜 동률로 뽑혀 분기 시계열이 비는 문제가 있었다."""
    best, best_end = {}, ""
    for t in REV:
        if t not in gaap:
            continue
        q = _fill_q4(_quarters(gaap, [t]), _annuals(gaap, [t]))
        if q and max(q) > best_end:
            best, best_end = q, max(q)
    return best


def _instants(gaap, tags):
    usd = _pick(gaap, tags, dur=False)
    if not usd:
        return {}
    seen = {e["end"]: e["val"] for e in usd if e.get("end") and "start" not in e}
    if not seen:
        seen = {e["end"]: e["val"] for e in usd if e.get("end")}
    return dict(sorted(seen.items()))


def _year_ago(d):
    """1년 전 같은 날(2월 29일은 2월 28일로)."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _yoy(series_ends, series, latest):
    """latest end 대비 ~1년 전(±40일) 값. 없으면 None."""
    ld = date.fromisoformat(latest)
    best, bestgap = None, 41
    for en in series_ends:
        gap = abs((_year_ago(ld) - date.fromisoformat(en)).days)
        if gap <= bestgap:
            best, bestgap = en, gap
    return series.get(best) if best else None


def _m(x):
    return None if x is None else round(x / 1e6, 1)


def fetch_companyfacts(sym):
    """SEC companyfacts 원본(JSON). 실패하면 None."""
    cik = _sec_cik(sym)
    if not cik:
        return None
    try:
        return netutil.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                                headers=_SEC_UA, timeout=30)
    except Exception as e:
        log.warning(f"[fund] {sym}: companyfacts 조회 실패: {e}")
        return None


def _build_one(sym, facts=None):
    """facts를 주면 그 재무로 계산(점수 검증의 '그 시점 공시만' 재계산용), 없으면 SEC에서 받는다."""
    j = facts if facts is not None else fetch_companyfacts(sym)
    if not j:
        return None
    g = j["facts"].get("us-gaap", {})

    rev = _rev_quarters(g)
    gp = _fill_q4(_quarters(g, GP), _annuals(g, GP))
    opi = _fill_q4(_quarters(g, OPINC), _annuals(g, OPINC))
    # NI/LIAB/ASSETS는 현재 스코어링에 쓰이지 않아 계산하지 않는다(불필요한 SEC 데이터 순회 축소).
    # 현금흐름은 10-Q에 YTD 누적으로만 나와 ~90일 값만 고르면 매년 1분기만 남는다 → 누적 차분.
    ocf = _flow_quarters(g, OCF)
    capex = _flow_quarters(g, CAPEX)
    rnd = _fill_q4(_quarters(g, RND), _annuals(g, RND))
    cash = _instants(g, CASH)
    cash_sti = _instants(g, CASH_STI)
    sti_series = [_instants(g, [t]) for t in STI]
    dlt = _instants(g, DEBT_LT)
    dcur = _instants(g, DEBT_CUR)
    shares = _quarters(g, SHARES, 80, 100) or _quarters(g, SHARES, 80, 200)

    if not rev:
        return None
    ends = sorted(rev)
    latest = ends[-1]

    def series8(d):
        return [{"end": en, "cq": _cq(en), "v": _m(d.get(en))} for en in ends[-8:]]

    rev_l = rev[latest]
    rev_yoy = None
    prev_y = _yoy(ends, rev, latest)
    if prev_y:
        rev_yoy = round((rev_l / prev_y - 1) * 100, 1) if prev_y else None
    # 성장 가속: 직전 분기 YoY와 비교
    rev_yoy_prev = None
    if len(ends) >= 2:
        pe = ends[-2]
        py = _yoy(ends, rev, pe)
        if py:
            rev_yoy_prev = round((rev.get(pe, 0) / py - 1) * 100, 1)

    opm = round(opi[latest] / rev_l * 100, 1) if latest in opi and rev_l else None
    opm_prev = None
    py_end = None
    ld = date.fromisoformat(latest)
    for en in ends:
        if abs((_year_ago(ld) - date.fromisoformat(en)).days) <= 40:
            py_end = en
    if py_end and py_end in opi and rev.get(py_end):
        opm_prev = round(opi[py_end] / rev[py_end] * 100, 1)
    opm_delta = round(opm - opm_prev, 1) if (opm is not None and opm_prev is not None) else None

    gm = round(gp[latest] / rev_l * 100, 1) if latest in gp and rev_l else None
    gm_list = [round(gp[en] / rev[en] * 100, 1) if (en in gp and rev.get(en)) else None
               for en in ends[-8:]]
    opm_list = [round(opi[en] / rev[en] * 100, 1) if (en in opi and rev.get(en)) else None
                for en in ends[-8:]]

    def instlast(d):
        return d[max(d)] if d else None
    # 현금 = 현금성자산 + 단기투자자산(대형사는 국채·MMF를 단기투자로 들고 있어 빼면 순부채로 왜곡)
    cash_l, has_sti = _liquid_cash(cash, cash_sti, sti_series)
    debt_l = (instlast(dlt) or 0) + (instlast(dcur) or 0)
    netcash = _m(cash_l - debt_l) if cash_l is not None else None

    # TTM FCF
    ocf_ttm, capex_ttm = _ttm(ocf), _ttm(capex)
    fcf = _m(ocf_ttm - capex_ttm) if (ocf_ttm is not None and capex_ttm is not None) else None

    # 희석
    dil = None
    if shares:
        sends = sorted(shares)
        sl = sends[-1]
        sy = _yoy(sends, shares, sl)
        if sy:
            dil = round((shares[sl] / sy - 1) * 100, 1)

    rnd_pct = round(rnd[latest] / rev_l * 100, 1) if latest in rnd and rev_l else None

    # 부채→자산 브릿지 (최근 1년 변화)
    bridge = None
    if py_end:
        d_debt = None
        if dlt:
            dl_now = (instlast(dlt) or 0) + (instlast(dcur) or 0)
            # 1년 전 부채
            def at(d, tgt):
                best, gap = None, 45
                for en in d:
                    gg = abs((date.fromisoformat(tgt) - date.fromisoformat(en)).days)
                    if gg <= gap:
                        best, gap = en, gg
                return d.get(best) if best else None
            dl_prev = (at(dlt, py_end) or 0) + (at(dcur, py_end) or 0)
            d_debt = dl_now - dl_prev
        capex_yr = sum(capex[en] for en in sorted(capex)[-4:]) if len(capex) >= 4 else None
        if d_debt is not None and d_debt > 0 and capex_yr:
            bridge = {"d_debt": _m(d_debt), "capex": _m(capex_yr)}

    d = {
        "ticker": sym, "name": NAMES.get(sym, sym), "sector": SECTORS.get(sym, ""),
        "asof": latest, "cq": _cq(latest),
        "rev": rev_l and round(rev_l / 1e6, 1), "rev_yoy": rev_yoy,
        "rev_yoy_prev": rev_yoy_prev,
        "opm": opm, "opm_delta": opm_delta, "gm": gm,
        "netcash": netcash, "cash": _m(cash_l), "cash_incl_sti": has_sti, "debt": _m(debt_l),
        "fcf": fcf, "dilution": dil, "rnd_pct": rnd_pct, "bridge": bridge,
        # 최근 분기 희석 가중평균 주식수(백만 주) — 시가총액(주가×주식수) 계산용
        "shares": round(shares[max(shares)] / 1e6, 2) if shares else None,
        "moat_score": _moat_quant(gm, gm_list, opm, opm_list, rnd_pct),
        "series": {"rev": series8(rev), "opi": series8(opi)},
    }
    d.update(_axes(d))
    return d


def _clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def _moat_quant(gm_now, gm_list, opm_now, opm_list, rnd_pct):
    """해자 = 정량 프록시. 매출총이익률(가격결정력) 수준+안정성+추세가 1순위.
    GM 태그 없으면(예: AMZN/GOOGL) 영업이익률로 폴백(상한 낮춤). 둘 다 없으면 None."""
    use_gm = gm_now is not None and len([v for v in gm_list if v is not None]) >= 2
    if use_gm:
        now, series, lvl_cap, base = gm_now, gm_list, 62, 80.0
    elif opm_now is not None and len([v for v in opm_list if v is not None]) >= 2:
        now, series, lvl_cap, base = opm_now, opm_list, 48, 50.0   # 폴백은 상한↓
    else:
        return None
    vals = [v for v in series if v is not None]
    lvl = _clamp(now / base * lvl_cap, 0, lvl_cap)
    std = statistics.pstdev(vals) if len(vals) >= 3 else abs(vals[-1] - vals[0])
    stab = 26 if std <= 2 else 18 if std <= 5 else 8 if std <= 10 else 2
    avg = sum(vals) / len(vals)
    trend = 12 if now > avg + 1 else (6 if now >= avg - 1 else 0)
    rd = 4 if (rnd_pct or 0) >= 10 else 0               # 지속적 기술 투자 소량 가점
    return round(_clamp(lvl + stab + trend + rd))


def _axes(d):
    """4축 (성장·수익성경로·재무건전성·주주가치) → 신호등·부분점수, 종합점수, 태그."""
    yoy = d.get("rev_yoy")
    opm = d.get("opm")
    opd = d.get("opm_delta")
    nc = d.get("netcash")
    fcf = d.get("fcf")
    dil = d.get("dilution")

    # ① 성장 — 성장주 발굴의 핵심축. 저성장은 급감, 고성장은 급증.
    if yoy is None:
        g_sig, g_sc, g_lab = "y", 35, "성장률 산출 불가"
    else:
        g_sc = _clamp((yoy - 10) * 2.0)     # 15%→10 · 25%→30 · 40%→60 · 60%+→100
        accel = (d.get("rev_yoy_prev") is not None and yoy > d["rev_yoy_prev"] + 2)
        g_sig = "g" if yoy >= 25 else "y" if yoy >= 12 else "r"
        g_lab = f"매출 YoY {yoy:+.0f}%" + (" · 가속" if accel else "")

    # ② 수익성 경로
    if opm is None:
        p_sig, p_sc, p_lab = "y", 40, "마진 산출 불가"
    elif opm > 0:
        p_sig, p_sc = "g", _clamp(75 + opm / 2)
        p_lab = f"영업이익률 +{opm:.0f}% · 흑자"
    elif opd is not None and opd >= 3:
        p_sc = _clamp(45 + opd * 2.5)
        p_sig = "g" if opd >= 8 else "y"
        p_lab = f"적자 갭 축소 (Δ{opd:+.0f}%p)"
    else:
        p_sig, p_sc = "r", _clamp(30 + (opd or 0))
        p_lab = f"적자 갭 정체·확대 (Δ{(opd or 0):+.0f}%p)"

    # ③ 재무 건전성
    if nc is None:
        b_sig, b_sc, b_lab = "y", 40, "재무 산출 불가"
    elif nc > 0:
        b_sig, b_sc, b_lab = "g", 85, f"순현금 ${abs(nc)/1000:.1f}B"
    elif fcf is not None and fcf > 0:
        b_sig, b_sc, b_lab = "y", 55, "순부채·FCF 흑자"
    else:
        b_sig, b_sc, b_lab = "r", 30, "순부채·현금소진"

    # ④ 주주가치
    if dil is None:
        s_sig, s_sc, s_lab = "y", 45, "희석 산출 불가"
    else:
        s_sc = _clamp(100 - dil * 4 + (15 if (fcf or 0) > 0 else 0))
        s_sig = "g" if (dil <= 3 and (fcf or 0) >= 0) else "y" if dil <= 10 else "r"
        s_lab = f"주식수 {dil:+.0f}%" + (" · FCF흑자" if (fcf or 0) > 0 else " · FCF적자")

    # 성장 가중(0.42). 우량주(수익성·재무 만점이지만 저성장)가 상위권 못 오게.
    score = round(0.42 * g_sc + 0.20 * p_sc + 0.16 * b_sc + 0.22 * s_sc)
    # 저성장 게이트: 성장주 발굴이므로 저성장 대형주는 상한을 둔다.
    if yoy is not None:
        if yoy < 12:
            score = min(score, 50)
        elif yoy < 22:
            score = min(score, 72)

    # 한 줄 태그(가장 두드러진 특징)
    if opm and opm > 0 and yoy and yoy >= 30:
        tag = "고성장·흑자"
    elif opd is not None and opd >= 3 and opm is not None and opm < 0:
        tag = "적자 갭 축소·투자형"
    elif yoy and yoy >= 60:
        tag = "초고성장"
    elif dil is not None and dil > 12:
        tag = "성장하나 희석 큼"
    elif p_sig == "r":
        tag = "적자 갭 정체"
    else:
        tag = "성장 지속"

    return {
        "score": score,
        "axes": {
            "growth": {"sig": g_sig, "sc": round(g_sc), "lab": g_lab},
            "path": {"sig": p_sig, "sc": round(p_sc), "lab": p_lab},
            "balance": {"sig": b_sig, "sc": round(b_sc), "lab": b_lab},
            "shareholder": {"sig": s_sig, "sc": round(s_sc), "lab": s_lab},
        },
        "tag": tag,
    }


def update_score_history(funds: list[dict[str, Any]], today: str,
                         path: str = "data/score_history.json", keep: int = 40) -> dict[str, list]:
    """종목별 종합점수 이력에 한 줄 추가. 직전 기록과 점수·분기가 같으면 추가하지 않는다.

    {ticker: [{"date": "YYYY-MM-DD", "cq": "2026-2", "score": 62}, ...]} (오래된 것부터, 최대 keep개).
    점수 백테스트(이후 수익률 비교)와 화면의 '지난 변화 대비 ▲▼'에 쓰인다."""
    try:
        hist = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    for d in funds:
        rows = hist.setdefault(d["ticker"], [])
        last = rows[-1] if rows else None
        if last and last.get("score") == d.get("score") and last.get("cq") == d.get("cq"):
            continue
        if last and last.get("date") == today:
            rows.pop()                      # 같은 날 여러 번 갱신되면 마지막 값만
        rows.append({"date": today, "cq": d.get("cq"), "score": d.get("score")})
        del rows[:-keep]
    json.dump(hist, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return hist


def _load_json(path: str, default: Any) -> Any:
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build_fundamentals(path: str = "data/fundamentals.json",
                       tickers: list[str] | None = None,
                       screen_path: str = "data/screen.json",
                       universe_path: str = "data/universe.json",
                       cache_path: str = "data/fund_cache.json",
                       max_age_days: int = 7) -> list[dict[str, Any]]:
    """정밀 분석(4축 점수 등) 대상 = 관심 종목(EARNINGS_TICKERS) + 1차 선별(나스닥 100) 계산 가능 종목.

    관심 종목은 매번 새로 계산한다. 나머지는 증분: 1차 선별이 준 최신 공시번호(accn)가 캐시와 같고
    max_age_days 안에 계산했으면 캐시를 재사용(종목별 SEC 전체 재무 평균 3MB를 매번 받지 않기 위해)."""
    watch = list(tickers or EARNINGS_TICKERS)
    screen = {r["t"]: r for r in _load_json(screen_path, {}).get("rows", [])}
    uni = {r["t"]: r for r in _load_json(universe_path, {}).get("rows", [])}
    cache = _load_json(cache_path, {})
    today = date.today()
    order = watch + [t for t in screen if t not in watch]
    out, fetched, reused = [], 0, 0
    for t in order:
        c = cache.get(t) or {}
        fresh = (t not in watch and c.get("d") and c.get("accn") == screen.get(t, {}).get("accn")
                 and (today - date.fromisoformat(c.get("built", "1970-01-01"))).days < max_age_days)
        if fresh:
            d = c["d"]
            reused += 1
        else:
            d = _build_one(t)
            fetched += 1
            time.sleep(0.3)
            if not d:
                log.info(f"[fund] {t}: skip")
                continue
            if t not in NAMES and uni.get(t, {}).get("name"):
                d["name"] = uni[t]["name"]
            if t not in SECTORS and uni.get(t, {}).get("sector"):
                d["sector"] = uni[t]["sector"]
            cache[t] = {"accn": screen.get(t, {}).get("accn"), "built": today.isoformat(), "d": d}
        d["watch"] = t in watch
        out.append(d)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log.info(f"[fund] 저장 {len(out)}개(새로 계산 {fetched} · 캐시 {reused}) → {path}")
    if out:
        hist_path = os.path.join(os.path.dirname(path) or ".", "score_history.json")
        update_score_history(out, today.isoformat(), hist_path)
    return out


# =========================================================
# 정성 분석 (10-K 사업·리스크 → AI 해자·산업필연성·확장)
# =========================================================
import html as _htmlmod  # noqa: E402
import re as _re  # noqa: E402


def _last_section(t, start_pat, maxlen):
    """start 패턴의 '마지막' occurrence(=목차 아닌 실제 본문)에서 maxlen만큼."""
    pos = [m.start() for m in _re.finditer(start_pat, t, _re.I)]
    if not pos:
        return ""
    s = pos[-1]
    return t[s:s + maxlen]


def _sec_10k_sections(sym):
    """최신 10-K의 사업(Item1)·리스크(Item1A) 발췌 + accession. 실패 시 None."""
    cik = _sec_cik(sym)
    if not cik:
        return None
    try:
        rec = netutil.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json",
                               headers=_SEC_UA, timeout=20)["filings"]["recent"]
        acc = doc = when = None
        for form, a, pd, adt in zip(rec["form"], rec["accessionNumber"],
                                    rec["primaryDocument"], rec["acceptanceDateTime"]):
            if form == "10-K":
                acc, doc, when = a, pd, adt
                break
        if not acc:
            return None
        accn = acc.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{doc}"
        raw = netutil.get(url, headers=_SEC_UA, timeout=30).text
        text = _htmlmod.unescape(_re.sub(r"\s+", " ",
                                         _re.sub(r"<[^>]+>", " ", raw))).strip()
        biz = _last_section(text, r"item\s*1\.?\s+business", 7000)
        risk = _last_section(text, r"item\s*1a\.?\s+risk\s+factors", 8000)
        if len(biz) < 500 and len(risk) < 500:
            return None
        return {"acc": acc, "when": when, "biz": biz, "risk": risk}
    except Exception as e:
        log.warning(f"[qual] {sym}: 10-K 조회 실패: {e}")
        return None


def _gen_qual(client, d, sec):
    name, sym = d["name"], d["ticker"]
    prof = (f"매출 {d.get('rev')}M·YoY {d.get('rev_yoy')}%, 영업이익률 {d.get('opm')}%"
            f"(전년비 Δ{d.get('opm_delta')}%p), 매출총이익률 {d.get('gm')}%, "
            f"순현금 {d.get('netcash')}M, 주식수 YoY {d.get('dilution')}%, "
            f"R&D/매출 {d.get('rnd_pct')}%")
    prompt = (
        f"{name}({sym}, {d.get('sector','')})의 성장주 정성 분석이다. "
        "아래 10-K 발췌와 재무 프로파일에 근거해 한국어 JSON만 출력하라.\n"
        f"[재무 프로파일]\n{prof}\n"
        f"[10-K 사업 섹션 발췌]\n{sec['biz'][:6000]}\n"
        f"[10-K 리스크 섹션 발췌]\n{sec['risk'][:6000]}\n\n"
        "규칙:\n"
        "- 발췌·널리 알려진 사실만. 수치·주장 지어내지 말 것. 투자 조언 금지.\n"
        "- 각 항목은 한국어로 간결하게(2문장 이내). 애널리스트 톤, 냉철하게.\n"
        "- moat(경쟁우위/해자): 진입장벽·전환비용·규모·기술·네트워크·가격결정력(높은 GM) 등 근거로.\n"
        "- moat_score: 해자 강도 주관 점수 0~100 정수.\n"
        "- necessity(산업 필연성): 이 산업/제품이 미래에 구조적으로 필요한 이유·수요 지속성.\n"
        "- expansion(확장 시나리오): TAM 확장·인접시장·신제품으로 가치가 커지는 경로.\n"
        "- risk_note(핵심 리스크): 리스크 섹션에서 가장 중요한 것 1개, 한 문장.\n"
        '형식: {"moat":"","moat_score":0,"necessity":"","expansion":"","risk_note":""}'
    )
    resp = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}, max_tokens=700)
    return json.loads(resp.choices[0].message.content)


def build_qualitative(fund_path: str = "data/fundamentals.json",
                      cache_path: str = "data/qual_cache.json",
                      client: Any = None) -> list[dict[str, Any]]:
    """fundamentals.json 각 종목에 10-K 기반 정성 분석(qual)을 추가.
    qual_cache.json에 (ticker→acc,qual) 캐시 → 10-K 바뀔 때만 재생성(비용 절감)."""
    if client is None:
        client = get_openai_client()
    try:
        funds = json.load(open(fund_path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    try:
        cache = json.load(open(cache_path, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    for d in funds:
        t = d["ticker"]
        if t not in EARNINGS_TICKERS:      # 정성 분석은 관심 종목만(비용·시간)
            continue
        sec = _sec_10k_sections(t)
        if not sec:
            if cache.get(t, {}).get("qual"):
                d["qual"] = cache[t]["qual"]
            log.info(f"[qual] {t}: 10-K 없음")
            continue
        if cache.get(t, {}).get("acc") == sec["acc"] and cache[t].get("qual"):
            d["qual"] = cache[t]["qual"]
            log.info(f"[qual] {t}: 캐시 재사용")
            continue
        try:
            q = _gen_qual(client, d, sec)
            q["src"] = sec["when"][:10] if sec.get("when") else ""
            d["qual"] = q
            cache[t] = {"acc": sec["acc"], "qual": q}
            log.info(f"[qual] {t}: 생성 (해자 {q.get('moat_score')}점)")
        except Exception as e:
            log.warning(f"[qual] {t}: 실패 {e}")
        time.sleep(0.3)
    json.dump(funds, open(fund_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log.info(f"[qual] 완료 → {fund_path}")
    return funds


if __name__ == "__main__":
    from settings import configure_logging
    configure_logging()
    build_fundamentals("fundamentals_test.json",
                       ["RKLB", "PLTR", "HIMS", "IREN", "NVDA", "RDW"])
