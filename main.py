# -*- coding: utf-8 -*-
"""브리핑 파이프라인 오케스트레이터. 수집, 요약, 발행, 푸시 알림을 한 번에 실행한다.

입력: 환경변수(OPENAI_API_KEY, STOCK_TICKERS, CRYPTO_TICKERS 등), news_brief.py/topic_briefing.py/realestate_briefing.py/trump_briefing.py, fundamentals.py, econ_results.py
출력: docs/index.html(publish_site.publish 경유로 발행), 앱 푸시·이메일 알림(notify.py). `refresh` 모드는 실적/시세/10-K만 갱신 후 재렌더만 한다
실행: python main.py (전체 브리핑) 또는 python main.py refresh (LLM 뉴스 수집 없이 실적·시세만 갱신 후 재렌더)
관련: news_brief.py, publish_site.py, notify.py, fundamentals.py, econ_results.py, settings.py, sec.py, quotes.py, earnings.py
"""
import os
import time
import html
import re
from datetime import datetime
from urllib.parse import quote

import feedparser
import requests
from openai import OpenAI

from settings import (
    KST, SUMMARY_MODEL, SUMMARY_MAX_TOKENS, NEWS_PER_TICKER, TICKER_NAMES,
)

# ---- 호환 re-export: DAG/fundamentals가 main.X 로 접근 ----
from quotes import fetch_quote, fetch_all_quotes, build_prices
from earnings import build_earnings, build_reports, EARNINGS_TICKERS, _EARN_KO
from sec import _sec_cik, _SEC_UA, _sec_8k_press
from settings import stock_tickers, crypto_tickers, TICKER_NAMES, NEWS_PER_TICKER, KST


# =========================================================
# 1) ChatGPT 요약 (모델 env화 + fallback + rate limit 처리)
# =========================================================
def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def chatgpt_summarize(text, client=None, max_retries=2):
    """뉴스 텍스트를 한국어로 요약.
    - 모델명은 SUMMARY_MODEL(env)에서 가져옴 (하드코딩 금지)
    - 빈 입력 / API 에러 / rate limit 처리
    - 실패 시 원문 일부를 fallback 으로 반환
    """
    text = (text or "").strip()
    if not text:
        return "(요약할 뉴스 본문이 없습니다)"

    if client is None:
        client = get_openai_client()
    if client is None:
        # API 키가 없으면 요약 없이 원문 앞부분만 fallback
        return text[:200] + ("..." if len(text) > 200 else "")

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": f"다음 뉴스 내용을 한국어로 2~3문장으로 간결히 요약해줘:\n{text}",
                    }
                ],
                max_tokens=SUMMARY_MAX_TOKENS,
            )
            content = response.choices[0].message.content
            return content.strip() if content else "(요약 결과가 비어 있습니다)"
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            # rate limit / 일시적 오류는 지수 백오프 재시도
            if "rate" in msg or "429" in msg or "timeout" in msg or "503" in msg:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
            break

    # 최종 실패 시: 원문 앞부분 fallback (메일이 깨지지 않도록)
    fallback = text[:200] + ("..." if len(text) > 200 else "")
    return f"(요약 실패, 원문 일부) {fallback}"


# =========================================================
# 2) 뉴스 수집
#
# [중요 - 수집 기준 명확화]
# Yahoo Finance RSS(및 yfinance)는 "조회수/인기순/트렌딩" 정렬을 제공하지 않는다.
#   - RSS 피드는 발행시간 역순(최신순)으로만 내려온다.
#   - 조회수(view count) 데이터 자체가 공개 API로 노출되지 않으므로
#     "조회수 많은 뉴스" 정렬은 기술적으로 불가능하다.
# 따라서 현실적인 대체 정렬 기준을 적용한다:
#   1) 발행시간 최신순
#   2) 제목/요약에 티커명 또는 기업명이 포함된 뉴스 우선 (관련성)
#   3) 동일 뉴스 중복 제거 (제목/링크 기준)
#   4) Google News RSS로 티커별 최신 뉴스를 보완
# 각 기사: publisher, published_at, link, title, related_ticker 저장.
# =========================================================
def _entry_published_ts(entry):
    """RSS entry의 발행시각을 epoch(float)로. 없으면 0."""
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            try:
                return time.mktime(val)
            except Exception:
                pass
    return 0.0


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)  # HTML 태그 제거
    return html.unescape(text).strip()


def fetch_news_articles(ticker):
    """티커별 뉴스 기사 목록(dict)을 구조화해서 반환."""
    articles = []
    name = TICKER_NAMES.get(ticker, "")

    # --- 소스 1: Yahoo Finance RSS (기본, 최신순) ---
    yahoo_url = (
        f"https://feeds.finance.yahoo.com/rss/2.0/headline"
        f"?s={ticker}&region=US&lang=en-US"
    )
    # --- 소스 2: Google News RSS (보완) ---
    query = f'{ticker} OR "{name}"' if name else ticker
    google_url = (
        f"https://news.google.com/rss/search?q={quote(query)}"
        f"&hl=en-US&gl=US&ceid=US:en"
    )

    for src_url, src_name in ((yahoo_url, "Yahoo Finance"), (google_url, "Google News")):
        try:
            feed = feedparser.parse(src_url)
        except Exception:
            continue
        for entry in feed.entries:
            title = _clean(entry.get("title", ""))
            if not title:
                continue
            publisher = src_name
            # Google News는 source 태그에 실제 매체명을 담는 경우가 있음
            if entry.get("source") and entry["source"].get("title"):
                publisher = entry["source"]["title"]
            articles.append(
                {
                    "title": title,
                    "summary": _clean(entry.get("summary", "")),
                    "link": entry.get("link", ""),
                    "publisher": publisher,
                    "published_at": _entry_published_ts(entry),
                    "related_ticker": ticker,
                }
            )

    # --- 중복 제거 (정규화한 제목 기준) ---
    seen = set()
    unique = []
    for a in articles:
        key = re.sub(r"\W+", "", a["title"].lower())[:80]
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    # --- 정렬: (관련성 우선) → (최신순) ---
    def relevance(a):
        blob = (a["title"] + " " + a["summary"]).lower()
        hit = ticker.split("-")[0].lower() in blob
        if name and name.lower() in blob:
            hit = True
        return 1 if hit else 0

    unique.sort(key=lambda a: (relevance(a), a["published_at"]), reverse=True)
    return unique[:NEWS_PER_TICKER]


def fetch_and_summarize_news(ticker, client=None):
    """티커별 뉴스를 수집·요약해 메일용 문자열 리스트로 반환."""
    articles = fetch_news_articles(ticker)
    if not articles:
        return [f"📰 [{ticker}] 수집된 뉴스가 없습니다.\n"]

    summaries = []
    for a in articles:
        summary = chatgpt_summarize(a["title"] + "\n" + a["summary"], client=client)
        when = (
            datetime.fromtimestamp(a["published_at"], KST).strftime("%m/%d %H:%M")
            if a["published_at"]
            else "시간미상"
        )
        summaries.append(
            f"📰 [{ticker}] {a['title']}\n"
            f"   ({a['publisher']} · {when})\n"
            f"→ {summary}\n"
        )
    return summaries


# =========================================================
# 3) 공포탐욕지수
#
# [중요 - 값이 다른 원인 분석]
# 기존 코드는 api.alternative.me/fng 를 사용했는데, 이것은
# "Crypto Fear & Greed Index"(암호화폐 전용)다.
# 반면 INDEXerGO / CNN 등이 보여주는 값은
# "CNN Fear & Greed Index"(미국 주식시장 기준)로 산출 방식과 대상이 전혀 다르다.
# 즉 두 지표는 애초에 다른 지수이므로 값이 일치하지 않는 것이 정상이다.
# → 주식시장 지표는 CNN, 암호화폐 지표는 Alternative.me 로 분리하고
#   각각 출처를 명확히 표기한다.
# =========================================================
def get_cnn_fear_greed():
    """CNN Fear & Greed Index (미국 주식시장 기준).
    CNN 비공식 JSON 엔드포인트. 브라우저 User-Agent 필요(없으면 418).
    ※ 도메인 주의: CNN이 .com → .io 로 이전함.
      구(舊) production.dataviz.cnn.com 은 DNS 해석이 안 돼 NameResolutionError 발생.
      현재 유효 엔드포인트는 production.dataviz.cnn.io 이다.
    """
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        fg = r.json()["fear_and_greed"]
        return {
            "source": "CNN 기준",
            "value": round(float(fg["score"])),
            "classification": str(fg.get("rating", "")).title(),
            "updated_at": fg.get("timestamp", ""),
        }
    except Exception as e:
        return {
            "source": "CNN 기준",
            "value": None,
            "classification": f"가져오기 실패: {e}",
            "updated_at": "",
        }


def get_crypto_fear_greed():
    """Crypto Fear & Greed Index (암호화폐 기준, Alternative.me)."""
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=15)
        r.raise_for_status()
        data = r.json()["data"][0]
        ts = data.get("timestamp", "")
        updated = ""
        if ts:
            try:
                updated = datetime.fromtimestamp(int(ts), KST).strftime(
                    "%Y-%m-%d %H:%M KST"
                )
            except Exception:
                updated = ts
        return {
            "source": "크립토 기준",
            "value": int(data["value"]),
            "classification": data.get("value_classification", ""),
            "updated_at": updated,
        }
    except Exception as e:
        return {
            "source": "크립토 기준",
            "value": None,
            "classification": f"가져오기 실패: {e}",
            "updated_at": "",
        }


def format_fear_greed_section():
    """공포탐욕지수 섹션 문자열 생성 (출처 명확히 표기)."""
    stock = get_cnn_fear_greed()
    crypto = get_crypto_fear_greed()

    def line(d):
        val = d["value"] if d["value"] is not None else "-"
        return f"  - {d['source']}: {val} ({d['classification']})"
        
    return (
        "\n📊 공포탐욕지수\n"
        f"{line(stock)}\n"
        f"{line(crypto)}\n"
    )


# =========================================================
# 메인 실행
# =========================================================
def build_body(client=None):
    stock_summaries = []
    crypto_summaries = []

    for ticker in stock_tickers:
        stock_summaries.extend(fetch_and_summarize_news(ticker, client=client))
    for ticker in crypto_tickers:
        crypto_summaries.extend(fetch_and_summarize_news(ticker, client=client))

    now = datetime.now(KST)
    body = f"[오늘의 뉴스 요약] {now.strftime('%Y-%m-%d %H:%M KST')}\n\n"
    # 💹 경제 PART (국내+글로벌 거시 맥락을 먼저)
    try:
        from topic_briefing import build_economy_section
        body += build_economy_section(client=client) + "\n\n"
    except Exception as e:
        body += f"💹 경제 PART\n(생성 실패: {e})\n\n"

    body += "📈 해외주식 PART\n"
    body += "\n".join(stock_summaries) + "\n\n"
    body += "🪙 코인 PART\n"
    body += "\n".join(crypto_summaries)

    # 🌐 코인시장 PART (코인 시장 전반 뉴스·흐름·전망)
    try:
        from topic_briefing import build_crypto_market_section
        body += "\n\n" + build_crypto_market_section(client=client)
    except Exception as e:
        body += f"\n\n🌐 코인시장 PART\n(생성 실패: {e})"

    body += "\n" + format_fear_greed_section()

    # 🏘️ 부동산 PART (구글 뉴스 종합 + LLM 요약/전망).
    # 부동산 수집/요약 실패가 뉴스 메일 전체를 깨지 않도록 방어.
    try:
        from realestate_briefing import build_realestate_section
        body += "\n\n" + build_realestate_section(client=client)
    except Exception as e:
        body += f"\n\n🏘️ 부동산 PART\n(생성 실패: {e})"

    # 💬 트럼프 PART (Truth Social 발언 번역·요약).
    try:
        from trump_briefing import build_trump_section
        body += "\n\n" + build_trump_section(client=client)
    except Exception as e:
        body += f"\n\n💬 트럼프 PART\n(생성 실패: {e})"
    return body


if __name__ == "__main__":
    import sys as _sys
    # 'refresh' 모드: 뉴스·메일 없이 실적/시세/보고서만 갱신 후 저장된 본문으로 재렌더.
    #   → 실적 발표(SEC 8-K) 직후 자주 돌려 '즉각 반영'. (Yahoo 지연 무관)
    if len(_sys.argv) > 1 and _sys.argv[1] == "refresh":
        try:
            from publish_site import rebuild_all
            build_earnings()
            quotes = fetch_all_quotes()
            build_prices(quotes=quotes)
            build_reports(client=get_openai_client())
            try:
                from fundamentals import build_fundamentals, build_qualitative
                build_fundamentals()          # data/fundamentals.json (성장주 탭)
                build_qualitative(client=get_openai_client())  # 10-K 정성(캐시)
            except Exception as fe:  # noqa
                print(f"[refresh] fundamentals 실패: {fe}")
            print("[refresh] 재빌드:", rebuild_all())
        except Exception as e:  # noqa
            print(f"[refresh] 실패: {e}")
        _sys.exit(0)

    client = get_openai_client()
    final_body = build_body(client=client)

    # DRY_RUN=1 이면 발송/발행 없이 본문만 출력 (테스트용)
    if os.getenv("DRY_RUN") == "1":
        print(final_body)
    else:
        # 웹 페이지 발행 (docs/index.html → GitHub Pages)
        # 실패해도 메일 발송은 계속되도록 방어
        if os.getenv("PUBLISH_SITE", "1") != "0":
            try:
                from publish_site import publish
                build_earnings()          # data/earnings.json 갱신(실패해도 기존 유지)
                quotes = fetch_all_quotes()
                build_prices(quotes=quotes)   # docs/prices.json (내 목표 현재가)
                build_reports(client=client)  # data/reports.json (실적 보고서)
                try:
                    from fundamentals import build_fundamentals, build_qualitative
                    build_fundamentals()      # data/fundamentals.json (성장주 탭)
                    build_qualitative(client=client)  # 10-K 정성(캐시)
                except Exception as fe:
                    print(f"[site] fundamentals 실패: {fe}")
                try:
                    from econ_results import refresh as refresh_econ
                    print("[site] 경제지표 결과:", refresh_econ())  # data/econ_results.json
                except Exception as ee:
                    print(f"[site] econ_results 실패: {ee}")
                print("[site] 발행:", publish(final_body, quotes=quotes))
            except Exception as e:
                print(f"[site] 발행 실패: {e}")

        # 새 브리핑 알림. 기본은 '앱 푸시'(배지+팝업)로 보낸다.
        site = os.getenv(
            "SITE_URL", "https://kkkkkijun.github.io/stock_news_mailer/")
        now = datetime.now(KST)
        tag = "오전" if now.hour < 12 else "오후"
        notice = (
            f"{now.month}월 {now.day}일 {tag} 뉴스 브리핑이 준비됐습니다.\n\n"
            f"{site}\n\n"
            "경제 · 해외주식 · 코인 · 부동산 브리핑을 사이트에서 확인하세요.\n"
            "지난 브리핑은 사이트의 '지난 브리핑'에서 날짜별로 볼 수 있습니다.\n")
        from notify import notify_briefing
        notify_briefing(now, site, notice)
