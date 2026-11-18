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
# Ostium 공식 SDK(@ostium/builder-sdk)의 기본 서브그래프 엔드포인트. 같은 스키마, 사이트 도메인 CORS 허용.
# 예전 Ormi 공개 엔드포인트는 2026-11-18부터 요청 1건에도 429(Too many requests)라 예비로만 둔다.
URL = "https://builder.prod.bedrock.ostium.io/v1/subgraph/gn"
URLS = (URL,
        "https://api.subgraph.ormilabs.com/api/public/"
        "67a599d5-c8d2-4cc4-9c4d-2975a97bc5d8/subgraphs/ost-prod/live/gn")
STALE_HOURS = 12      # 모든 엔드포인트가 실패해도 기존 스냅샷이 이보다 새로우면 실패로 치지 않음

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


def _fetch_from(url):
    out, skip = [], 0
    while True:
        query = ('{ trades(first:1000, skip:%d, where:{isOpen:true}){ '
                 'isBuy leverage collateral trader pair{ from to } } }' % skip)
        r = netutil.post_json(url, {"query": query}, timeout=40, backoff=3)
        body = r.json()
        if body.get("errors") or not isinstance((body.get("data") or {}).get("trades"), list):
            raise RuntimeError(f"서브그래프 오류 응답: {str(body)[:200]}")
        t = body["data"]["trades"]
        out += t
        if len(t) < 1000 or skip > 8000:
            break
        skip += 1000
    return out


def _fetch_all(urls=URLS):
    """엔드포인트를 순서대로 시도. 하나라도 성공하면 그 결과(페이지를 섞지 않도록 엔드포인트 단위로 통째 재시도)."""
    errs = []
    for url in urls:
        try:
            return _fetch_from(url)
        except Exception as e:
            host = url.split("/")[2] if "//" in url else url
            log.warning(f"[rwa] {host} 실패: {e}")
            errs.append(f"{host}: {e}")
    raise RuntimeError("모든 Ostium 엔드포인트 실패 — " + " | ".join(errs))


def _snapshot_age_h(path, now=None):
    """기존 스냅샷 asof(KST) 기준 경과 시간. 없거나 읽을 수 없으면 None."""
    try:
        asof = json.load(open(path, encoding="utf-8"))["asof"]
        dt = datetime.strptime(asof, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    except Exception:
        return None
    return ((now or datetime.now(KST)) - dt).total_seconds() / 3600


def refresh(out_path="docs/rwamap.json", stale_hours=STALE_HOURS):
    """정기 갱신. 일시 장애면 기존 스냅샷을 유지하고 경고만(같은 단계의 고래·히트맵 갱신까지 막지 않도록).
    스냅샷이 stale_hours보다 오래됐으면 실패(종료코드 1)로 알린다. 반환: 종료코드."""
    try:
        build_rwa(out_path)
        return 0
    except Exception as e:
        age = _snapshot_age_h(out_path)
        print(f"::warning title=지도(Ostium) 갱신 실패::기존 스냅샷 유지"
              f"({'없음' if age is None else f'{age:.1f}시간 전'}) — {e}")
        if age is not None and age <= stale_hours:
            log.warning(f"[rwa] 갱신 실패, 기존 스냅샷 유지({age:.1f}h): {e}")
            return 0
        log.error(f"[rwa] 갱신 실패, 스냅샷이 없거나 {stale_hours}시간 넘게 오래됨: {e}")
        return 1


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
    # cfg: 분류 기준·표시명. 지도 탭이 브라우저에서 Ostium을 직접 조회해 같은 규칙으로 다시 집계할 때 쓴다(규칙 단일 출처).
    cfg = {"crypto": sorted(CRYPTO), "index": sorted(INDEX), "commod": sorted(COMMOD),
           "forex": sorted(FOREX_FROM), "bond": sorted(BOND), "disp": DISP, "url": URL}
    data = {"asof": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
            "positions": len(trades), "assets": assets, "cfg": cfg}
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
        sys.exit(refresh("docs/rwamap.json"))
    else:
        build_rwa("rwamap_test.json")
