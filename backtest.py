"""성장주 '점수 검증' — 시점 기준(point-in-time) 백테스트.

과거 각 시점에 '그때까지 SEC에 공시된 재무만'으로 품질 점수를 다시 계산하고(공시일 filed 기준,
미래 정보 차단), 점수 상위 절반과 하위 절반의 이후 3·6개월 주가 수익률을 비교한다.
입력: data/fundamentals.json(대상 종목), SEC companyfacts, Yahoo chart(일봉 종가)
출력: data/backtest.json — 성장주 탭 '점수 검증' 화면이 읽는다.
실행: main.py refresh 안에서 build_backtest()(max_age_days 지나면만 재계산) 또는 python backtest.py
한계: 종목이 '지금' 정밀 분석 대상이라 생존·선택 편향이 있고, 수익률은 배당 제외 주가 기준.
"""
from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import date, timedelta
from typing import Any

import netutil

log = logging.getLogger(__name__)

HORIZONS = (91, 182)                    # 3개월 · 6개월(일)
AXES = ("growth", "path", "balance", "shareholder")
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def eval_dates(today: date, start_year: int = 2023, horizon: int = HORIZONS[0]) -> list[date]:
    """실적 시즌 직후(2·5·8·11월 15일) 시점 중 이후 horizon일 수익률을 알 수 있는 것."""
    out = []
    for y in range(start_year, today.year + 1):
        for m in (2, 5, 8, 11):
            d = date(y, m, 15)
            if d + timedelta(days=horizon) <= today:
                out.append(d)
    return out


def filter_facts(facts: dict[str, Any], asof: date) -> dict[str, Any]:
    """companyfacts에서 asof 날짜까지 공시(filed)된 값만 남긴 사본(us-gaap만)."""
    cut = asof.isoformat()
    g = facts.get("facts", {}).get("us-gaap", {})
    out = {}
    for tag, body in g.items():
        units = {u: [r for r in rows if r.get("filed", "9999") <= cut] for u, rows in body.get("units", {}).items()}
        units = {u: rows for u, rows in units.items() if rows}
        if units:
            out[tag] = {"units": units}
    return {"facts": {"us-gaap": out}}


def close_at(series: list[tuple[str, float]], d: date) -> float | None:
    """d 이전(포함) 마지막 거래일 종가. series = [(YYYY-MM-DD, 종가), …] 오름차순."""
    key, best = d.isoformat(), None
    for dd, c in series:
        if dd > key:
            break
        best = c
    return best


def fetch_closes(sym: str) -> list[tuple[str, float]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d"
    res = netutil.get_json(url, headers=_UA, timeout=20)["chart"]["result"][0]
    ts, cl = res.get("timestamp") or [], res["indicators"]["quote"][0]["close"]
    return [(date.fromtimestamp(t).isoformat(), c) for t, c in zip(ts, cl) if c]


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1        # 동점은 평균 순위
        i = j + 1
    return r


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """순위 상관(-1~1). 점수가 높을수록 수익률도 높았으면 +."""
    if len(xs) < 5:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    try:
        return statistics.correlation(rx, ry)
    except statistics.StatisticsError:
        return None


def halves(obs: list[dict[str, Any]], key: str, ret: str) -> tuple[float, float] | None:
    """key 기준 상위 절반·하위 절반의 평균 수익률."""
    rs = sorted((o for o in obs if o.get(ret) is not None), key=lambda o: -o[key])
    if len(rs) < 4:
        return None
    h = len(rs) // 2
    return statistics.mean(o[ret] for o in rs[:h]), statistics.mean(o[ret] for o in rs[h:])


def summarize(obs: list[dict[str, Any]]) -> dict[str, Any]:
    """관측치 [{d,t,score,ax:{…},r3,r6}] → 화면용 요약."""
    dates = sorted({o["d"] for o in obs})
    per, out = [], {}
    for d in dates:
        o = [x for x in obs if x["d"] == d]
        row = {"d": d, "n": len(o), "top": sorted(o, key=lambda x: -x["score"])[:5]}
        row["top"] = [x["t"] for x in row["top"]]
        for k, ret in (("3", "r3"), ("6", "r6")):
            hv = halves(o, "score", ret)
            if hv:
                row["hi" + k], row["lo" + k] = round(hv[0], 1), round(hv[1], 1)
                ok = [x for x in o if x.get(ret) is not None]
                ic = spearman([x["score"] for x in ok], [x[ret] for x in ok])
                row["ic" + k] = None if ic is None else round(ic, 2)
        per.append(row)
    for k in ("3", "6"):
        rows = [r for r in per if ("hi" + k) in r]
        if not rows:
            continue
        ics = [r["ic" + k] for r in rows if r.get("ic" + k) is not None]
        out["h" + k] = {
            "dates": len(rows),
            "hi": round(statistics.mean(r["hi" + k] for r in rows), 1),
            "lo": round(statistics.mean(r["lo" + k] for r in rows), 1),
            "wins": sum(1 for r in rows if r["hi" + k] > r["lo" + k]),
            "ic": round(statistics.mean(ics), 2) if ics else None,
        }
    axes = {}
    for a in AXES:
        sp = []
        for d in dates:
            o = [dict(x, _a=x["ax"][a]) for x in obs if x["d"] == d and a in x.get("ax", {})]
            hv = halves(o, "_a", "r3")
            if hv:
                sp.append(hv[0] - hv[1])
        if sp:
            axes[a] = {"spread": round(statistics.mean(sp), 1), "wins": sum(1 for s in sp if s > 0), "dates": len(sp)}
    return {"per": per, "axes": axes, **out}


def _observe(t: str, facts: dict[str, Any], closes: list[tuple[str, float]],
             dates: list[date], today: date) -> list[dict[str, Any]]:
    import fundamentals as F
    out = []
    for d0 in dates:
        p0 = close_at(closes, d0)
        if not p0 or not closes or closes[0][0] > (d0 - timedelta(days=5)).isoformat():
            continue                                    # 그 시점에 상장 전
        try:
            d = F._build_one(t, facts=filter_facts(facts, d0))
        except Exception as e:  # noqa: BLE001 — 한 시점 실패가 전체를 막지 않게
            log.info(f"[bt] {t} {d0}: {e}")
            continue
        if not d or not d.get("asof"):
            continue
        if (d0 - date.fromisoformat(d["asof"])).days > 200:
            continue                                    # 그 시점 최신 재무가 너무 오래됨(공시 공백)
        o = {"d": d0.isoformat(), "t": t, "score": d["score"],
             "ax": {a: d["axes"][a]["sc"] for a in AXES}}
        for h, k in zip(HORIZONS, ("r3", "r6")):
            if d0 + timedelta(days=h) <= today:
                p1 = close_at(closes, d0 + timedelta(days=h))
                if p1:
                    o[k] = round((p1 / p0 - 1) * 100, 2)
        out.append(o)
    return out


def build_backtest(path: str = "data/backtest.json", fund_path: str = "data/fundamentals.json",
                   max_age_days: int = 28, today: date | None = None) -> dict[str, Any] | None:
    """정밀 분석 종목 전체로 점수 검증을 계산해 path에 저장. 최근(max_age_days 이내)에 했으면 건너뜀."""
    import fundamentals as F
    today = today or date.today()
    try:
        prev = json.load(open(path, encoding="utf-8"))
        if (today - date.fromisoformat(prev.get("built", "1970-01-01"))).days < max_age_days:
            log.info(f"[bt] 최근 계산({prev.get('built')}) → 건너뜀")
            return prev
    except (OSError, ValueError):
        pass
    tickers = [d["ticker"] for d in json.load(open(fund_path, encoding="utf-8"))]
    dates = eval_dates(today)
    obs, skipped = [], []
    t0 = time.time()
    for t in tickers:
        facts = F.fetch_companyfacts(t)
        try:
            closes = fetch_closes(t)
        except Exception as e:  # noqa: BLE001
            log.info(f"[bt] {t}: 주가 실패 {e}")
            closes = []
        if not facts or not closes:
            skipped.append(t)
            continue
        obs += _observe(t, facts, closes, dates, today)
        time.sleep(0.15)
    if not obs:
        return None
    res = {"built": today.isoformat(), "universe": len(tickers), "skipped": skipped,
           "n": len(obs), "first": dates[0].isoformat(), "last": dates[-1].isoformat(),
           **summarize(obs)}
    json.dump(res, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log.info(f"[bt] 관측 {len(obs)}건 · {len(dates)}개 시점 · {time.time() - t0:.0f}s → {path}")
    return res


if __name__ == "__main__":
    import sys
    from settings import configure_logging
    configure_logging()
    r = build_backtest(max_age_days=0 if "--force" in sys.argv else 28)
    if r:
        print(json.dumps({k: r[k] for k in r if k not in ("per",)}, ensure_ascii=False, indent=1))
