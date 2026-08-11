"""성장주 발굴 — SEC XBRL companyfacts 기반 재무 파이프라인.
main.py의 _sec_cik / _SEC_UA 재사용. build_fundamentals()가 data/fundamentals.json 생성.
"""
import json
import time
from datetime import date

import requests

import main

REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
       "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
GP = ["GrossProfit"]
OPINC = ["OperatingIncomeLoss"]
NI = ["NetIncomeLoss"]
OCF = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment"]
RND = ["ResearchAndDevelopmentExpense"]
ASSETS = ["Assets"]
LIAB = ["Liabilities"]
CASH = ["CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
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


def _instants(gaap, tags):
    usd = _pick(gaap, tags, dur=False)
    if not usd:
        return {}
    seen = {e["end"]: e["val"] for e in usd if e.get("end") and "start" not in e}
    if not seen:
        seen = {e["end"]: e["val"] for e in usd if e.get("end")}
    return dict(sorted(seen.items()))


def _yoy(series_ends, series, latest):
    """latest end 대비 ~1년 전(±40일) 값. 없으면 None."""
    ld = date.fromisoformat(latest)
    best, bestgap = None, 41
    for en in series_ends:
        gap = abs((ld.replace(year=ld.year - 1) - date.fromisoformat(en)).days)
        if gap <= bestgap:
            best, bestgap = en, gap
    return series.get(best) if best else None


def _m(x):
    return None if x is None else round(x / 1e6, 1)


def _build_one(sym):
    cik = main._sec_cik(sym)
    if not cik:
        return None
    try:
        j = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                         headers=main._SEC_UA, timeout=30).json()
    except Exception:
        return None
    g = j["facts"].get("us-gaap", {})

    rev = _fill_q4(_quarters(g, REV), _annuals(g, REV))
    gp = _fill_q4(_quarters(g, GP), _annuals(g, GP))
    opi = _fill_q4(_quarters(g, OPINC), _annuals(g, OPINC))
    ni = _fill_q4(_quarters(g, NI), _annuals(g, NI))
    ocf = _fill_q4(_quarters(g, OCF), _annuals(g, OCF))
    capex = _fill_q4(_quarters(g, CAPEX), _annuals(g, CAPEX))
    rnd = _fill_q4(_quarters(g, RND), _annuals(g, RND))
    cash = _instants(g, CASH)
    liab = _instants(g, LIAB)
    assets = _instants(g, ASSETS)
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
        if abs((ld.replace(year=ld.year - 1) - date.fromisoformat(en)).days) <= 40:
            py_end = en
    if py_end and py_end in opi and rev.get(py_end):
        opm_prev = round(opi[py_end] / rev[py_end] * 100, 1)
    opm_delta = round(opm - opm_prev, 1) if (opm is not None and opm_prev is not None) else None

    gm = round(gp[latest] / rev_l * 100, 1) if latest in gp and rev_l else None

    def instlast(d):
        return d[max(d)] if d else None
    cash_l = instlast(cash)
    debt_l = (instlast(dlt) or 0) + (instlast(dcur) or 0)
    netcash = _m(cash_l - debt_l) if cash_l is not None else None

    # TTM FCF
    def ttm(d):
        vals = [d[en] for en in sorted(d)[-4:]]
        return sum(vals) if len(vals) == 4 else None
    ocf_ttm, capex_ttm = ttm(ocf), ttm(capex)
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
        "netcash": netcash, "cash": _m(cash_l), "debt": _m(debt_l),
        "fcf": fcf, "dilution": dil, "rnd_pct": rnd_pct, "bridge": bridge,
        "series": {"rev": series8(rev), "opi": series8(opi)},
    }
    d.update(_axes(d))
    return d


def _clamp(x, lo=0, hi=100):
    return max(lo, min(hi, x))


def _axes(d):
    """4축 (성장·수익성경로·재무건전성·주주가치) → 신호등·부분점수, 종합점수, 태그."""
    yoy = d.get("rev_yoy")
    opm = d.get("opm")
    opd = d.get("opm_delta")
    nc = d.get("netcash")
    fcf = d.get("fcf")
    dil = d.get("dilution")

    # ① 성장
    if yoy is None:
        g_sig, g_sc, g_lab = "y", 40, "성장률 산출 불가"
    else:
        g_sc = _clamp(yoy * 1.6)
        accel = (d.get("rev_yoy_prev") is not None and yoy > d["rev_yoy_prev"] + 2)
        g_sig = "g" if yoy >= 25 else "y" if yoy >= 10 else "r"
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

    score = round(0.30 * g_sc + 0.25 * p_sc + 0.25 * b_sc + 0.20 * s_sc)

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


def build_fundamentals(path="data/fundamentals.json", tickers=None):
    tickers = tickers or main.EARNINGS_TICKERS
    out = []
    for t in tickers:
        d = _build_one(t)
        if d:
            out.append(d)
            print(f"[fund] {t}: 매출 {d['rev']}M YoY {d['rev_yoy']}% · "
                  f"영업마진 {d['opm']}%(Δ{d['opm_delta']}) · 순현금 {d['netcash']}M · "
                  f"희석 {d['dilution']}%")
        else:
            print(f"[fund] {t}: skip")
        time.sleep(0.3)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[fund] 저장 {len(out)}개 → {path}")
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
    cik = main._sec_cik(sym)
    if not cik:
        return None
    try:
        rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                           headers=main._SEC_UA, timeout=20).json()["filings"]["recent"]
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
        raw = requests.get(url, headers=main._SEC_UA, timeout=30).text
        text = _htmlmod.unescape(_re.sub(r"\s+", " ",
                                         _re.sub(r"<[^>]+>", " ", raw))).strip()
        biz = _last_section(text, r"item\s*1\.?\s+business", 7000)
        risk = _last_section(text, r"item\s*1a\.?\s+risk\s+factors", 8000)
        if len(biz) < 500 and len(risk) < 500:
            return None
        return {"acc": acc, "when": when, "biz": biz, "risk": risk}
    except Exception:
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
        model=main.SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}, max_tokens=700)
    return json.loads(resp.choices[0].message.content)


def build_qualitative(fund_path="data/fundamentals.json",
                      cache_path="data/qual_cache.json", client=None):
    """fundamentals.json 각 종목에 10-K 기반 정성 분석(qual)을 추가.
    qual_cache.json에 (ticker→acc,qual) 캐시 → 10-K 바뀔 때만 재생성(비용 절감)."""
    if client is None:
        client = main.get_openai_client()
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
        sec = _sec_10k_sections(t)
        if not sec:
            if cache.get(t, {}).get("qual"):
                d["qual"] = cache[t]["qual"]
            print(f"[qual] {t}: 10-K 없음")
            continue
        if cache.get(t, {}).get("acc") == sec["acc"] and cache[t].get("qual"):
            d["qual"] = cache[t]["qual"]
            print(f"[qual] {t}: 캐시 재사용")
            continue
        try:
            q = _gen_qual(client, d, sec)
            q["src"] = sec["when"][:10] if sec.get("when") else ""
            d["qual"] = q
            cache[t] = {"acc": sec["acc"], "qual": q}
            print(f"[qual] {t}: 생성 (해자 {q.get('moat_score')}점)")
        except Exception as e:
            print(f"[qual] {t}: 실패 {e}")
        time.sleep(0.3)
    json.dump(funds, open(fund_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"[qual] 완료 → {fund_path}")
    return funds


if __name__ == "__main__":
    build_fundamentals("fundamentals_test.json",
                       ["RKLB", "PLTR", "HIMS", "IREN", "NVDA", "RDW"])
