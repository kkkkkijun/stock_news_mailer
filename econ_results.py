"""경제지표 발표 결과 수집 (FXStreet 캘린더 API, 무키).

data/econ/*.csv 의 Id 와 API 의 eventDate id 가 동일하므로 id 로 정확히 붙인다.
높음(HIGH) · 미국/한국/일본 지표만 저장 → data/econ_results.json
  { "<id>": {"name":..., "dt":"UTC ISO", "act":"48.7", "cons":"49.0", "prev":"48.0",
             "act_n":48.7, "cons_n":49.0} }
브리핑 발행(main.py) 때 refresh() 호출 → 지난 며칠 결과 + 향후 예상치를 병합 저장.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import requests

API = "https://calendar-api.fxstreet.com/en/api/v1/eventDates/{a}/{b}"
HDR = {"Referer": "https://www.fxstreet.com/", "Origin": "https://www.fxstreet.com",
       "User-Agent": "Mozilla/5.0"}
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "data", "econ_results.json")
CCY = {"USD", "KRW", "JPY"}


def _num(v):
    if v is None:
        return None
    s = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def fmt(v, unit, potency):
    """FXStreet 수치 → 표시 문자열. potency(K/M/B) + unit($/%)."""
    s = _num(v)
    if s is None:
        return None
    if potency in ("K", "M", "B"):
        s += potency
    if unit == "%":
        s += "%"
    elif unit == "$":
        s = ("-$" + s[1:]) if s.startswith("-") else ("$" + s)
    return s


def load():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def refresh(days_back=9, days_fwd=45):
    """지난 days_back일 ~ 향후 days_fwd일 HIGH 지표를 주 단위로 받아 병합 저장."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = (now + timedelta(days=days_fwd)).replace(hour=0, minute=0, second=0, microsecond=0)
    res = load()
    got = 0
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=7), end)
        url = API.format(a=cur.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         b=nxt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        try:
            r = requests.get(url, headers=HDR, timeout=20)
            r.raise_for_status()
            items = r.json()
        except Exception as e:  # noqa
            print(f"[econ] fetch 실패 {cur.date()}~{nxt.date()}: {e}")
            cur = nxt
            continue
        for it in items:
            if it.get("volatility") != "HIGH" or it.get("currencyCode") not in CCY:
                continue
            u, p = it.get("unit"), it.get("potency")
            prev = it.get("revised") if it.get("revised") is not None else it.get("previous")
            res[it["id"]] = {
                "name": it.get("name"), "dt": it.get("dateUtc"),
                "act": fmt(it.get("actual"), u, p),
                "cons": fmt(it.get("consensus"), u, p),
                "prev": fmt(prev, u, p),
                "act_n": it.get("actual"), "cons_n": it.get("consensus"),
            }
            got += 1
        cur = nxt
    # 오래된 항목 정리(120일 이전)
    cutoff = (now - timedelta(days=120)).strftime("%Y-%m-%dT")
    res = {k: v for k, v in res.items() if (v.get("dt") or "9") >= cutoff}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=0)
    return f"{got}건 수집 / 총 {len(res)}건"


if __name__ == "__main__":
    print(refresh())
