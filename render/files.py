# -*- coding: utf-8 -*-
"""원문·시세·실적·경제지표 데이터 저장/로드(publish_site.py 분리)."""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import date, datetime, timedelta

import pytz

from render import config
from render.config import KST

log = logging.getLogger(__name__)


# =========================================================
# 발행 / 재렌더링 (저장·로드)
# =========================================================
def _slug(now):
    return now.strftime("%Y-%m-%d") + ("-am" if now.hour < 12 else "-pm")


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _save_body(body, now):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    _write(os.path.join(config.DATA_DIR, _slug(now) + ".txt"),
           now.isoformat() + "\n\n" + body)


def _save_quotes(quotes, now):
    """시세 데이터를 회차별 동반 JSON으로 저장(있을 때만). rebuild 시 재사용."""
    if not quotes:
        return
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(os.path.join(config.DATA_DIR, _slug(now) + ".quotes.json"),
              "w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False)


def _load_quotes(slug):
    path = os.path.join(config.DATA_DIR, slug + ".quotes.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        log.warning("failed to load quotes file: %s", path, exc_info=True)
        return None


def _load_body(path):
    raw = open(path, encoding="utf-8").read()
    head, _, body = raw.partition("\n\n")
    try:
        now = datetime.fromisoformat(head.strip())
    except ValueError:
        log.warning("failed to parse timestamp header in %s: %r", path, head)
        now = None
    return now, body


def _load_reports():
    try:
        with open(config.REPORTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.info("reports file not found: %s", config.REPORTS_FILE)
        return []
    except (OSError, ValueError):
        log.warning("failed to load reports file: %s", config.REPORTS_FILE, exc_info=True)
        return []


def _load_earnings(now):
    """data/earnings.json(큐레이션) → 지난 일정 제외, 날짜순(미정은 뒤)."""
    try:
        with open(config.EARN_FILE, encoding="utf-8") as f:
            rows = json.load(f)
    except FileNotFoundError:
        log.info("earnings file not found: %s", config.EARN_FILE)
        return []
    except (OSError, ValueError):
        log.warning("failed to load earnings file: %s", config.EARN_FILE, exc_info=True)
        return []
    out = []
    for r in rows:
        d = None
        if r.get("date"):
            try:
                d = date.fromisoformat(r["date"])
            except ValueError:
                d = None
        # 발표 완료 = 실제 발표 시각(ts)이 지났을 때만 (발표일 당일이어도 시각 전이면 예정)
        ts = r.get("ts")
        reported = bool(ts and now.timestamp() >= ts)
        out.append({"ticker": (r.get("ticker") or "").upper(),
                    "name": r.get("name") or "", "date": d,
                    "ts": r.get("ts"),
                    "est": bool(r.get("est")),
                    "reported": reported,
                    "detail": r.get("detail") or {}})
    out.sort(key=lambda e: (e["date"] is None, e["date"] or date.max))
    return out


def _is_fresh(r, now, days=2):
    """최근 발표(N일 내) 보고서 → 실적 결과 자동 진입 대상."""
    try:
        return 0 <= (now.date() - date.fromisoformat(r.get("date", ""))).days <= days
    except (ValueError, TypeError):
        return False


def _load_fundamentals():
    try:
        with open(config.FUND_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        log.info("fundamentals file not found: %s", config.FUND_FILE)
        return []
    except (OSError, ValueError):
        log.warning("failed to load fundamentals file: %s", config.FUND_FILE, exc_info=True)
        return []


def _load_econ_events(now):
    """data/econ/*.csv 병합 → MEDIUM/HIGH만, UTC→KST, 'now 이후' 임박순."""
    if not os.path.isdir(config.ECON_DIR):
        return []
    rows = {}
    for fn in os.listdir(config.ECON_DIR):
        if not fn.endswith(".csv"):
            continue
        try:
            with open(os.path.join(config.ECON_DIR, fn), encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    imp = (row.get("Impact") or "").strip().upper()
                    if imp not in ("LOW", "MEDIUM", "HIGH"):
                        continue
                    ccy = (row.get("Currency") or "").strip().upper()
                    if ccy not in config._ECON_CCY:          # 미국·한국·일본만
                        continue
                    try:
                        dt = pytz.utc.localize(
                            datetime.strptime((row.get("Start") or "").strip(),
                                              "%m/%d/%Y %H:%M:%S")).astimezone(KST)
                    except ValueError:
                        continue
                    key = row.get("Id") or (row.get("Start", "") + row.get("Name", ""))
                    rows[key] = {"dt": dt, "name": (row.get("Name") or "").strip(),
                                 "impact": imp, "cur": ccy}
        except OSError:
            log.warning("failed to read econ csv: %s", fn, exc_info=True)
            continue
    # B 로직: 이번 달=오늘 이후만 · 미래 달=전체 · 지난 달=제외
    #   + 높음(HIGH) 지표는 지난 7일치(결과 있는 것)를 남겨 '발표 결과'를 보여준다.
    try:
        from econ_results import load as _load_res
        results = _load_res()
    except Exception:  # noqa
        log.info("econ_results unavailable, continuing without result badges", exc_info=True)
        results = {}
    cur_ym = now.strftime("%Y-%m")
    today = now.date()
    keep_from = today - timedelta(days=7)      # 주말 넘어도 금요일 고용지표 등 유지
    kept = []
    for key, e in rows.items():
        d = e["dt"].date()
        recent_high = (e["impact"] == "HIGH" and keep_from <= d < today
                       and bool((results.get(key) or {}).get("act")))   # 결과 있는 것만
        if not recent_high:
            ym = e["dt"].strftime("%Y-%m")
            if ym < cur_ym:
                continue
            if ym == cur_ym and d < today:
                continue
        e["past"] = e["dt"] <= now
        e["res"] = results.get(key) if e["impact"] == "HIGH" else None
        kept.append(e)
    kept.sort(key=lambda e: e["dt"])
    # 월별로 묶기: [[ym, label, [events...]], ...] (오름차순)
    months = []
    for e in kept:
        ym = e["dt"].strftime("%Y-%m")
        if not months or months[-1][0] != ym:
            months.append([ym, f"{e['dt'].year}년 {e['dt'].month}월", []])
        months[-1][2].append(e)
    return months
