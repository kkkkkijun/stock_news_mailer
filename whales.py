"""고래 추적 — Hyperliquid 무료 공개 API.
build_whale_list(): 리더보드에서 상위 고래 주소 선별(하루 1회).
build_whales(): 고래별 포지션 스냅샷 → 코인별 롱/숏·레버 집계(15분).

입력: Hyperliquid leaderboard API, clearinghouseState API
출력: docs/whales.json
실행: python whales.py refresh (docs/whales.json 갱신) 또는 python whales.py [N] (테스트용 wl_test.json/wh_test.json 생성)
관련: main.py, publish_site.py, netutil.py
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import netutil

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
INFO = "https://api.hyperliquid.xyz/info"
LB = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
HDR = {"Content-Type": "application/json"}


def _now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M")


def build_whale_list(path: str = "data/whale_list.json", top: int = 90,
                    min_acct: int = 50000) -> list[str]:
    """계정가치 큰 순 + allTime 수익 양수인 상위 top명."""
    rows = netutil.get(LB, timeout=90).json()["leaderboardRows"]

    def sc(r):
        wp = dict(r.get("windowPerformances", []))
        return (float(r.get("accountValue") or 0),
                float(wp.get("allTime", {}).get("pnl") or 0))
    good = [r for r in rows if sc(r)[1] > 0 and sc(r)[0] >= min_acct]
    good.sort(key=lambda r: sc(r)[0], reverse=True)
    addrs = [r["ethAddress"] for r in good[:top]]
    json.dump({"asof": _now(), "addrs": addrs},
              open(path, "w", encoding="utf-8"), ensure_ascii=False)
    log.info(f"[whales] 고래 목록 {len(addrs)}명 저장")
    return addrs


def _mids():
    try:
        return netutil.post_json(INFO, {"type": "allMids"}, headers=HDR, timeout=20).json()
    except Exception as e:
        log.warning(f"[whales] mids 조회 실패: {e}")
        return {}


def _positions(addr):
    r = netutil.post_json(INFO, {"type": "clearinghouseState", "user": addr},
                          headers=HDR, timeout=20).json()
    out = []
    for p in r.get("assetPositions", []):
        q = p["position"]
        szi = float(q.get("szi") or 0)
        if szi == 0:
            continue
        out.append({"coin": q["coin"], "szi": szi,
                    "entry": float(q.get("entryPx") or 0),
                    "lev": float((q.get("leverage") or {}).get("value") or 0),
                    "upnl": float(q.get("unrealizedPnl") or 0)})
    return out


def build_whales(list_path: str = "data/whale_list.json",
                out_path: str = "docs/whales.json") -> dict[str, Any]:
    addrs = json.load(open(list_path, encoding="utf-8"))["addrs"]
    mids = _mids()
    agg = {}
    top_pos = []
    ok = 0
    for a in addrs:
        try:
            poss = _positions(a)
            ok += 1
        except Exception as e:
            log.warning(f"[whales] {a} 포지션 조회 실패: {e}")
            continue
        for p in poss:
            price = float(mids.get(p["coin"]) or p["entry"] or 0)
            ntl = abs(p["szi"]) * price
            if ntl <= 0:
                continue
            c = agg.setdefault(p["coin"], {"lU": 0, "sU": 0, "lN": 0, "sN": 0,
                                           "levS": 0, "levC": 0})
            if p["szi"] > 0:
                c["lU"] += ntl
                c["lN"] += 1
            else:
                c["sU"] += ntl
                c["sN"] += 1
            if p["lev"]:
                c["levS"] += p["lev"]
                c["levC"] += 1
            top_pos.append({"a": a[:6] + "…" + a[-4:], "coin": p["coin"],
                            "side": "L" if p["szi"] > 0 else "S",
                            "ntl": round(ntl / 1e6, 3), "lev": p["lev"],
                            "upnl": round(p["upnl"] / 1e6, 3)})
        time.sleep(0.08)
    coins = []
    for t, c in agg.items():
        tot = c["lU"] + c["sU"]
        if tot <= 0:
            continue
        coins.append({"t": t, "n": c["lN"] + c["sN"],
                      "l": round(c["lU"] / 1e6, 2), "s": round(c["sU"] / 1e6, 2),
                      "lev": round(c["levS"] / c["levC"], 1) if c["levC"] else 0,
                      "net": round((c["lU"] - c["sU"]) / tot, 3)})
    coins.sort(key=lambda x: -(x["l"] + x["s"]))
    top_pos.sort(key=lambda x: -x["ntl"])
    data = {"asof": _now(), "whales": ok, "coins": coins, "top": top_pos[:25]}
    json.dump(data, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log.info(f"[whales] {ok}명 스냅샷 · 코인 {len(coins)}종 · 저장 {out_path}")
    return data


def refresh(list_path: str = "data/whale_list.json", out_path: str = "docs/whales.json",
           top: int = 90, list_max_age_h: int = 20) -> dict[str, Any]:
    """워크플로용: 고래 목록이 없거나 오래됐으면 갱신 후 포지션 스냅샷."""
    import os
    need = True
    if os.path.exists(list_path):
        try:
            asof = json.load(open(list_path, encoding="utf-8")).get("asof", "")
            dt = datetime.strptime(asof, "%Y-%m-%d %H:%M").replace(tzinfo=KST)
            need = (datetime.now(KST) - dt) > timedelta(hours=list_max_age_h)
        except Exception as e:
            log.warning(f"[whales] 목록 나이 판정 실패(갱신 시도): {e}")
            need = True
    if need:
        try:
            build_whale_list(list_path, top=top)
        except Exception as e:
            log.warning(f"[whales] 목록 갱신 실패(기존 사용): {e}")
    return build_whales(list_path, out_path)


if __name__ == "__main__":
    import sys
    from settings import configure_logging
    configure_logging()
    if len(sys.argv) > 1 and sys.argv[1] == "refresh":
        refresh()
        sys.exit(0)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    build_whale_list("wl_test.json", top=n)
    d = build_whales("wl_test.json", "wh_test.json")
    print("\n=== 코인별 집계(상위) ===")
    for c in d["coins"][:12]:
        dir_ = "순롱" if c["net"] >= 0 else "순숏"
        print(f"  {c['t']:8} 롱${c['l']}M({c['n']}명 중) 숏${c['s']}M · {dir_} {abs(c['net'])*100:.0f}% · 평균레버 {c['lev']}x")
