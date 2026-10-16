# -*- coding: utf-8 -*-
"""성장주 1차 선별: SEC frames API로 나스닥 100 전 종목의 분기 매출·성장·이익률을 한 번에 계산.

frames API는 항목·분기별로 전 상장사 값을 한 번에 준다(요청 약 14회·수 MB) — 종목별 전체 재무(평균 3MB)를
받지 않고도 표를 채운다. 정밀 분석(fundamentals.py)은 여기서 얻은 공시번호(accn)로 바뀐 종목만 다시 받는다.

매출 규칙: ① 총매출(Revenues) 우선, 없으면 고객 계약 매출 등 ② 비교하는 두 분기는 같은 태그
③ 총매출과 고객 계약 매출 성장률이 10%p 넘게 다르면 gap으로 표시(화면 '매출 정의 확인').
회계연도가 달라 최근 달력 분기 값이 없으면 직전 분기끼리 비교(per에 기록).

입력: data/universe.json(대상), SEC frames API
출력: data/screen.json {asof, periods, rows:[{t, cik, per, tag, rev, yoy, opm, gw, gap, shares_dil, accn}], miss:[...]}
관련: universe.py, fundamentals.py, render/growth.py
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date
from typing import Any

import netutil
from sec import _SEC_UA, _sec_cik

log = logging.getLogger(__name__)

REV_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"]
TAG_KO = {REV_TAGS[0]: "총매출", REV_TAGS[1]: "고객계약"}
GAP_PP = 10.0            # 규칙 ③ 기준(%p)
GW_FLAG_PCT = 30.0       # 영업권 1년 증가율 경고 기준(%)
FILING_LAG_DAYS = 50     # 분기 종료 후 이 기간이 지나야 대부분 10-Q가 나와 있다


def recent_periods(today: date) -> list[tuple[str, str]]:
    """[(최근 분기, 1년 전 분기), (그 직전 분기, 1년 전)] — 공시가 대부분 나온 최근 달력 분기부터."""
    y, q = today.year, (today.month - 1) // 3 + 1
    out = []
    for _ in range(8):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        end = date(y, q * 3, 30 if q in (2, 3) else 31)
        if (today - end).days >= FILING_LAG_DAYS:
            out.append((f"CY{y}Q{q}", f"CY{y - 1}Q{q}"))
        if len(out) == 2:
            break
    return out


def _frame(tag: str, period: str, unit: str = "USD") -> dict[int, dict[str, Any]]:
    """frames API 한 장 → {cik: {"val", "accn"}}. 해당 기간 데이터가 없으면 빈 dict."""
    try:
        j = netutil.get_json(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/{unit}/{period}.json",
                             headers=_SEC_UA, timeout=60)
    except Exception as e:  # noqa: BLE001 — 404(아직 없는 기간) 포함
        log.info(f"[screen] frame {tag} {period} 없음: {e}")
        return {}
    finally:
        time.sleep(0.15)
    return {d["cik"]: {"val": d["val"], "accn": d.get("accn")} for d in j.get("data", [])}


def pick_revenue(frames: dict, cik: int, periods: list[tuple[str, str]]) -> dict[str, Any] | None:
    """규칙 ①②③ 적용. frames: {(tag, period): {cik: {...}}}. 순수 함수(테스트 대상)."""
    for cur, prev in periods:
        pairs = {}
        for t in REV_TAGS:
            a, b = frames.get((t, cur), {}).get(cik), frames.get((t, prev), {}).get(cik)
            if a and b and a["val"] and b["val"]:
                pairs[t] = (a, b)
        if not pairs:
            continue
        tag = next(t for t in REV_TAGS if t in pairs)
        a, b = pairs[tag]
        gap = None
        if REV_TAGS[0] in pairs and REV_TAGS[1] in pairs:
            g = [(pairs[t][0]["val"] / pairs[t][1]["val"] - 1) * 100 for t in REV_TAGS[:2]]
            gap = round(abs(g[0] - g[1]), 1)
        return {"per": cur[2:], "tag": TAG_KO.get(tag, "기타"), "rev": a["val"] / 1e6,
                "yoy": round((a["val"] / b["val"] - 1) * 100, 1), "gap": gap, "accn": a.get("accn"),
                "_cur": cur}
    return None


def build_screen(universe_path: str = "data/universe.json", path: str = "data/screen.json",
                 today: date | None = None) -> dict[str, Any]:
    uni = json.load(open(universe_path, encoding="utf-8"))
    periods = recent_periods(today or date.today())
    frames = {(t, p): _frame(t, p) for t in REV_TAGS for pair in periods for p in pair}
    op = {cur: _frame("OperatingIncomeLoss", cur) for cur, _ in periods}
    sh = {cur: _frame("WeightedAverageNumberOfDilutedSharesOutstanding", cur, "shares") for cur, _ in periods}
    shb = {cur: _frame("WeightedAverageNumberOfSharesOutstandingBasic", cur, "shares") for cur, _ in periods}
    gw_now = _frame("Goodwill", periods[0][0] + "I")
    gw_ago = _frame("Goodwill", periods[0][1] + "I")
    rows, miss, seen = [], [], set()
    for u in uni["rows"]:
        cik = _sec_cik(u["t"])
        cik = int(cik) if cik else None
        r = pick_revenue(frames, cik, periods) if cik else None
        if not r:
            miss.append(u["t"])
            continue
        if cik in seen:                 # GOOGL/GOOG 같은 회사 중복 제거(앞 티커 유지)
            continue
        seen.add(cik)
        cur = r.pop("_cur")
        o = op[cur].get(cik)
        # 주식수: 희석 가중평균 → 없으면 기본 가중평균(시총 기준 표시용 basis)
        s = sh[cur].get(cik) or next((sh[c].get(cik) for c, _ in periods if sh[c].get(cik)), None)
        basis = "희석"
        if not s:
            s = shb[cur].get(cik) or next((shb[c].get(cik) for c, _ in periods if shb[c].get(cik)), None)
            basis = "기본" if s else None
        g1, g0 = gw_now.get(cik), gw_ago.get(cik)
        rows.append({"t": u["t"], "cik": cik, **r,
                     "opm": round(o["val"] / (r["rev"] * 1e6) * 100, 1) if o else None,
                     "gw": round((g1["val"] / g0["val"] - 1) * 100, 1) if (g1 and g0 and g0["val"]) else None,
                     "shares_dil": round(s["val"] / 1e6, 2) if s else None, "shares_basis": basis})
    data = {"asof": (today or date.today()).isoformat(), "periods": [list(p) for p in periods],
            "rows": rows, "miss": miss}
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log.info(f"[screen] {len(rows)}개 계산 · 계산 불가 {len(miss)}개 {miss} · 기간 {periods} → {path}")
    return data


if __name__ == "__main__":
    from settings import configure_logging
    configure_logging()
    build_screen()
