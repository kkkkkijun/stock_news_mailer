# -*- coding: utf-8 -*-
"""뉴스 브리핑 공통 엔진.

구글 뉴스 RSS(폭넓은 발견) + 언론사 RSS(사실 근거가 되는 '리드 문단')를 모아
OpenAI 로 ① 오늘 한눈에 ② 핵심 뉴스 ③ 흐름·전망 을 만들어 plain-text 섹션을 반환.

topic_briefing.py(경제·코인시장)와 realestate_briefing.py(부동산)가 이 모듈을
공유한다. 주제별로 다른 것은 '설정'(쿼리·피드·키워드·문구)뿐이다.

핵심 설계
- 구글 뉴스 RSS 의 description 에는 제목·매체명만 있어 요약 근거가 되지 못한다.
  → 언론사 RSS 에서 리드 문단을 따로 확보해 LLM 에 함께 넘긴다.
- 구글 뉴스 항목이 더 최신이라 그냥 두면 리드 있는 기사가 밀려난다.
  → select_candidates() 로 리드 보유 기사를 우선 배치한다.
- 같은 사건 기사가 중복 선택되는 문제는 프롬프트만으론 불안정하다.
  → dedupe_picks() 로 코드 레벨에서 한 번 더 거른다.

자체 완결형: feedparser / openai / pytz (기존 requirements) 만 사용.
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

# 포털 재게시·수집형 출처 제외 (원 매체가 아니라 재게시 링크로 잡히는 경우)
BLOCKED_PUBLISHERS = {
    "v.daum.net", "n.news.naver.com", "news.naver.com", "media.naver.com",
    "daum.net", "naver.com",
}

# [2단계] 선정 기사 원문 본문 수집 설정
ARTICLE_BODY_CHARS = int(os.getenv("ARTICLE_BODY_CHARS", "1500"))
ARTICLE_FETCH_TIMEOUT = int(os.getenv("ARTICLE_FETCH_TIMEOUT", "12"))
USE_ARTICLE_BODIES = os.getenv("USE_ARTICLE_BODIES", "1") != "0"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


# =========================================================
# 공통 유틸
# =========================================================
def get_openai_client():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        return None


def clean(t):
    if not t:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", t)).strip()


def entry_ts(entry):
    for k in ("published_parsed", "updated_parsed"):
        v = entry.get(k)
        if v:
            try:
                return time.mktime(v)
            except Exception:
                pass
    return 0.0


def when_str(ts):
    if not ts:
        return "시간미상"
    try:
        return datetime.fromtimestamp(ts, KST).strftime("%m/%d %H:%M")
    except Exception:
        return "시간미상"


def _toks(s):
    return {w for w in re.sub(r"[^0-9A-Za-z가-힣 ]", " ", s or "").split()
            if len(w) > 1}


def is_blocked_publisher(pub):
    """포털 재게시/도메인형 출처면 True. (매체명이 비어 있으면 통과)"""
    p = (pub or "").strip().lower()
    if not p:
        return False
    if p in BLOCKED_PUBLISHERS:
        return True
    # 'v.daum.net', 'ppss.kr' 처럼 공백 없는 순수 도메인 형태 = 재게시/블로그성
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}", p))


def news_window():
    """구글 뉴스 검색 기간. 오전 회차(07:37)는 when:1d 로는 전일 오전이 잘리므로
    2일 창으로 넓혀 '전일 전체'를 포괄한다. 오후 회차는 당일 위주로 1일."""
    return "2d" if datetime.now(KST).hour < 12 else "1d"


# =========================================================
# 수집
# =========================================================
def fetch_google_pool(queries, pool_per_query=30):
    """구글 뉴스 RSS 다중 쿼리 → 기사 풀(리드 없음). 포털 재게시 출처는 제외.

    queries: (query, hl, gl, ceid) 튜플 목록. query 안의 'when:1d' 는 실행 시각에
             따라 자동으로 넓혀진다(news_window).
    """
    arts = []
    window = news_window()
    for q, hl, gl, ceid in queries:
        q = q.replace("when:1d", f"when:{window}")
        url = (f"https://news.google.com/rss/search?q={quote(q)}"
               f"&hl={hl}&gl={gl}&ceid={ceid}")
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue
        for e in feed.entries[:pool_per_query]:
            title = clean(e.get("title", ""))
            if not title:
                continue
            pub = ""
            if e.get("source") and e["source"].get("title"):
                pub = e["source"]["title"]
            if is_blocked_publisher(pub):
                continue
            # 구글 뉴스 RSS 는 리드 문단을 주지 않는다(제목·매체명뿐) → lead 비움
            # 링크도 JS 리다이렉트라 본문 수집 불가 → link 비움
            arts.append({"title": title, "publisher": pub,
                         "ts": entry_ts(e), "lead": "", "link": ""})
    return arts


def fetch_publisher_pool(feeds, keywords, max_age_days=2, lead_chars=220):
    """언론사 RSS에서 주제 키워드에 맞는 최근 기사 + '리드 문단'을 수집."""
    out, now = [], time.time()
    for name, url in feeds:
        try:
            f = feedparser.parse(url)
        except Exception:
            continue
        for e in f.entries:
            title = clean(e.get("title", ""))
            if not title:
                continue
            lead = clean(e.get("summary", ""))
            if keywords and not any(k in (title + " " + lead) for k in keywords):
                continue
            ts = entry_ts(e)
            if ts and (now - ts) > max_age_days * 86400:
                continue
            out.append({"title": title, "publisher": name, "ts": ts,
                        "lead": lead[:lead_chars],
                        # 2단계에서 원문 본문을 가져오기 위해 링크 보관
                        "link": e.get("link", "")})
    return out


def merge_pool(items):
    """제목 기준 중복 제거(리드가 있는 쪽 우선) 후 최신순 정렬."""
    best = {}
    for a in items:
        key = "".join(c for c in a["title"].lower() if c.isalnum())[:80]
        if not key:
            continue
        cur = best.get(key)
        if cur is None or (not cur.get("lead") and a.get("lead")):
            best[key] = a
    uniq = list(best.values())
    uniq.sort(key=lambda a: a["ts"], reverse=True)
    return uniq


def select_candidates(pool, limit=40, lead_quota=25):
    """리드(사실 근거)가 있는 기사를 우선 배치하고, 나머지는 구글 뉴스로 채운다."""
    withlead = [a for a in pool if a.get("lead")]
    nolead = [a for a in pool if not a.get("lead")]
    picked = withlead[:lead_quota]
    return (picked + nolead[:limit - len(picked)])[:limit]


def dedupe_picks(picks, head_overlap=0.6, full_jaccard=0.5):
    """선택된 뉴스 중 '사실상 같은 사건'을 제거(프롬프트만으론 불안정해 코드로 보강).

    - 제목 단어 overlap 계수(교집합/짧은쪽) ≥ 0.6  → 같은 사건으로 간주
    - 또는 제목+요약 Jaccard ≥ 0.5
    """
    kept = []
    for p in picks:
        hp = _toks(p.get("headline", ""))
        fp = _toks(f"{p.get('headline','')} {p.get('summary','')}")
        dup = False
        for q in kept:
            hq = _toks(q.get("headline", ""))
            fq = _toks(f"{q.get('headline','')} {q.get('summary','')}")
            if hp and hq and len(hp & hq) / min(len(hp), len(hq)) >= head_overlap:
                dup = True
                break
            if fp and fq and len(fp & fq) / len(fp | fq) >= full_jaccard:
                dup = True
                break
        if not dup:
            kept.append(p)
    return kept


# =========================================================
# 분석(LLM) · 렌더링
# =========================================================
def analyze(pool, client, *, role, theme_options, top_n,
            scope="", today_hint="오늘 상황 요약 2~3문장(무슨 일/전반 분위기)",
            pick_criteria="중요한 순으로"):
    """후보 뉴스를 OpenAI로 분석 → (today, picks, outlook)."""
    candidates = select_candidates(pool)
    rows = []
    for i, a in enumerate(candidates):
        rows.append(f"{i}. {a['title']} ({a['publisher']})")
        if a.get("lead"):
            rows.append(f"   리드: {a['lead']}")
    listing = "\n".join(rows)

    prompt = (
        f"너는 {role}다. 아래는 오늘 수집된 관련 뉴스 후보다. "
        "'리드'는 기사 도입부(사실 근거)다. 요약은 반드시 리드에 근거해 작성하고, "
        "리드가 없는 항목은 제목이 말하는 범위를 넘어 추측하지 마라. "
        "가능하면 리드가 있는(근거가 확인되는) 기사를 우선 선택해라. "
        "이 목록의 정보만 근거로(후보에 없는 수치·사실을 지어내지 말 것) "
        f"{scope}브리핑을 작성해라. 반드시 아래 JSON 형식으로만 출력:\n"
        f'{{"today":"{today_hint}",'
        '"picks":[{"index":정수,"theme":"분류","headline":"간결한 한국어 제목",'
        '"summary":"1~2문장 요약"}],'
        '"outlook":["단기 흐름·관전 포인트 문장","..."]}\n'
        "- theme 은 다음 중 정확히 하나만 고르라(여러 개 나열·구분자 표기 금지): "
        f"{theme_options}\n"
        f"- picks 는 {pick_criteria} {top_n + 3}건까지 제시하라"
        f"(중복 제거 후 상위 {top_n}건만 사용하므로 여유분 포함). "
        "단순 사건·사고·광고성·연예성 기사는 제외.\n"
        "- **같은 사건을 다룬 기사는 반드시 1건만 선택**하라. 원본/종합/타사 재보도 등 "
        "내용이 사실상 동일하면 근거가 가장 충실한 1건만 남기고, 남는 자리는 "
        "서로 다른 사건·주제의 뉴스로 채워라. picks 끼리 주제가 겹치지 않게 하라.\n"
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
    for p in data.get("picks", [])[:top_n + 3]:
        try:
            src = candidates[int(p["index"])]
        except Exception:
            src = {"publisher": "", "ts": 0}
        picks.append({
            # 모델이 "금리|정책" 처럼 여러 개를 넣는 경우가 있어 첫 항목만 사용
            "theme": re.split(r"[|,/·]", (p.get("theme") or ""))[0].strip(),
            "headline": (p.get("headline") or "").strip(),
            "summary": (p.get("summary") or "").strip(),
            "publisher": src.get("publisher", ""),
            "when": when_str(src.get("ts", 0)),
            "link": src.get("link", ""),   # 2단계 본문 수집용
        })
    picks = dedupe_picks(picks)[:top_n]
    outlook = [o.strip() for o in data.get("outlook", []) if o and o.strip()]
    return (data.get("today") or "").strip(), picks, outlook


def fetch_article_body(url, max_chars=None):
    """기사 원문에서 본문만 추출(실패 시 빈 문자열).

    구글 뉴스 링크는 JS 리다이렉트라 본문을 얻을 수 없어 건너뛴다.
    언론사 RSS 로 들어온 기사만 원문 URL 을 가지고 있다.
    """
    max_chars = max_chars or ARTICLE_BODY_CHARS
    if not url or "news.google.com" in url:
        return ""
    try:
        import requests
        import trafilatura
    except Exception:
        return ""          # 의존성 없으면 2단계 자체를 건너뜀
    try:
        r = requests.get(url, headers={"User-Agent": _UA},
                         timeout=ARTICLE_FETCH_TIMEOUT)
        if r.status_code != 200:
            return ""
        txt = trafilatura.extract(r.text) or ""
        return re.sub(r"\n{2,}", "\n", txt).strip()[:max_chars]
    except Exception:
        return ""


def refine_with_bodies(picks, client, *, role, scope="",
                       today_hint="오늘 상황 요약 2~3문장(무슨 일/전반 분위기)"):
    """[2단계] 선정된 기사의 '원문 본문'을 근거로 today/요약/전망을 다시 작성.

    본문을 하나도 확보하지 못하면 None 을 돌려 1단계 결과를 그대로 쓰게 한다.
    """
    bodies = 0
    for p in picks:
        p["_body"] = fetch_article_body(p.get("link", ""))
        if p["_body"]:
            bodies += 1
    if not bodies:
        return None

    # 본문을 확보한 항목만 재작성 대상으로 넘긴다.
    # (본문 없는 항목까지 넘기면 모델이 "정보 제공 불가" 같은 문구로 덮어써 버린다)
    rows = []
    for i, p in enumerate(picks):
        if not p["_body"]:
            continue
        rows.append(f"[{i}] {p['headline']} ({p['publisher']})")
        rows.append(p["_body"])
    listing = "\n\n".join(rows)

    prompt = (
        f"너는 {role}다. 아래는 오늘 선정된 주요 기사와 그 '본문'이다. "
        "본문에 실제로 있는 사실만 사용해 요약과 전망을 다시 작성하라. "
        f"{scope}관점으로 작성하고, 반드시 아래 JSON 형식으로만 출력:\n"
        f'{{"today":"{today_hint}",'
        '"items":[{"i":정수,"summary":"1~2문장 요약"}],'
        '"outlook":["단기 흐름·관전 포인트 문장","..."]}\n'
        "- summary 는 본문의 구체적 수치·주체·시점을 살려 1~2문장으로 작성.\n"
        "- i 는 위 대괄호 번호를 그대로 사용하고, 제시된 기사마다 하나씩 작성.\n"
        "- outlook 은 3~4개, 단정적 예측·투자권유가 아니라 '관전 포인트/시사점'으로 서술.\n"
        "- 영어 기사가 섞여 있어도 모든 출력은 한국어로 작성.\n\n"
        f"[기사]\n{listing}"
    )
    resp = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1400,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)

    for it in data.get("items", []):
        try:
            i = int(it["i"])
            s = (it.get("summary") or "").strip()
        except Exception:
            continue
        # 본문을 확보한 항목만 덮어쓴다(나머지는 1단계 요약 유지)
        if 0 <= i < len(picks) and s and picks[i].get("_body"):
            picks[i]["summary"] = s
    for p in picks:
        p.pop("_body", None)

    today = (data.get("today") or "").strip()
    outlook = [o.strip() for o in data.get("outlook", []) if o and o.strip()]
    return today, picks, outlook


def _fallback_headlines(pool, header, top_n, note=""):
    """LLM 사용 불가/실패 시 최신 제목만이라도 전달."""
    lines = [header, "", "[핵심 뉴스]"]
    for a in pool[:top_n]:
        lines.append(f"• {a['title']} ({a['publisher']} · {when_str(a['ts'])})")
    if note:
        lines.append(note)
    return "\n".join(lines)


def render_section(header, today, picks, outlook, today_label):
    lines = [header, ""]
    if today:
        lines += [today_label, today, ""]
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
# 주제별 진입점에서 호출하는 단일 함수
# =========================================================
def build_briefing(*, header, queries, role, theme_options,
                   feeds=(), keywords=(), top_n=5, pool_per_query=30,
                   scope="", today_label="[오늘 한눈에]",
                   today_hint="오늘 상황 요약 2~3문장(무슨 일/전반 분위기)",
                   pick_criteria="중요한 순으로",
                   empty_msg="오늘 수집된 뉴스가 없습니다.",
                   feed_max_age_days=2, lead_chars=220, client=None):
    """주제별 브리핑 섹션 문자열 반환. 실패해도 빈 값은 반환하지 않는다."""
    if client is None:
        client = get_openai_client()
    try:
        pool = merge_pool(
            fetch_publisher_pool(feeds, keywords,
                                 max_age_days=feed_max_age_days,
                                 lead_chars=lead_chars)
            + fetch_google_pool(queries, pool_per_query=pool_per_query)
        )
    except Exception as e:  # noqa
        return f"{header}\n(뉴스 수집 실패: {e})"
    if not pool:
        return f"{header}\n{empty_msg}"
    if client is None:
        return _fallback_headlines(pool, header, top_n)
    try:
        today, picks, outlook = analyze(
            pool, client, role=role, theme_options=theme_options, top_n=top_n,
            scope=scope, today_hint=today_hint, pick_criteria=pick_criteria)
    except Exception as e:  # noqa
        return _fallback_headlines(pool, header, top_n,
                                   note=f"(요약 생성 실패: {e})")

    # [2단계] 선정 기사의 원문 본문을 근거로 요약·전망 보강.
    # 본문 수집/재작성이 실패해도 1단계 결과를 그대로 사용한다.
    if USE_ARTICLE_BODIES:
        try:
            refined = refine_with_bodies(picks, client, role=role, scope=scope,
                                         today_hint=today_hint)
            if refined:
                today, picks, outlook = refined
        except Exception:  # noqa
            pass

    return render_section(header, today, picks, outlook, today_label)
