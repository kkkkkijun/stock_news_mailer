# -*- coding: utf-8 -*-
"""SEC EDGAR 접근 헬퍼(CIK 조회, 8-K 보도자료 본문).

입력: SEC EDGAR 공개 API(company_tickers.json, submissions, Archives 문서)
출력: 종목별 CIK, 최근 실적 8-K(Item 2.02) 보도자료 본문(dict) 또는 None
실행: 별도 실행 없음 — earnings.py/fundamentals.py가 import해서 사용
관련: settings.py, earnings.py, fundamentals.py
"""
import re

import requests

from settings import KST

# =========================================================
# 실적 보고서용 SEC 접근 헬퍼
#   CIK 조회 + 최근 8-K(Item 2.02) 보도자료 원문 텍스트 추출.
# =========================================================
_SEC_UA = {"User-Agent": "stock-news-mailer research (contact: tjrlwns93@ermore.co.kr)"}
_CIK_CACHE = None


def _sec_cik(sym):
    global _CIK_CACHE
    if _CIK_CACHE is None:
        try:
            ct = requests.get("https://www.sec.gov/files/company_tickers.json",
                              headers=_SEC_UA, timeout=15).json()
            _CIK_CACHE = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in ct.values()}
        except Exception:
            _CIK_CACHE = {}
    return _CIK_CACHE.get(sym)


def _sec_8k_press(sym):
    """최근 실적 8-K(Item 2.02)의 보도자료 원문 텍스트 + 메타. 실패 시 None."""
    import re
    import html as _html
    cik = _sec_cik(sym)
    if not cik:
        return None
    try:
        rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                           headers=_SEC_UA, timeout=15).json()["filings"]["recent"]
        acc = accept = None
        for form, a, items, adt in zip(rec["form"], rec["accessionNumber"],
                                       rec["items"], rec["acceptanceDateTime"]):
            if form == "8-K" and "2.02" in (items or ""):
                acc, accept = a, adt
                break
        if not acc:
            return None
        accn = acc.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}"
        # 문서 목록: index.json(타입·크기) 우선, 실패 시 디렉터리 HTML 스크랩.
        htms = []
        try:
            for it in requests.get(base + "/index.json", headers=_SEC_UA,
                                   timeout=15).json()["directory"]["item"]:
                n = it.get("name", "")
                if n.lower().endswith((".htm", ".html")):
                    htms.append((n, (it.get("type") or ""), int(it.get("size") or 0)))
        except Exception:
            for n in re.findall(r'href="([^"]+\.html?)"',
                                requests.get(base + "/", headers=_SEC_UA, timeout=15).text):
                htms.append((n.split("/")[-1], "", 0))
        pr = None
        for n, ty, _sz in htms:                       # 1) EX-99* 타입
            if ty.upper().startswith("EX-99"):
                pr = n
                break
        if not pr:                                    # 2) 이름 패턴
            for n, ty, _sz in htms:
                if re.search(r"ex.?-?99|press|earn|release", n, re.I):
                    pr = n
                    break
        if not pr:                                    # 3) 래퍼/인덱스 제외 후 가장 큰 htm
            cand = sorted([(sz, n) for n, ty, sz in htms
                           if not re.search(r"index|form|8-?k|primary", n, re.I)],
                          reverse=True)
            pr = cand[0][1] if cand else (htms[0][0] if htms else None)
        if not pr:
            return None
        url = base + "/" + pr
        raw = requests.get(url, headers=_SEC_UA, timeout=15).text
        text = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))).strip()
        return {"text": text[:7000], "url": url, "acc": acc, "accept": accept}
    except Exception:
        return None


def _report_kdate(accept):
    """8-K 접수시각(ET ISO) → KST (yymmdd, YYYY-MM-DD)."""
    from datetime import datetime as _dt
    for s in (accept, re.sub(r"\.\d+", "", accept or "")):
        try:
            return (_dt.fromisoformat(s).astimezone(KST).strftime("%y%m%d"),
                    _dt.fromisoformat(s).astimezone(KST).strftime("%Y-%m-%d"))
        except (ValueError, TypeError, AttributeError):
            continue
    return "", ""
