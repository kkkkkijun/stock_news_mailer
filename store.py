# -*- coding: utf-8 -*-
"""브리핑 구조화 저장소(SQLite).

목적: 지금까지 plain-text(data/*.txt)로만 남던 브리핑을 **조회 가능한 구조**로
색인한다. 검색·이력·전일 대비 변화·개인화의 토대가 된다.

설계 원칙
- 기존 파이프라인(수집→요약→HTML)은 **전혀 건드리지 않는다**. 이 모듈은
  이미 저장된 data/*.txt(+*.quotes.json)를 **읽어** DB로 색인하는 파생 인덱스다.
- 새 의존성 없음(표준 sqlite3). DB는 원문에서 언제든 재생성 가능하므로
  git 에 커밋하지 않는다(.gitignore). 원문 텍스트가 항상 진실의 원천.
- publish_site 의 파서(_split_sections/_parse_part)를 재사용해 중복 로직 없음.

사용
  python store.py reindex          # data/*.txt 전체를 DB로 재색인
  python store.py search 금리       # 헤드라인/요약 검색
  python store.py stats            # 색인 현황
"""
import os
import re
import sqlite3

from publish_site import (
    DATA_DIR, PARTS, HERO_PARTS,
    _split_sections, _parse_part, _load_body, _load_quotes,
)

DB_PATH = os.path.join(DATA_DIR, "briefings.db")
_SLUG_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})-(am|pm)")

SCHEMA = """
CREATE TABLE IF NOT EXISTS briefings(
  slug TEXT PRIMARY KEY,
  date TEXT, ampm TEXT, generated_at TEXT
);
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT, date TEXT, ampm TEXT,
  part TEXT, part_name TEXT, kind TEXT, is_hero INTEGER,
  theme TEXT, ticker TEXT,
  headline TEXT, summary TEXT,
  publisher TEXT, source_time TEXT, position INTEGER
);
CREATE TABLE IF NOT EXISTS quotes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT, date TEXT, ampm TEXT, part TEXT,
  ticker TEXT, price REAL, chg REAL, asof TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_headline ON items(headline);
CREATE INDEX IF NOT EXISTS idx_items_part     ON items(part);
CREATE INDEX IF NOT EXISTS idx_items_date     ON items(date);
CREATE INDEX IF NOT EXISTS idx_items_ticker   ON items(ticker);
CREATE INDEX IF NOT EXISTS idx_quotes_ticker  ON quotes(ticker);
"""


def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def _split_src(src):
    """'매일경제 · 07/30 08:25' → ('매일경제', '07/30 08:25')."""
    if not src:
        return "", ""
    parts = [p.strip() for p in src.split("·")]
    if len(parts) >= 2:
        return parts[0], " · ".join(parts[1:])
    return parts[0], ""


def index_briefing(con, slug, now, body, quotes=None):
    """한 회차(slug)를 DB에 색인(기존 행은 교체). publish_site 파서 재사용."""
    m = _SLUG_RE.fullmatch(slug)
    date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
    ampm = m.group(4) if m else ""
    gen = now.isoformat() if now else ""

    con.execute("DELETE FROM items  WHERE slug=?", (slug,))
    con.execute("DELETE FROM quotes WHERE slug=?", (slug,))
    con.execute("INSERT OR REPLACE INTO briefings VALUES(?,?,?,?)",
                (slug, date, ampm, gen))

    for title, lines in _split_sections(body):
        match = next(((pid, name) for pid, _i, name, key in PARTS if key in title),
                     None)
        if not match:
            continue
        pid, pname = match
        _summary, items, _blocks, _note = _parse_part(lines)
        for pos, it in enumerate(items):
            if not it.get("title"):
                continue
            kind = it.get("kind", "")
            label = (it.get("label") or "").strip()
            theme = label if kind == "tag" else ""
            ticker = label if kind == "ticker" else ""
            pub, stime = _split_src(it.get("src", ""))
            is_hero = 1 if (pid in HERO_PARTS and pos == 0) else 0
            con.execute(
                "INSERT INTO items(slug,date,ampm,part,part_name,kind,is_hero,"
                "theme,ticker,headline,summary,publisher,source_time,position)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (slug, date, ampm, pid, pname, kind, is_hero, theme, ticker,
                 it.get("title", ""), it.get("desc", ""), pub, stime, pos))

    for part, cards in (quotes or {}).items():
        if not isinstance(cards, list):
            continue
        for c in cards:
            con.execute(
                "INSERT INTO quotes(slug,date,ampm,part,ticker,price,chg,asof)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (slug, date, ampm, part, c.get("ticker"), c.get("price"),
                 c.get("chg"), c.get("asof")))
    con.commit()


def reindex_all(path=DB_PATH):
    """data/*.txt 전체를 DB로 재색인(전량 재생성). 색인한 회차 수 반환."""
    con = connect(path)
    for t in ("items", "quotes", "briefings"):
        con.execute(f"DELETE FROM {t}")
    n = 0
    for fn in sorted(f for f in os.listdir(DATA_DIR) if f.endswith(".txt")):
        slug = fn[:-4]
        if not _SLUG_RE.fullmatch(slug):
            continue
        now, body = _load_body(os.path.join(DATA_DIR, fn))
        if not body.strip():
            continue
        index_briefing(con, slug, now, body, _load_quotes(slug))
        n += 1
    con.commit()
    con.close()
    return n


def search(term, part=None, ticker=None, since=None, until=None,
           limit=50, path=DB_PATH):
    """헤드라인/요약 부분일치 검색(+ 파트·티커·기간 필터). dict 목록 반환."""
    con = connect(path)
    con.row_factory = sqlite3.Row
    sql = ("SELECT date,ampm,part_name,theme,ticker,headline,summary,"
           "publisher,source_time FROM items WHERE 1=1")
    args = []
    if term:
        sql += " AND (headline LIKE ? OR summary LIKE ?)"
        args += [f"%{term}%", f"%{term}%"]
    if part:
        sql += " AND part=?"
        args.append(part)
    if ticker:
        sql += " AND ticker=?"
        args.append(ticker)
    if since:
        sql += " AND date>=?"
        args.append(since)
    if until:
        sql += " AND date<=?"
        args.append(until)
    sql += " ORDER BY date DESC, ampm DESC, position ASC LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    con.close()
    return rows


def stats(path=DB_PATH):
    con = connect(path)
    b = con.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]
    it = con.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    q = con.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
    by_part = con.execute(
        "SELECT part_name, COUNT(*) FROM items GROUP BY part_name "
        "ORDER BY COUNT(*) DESC").fetchall()
    con.close()
    return {"briefings": b, "items": it, "quotes": q, "by_part": by_part}


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "reindex":
        print(f"색인 완료: {reindex_all()}개 회차 → {DB_PATH}")
    elif cmd == "search" and len(sys.argv) > 2:
        for r in search(sys.argv[2]):
            tag = r["ticker"] or r["theme"] or ""
            tag = f"({tag}) " if tag else ""
            print(f"{r['date']} {r['ampm']} [{r['part_name']}] {tag}{r['headline']}"
                  f"  — {r['publisher']} {r['source_time']}")
    elif cmd == "stats":
        s = stats()
        print(f"회차 {s['briefings']} · 항목 {s['items']} · 시세 {s['quotes']}")
        for name, c in s["by_part"]:
            print(f"  {name}: {c}")
    else:
        print("사용법: python store.py [reindex | search <검색어> | stats]")
