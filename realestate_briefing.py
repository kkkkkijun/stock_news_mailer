# -*- coding: utf-8 -*-
"""부동산 뉴스 PART — 기존 뉴스 이메일 본문에 덧붙이는 섹션을 생성.

구글 뉴스 RSS(한국)에서 부동산 종합 뉴스를 수집하고 OpenAI로
  ① 오늘의 부동산 한눈에  ② 핵심 뉴스  ③ 흐름·전망
을 정리해 plain-text 섹션 문자열을 반환한다.
main.py 의 build_body() 가 이 섹션을 '공포탐욕지수' 다음에 붙인다.

자체 완결형: feedparser / openai / pytz (기존 requirements) 만 사용하며
main.py 버전에 의존하지 않는다.

환경변수:
  OPENAI_API_KEY            요약용 (없으면 최신 뉴스 제목 나열로 fallback)
  OPENAI_SUMMARY_MODEL      기본 gpt-4o-mini
  REALESTATE_TOP_N          핵심 뉴스 개수(기본 6)
  REALESTATE_POOL_PER_QUERY 쿼리당 수집 개수(기본 25)
"""
import os
import re
import json
import html
import time
from datetime import datetime
from urllib.parse import quote

import feedparser
import pytz

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

KST = pytz.timezone("Asia/Seoul")
SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
POOL_PER_QUERY = int(os.getenv("REALESTATE_POOL_PER_QUERY", "25"))
TOP_N = int(os.getenv("REALESTATE_TOP_N", "6"))

# 종합·전국/수도권 부동산 뉴스 쿼리 (구글 뉴스 RSS, 최근 1일)
QUERIES = [
    "(부동산 OR 아파트 OR 집값 OR 매매) when:1d",
    "(전세 OR 월세 OR 임대차 OR 역전세) when:1d",
    "(부동산 정책 OR 부동산 규제 OR 대출규제 OR LTV OR DSR) when:1d",
    "(주택담보대출 OR 특례보금자리 OR 디딤돌대출 OR 부동산 금리) when:1d",
    "(분양 OR 청약 OR 아파트 공급 OR 미분양) when:1d",
    "(재건축 OR 재개발 OR 정비사업) when:1d",
    "(집값 동향 OR 아파트값 OR 부동산 시장 OR 거래량) when:1d",
]


def get_openai_client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        return None


def _clean(t):
    if not t:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip()


def _ts(entry):
    for k in ("published_parsed", "updated_parsed"):
        v = entry.get(k)
        if v:
            try:
                return time.mktime(v)
            except Exception:
                pass
    return 0.0


def _when(ts):
    if not ts:
        return "시간미상"
    try:
        return datetime.fromtimestamp(ts, KST).strftime("%m/%d %H:%M")
    except Exception:
        return "시간미상"


def fetch_pool():
    """구글 뉴스 RSS 다중 쿼리 → 중복 제거 → 최신순 정렬된 기사 풀."""
    arts = []
    for q in QUERIES:
        url = (f"https://news.google.com/rss/search?q={quote(q)}"
               f"&hl=ko&gl=KR&ceid=KR:ko")
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for e in feed.entries[:POOL_PER_QUERY]:
            title = _clean(e.get("title", ""))
            if not title:
                continue
            pub = ""
            if e.get("source") and e["source"].get("title"):
                pub = e["source"]["title"]
            arts.append({"title": title, "link": e.get("link", ""),
                         "publisher": pub, "ts": _ts(e)})
    seen, uniq = set(), []
    for a in arts:
        key = "".join(c for c in a["title"].lower() if c.isalnum())[:80]
        if key and key not in seen:
            seen.add(key)
            uniq.append(a)
    uniq.sort(key=lambda a: a["ts"], reverse=True)
    return uniq


def _analyze(pool, client):
    """후보 뉴스를 OpenAI로 분석 → (today, picks, outlook)."""
    candidates = pool[:40]
    listing = "\n".join(f"{i}. {a['title']} ({a['publisher']})"
                        for i, a in enumerate(candidates))
    prompt = (
        "너는 한국 부동산 시장 애널리스트다. 아래는 오늘 수집된 부동산 관련 뉴스 후보다. "
        "이 목록의 정보만 근거로(후보에 없는 수치·사실을 지어내지 말 것) 전국·수도권 종합 "
        "관점의 브리핑을 작성해라. 반드시 아래 JSON 형식으로만 출력:\n"
        '{"today":"오늘 부동산 시장 요약 2~3문장(무슨 일/전반 분위기)",'
        '"picks":[{"index":정수,"theme":"정책|매매|전세|분양청약|재건축|금리|기타",'
        '"headline":"간결한 한국어 제목","summary":"1~2문장 요약"}],'
        '"outlook":["단기 흐름·관전 포인트 문장","..."]}\n'
        f"- picks 는 시장·정책·가격 관점에서 중요한 순으로 최대 {TOP_N}건, "
        "단순 사건·사고·광고성·연예성 기사는 제외.\n"
        "- outlook 은 3~4개, 단정적 예측·투자권유가 아니라 '관전 포인트/시사점'으로 서술.\n"
        "- 뉴스가 빈약한 날은 억지로 부풀리지 말고 사실대로 짧게.\n\n"
        f"[후보 목록]\n{listing}"
    )
    resp = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1400,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    picks = []
    for p in data.get("picks", [])[:TOP_N]:
        try:
            src = candidates[int(p["index"])]
        except Exception:
            src = {"publisher": "", "link": "", "ts": 0}
        picks.append({
            "theme": p.get("theme", ""),
            "headline": (p.get("headline") or "").strip(),
            "summary": (p.get("summary") or "").strip(),
            "publisher": src.get("publisher", ""),
            "when": _when(src.get("ts", 0)),
            "link": src.get("link", ""),
        })
    outlook = [o.strip() for o in data.get("outlook", []) if o and o.strip()]
    return (data.get("today") or "").strip(), picks, outlook


def _fallback_headlines(pool, header, note=""):
    lines = [header, "", "[핵심 뉴스]"]
    for a in pool[:TOP_N]:
        lines.append(f"• {a['title']} ({a['publisher']} · {_when(a['ts'])})")
        if a["link"]:
            lines.append(f"  {a['link']}")
    if note:
        lines.append(note)
    return "\n".join(lines)


def build_realestate_section(client=None):
    """이메일 본문에 붙일 '부동산 PART' 문자열 반환. 실패해도 빈 값은 반환하지 않음."""
    header = "🏘️ 부동산 PART"
    if client is None:
        client = get_openai_client()
    try:
        pool = fetch_pool()
    except Exception as e:  # noqa
        return f"{header}\n(뉴스 수집 실패: {e})"
    if not pool:
        return f"{header}\n오늘 수집된 부동산 뉴스가 없습니다."
    if client is None:
        return _fallback_headlines(pool, header)
    try:
        today, picks, outlook = _analyze(pool, client)
    except Exception as e:  # noqa
        return _fallback_headlines(pool, header, note=f"(요약 생성 실패: {e})")

    lines = [header, ""]
    if today:
        lines += ["[오늘의 부동산 한눈에]", today, ""]
    if picks:
        lines.append("[핵심 뉴스]")
        for i, p in enumerate(picks, 1):
            tag = f"({p['theme']}) " if p["theme"] else ""
            lines.append(f"{i}. {tag}{p['headline']}")
            if p["summary"]:
                lines.append(f"   → {p['summary']}")
            meta = " · ".join(x for x in (p["publisher"], p["when"]) if x)
            if meta:
                lines.append(f"   ({meta})")
            if p["link"]:
                lines.append(f"   {p['link']}")
        lines.append("")
    if outlook:
        lines.append("[흐름·전망]")
        for o in outlook:
            lines.append(f"• {o}")
        lines.append("")
    lines.append("※ 정보 제공용이며 투자판단의 책임은 본인에게 있습니다. · 출처: 구글 뉴스")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(build_realestate_section())
