# -*- coding: utf-8 -*-
"""트럼프 SNS(Truth Social) 발언 브리핑 섹션.

trumpstruth.org(Truth Social 공개 미러) RSS에서 최근 게시물을 수집하고
OpenAI로 한국어 번역·요약한다. main.py build_body() 가 '💬 트럼프 PART' 로 붙인다.

- 범위: 전체 발언 요약(시장 관련만 아니라 전반). 다만 광고성/재게시 반복은 정리.
- 원문이 영어라 반드시 번역+요약. 정치적 주장은 '트럼프의 주장'임을 명확히.
- 단일 소스(비공식 미러)라 실패 시 조용히 섹션을 비우고 메일 본체는 유지.

자체 완결형: feedparser / openai(news_brief 재사용) / pytz.
환경변수: TRUMP_MAX_POSTS(요약 대상 최대 게시물, 기본 25),
          TRUMP_TOP_N(노출 발언 수, 기본 6), TRUMP_MAX_AGE_HOURS(기본 24)
"""
import os
import re
import json
import html
import time
import calendar
from datetime import datetime

import feedparser
import pytz

from news_brief import get_openai_client, SUMMARY_MODEL

KST = pytz.timezone("Asia/Seoul")
FEED_URL = os.getenv("TRUMP_FEED_URL", "https://trumpstruth.org/feed")
MAX_POSTS = int(os.getenv("TRUMP_MAX_POSTS", "25"))
TOP_N = int(os.getenv("TRUMP_TOP_N", "6"))
MAX_AGE_HOURS = int(os.getenv("TRUMP_MAX_AGE_HOURS", "24"))
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _clean(t):
    return html.unescape(re.sub(r"<[^>]+>", " ", t or "")).strip()


def _ts(e):
    for k in ("published_parsed", "updated_parsed"):
        if e.get(k):
            try:
                # feedparser 의 *_parsed 는 UTC → timegm(로컬 타임존 무관)
                return calendar.timegm(e[k])
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


def fetch_posts():
    """최근 발언(dict: text, ts, when) 목록. 최신순."""
    feed = feedparser.parse(FEED_URL, request_headers={"User-Agent": _UA})
    now, out = time.time(), []
    for e in feed.entries:
        text = _clean(e.get("summary", "") or e.get("title", ""))
        # 서명 꼬리("President DONALD J. TRUMP") 제거
        text = re.sub(r"\s*President DONALD J\.?\s*TRUMP\.?\s*$", "", text).strip()
        if not text:
            continue
        ts = _ts(e)
        if ts and (now - ts) > MAX_AGE_HOURS * 3600:
            continue
        out.append({"text": text[:600], "ts": ts, "when": _when(ts)})
    out.sort(key=lambda a: a["ts"], reverse=True)
    return out[:MAX_POSTS]


def _analyze(posts, client):
    listing = "\n".join(f"[{i}] ({p['when']}) {p['text']}"
                        for i, p in enumerate(posts))
    prompt = (
        "다음은 도널드 트럼프 미국 대통령이 소셜미디어(Truth Social)에 올린 최근 "
        "게시물 원문(영어)이다. 한국 독자를 위해 한국어로 정리하라. "
        "반드시 아래 JSON 형식으로만 출력:\n"
        '{"today":"오늘 트럼프 발언의 전반 분위기·핵심 주제 2~3문장",'
        '"posts":[{"i":정수,"topic":"분류","summary":"발언 요지 1~2문장 한국어"}],'
        '"market":"시장·경제·관세·연준 관련 언급이 있으면 그 요지 1~2문장. '
        '관련 언급이 없으면 이 값은 반드시 빈 문자열 \\"\\" 로 둘 것(설명 문구를 넣지 말 것)",'
        '"outlook":["발언이 정책·시장·외교에 주는 시사점 또는 관전 포인트 문장","..."]}\n'
        "- topic 은 다음 중 하나: 경제·통상, 외교·안보, 국내정치, 인사·지지, 사법·논란, 기타\n"
        f"- posts 는 중요·화제성 순으로 최대 {TOP_N}건. 같은 내용 반복·단순 지지선언 "
        "남발은 하나로 합치고, 서로 다른 주제로 채워라.\n"
        "- outlook 은 2~4개. 오늘 발언을 바탕으로 앞으로 지켜볼 지점·파급 가능성을 "
        "'관전 포인트/시사점'으로 서술하되, 단정적 예측이나 투자권유는 금지. "
        "발언에 없는 사실을 지어내지 말고 '~할 가능성', '~에 주목' 같은 신중한 표현을 써라.\n"
        "- 원문에 있는 내용만 사용하고 없는 사실을 지어내지 마라. "
        "정치적 주장은 '트럼프가 ~라고 주장/언급'처럼 화자를 명확히 하라.\n"
        "- 과격한 표현은 순화하되 핵심 의미는 살려라.\n\n"
        f"[게시물]\n{listing}"
    )
    resp = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1300,
        response_format={"type": "json_object"},
    )
    data = json.loads(resp.choices[0].message.content)
    picks = []
    for p in data.get("posts", [])[:TOP_N]:
        try:
            src = posts[int(p["i"])]
        except Exception:
            src = {"when": ""}
        picks.append({
            "topic": re.split(r"[|,/·]", (p.get("topic") or ""))[0].strip(),
            "summary": (p.get("summary") or "").strip(),
            "when": src.get("when", ""),
        })
    outlook = [o.strip() for o in data.get("outlook", []) if o and o.strip()]
    market = (data.get("market") or "").strip()
    # 모델이 빈 문자열 대신 '빈 문자열'/'없음' 같은 무의미 값을 넣는 경우 제거
    if market in ("", "빈 문자열", "없음", "해당 없음", "N/A", "null", "None"):
        market = ""
    return (data.get("today") or "").strip(), picks, market, outlook


def build_trump_section(client=None):
    """이메일/사이트 본문에 붙일 '트럼프 PART' 문자열. 실패해도 빈 값 아님."""
    header = "💬 트럼프 PART"
    if client is None:
        client = get_openai_client()
    try:
        posts = fetch_posts()
    except Exception as e:  # noqa
        return f"{header}\n(발언 수집 실패: {e})"
    if not posts:
        return f"{header}\n최근 {MAX_AGE_HOURS}시간 내 새 발언이 없습니다."
    if client is None:
        lines = [header, "", "[최근 발언]"]
        for p in posts[:TOP_N]:
            lines.append(f"• ({p['when']}) {p['text'][:120]}")
        return "\n".join(lines)
    try:
        today, picks, market, outlook = _analyze(posts, client)
    except Exception as e:  # noqa
        lines = [header, "", "[최근 발언]"]
        for p in posts[:TOP_N]:
            lines.append(f"• ({p['when']}) {p['text'][:120]}")
        lines.append(f"(요약 실패: {e})")
        return "\n".join(lines)

    lines = [header, ""]
    if today:
        lines += ["[오늘 한눈에]", today, ""]
    if picks:
        lines.append("[주요 발언]")
        for i, p in enumerate(picks, 1):
            tag = f"({p['topic']}) " if p["topic"] else ""
            lines.append(f"{i}. {tag}{p['summary']}")
            if p["when"]:
                lines.append(f"   (Truth Social · {p['when']})")
        lines.append("")
    if market:
        lines += ["[시장·경제 관련]", f"• {market}", ""]
    if outlook:
        lines.append("[흐름·전망]")
        for o in outlook:
            lines.append(f"• {o}")
        lines.append("")
    lines.append("※ 트럼프 본인의 소셜미디어 발언으로, 사실 여부는 별도 확인이 필요합니다.")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(build_trump_section())
