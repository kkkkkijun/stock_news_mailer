# -*- coding: utf-8 -*-
"""경제 · 코인시장 브리핑 섹션 (설정 전용).

수집·요약·렌더링 로직은 전부 news_brief.py 에 있고, 이 파일은 주제별 설정
(구글 뉴스 쿼리 / 언론사 RSS / 키워드 / 문구)만 정의한다.
main.py 의 build_body() 가 아래 두 함수를 호출한다.

환경변수:
  OPENAI_API_KEY            요약용 (없으면 최신 뉴스 제목 나열로 fallback)
  OPENAI_SUMMARY_MODEL      기본 gpt-4o-mini
  TOPIC_TOP_N               핵심 뉴스 개수(기본 5)
  TOPIC_POOL_PER_QUERY      쿼리당 수집 개수(기본 30)
"""
import os

from news_brief import build_briefing, get_openai_client  # noqa: F401

TOP_N = int(os.getenv("TOPIC_TOP_N", "5"))
POOL_PER_QUERY = int(os.getenv("TOPIC_POOL_PER_QUERY", "30"))

# --- 구글 뉴스 검색 (폭넓은 발견) : (query, hl, gl, ceid) ---
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

# --- 언론사 RSS (요약 근거가 되는 '리드 문단' 제공) ---
ECONOMY_FEEDS = [
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
    ("연합뉴스", "https://www.yna.co.kr/rss/industry.xml"),
    ("매일경제", "https://www.mk.co.kr/rss/30100041/"),
]
ECONOMY_KEYWORDS = [
    "금리", "환율", "물가", "성장", "고용", "연준", "인플레", "수출", "경기",
    "한국은행", "GDP", "국고채", "채권", "무역", "재정",
]

CRYPTO_FEEDS = [
    ("토큰포스트", "https://www.tokenpost.kr/rss"),
]
CRYPTO_KEYWORDS = [
    "비트코인", "가상자산", "암호화폐", "이더리움", "스테이블", "블록체인",
    "업비트", "빗썸", "알트코인", "코인",
]


def build_economy_section(client=None):
    return build_briefing(
        header="💹 경제 PART",
        queries=ECONOMY_QUERIES,
        feeds=ECONOMY_FEEDS, keywords=ECONOMY_KEYWORDS,
        role="한국·글로벌 거시경제(금리·환율·물가·성장·고용·정책) 담당 애널리스트",
        theme_options="금리, 환율, 물가, 성장, 고용, 정책, 기타",
        top_n=TOP_N, pool_per_query=POOL_PER_QUERY, client=client,
    )


def build_crypto_market_section(client=None):
    return build_briefing(
        header="🌐 코인시장 PART",
        queries=CRYPTO_MARKET_QUERIES,
        feeds=CRYPTO_FEEDS, keywords=CRYPTO_KEYWORDS,
        role="가상자산(코인) 시장 전반 담당 애널리스트",
        theme_options="시세, 규제, ETF, 온체인, 거래소, 정책, 기타",
        top_n=TOP_N, pool_per_query=POOL_PER_QUERY, client=client,
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
