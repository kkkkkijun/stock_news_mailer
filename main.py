# -*- coding: utf-8 -*-
"""브리핑 파이프라인 오케스트레이터. 수집, 요약, 발행, 푸시 알림을 한 번에 실행한다.

입력: 환경변수(OPENAI_API_KEY, STOCK_TICKERS, CRYPTO_TICKERS 등), news_brief.py/topic_briefing.py/realestate_briefing.py/trump_briefing.py, fundamentals.py, econ_results.py
출력: docs/index.html(publish_site.publish 경유로 발행), 앱 푸시·이메일 알림(notify.py). `refresh` 모드는 실적/시세/10-K만 갱신 후 재렌더만 한다
실행: python main.py (전체 브리핑) 또는 python main.py refresh (LLM 뉴스 수집 없이 실적·시세만 갱신 후 재렌더)
관련: news_brief.py, publish_site.py, notify.py, fundamentals.py, econ_results.py, settings.py, sec.py, quotes.py, earnings.py, llm.py, newsfeed.py
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import netutil
from settings import KST, stock_tickers, crypto_tickers

# ---- 호환 re-export: DAG/fundamentals가 main.X 로 접근 ----
from llm import get_openai_client, chatgpt_summarize
from newsfeed import fetch_news_articles
from quotes import fetch_quote, fetch_all_quotes, build_prices
from earnings import build_earnings, build_reports, EARNINGS_TICKERS, _EARN_KO
from sec import _sec_cik, _SEC_UA, _sec_8k_press

__all__ = [
    "get_openai_client", "chatgpt_summarize", "fetch_news_articles",
    "fetch_quote", "fetch_all_quotes", "build_prices",
    "build_earnings", "build_reports", "EARNINGS_TICKERS", "_EARN_KO",
    "_sec_cik", "_SEC_UA", "_sec_8k_press",
]

log = logging.getLogger(__name__)


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
        r = netutil.get(url, headers=headers, timeout=15)
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
        r = netutil.get("https://api.alternative.me/fng/?limit=1", timeout=15)
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

    # 티커별 뉴스 수집·요약은 서로 독립적이므로 병렬로 실행하되,
    # executor.map은 입력 순서를 보존해 반환하므로 본문 순서는 순차 실행과 동일하다.
    with ThreadPoolExecutor(max_workers=3) as ex:
        for res in ex.map(lambda t: fetch_and_summarize_news(t, client=client), stock_tickers):
            stock_summaries.extend(res)
    with ThreadPoolExecutor(max_workers=3) as ex:
        for res in ex.map(lambda t: fetch_and_summarize_news(t, client=client), crypto_tickers):
            crypto_summaries.extend(res)

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
    from settings import configure_logging
    configure_logging()
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
                log.exception(f"[refresh] fundamentals 실패: {fe}")
            log.info(f"[refresh] 재빌드: {rebuild_all()}")
        except Exception as e:  # noqa
            log.exception(f"[refresh] 실패: {e}")
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
                    log.exception(f"[site] fundamentals 실패: {fe}")
                try:
                    from econ_results import refresh as refresh_econ
                    log.info(f"[site] 경제지표 결과: {refresh_econ()}")  # data/econ_results.json
                except Exception as ee:
                    log.exception(f"[site] econ_results 실패: {ee}")
                log.info(f"[site] 발행: {publish(final_body, quotes=quotes)}")
            except Exception as e:
                log.exception(f"[site] 발행 실패: {e}")

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
