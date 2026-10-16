# -*- coding: utf-8 -*-
"""성장주 '전체 선별' 대상(나스닥 100) 목록·현재가·섹터 수집.

입력: 나스닥 공식 API(구성 종목·현재가·시총), S&P 500 구성표(GICS 섹터), SEC submissions(SIC 업종코드)
출력: data/universe.json {asof, rows:[{t, name, px, mcap_nq, sector, sector_src}]}
실행: python universe.py (단독 갱신). 평소엔 main.py refresh가 build_universe() 호출
관련: screen.py(1차 선별), fundamentals.py(정밀 분석 대상), render/growth.py(전체 선별 표)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from typing import Any

import netutil
from sec import _SEC_UA, _sec_cik

log = logging.getLogger(__name__)

NDX_API = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
NDX_HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124",
           "Accept": "application/json", "Origin": "https://www.nasdaq.com",
           "Referer": "https://www.nasdaq.com/"}
SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

GICS_KO = {"Information Technology": "정보기술", "Health Care": "헬스케어", "Financials": "금융",
           "Consumer Discretionary": "경기소비재", "Communication Services": "커뮤니케이션",
           "Industrials": "산업재", "Consumer Staples": "필수소비재", "Energy": "에너지",
           "Utilities": "유틸리티", "Real Estate": "부동산", "Materials": "소재"}
# SEC SIC 코드 → GICS 섹터 근사. 위에서부터 첫 일치.
SIC_MAP = [((2830, 2836), "헬스케어"), ((3841, 3851), "헬스케어"), ((8000, 8099), "헬스케어"),
           ((8731, 8731), "헬스케어"), ((3570, 3579), "정보기술"), ((3600, 3699), "정보기술"),
           ((3820, 3829), "정보기술"), ((7370, 7379), "정보기술"), ((4800, 4899), "커뮤니케이션"),
           ((7810, 7819), "커뮤니케이션"), ((2710, 2741), "커뮤니케이션"), ((1300, 1399), "에너지"),
           ((2900, 2999), "에너지"), ((4900, 4999), "유틸리티"), ((6798, 6798), "부동산"),
           ((6500, 6599), "부동산"), ((6000, 6799), "금융"), ((3711, 3716), "경기소비재"),
           ((5200, 5399), "경기소비재"), ((5500, 5999), "경기소비재"), ((7000, 7099), "경기소비재"),
           ((5400, 5499), "필수소비재"), ((2000, 2199), "필수소비재"), ((3720, 3729), "산업재"),
           ((3760, 3769), "산업재"), ((3400, 3599), "산업재"), ((4000, 4799), "산업재"),
           ((8700, 8799), "산업재"), ((1000, 1499), "소재"), ((2800, 2899), "소재"), ((3300, 3399), "소재")]
# SIC가 실제 사업과 크게 어긋나는 경우만 수동 보정(근거: 회사 공시 사업 설명)
SECTOR_OVERRIDE = {"MELI": "경기소비재", "SPCX": "산업재"}


def sic_sector(code: int) -> str:
    for (lo, hi), name in SIC_MAP:
        if lo <= code <= hi:
            return name
    return "기타"


def clean_name(n: str) -> str:
    n = re.sub(r"\s+(Class [A-C] )?(Common Stock|Ordinary Shares|American Depositary Shares).*$", "", n)
    return n.replace(", Inc.", "").replace(" Inc.", "").strip()


def _num(s: str | None) -> float | None:
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def build_universe(path: str = "data/universe.json") -> dict[str, Any]:
    """나스닥 100 구성·현재가 + 섹터(GICS 우선, 없으면 SIC). 섹터는 이전 파일 캐시를 재사용한다."""
    try:
        prev = {r["t"]: r for r in json.load(open(path, encoding="utf-8")).get("rows", [])}
    except (OSError, ValueError):
        prev = {}
    j = netutil.get_json(NDX_API, headers=NDX_HDR, timeout=30)["data"]
    gics = {}
    try:
        text = netutil.get(SP500_CSV, timeout=30).text
        gics = {r["Symbol"].replace(".", "-"): r["GICS Sector"] for r in csv.DictReader(io.StringIO(text))}
    except Exception as e:  # noqa: BLE001 — 섹터는 부가정보, 실패해도 진행
        log.warning(f"[universe] S&P 구성표 실패: {e}")
    rows = []
    for x in j["data"]["rows"]:
        t = x["symbol"]
        sec, src = None, ""
        if t in SECTOR_OVERRIDE:
            sec, src = SECTOR_OVERRIDE[t], "수동 보정"
        elif t in gics:
            sec, src = GICS_KO.get(gics[t], gics[t]), "GICS"
        elif prev.get(t, {}).get("sector"):
            sec, src = prev[t]["sector"], prev[t].get("sector_src", "")
        else:
            cik = _sec_cik(t)
            if cik:
                try:
                    sub = netutil.get_json(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json",
                                           headers=_SEC_UA, timeout=30)
                    code = int(sub.get("sic") or 0)
                    sec, src = sic_sector(code), f"SIC {code} {sub.get('sicDescription', '')}".strip()
                    time.sleep(0.15)
                except Exception as e:  # noqa: BLE001
                    log.warning(f"[universe] {t} SIC 조회 실패: {e}")
        rows.append({"t": t, "name": clean_name(x.get("companyName", "")), "px": _num(x.get("lastSalePrice")),
                     "mcap_nq": (_num(x.get("marketCap")) or 0) / 1e6 or None,
                     "sector": sec or "", "sector_src": src})
    data = {"asof": j.get("date", ""), "rows": rows}
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log.info(f"[universe] 나스닥 100 {len(rows)}개 · 기준 {data['asof']} → {path}")
    return data


if __name__ == "__main__":
    from settings import configure_logging
    configure_logging()
    build_universe()
