# -*- coding: utf-8 -*-
"""홈 화면 데이터: 나스닥 100 히트맵 + 주요 지표 띠 → docs/treemap.json.

입력: data/universe.json(나스닥 100 목록·이름·섹터·시총·기준가), data/screen.json(같은 회사 중복 제거용),
      Yahoo Finance spark(한 번에 20종목, 무인증) — 현재가·전일 종가
출력: docs/treemap.json {asof, built, idx:[{s,lab,px,chg,pre,suf}], rows:[{t,n,s,m,c}]}
      asof = 미국 주식 마지막 거래 시각(장 마감 중엔 그대로), built = 갱신 시각(매시)
      m = 시가총액(십억 달러, 아침 나스닥 시총 × 현재가/기준가), c = 전일 종가 대비 등락률(%)
실행: map-refresh 워크플로가 매시(cron-job.org → repository_dispatch) `python treemap.py`
관련: universe.py, render/home.py(홈 화면), .github/workflows/map-refresh.yml

주의: 등락률은 반드시 range=1d의 chartPreviousClose로 계산한다. 일봉 배열의 마지막 값은 장중·장 직후에
None이라, None을 걸러 '끝에서 두 번째'를 쓰면 이틀 전 종가와 비교하게 된다(GOOGL −12.6%가 −11.5%로 나옴).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

import netutil
from settings import KST

log = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_SPARK = "https://query1.finance.yahoo.com/v7/finance/spark"
_BATCH = 20                                   # spark는 한 번에 20종목까지
# (심볼, 표시 이름, 앞 기호, 뒤 기호)
INDICES = (("^GSPC", "S&P 500", "", ""), ("^IXIC", "나스닥", "", ""), ("^DJI", "다우", "", ""),
           ("^VIX", "VIX", "", ""), ("^TNX", "미 10년물", "", "%"), ("KRW=X", "원/달러", "", ""),
           ("CL=F", "WTI", "$", ""), ("GC=F", "금", "$", ""), ("BTC-USD", "비트코인", "$", ""))


def parse_spark(j: dict[str, Any]) -> dict[str, dict[str, float]]:
    """spark 응답 → {심볼: {px, prev, chg, ts}}. 가격이나 전일 종가가 없으면 건너뜀."""
    out = {}
    for x in (j.get("spark") or {}).get("result") or []:
        try:
            m = x["response"][0]["meta"]
            px, prev = m.get("regularMarketPrice"), m.get("chartPreviousClose")
        except (KeyError, IndexError, TypeError):
            continue
        if px and prev:
            out[x["symbol"]] = {"px": px, "prev": prev, "chg": (px / prev - 1) * 100,
                                "ts": m.get("regularMarketTime") or 0}
    return out


def fetch_spark(symbols: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i in range(0, len(symbols), _BATCH):
        part = symbols[i:i + _BATCH]
        try:
            j = netutil.get_json(_SPARK, params={"symbols": ",".join(part), "range": "1d", "interval": "1d"},
                                 headers=_UA, timeout=20)
            out.update(parse_spark(j))
        except Exception as e:  # noqa: BLE001 — 한 묶음 실패가 전체를 막지 않게
            log.warning("[treemap] spark %s… 실패: %s", part[0], e)
        time.sleep(0.3)
    return out


def _load(path: str, default: Any) -> Any:
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def build_rows(universe: dict[str, Any], screen: dict[str, Any], quotes: dict[str, dict[str, float]]) -> list[dict]:
    """나스닥 100 → 히트맵 행. 같은 회사의 다른 종류 주식(GOOG 등)은 1차 선별 결과 기준으로 뺀다."""
    keep = {r["t"] for r in screen.get("rows", [])} | set(screen.get("miss") or [])
    rows = []
    for r in universe.get("rows", []):
        t = r["t"]
        if keep and t not in keep:
            continue
        q = quotes.get(t)
        if not q or not r.get("mcap_nq"):
            continue
        scale = q["px"] / r["px"] if r.get("px") else 1.0
        rows.append({"t": t, "n": r.get("name") or t, "s": r.get("sector") or "기타",
                     "m": round(r["mcap_nq"] * scale / 1000, 1), "c": round(q["chg"], 2)})
    return rows


def build_treemap(path: str = "docs/treemap.json", universe_path: str = "data/universe.json",
                  screen_path: str = "data/screen.json") -> dict[str, Any] | None:
    universe = _load(universe_path, {})
    if not universe.get("rows"):
        log.warning("[treemap] universe 없음 → 건너뜀")
        return None
    syms = [r["t"] for r in universe["rows"]] + [s for s, *_ in INDICES]
    q = fetch_spark(syms)
    rows = build_rows(universe, _load(screen_path, {}), q)
    if len(rows) < 50:                          # 대부분 실패면 기존 파일 유지
        log.warning("[treemap] 시세 %d개뿐 → 기존 파일 유지", len(rows))
        return None
    idx = [{"s": s, "lab": lab, "px": round(q[s]["px"], 4), "chg": round(q[s]["chg"], 2), "pre": pre, "suf": suf}
           for s, lab, pre, suf in INDICES if s in q]
    ts = max((q[r["t"]]["ts"] for r in rows), default=0)
    built = datetime.now(KST).isoformat(timespec="seconds")
    out = {"asof": datetime.fromtimestamp(ts, KST).isoformat() if ts else built,   # 미국 주식 마지막 거래 시각
           "built": built,                                                          # 이 파일을 만든 시각(매시)
           "idx": idx, "rows": rows}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    log.info("[treemap] %d종목 · 지표 %d개 · 기준 %s → %s", len(rows), len(idx), out["asof"], path)
    return out


if __name__ == "__main__":
    from settings import configure_logging
    configure_logging()
    build_treemap()
