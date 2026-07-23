# -*- coding: utf-8 -*-
import os
import time
import smtplib
import html
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from urllib.parse import quote

import feedparser
import requests
import pytz
from openai import OpenAI

# .env 로컬 테스트 지원 (GitHub Actions에서는 secrets로 주입되므로 없어도 됨)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# =========================================================
# 설정 (가능한 값은 환경변수로 override, 없으면 기본값 사용)
# =========================================================
KST = pytz.timezone("Asia/Seoul")

# 요약 모델: 코드에 하드코딩하지 않고 env로 변경 가능.
# 기본값 gpt-4o-mini = 저비용/충분한 한국어 요약 품질.
# 품질 우선이면 gpt-4.1-mini 등으로 교체 가능.
SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
SUMMARY_MAX_TOKENS = int(os.getenv("OPENAI_SUMMARY_MAX_TOKENS", "500"))

# 종목 리스트 (env로 override 가능, 콤마 구분)
stock_tickers = os.getenv("STOCK_TICKERS", "NVDA,TSLA,HIMS,RDW").split(",")
crypto_tickers = os.getenv("CRYPTO_TICKERS", "BTC-USD,ETH-USD,SOL-USD").split(",")
stock_tickers = [t.strip() for t in stock_tickers if t.strip()]
crypto_tickers = [t.strip() for t in crypto_tickers if t.strip()]

# 수신자 (env로 override 가능)
recipients = os.getenv(
    "EMAIL_RECIPIENTS", "seo930714@gmail.com,mjikshouse@naver.com"
).split(",")
recipients = [r.strip() for r in recipients if r.strip()]

# 티커별 최대 뉴스 개수
NEWS_PER_TICKER = int(os.getenv("NEWS_PER_TICKER", "3"))

# 기업명 매핑 (제목/요약에 기업명 포함 뉴스 우선 정렬용)
TICKER_NAMES = {
    "NVDA": "Nvidia",
    "TSLA": "Tesla",
    "HIMS": "Hims",
    "RDW": "Redwire Corp",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
}


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
# 4) 이메일 발송
# =========================================================
def send_email(body, subject=None):
    # 발송 시각 표기는 항상 KST(timezone-aware)로 고정
    now = datetime.now(KST)
    hour = now.hour

    if subject is None:
        # 실제 스케줄(07:37 / 17:13) 기준으로 오전/오후 판정
        time_tag = "1차 (오전)" if hour < 12 else "2차 (오후)"
        # %-m/%-d 는 리눅스 전용이라 OS 무관하게 직접 조합
        subject = f"[{now.month}/{now.day} 뉴스 요약 - {time_tag}]"

    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    if not email_user or not email_pass:
        raise RuntimeError("EMAIL_USER / EMAIL_PASS 환경변수가 설정되지 않았습니다.")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_user, email_pass)
        server.sendmail(email_user, recipients, msg.as_string())


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
    return body


if __name__ == "__main__":
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
                print("[site] 발행:", publish(final_body))
            except Exception as e:
                print(f"[site] 발행 실패: {e}")

        # 알림 메일: 본문 전체가 아니라 '준비됐다 + 사이트 링크' 만 짧게 보낸다.
        # 메일이 오지 않으면 파이프라인에 문제가 있다는 신호도 된다.
        # 끄려면 워크플로에서 SEND_EMAIL: '0'.
        if os.getenv("SEND_EMAIL", "1") != "0":
            site = os.getenv(
                "SITE_URL", "https://kkkkkijun.github.io/stock_news_mailer/")
            now = datetime.now(KST)
            tag = "오전" if now.hour < 12 else "오후"
            notice = (
                f"{now.month}월 {now.day}일 {tag} 뉴스 브리핑이 준비됐습니다.\n\n"
                f"{site}\n\n"
                "경제 · 해외주식 · 코인 · 부동산 브리핑을 사이트에서 확인하세요.\n"
                "지난 브리핑은 사이트의 '지난 브리핑'에서 날짜별로 볼 수 있습니다.\n")
            send_email(notice,
                       subject=f"[{now.month}/{now.day} {tag}] "
                               "뉴스 브리핑이 준비됐습니다")
