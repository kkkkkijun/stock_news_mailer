"""지도 탭 — Ostium(온체인 RWA 파생) 서브그래프 기반.
암호화폐/주식/지수/원자재 4개 카테고리 자산별 롱·숏·레버 집계 → docs/rwamap.json.

입력: Ostium 서브그래프(Arbitrum) API
출력: docs/rwamap.json
실행: python rwa.py refresh (docs/rwamap.json 갱신) 또는 python rwa.py (테스트용 rwamap_test.json 생성)
관련: main.py, publish_site.py, netutil.py
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

import netutil

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
URL = ("https://api.subgraph.ormilabs.com/api/public/"
       "67a599d5-c8d2-4cc4-9c4d-2975a97bc5d8/subgraphs/ost-prod/live/gn")

CRYPTO = {"BTC", "ETH", "ADA", "BNB", "HYPE", "LINK", "SOL", "TRX", "XRP"}
INDEX = {"SPX", "DJI", "NDX", "DAX", "FTSE", "HSI", "NIK", "KR2550"}
COMMOD = {"BRENT", "CL", "HG", "XAU", "XAG", "XPD", "XPT", "UNG", "URA",
          "REMX", "XLE"}
FOREX_FROM = {"EUR", "GBP", "AUD", "NZD", "CAD", "JPY", "CHF", "USD"}
BOND = {"HYG", "TLT"}
DISP = {"XAU": "금", "XAG": "은", "HG": "구리", "CL": "WTI", "BRENT": "브렌트",
        "XPD": "팔라듐", "XPT": "백금", "URA": "우라늄", "REMX": "희토류",
        "XLE": "에너지", "UNG": "천연가스", "NDX": "나스닥", "DJI": "다우",
        "NIK": "닛케이", "HSI": "항셍", "KR2550": "한국"}


def _cat(sym, to):
    if sym in FOREX_FROM or to != "USD":
        return None            # 환 제외
    if sym in BOND:
        return None            # 채권 제외
    if sym in CRYPTO:
        return "암호화폐"
    if sym in INDEX:
        return "지수"
    if sym in COMMOD:
        return "원자재"
    return "주식"


def _fetch_all():
    out, skip = [], 0
    while True:
        query = ('{ trades(first:1000, skip:%d, where:{isOpen:true}){ '
                 'isBuy leverage collateral trader pair{ from to } } }' % skip)
        r = netutil.post_json(URL, {"query": query}, timeout=40)
        t = r.json().get("data", {}).get("trades", [])
        out += t
        if len(t) < 1000 or skip > 8000:
            break
        skip += 1000
    return out


def build_rwa(out_path: str = "docs/rwamap.json") -> dict[str, Any]:
    trades = _fetch_all()
    agg = {}
    for x in trades:
        sym = x["pair"]["from"]
        c = _cat(sym, x["pair"]["to"])
        if not c:
            continue
        usd = (float(x["collateral"]) / 1e6) * (float(x["leverage"]) / 100.0)
        if usd <= 0:
            continue
        a = agg.setdefault(sym, {"cat": c, "lU": 0.0, "sU": 0.0, "levS": 0.0,
                                 "levC": 0, "traders": set()})
        if x["isBuy"]:
            a["lU"] += usd
        else:
            a["sU"] += usd
        a["levS"] += float(x["leverage"]) / 100.0
        a["levC"] += 1
        a["traders"].add(x["trader"])
    assets = []
    for sym, a in agg.items():
        tot = a["lU"] + a["sU"]
        if tot <= 0:
            continue
        assets.append({
            "t": sym, "disp": DISP.get(sym, sym), "cat": a["cat"],
            "l": round(a["lU"] / 1e6, 3), "s": round(a["sU"] / 1e6, 3),
            "tot": round(tot / 1e6, 3), "n": len(a["traders"]),
            "lev": round(a["levS"] / a["levC"], 1) if a["levC"] else 0,
            "net": round((a["lU"] - a["sU"]) / tot, 3),
        })
    assets.sort(key=lambda z: -z["tot"])
    data = {"asof": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            "positions": len(trades), "assets": assets}
    json.dump(data, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    cats = {}
    for z in assets:
        cats[z["cat"]] = cats.get(z["cat"], 0) + 1
    log.info(f"[rwa] 포지션 {len(trades)} · 자산 {len(assets)} · 카테고리 {cats} → {out_path}")
    return data


if __name__ == "__main__":
    import sys
    from settings import configure_logging
    configure_logging()
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        build_rwa("docs/rwamap.json")
    else:
        build_rwa("rwamap_test.json")
