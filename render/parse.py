# -*- coding: utf-8 -*-
"""브리핑 본문(plain text) 파싱(publish_site.py 분리)."""
from __future__ import annotations

import logging
import os
import re

from render import config
from render.config import PARTS
from render.files import _load_body

log = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"^(📈|🪙|📊|💹|🌐|🏘️|💬)\s*(.+)$")
_LABEL_RE = re.compile(r"^\[(.+)\]$")
_ITEM_RE = re.compile(r"^(\d+)\.\s*(?:\((.+?)\)\s*)?(.+)$")
_TICKER_RE = re.compile(r"^📰\s*\[(.+?)\]\s*(.+)$")
_BRIEF_RE = re.compile(r"^🧭\s*\[(.+?)\]\s*(.+)$")          # 종목 한 줄 총평(main.fetch_and_summarize_news)
_SENTS = {"호재": "g", "악재": "b", "중립": "n", "제외": "x"}
_FG_RE = re.compile(r"^-\s*(.+?)\s*:\s*(\d+)\s*\((.+?)\)")


# =========================================================
# 본문 파싱
# =========================================================
def _split_sections(body):
    """본문을 [(섹션제목, [내용줄])] 로 분해."""
    out, cur = [], None
    for raw in body.splitlines():
        s = raw.strip()
        if not s:
            continue
        m = _SECTION_RE.match(s)
        if m:
            cur = (f"{m.group(1)} {m.group(2)}", [])
            out.append(cur)
            continue
        if cur is not None:
            cur[1].append(s)
    return out


def _parse_part(lines):
    """섹션 내용을 (요약, [항목], [전망], 전망라벨, 노트) 로 구조화.

    - [오늘 한눈에] → 요약 문단
    - 숫자 항목(1. …) / 티커(📰 …) → 뉴스/발언 카드
      티커 기사 뒤 '🏷 판정 | 한글 헤드라인 | 근거 | 중복 수' → sent(g/b/n/x)·ko·why·dups,
      '🔗 URL' → link, 앞의 '🧭 [티커] 총평' → 그 종목 첫 기사의 brief (없으면 예전 형식 그대로)
    - '• …' 불릿 → 전망 리스트(라벨은 직전 [ ] 이름 유지)
    - '※ …' → 하단 노트
    """
    summary, items, blocks, note = "", [], [], ""
    curblock, cur, cur_label = None, None, ""
    briefs: dict[str, str] = {}
    mode = "items"
    for s in lines:
        m = _LABEL_RE.match(s)
        if m:
            cur_label = m.group(1)
            mode = "sum" if "한눈에" in cur_label else "items"
            cur = curblock = None
            continue
        if s.startswith("※"):
            note = (note + " " + s.lstrip("※").strip()).strip()
            continue
        if mode == "sum":
            summary = (summary + " " + s).strip()
            continue
        if s and s[0] in "•-":
            txt = s[1:].strip()
            if txt:                      # 빈 불릿은 무시
                if curblock is None:
                    curblock = (cur_label or "흐름·전망", [])
                    blocks.append(curblock)
                curblock[1].append(txt)
            cur = None
            continue

        mb = _BRIEF_RE.match(s)
        if mb:
            briefs[mb.group(1)] = mb.group(2).strip()
            cur = None
            continue
        mt = _TICKER_RE.match(s)
        if mt:
            cur = {"kind": "ticker", "label": mt.group(1),
                   "title": mt.group(2), "desc": "", "src": ""}
            if mt.group(1) in briefs:               # 총평은 그 종목 첫 기사에 붙인다
                cur["brief"] = briefs.pop(mt.group(1))
            items.append(cur)
            continue
        if cur is not None and s.startswith("🏷"):
            # 🏷 판정 | 한글 헤드라인 | 근거 | 같은 내용 다른 출처 수
            f = [x.strip() for x in s[1:].lstrip("️").split("|")]
            if f and f[0] in _SENTS:
                cur["sent"] = _SENTS[f[0]]
                cur["ko"] = f[1] if len(f) > 1 else ""
                cur["why"] = f[2] if len(f) > 2 else ""
                cur["dups"] = int(f[3]) if len(f) > 3 and f[3].isdigit() else 0
            continue
        if cur is not None and s.startswith("🔗"):
            url = s[1:].strip()
            if url.startswith(("http://", "https://")):
                cur["link"] = url
            continue
        mi = _ITEM_RE.match(s)
        if mi:
            cur = {"kind": "tag", "label": (mi.group(2) or "").strip(),
                   "title": mi.group(3), "desc": "", "src": ""}
            items.append(cur)
            continue
        if cur is not None:
            if s.startswith("→"):
                cur["desc"] = s.lstrip("→").strip()
            elif s.startswith("(") and s.endswith(")"):
                cur["src"] = s[1:-1].strip()
    return summary, items, blocks, note


def _fear_greed(sections):
    for title, lines in sections:
        if "공포탐욕" in title:
            found = []
            for ln in lines:
                m = _FG_RE.match(ln)
                if m:
                    found.append((m.group(1), m.group(2), m.group(3)))
            return found
    return []


def _mood_color(value):
    """0-24 / 25-44 / 45-55 / 56-75 / 76-100 구간 색상."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return "#94a3b8"
    # 흰 글자 배지 배경 → 모두 흰색 대비 4.5:1 이상(WCAG AA)인 진한 톤
    if v <= 24:
        return "#c0392b"
    if v <= 44:
        return "#b45309"
    if v <= 55:
        return "#a16207"
    if v <= 75:
        return "#15803d"
    return "#2e7d32"


def _news_toks(s):
    """헤드라인 → 2글자 이상 토큰 집합(유사도 비교용)."""
    return {w for w in re.sub(r"[^0-9A-Za-z가-힣 ]", " ", s or "").split()
            if len(w) > 1}


def _prev_item_tokensets(slug, back=2):
    """slug 직전 `back`개 회차의 뉴스 헤드라인 토큰셋 목록.

    직전 브리핑(들)에 이미 나온 사건인지 비교하는 근거. 저장된 data/*.txt 만
    읽으므로 DB 없이 GitHub Actions 에서도 동작(과거 회차는 커밋되어 있음).
    slug 자신은 제외. 이전 회차가 없으면 빈 목록(→ 아무것도 NEW 로 표시 안 함).
    """
    try:
        slugs = sorted(f[:-4] for f in os.listdir(config.DATA_DIR) if f.endswith(".txt"))
    except OSError:
        log.warning("failed to list data dir: %s", config.DATA_DIR, exc_info=True)
        return []
    prev = slugs[:slugs.index(slug)] if slug in slugs else slugs
    out = []
    for s in prev[-back:]:
        _now, body = _load_body(os.path.join(config.DATA_DIR, s + ".txt"))
        for title, sec_lines in _split_sections(body):
            if not any(key in title for _p, _i, _n, key in PARTS):
                continue
            _s, items, _b, _n = _parse_part(sec_lines)
            for it in items:
                t = _news_toks(it.get("title", ""))
                if t:
                    out.append(t)
    return out


def _is_new(headline, prev_sets, thresh=0.6):
    """직전 회차들의 헤드라인과 60% 미만으로 겹치면 '새 뉴스'로 본다."""
    if not prev_sets:
        return False
    h = _news_toks(headline)
    if not h:
        return False
    for p in prev_sets:
        if len(h & p) / min(len(h), len(p)) >= thresh:
            return False
    return True
