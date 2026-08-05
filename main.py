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
stock_tickers = os.getenv("STOCK_TICKERS", "NVDA,TSLA,HIMS,RDW,IREN").split(",")
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
    "IREN": "IREN Limited",
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

    # 💬 트럼프 PART (Truth Social 발언 번역·요약).
    try:
        from trump_briefing import build_trump_section
        body += "\n\n" + build_trump_section(client=client)
    except Exception as e:
        body += f"\n\n💬 트럼프 PART\n(생성 실패: {e})"
    return body


# =========================================================
# 시세 (웹 페이지 시세 카드 + 스파크라인용)
#  - 이메일 본문에는 넣지 않고, publish_site 에 넘겨 웹에서만 카드로 렌더.
#  - Yahoo Finance chart JSON(무인증)로 현재가·전일대비·일봉 종가 시계열 수집.
#  - 실패(429/네트워크 등)해도 None 반환 → 카드 없이 조용히 넘어감.
# =========================================================
_QUOTE_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def fetch_quote(symbol):
    """티커 하나의 {ticker, price, chg(%), spark[종가…]} 반환. 실패 시 None."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           "?range=1mo&interval=1d")
    try:
        r = requests.get(url, headers=_QUOTE_UA, timeout=15)
        res = r.json()["chart"]["result"][0]
        meta = res["meta"]
        closes = [c for c in res["indicators"]["quote"][0]["close"]
                  if c is not None]
        price = meta.get("regularMarketPrice")
        if price is None and closes:
            price = closes[-1]
        # 전일 대비(일간) 등락: meta.previousClose 는 range 기준 한 달 전 값을
        # 주는 경우가 있어, 일봉 종가 시계열의 '전일 종가'로 계산한다.
        prev = closes[-2] if len(closes) >= 2 else None
        chg = round((price - prev) / prev * 100, 2) if price and prev else None
        return {
            "ticker": symbol,
            "price": round(price, 2) if price is not None else None,
            "chg": chg,
            "spark": [round(c, 2) for c in closes[-14:]],
        }
    except Exception:
        return None


def fetch_all_quotes():
    """설정된 모든 티커(주식+코인) 시세 수집. 파트 id(os/coin)로 묶는다.

    각 카드에 수집 기준시각(asof, KST)을 붙여 화면에 '언제 가격인지' 표기한다.
    """
    out = {"os": [], "coin": []}
    for t in stock_tickers:
        q = fetch_quote(t)
        if q:
            out["os"].append(q)
    for t in crypto_tickers:
        q = fetch_quote(t)
        if q:
            out["coin"].append(q)
    asof = datetime.now(KST).strftime("%m/%d %H:%M")
    for group in out.values():
        for card in group:
            card["asof"] = asof
    return out


# =========================================================
# 기업 실적 일정 (M7 + 관심종목) → data/earnings.json (일정 탭 우측)
#   Yahoo quoteSummary calendarEvents(crumb 방식, 무키)로 종목별 '다음 실적일'.
#   전부 실패 시 기존 파일 유지(덮어쓰지 않음).
# =========================================================
_EARN_KO = {
    "NVDA": "엔비디아", "MSFT": "마이크로소프트", "AAPL": "애플",
    "GOOGL": "알파벳", "AMZN": "아마존", "META": "메타", "TSLA": "테슬라",
    "HIMS": "힘스앤허스", "RDW": "레드와이어", "IREN": "아이렌", "PLTR": "팔란티어",
    "RKLB": "로켓랩",
}
# M7 필수 + 관심종목(HIMS·RDW·IREN) + PLTR·RKLB(일정 전용)
EARNINGS_TICKERS = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "TSLA",
                    "HIMS", "RDW", "IREN", "PLTR", "RKLB"]


def _yahoo_earn_session():
    s = requests.Session()
    s.headers.update({"User-Agent": _QUOTE_UA["User-Agent"]})
    try:
        s.get("https://fc.yahoo.com", timeout=8)
    except Exception:
        pass
    crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb",
                  timeout=8).text.strip()
    return s, crumb


def _g(node, *keys):
    for k in keys:
        node = node.get(k) if isinstance(node, dict) else None
    return node


def _num(node):
    return node.get("raw") if isinstance(node, dict) else None


def _pctval(fmt):
    try:
        return float(str(fmt).replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _signfmt(fmt):
    """'5.54%' → ('+5.54%', True) / '-3%' → ('-3%', False)."""
    if fmt is None:
        return None, None
    f = str(fmt).strip()
    neg = f.startswith("-")
    if not neg and not f.startswith("+"):
        f = "+" + f
    return f, (not neg)


def _ym_ts(ts):
    if not ts:
        return ""
    from datetime import datetime as _dt
    x = _dt.utcfromtimestamp(ts)
    return f"{x.year % 100:02d}.{x.month:02d}"


def _ym_str(s):
    return f"{s[2:4]}.{s[5:7]}" if s and len(s) >= 7 else ""


def _fetch_earning(session, crumb, sym):
    """종목 다음 실적일 + 상세(직전실적·컨센서스·목표주가·의견·리비전·서프라이즈)."""
    from datetime import datetime as _dt
    mods = ("calendarEvents,earnings,earningsTrend,earningsHistory,"
            "financialData,recommendationTrend")
    r = session.get(f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                    f"{sym}?modules={mods}&crumb={crumb}", timeout=12)
    if r.status_code != 200:
        return None
    res = r.json()["quoteSummary"]["result"][0]

    ce = res.get("calendarEvents", {}).get("earnings", {})
    raws = [x["raw"] for x in ce.get("earningsDate", []) if "raw" in x]
    date = (_dt.fromtimestamp(min(raws), KST).strftime("%Y-%m-%d")
            if raws else None)   # 실적 발표일: 한국시간(KST) 기준
    est = bool(ce.get("isEarningsDateEstimate"))

    d = {}
    hist = res.get("earningsHistory", {}).get("history", []) or []
    if hist:
        last = hist[-1]
        ea, ee = _num(last.get("epsActual")), _num(last.get("epsEstimate"))
        sfmt, spos = _signfmt(_g(last, "surprisePercent", "fmt"))
        d["prev"] = {"period": _ym_ts(_num(last.get("quarter"))),
                     "eps_act": f"${ea:.2f}" if ea is not None else "-",
                     "eps_est": f"${ee:.2f}" if ee is not None else "-",
                     "surprise": sfmt, "surprise_pos": spos}
        sp = []
        for q in hist:
            v = _pctval(_g(q, "surprisePercent", "fmt"))
            if v is not None:
                sf, sposq = _signfmt(_g(q, "surprisePercent", "fmt"))
                sp.append({"fmt": sf, "v": v, "pos": sposq})
        d["surprises"] = sp
    for t in res.get("earningsTrend", {}).get("trend", []) or []:
        per = t.get("period")
        if per in ("0q", "+1q"):
            avg = _num(_g(t, "earningsEstimate", "avg"))
            lo = _num(_g(t, "earningsEstimate", "low"))
            hi = _num(_g(t, "earningsEstimate", "high"))
            gfmt, gpos = _signfmt(_g(t, "growth", "fmt"))
            rev = _g(t, "revenueEstimate", "avg", "fmt")
            blk = {"period": _ym_str(t.get("endDate")),
                   "eps": f"${avg:.2f}" if avg is not None else "-",
                   "eps_range": (f"${lo:.2f}~${hi:.2f}"
                                 if lo is not None and hi is not None else ""),
                   "rev": f"${rev}" if rev else "-",
                   "growth": gfmt, "growth_pos": gpos}
            if per == "0q":          # 곧 발표할 그 분기 = '이번 발표 예상'
                d["cur"] = blk
                d["rev"] = {"up": _num(_g(t, "epsRevisions", "upLast30days")),
                            "down": _num(_g(t, "epsRevisions", "downLast30days"))}
            else:                    # +1q = 그 다음 분기
                d["next"] = blk
    # 분기별(과거 실제 + 다가올 예상) → 기업실적 '분기별' 토글용.
    #   회계분기 종료월의 '캘린더 분기(1Q~4Q)'로 그룹핑(NVDA 등 오프셋 흡수).
    def _cq(per):
        try:
            y = 2000 + int(per[:2]); mo = int(per[3:5]); q = (mo - 1) // 3 + 1
            return f"{y}-{q}", f"{y} {q}Q"
        except (ValueError, TypeError):
            return None, None
    qmap = {}
    for q in hist:
        per = _ym_ts(_num(q.get("quarter")))
        cq, cql = _cq(per)
        if not cq:
            continue
        ea, ee = _num(q.get("epsActual")), _num(q.get("epsEstimate"))
        sfmt, spos = _signfmt(_g(q, "surprisePercent", "fmt"))
        qmap[cq] = {"cq": cq, "label": cql, "reported": True,
                    "eps_act": f"${ea:.2f}" if ea is not None else "-",
                    "eps_est": f"${ee:.2f}" if ee is not None else "-",
                    "surprise": sfmt, "surprise_pos": spos}
    for t in res.get("earningsTrend", {}).get("trend", []) or []:
        if t.get("period") in ("0q", "+1q"):
            cq, cql = _cq(_ym_str(t.get("endDate")))
            if not cq or cq in qmap:
                continue
            avg = _num(_g(t, "earningsEstimate", "avg"))
            rev = _g(t, "revenueEstimate", "avg", "fmt")
            e = {"cq": cq, "label": cql, "reported": False,
                 "eps_est": f"${avg:.2f}" if avg is not None else "-",
                 "rev": f"${rev}" if rev else None}
            if t.get("period") == "0q":
                e["date"] = date
            qmap[cq] = e
    d["quarters"] = [qmap[k] for k in sorted(qmap)]

    fd = res.get("financialData", {}) or {}
    pr, mn = _num(fd.get("currentPrice")), _num(fd.get("targetMeanPrice"))
    lo2, hi2 = _num(fd.get("targetLowPrice")), _num(fd.get("targetHighPrice"))
    up = round((mn - pr) / pr * 100) if pr and mn else None
    d["target"] = {"price": f"${pr:,.2f}" if pr else "-",
                   "mean": f"${mn:,.2f}" if mn else "-",
                   "range": (f"${lo2:,.0f}~${hi2:,.0f}" if lo2 and hi2 else ""),
                   "upside": (f"{'+' if up >= 0 else ''}{up}%" if up is not None else None),
                   "upside_pos": (up is not None and up >= 0)}
    _rk = {"strong_buy": "적극 매수", "buy": "매수", "hold": "보유",
           "underperform": "비중 축소", "sell": "매도"}
    key = fd.get("recommendationKey")
    d["rec"] = {"label": _rk.get(key, key or "-"),
                "count": _num(fd.get("numberOfAnalystOpinions"))}
    rt = res.get("recommendationTrend", {}).get("trend", []) or []
    if rt:
        t0 = rt[0]
        d["rec"].update({"buy": (t0.get("strongBuy", 0) or 0) + (t0.get("buy", 0) or 0),
                         "hold": t0.get("hold", 0) or 0,
                         "sell": (t0.get("sell", 0) or 0) + (t0.get("strongSell", 0) or 0)})
    return {"date": date, "ts": (min(raws) if raws else None),
            "est": est, "detail": d}


def build_earnings(path=None):
    import json
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "earnings.json")
    try:
        session, crumb = _yahoo_earn_session()
    except Exception as e:  # noqa
        print(f"[earnings] 세션 실패: {e}")
        return
    if not crumb:
        print("[earnings] crumb 없음 → 기존 파일 유지")
        return
    out, ok = [], False
    for t in EARNINGS_TICKERS:
        try:
            info = _fetch_earning(session, crumb, t)
        except Exception:
            info = None
        if info is not None:
            ok = True
        out.append({"ticker": t, "name": _EARN_KO.get(t, t),
                    "date": info["date"] if info else None,
                    "ts": info.get("ts") if info else None,
                    "est": bool(info["est"]) if info else False,
                    "detail": info.get("detail") if info else None})
    if not ok:
        print("[earnings] 전부 실패 → 기존 파일 유지")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[earnings] 저장: {sum(1 for r in out if r['date'])}/{len(out)}개 실적일")


def build_prices(path=None, quotes=None):
    """보유종목 현재가용 docs/prices.json 생성(same-origin → '내 목표' 앱이 읽음).
       추적 종목(주식+실적 티커)만. 전부 실패 시 기존 파일 유지."""
    import json
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "docs", "prices.json")
    prices = {}
    if quotes:  # 이미 받은 시세 재사용(중복 호출 방지)
        for group in quotes.values():
            for c in group:
                if c.get("price") is not None:
                    prices[c["ticker"]] = c["price"]
    want = set(EARNINGS_TICKERS) | set(stock_tickers)
    for t in sorted(want):
        if t in prices:
            continue
        q = fetch_quote(t)
        if q and q.get("price") is not None:
            prices[t] = q["price"]
    if not prices:
        print("[prices] 전부 실패 → 기존 파일 유지")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"asof": datetime.now(KST).strftime("%m/%d %H:%M"),
                   "prices": prices}, f, ensure_ascii=False, indent=1)
    print(f"[prices] 저장: {len(prices)}개 종목")


# =========================================================
# 실적 보고서 (SEC 8-K 원문 → AI 한글 요약) → data/reports.json
#   기업실적 '보고서' 탭. 최근(50일 내) 발표만, accession 캐시로 재생성 최소화.
# =========================================================
_SEC_UA = {"User-Agent": "stock-news-mailer research (contact: tjrlwns93@ermore.co.kr)"}
_CIK_CACHE = None


def _sec_cik(sym):
    global _CIK_CACHE
    if _CIK_CACHE is None:
        try:
            ct = requests.get("https://www.sec.gov/files/company_tickers.json",
                              headers=_SEC_UA, timeout=15).json()
            _CIK_CACHE = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in ct.values()}
        except Exception:
            _CIK_CACHE = {}
    return _CIK_CACHE.get(sym)


def _sec_8k_press(sym):
    """최근 실적 8-K(Item 2.02)의 보도자료 원문 텍스트 + 메타. 실패 시 None."""
    import re
    import html as _html
    cik = _sec_cik(sym)
    if not cik:
        return None
    try:
        rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                           headers=_SEC_UA, timeout=15).json()["filings"]["recent"]
        acc = accept = None
        for form, a, items, adt in zip(rec["form"], rec["accessionNumber"],
                                       rec["items"], rec["acceptanceDateTime"]):
            if form == "8-K" and "2.02" in (items or ""):
                acc, accept = a, adt
                break
        if not acc:
            return None
        accn = acc.replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}"
        # 문서 목록: index.json(타입·크기) 우선, 실패 시 디렉터리 HTML 스크랩.
        htms = []
        try:
            for it in requests.get(base + "/index.json", headers=_SEC_UA,
                                   timeout=15).json()["directory"]["item"]:
                n = it.get("name", "")
                if n.lower().endswith((".htm", ".html")):
                    htms.append((n, (it.get("type") or ""), int(it.get("size") or 0)))
        except Exception:
            for n in re.findall(r'href="([^"]+\.html?)"',
                                requests.get(base + "/", headers=_SEC_UA, timeout=15).text):
                htms.append((n.split("/")[-1], "", 0))
        pr = None
        for n, ty, _sz in htms:                       # 1) EX-99* 타입
            if ty.upper().startswith("EX-99"):
                pr = n
                break
        if not pr:                                    # 2) 이름 패턴
            for n, ty, _sz in htms:
                if re.search(r"ex.?-?99|press|earn|release", n, re.I):
                    pr = n
                    break
        if not pr:                                    # 3) 래퍼/인덱스 제외 후 가장 큰 htm
            cand = sorted([(sz, n) for n, ty, sz in htms
                           if not re.search(r"index|form|8-?k|primary", n, re.I)],
                          reverse=True)
            pr = cand[0][1] if cand else (htms[0][0] if htms else None)
        if not pr:
            return None
        url = base + "/" + pr
        raw = requests.get(url, headers=_SEC_UA, timeout=15).text
        text = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw))).strip()
        return {"text": text[:7000], "url": url, "acc": acc, "accept": accept}
    except Exception:
        return None


def _report_kdate(accept):
    """8-K 접수시각(ET ISO) → KST (yymmdd, YYYY-MM-DD)."""
    from datetime import datetime as _dt
    for s in (accept, re.sub(r"\.\d+", "", accept or "")):
        try:
            return (_dt.fromisoformat(s).astimezone(KST).strftime("%y%m%d"),
                    _dt.fromisoformat(s).astimezone(KST).strftime("%Y-%m-%d"))
        except (ValueError, TypeError, AttributeError):
            continue
    return "", ""


def _period_cq(per):
    """'26.06' → ('2026-2', '2026 2Q')."""
    try:
        y = 2000 + int(per[:2])
        q = (int(per[3:5]) - 1) // 3 + 1
        return f"{y}-{q}", f"{y} {q}Q"
    except (ValueError, TypeError, IndexError):
        return None, None


def _period_qend(per):
    """'26.06' → '2026-06-30' (해당 분기말 날짜, 문자열 비교용)."""
    try:
        y = 2000 + int(per[:2])
        mo = int(per[3:5])
        last = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}[mo]
        return f"{y}-{mo:02d}-{last:02d}"
    except (ValueError, TypeError, KeyError, IndexError):
        return "9999-99-99"


def _gen_report(client, name, sym, qlabel, numbers, press_text):
    import json as _json
    if client is None:
        return {"headline": f"{name} {qlabel} 실적", "verdict": "",
                "metrics": [], "guidance": "", "bullets": ["(요약 생성 불가: API 키 없음)"]}
    prompt = (
        f"{name}({sym})의 {qlabel} 실적 발표 자료다.\n"
        f"[확정 숫자]\n{numbers}\n\n"
        f"[발표문 원문 발췌]\n{press_text}\n\n"
        "위 정보로 '실적 보고서 요약'을 한국어로 작성해 JSON만 출력하라.\n"
        "확정 숫자·발표문에 있는 값만 쓰고, 없는 수치·주장은 지어내지 말 것. 투자 조언 금지.\n"
        '형식: {"headline":"한 줄 핵심(<=40자)","verdict":"beat|miss|inline",'
        '"metrics":[{"k":"지표","v":"값"}],'
        '"guidance":"가이던스 요지(없으면 빈문자열)",'
        '"bullets":["요약 3~4개; 실적/가이던스/주목; 마지막은 리스크·유의점"]}'
    )
    try:
        resp = client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}, max_tokens=700)
        data = _json.loads(resp.choices[0].message.content or "{}")
        return {"headline": data.get("headline", ""), "verdict": data.get("verdict", ""),
                "metrics": (data.get("metrics") or [])[:5],
                "guidance": data.get("guidance", ""),
                "bullets": (data.get("bullets") or [])[:4]}
    except Exception as e:
        print(f"[reports] {sym} 요약 실패: {e}")
        return {"headline": f"{name} {qlabel} 실적", "verdict": "",
                "metrics": [], "guidance": "", "bullets": []}


def build_reports(path=None, client=None):
    import json as _json
    from datetime import datetime as _dt
    edir = os.path.dirname(os.path.abspath(__file__))
    path = path or os.path.join(edir, "data", "reports.json")
    try:
        earns = {r["ticker"]: r for r in
                 _json.load(open(os.path.join(edir, "data", "earnings.json"), encoding="utf-8"))}
    except (OSError, ValueError):
        print("[reports] earnings.json 없음 → 중단")
        return
    try:
        existing = {r["ticker"]: r for r in _json.load(open(path, encoding="utf-8"))}
    except (OSError, ValueError):
        existing = {}
    if client is None:
        client = get_openai_client()
    now = datetime.now(KST)
    out = []
    for t in EARNINGS_TICKERS:
        er = earns.get(t)
        if not er:
            continue
        det = er.get("detail") or {}
        cur, prev = det.get("cur") or {}, det.get("prev") or {}
        rq = [q for q in (det.get("quarters") or []) if q.get("reported")]
        if not rq and not cur.get("period"):
            continue
        time.sleep(0.3)                     # SEC 레이트리밋 여유
        press = _sec_8k_press(t)
        if not press:
            if t in existing:
                out.append(existing[t])
            continue
        kshort, kiso = _report_kdate(press.get("accept"))
        try:
            days = (now.date() - _dt.strptime(kiso, "%Y-%m-%d").date()).days
        except (ValueError, TypeError):
            days = 999
        if days > 50:                       # 오래된 발표는 제외
            if t in existing:
                out.append(existing[t])
            continue
        if existing.get(t, {}).get("acc") == press["acc"]:   # 캐시
            out.append(existing[t])
            continue
        # 발표 분기 판정(8-K 접수일 기준): 접수일이 cur(0q) 분기말 이후면
        #   Yahoo 실제치 미반영 상태 → cur(0q)가 방금 발표분. 아니면 최신 실제분기(prev).
        cur_cq, cur_label = (_period_cq(cur["period"]) if cur.get("period") else (None, None))
        yahoo_lag = bool(cur_cq and kiso and kiso > _period_qend(cur["period"]))
        if yahoo_lag:
            cq, qlabel = cur_cq, cur_label
        elif rq:
            cq, qlabel = rq[-1].get("cq"), rq[-1].get("label", "")
        else:
            if t in existing:
                out.append(existing[t])
            continue
        if not cq:
            if t in existing:
                out.append(existing[t])
            continue
        try:
            qnum = int(cq.split("-")[1])
        except (ValueError, IndexError):
            qnum = 0
        name = _EARN_KO.get(t, t)
        if yahoo_lag:        # Yahoo 실제치 미반영 → 발표문 원문에서 실제 추출 유도
            numbers = (f"이번 분기 시장 예상 EPS {cur.get('eps', '-')} 매출 {cur.get('rev', '-')}; "
                       "실제 수치·서프라이즈는 발표문 원문 기준으로 추출할 것")
        else:
            numbers = (f"EPS 실제 {prev.get('eps_act', '-')} / 예상 {prev.get('eps_est', '-')} "
                       f"(서프라이즈 {prev.get('surprise', '-')})")
        print(f"[reports] {t} 8-K 요약 생성… ({qlabel})")
        summ = _gen_report(client, name, t, f"{qnum}분기", numbers, press["text"])
        rec = {"ticker": t, "name": name,
               "title": f"{kshort}_{name}_{qnum}분기_실적보고서",
               "date": kiso, "qnum": qnum, "quarter": qlabel, "cq": cq,
               "acc": press["acc"], "url": press["url"]}
        if not yahoo_lag:    # Yahoo 실제치 있을 때만 EPS/서프라이즈 첨부
            rec.update({"eps_act": prev.get("eps_act"), "eps_est": prev.get("eps_est"),
                        "surprise": prev.get("surprise"), "surprise_pos": prev.get("surprise_pos")})
        rec.update(summ)
        out.append(rec)
    if not out:
        print("[reports] 생성된 보고서 없음")
        return
    out.sort(key=lambda r: r.get("date", ""), reverse=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[reports] 저장: {len(out)}개")


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
                print("[site] 발행:", publish(final_body, quotes=quotes))
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
