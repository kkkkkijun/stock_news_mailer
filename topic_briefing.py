# -*- coding: utf-8 -*-
"""주제별 뉴스 브리핑 섹션 생성 (경제 / 코인시장).

구글 뉴스 RSS에서 주제별 뉴스를 수집하고 OpenAI로
  ① 오늘 한눈에  ② 핵심 뉴스  ③ 흐름·전망
을 정리해 plain-text 섹션 문자열을 반환한다.
main.py 의 build_body() 가 각 섹션을 이메일 본문에 붙인다.

realestate_briefing.py 와 동일한 방식이며, 주제(쿼리 세트)만 바꿔 재사용한다.
자체 완결형: feedparser / openai / pytz (기존 requirements) 만 사용.

환경변수:
  OPENAI_API_KEY            요약용 (없으면 최신 뉴스 제목 나열로 fallback)
  OPENAI_SUMMARY_MODEL      기본 gpt-4o-mini
  TOPIC_TOP_N               핵심 뉴스 개수(기본 5)
  TOPIC_POOL_PER_QUERY      쿼리당 수집 개수(기본 20)
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
POOL_PER_QUERY = int(os.getenv("TOPIC_POOL_PER_QUERY", "20"))
TOP_N = int(os.getenv("TOPIC_TOP_N", "5"))

# (query, hl, gl, ceid)
ECONOMY_QUERIES = [
    ("(한국은행 OR 기준금리 OR 원달러 환율 OR 소비자물가) when:1d", "ko", "KR", "KR:ko"),
    ("(경제성장률 OR 수출 OR 고용지표 OR 경기 전망) when:1d", "ko", "KR", "KR:ko"),
    ("(연준 OR 미국 금리 OR 인플레이션 OR 국채금리) when:1d", "ko", "KR", "KR:ko"),
    ('(federal reserve OR inflation OR "interest rates" OR economy) when:1d',
     "en-US", "US", "US:en"),
]

CRYPTO_MARKET_QUERIES = [
    ("(비트코인 OR 가상자산 OR 암호화폐 OR 코인 시장) when:1d", "ko", "KR", "KR:ko"),
    ("(비트코인 ETF OR 가상자산 규제 OR 스테이블코인 OR 업비트) when:1d", "ko", "KR", "KR:ko"),
    ('(bitcoin OR "crypto market" OR ethereum) when:1d', "en-US", "US", "US:en"),
    ('("bitcoin ETF" OR "crypto regulation" OR stablecoin) when:1d', "en-US", "US", "US:en"),
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


def fetch_pool(queries):
    """구글 뉴스 RSS 다중 쿼리 → 중복 제거 → 최신순 정렬된 기사 풀."""
    arts = []
    for q, hl, gl, ceid in queries:
        url = (f"https://news.google.com/rss/search?q={quote(q)}"
               f"&hl={hl}&gl={gl}&ceid={ceid}")
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
            arts.append({"title": title, "publisher": pub, "ts": _ts(e)})
    seen, uniq = set(), []
    for a in arts:
        key = "".join(c for c in a["title"].lower() if c.isalnum())[:80]
        if key and key not in seen:
            seen.add(key)
            uniq.append(a)
    uniq.sort(key=lambda a: a["ts"], reverse=True)
    return uniq


def _analyze(pool, client, topic_desc, theme_hint, top_n):
    """후보 뉴스를 OpenAI로 분석 → (today, picks, outlook)."""
    candidates = pool[:40]
    listing = "\n".join(f"{i}. {a['title']} ({a['publisher']})"
                        for i, a in enumerate(candidates))
    prompt = (
        f"너는 {topic_desc} 담당 애널리스트다. 아래는 오늘 수집된 관련 뉴스 후보다. "
        "이 목록의 정보만 근거로(후보에 없는 수치·사실을 지어내지 말 것) 브리핑을 작성해라. "
        "반드시 아래 JSON 형식으로만 출력:\n"
        '{"today":"오늘 상황 요약 2~3문장(무슨 일/전반 분위기)",'
        '"picks":[{"index":정수,"theme":"분류","headline":"간결한 한국어 제목",'
        '"summary":"1~2문장 요약"}],'
        '"outlook":["단기 흐름·관전 포인트 문장","..."]}\n'
        f"- theme 은 다음 중 하나: {theme_hint}\n"
        f"- picks 는 중요한 순으로 최대 {top_n}건, 단순 사건·사고·광고성·연예성 기사는 제외.\n"
        "- outlook 은 3~4개, 단정적 예측·투자권유가 아니라 '관전 포인트/시사점'으로 서술.\n"
        "- 영어 기사가 섞여 있어도 모든 출력은 한국어로 작성.\n"
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
    for p in data.get("picks", [])[:top_n]:
        try:
            src = candidates[int(p["index"])]
        except Exception:
            src = {"publisher": "", "ts": 0}
        picks.append({
            "theme": p.get("theme", ""),
            "headline": (p.get("headline") or "").strip(),
            "summary": (p.get("summary") or "").strip(),
            "publisher": src.get("publisher", ""),
            "when": _when(src.get("ts", 0)),
        })
    outlook = [o.strip() for o in data.get("outlook", []) if o and o.strip()]
    return (data.get("today") or "").strip(), picks, outlook


def _fallback_headlines(pool, header, top_n, note=""):
    lines = [header, "", "[핵심 뉴스]"]
    for a in pool[:top_n]:
        lines.append(f"• {a['title']} ({a['publisher']} · {_when(a['ts'])})")
    if note:
        lines.append(note)
    return "\n".join(lines)


def build_section(header, queries, topic_desc, theme_hint,
                  client=None, top_n=TOP_N):
    """주제별 브리핑 섹션 문자열 반환. 실패해도 빈 값은 반환하지 않음."""
    if client is None:
        client = get_openai_client()
    try:
        pool = fetch_pool(queries)
    except Exception as e:  # noqa
        return f"{header}\n(뉴스 수집 실패: {e})"
    if not pool:
        return f"{header}\n오늘 수집된 뉴스가 없습니다."
    if client is None:
        return _fallback_headlines(pool, header, top_n)
    try:
        today, picks, outlook = _analyze(pool, client, topic_desc,
                                         theme_hint, top_n)
    except Exception as e:  # noqa
        return _fallback_headlines(pool, header, top_n,
                                   note=f"(요약 생성 실패: {e})")

    lines = [header, ""]
    if today:
        lines += ["[오늘 한눈에]", today, ""]
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
        lines.append("")
    if outlook:
        lines.append("[흐름·전망]")
        for o in outlook:
            lines.append(f"• {o}")
    return "\n".join(lines).rstrip()


# =========================================================
# 주제별 진입점
# =========================================================
def build_economy_section(client=None):
    return build_section(
        "💹 경제 PART", ECONOMY_QUERIES,
        "한국·글로벌 거시경제(금리·환율·물가·성장·고용·정책)",
        "금리|환율|물가|성장|고용|정책|기타",
        client=client,
    )


def build_crypto_market_section(client=None):
    return build_section(
        "🌐 코인시장 PART", CRYPTO_MARKET_QUERIES,
        "가상자산(코인) 시장 전반",
        "시세|규제|ETF|온체인|거래소|정책|기타",
        client=client,
    )


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    c = get_openai_client()
    print(build_economy_section(c))
    print()
    print(build_crypto_market_section(c))
