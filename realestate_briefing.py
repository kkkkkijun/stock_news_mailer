# -*- coding: utf-8 -*-
"""부동산 브리핑 섹션 (설정 전용).

수집·요약·렌더링 로직은 전부 news_brief.py 에 있고, 이 파일은 부동산 주제 설정
(구글 뉴스 쿼리 / 언론사 RSS / 키워드 / 문구)만 정의한다.
main.py 의 build_body() 가 build_realestate_section() 을 호출한다.

환경변수:
  OPENAI_API_KEY             요약용 (없으면 최신 뉴스 제목 나열로 fallback)
  OPENAI_SUMMARY_MODEL       기본 gpt-4o-mini
  REALESTATE_TOP_N           핵심 뉴스 개수(기본 6)
  REALESTATE_POOL_PER_QUERY  쿼리당 수집 개수(기본 30)
"""
import os

from news_brief import build_briefing, get_openai_client  # noqa: F401

TOP_N = int(os.getenv("REALESTATE_TOP_N", "6"))
POOL_PER_QUERY = int(os.getenv("REALESTATE_POOL_PER_QUERY", "30"))

# --- 구글 뉴스 검색 (폭넓은 발견) : 전부 한국어/한국 지역 ---
_Q = [
    "(부동산 OR 아파트 OR 집값 OR 매매) when:1d",
    "(전세 OR 월세 OR 임대차 OR 역전세) when:1d",
    "(부동산 정책 OR 부동산 규제 OR 대출규제 OR LTV OR DSR) when:1d",
    "(주택담보대출 OR 특례보금자리 OR 디딤돌대출 OR 부동산 금리) when:1d",
    "(분양 OR 청약 OR 아파트 공급 OR 미분양) when:1d",
    "(재건축 OR 재개발 OR 정비사업) when:1d",
    "(집값 동향 OR 아파트값 OR 부동산 시장 OR 거래량) when:1d",
]
QUERIES = [(q, "ko", "KR", "KR:ko") for q in _Q]

# --- 언론사 RSS (요약 근거가 되는 '리드 문단' 제공) ---
REALESTATE_FEEDS = [
    ("매일경제", "https://www.mk.co.kr/rss/50300009/"),
    ("연합뉴스", "https://www.yna.co.kr/rss/economy.xml"),
]
REALESTATE_KEYWORDS = [
    "부동산", "아파트", "집값", "전세", "월세", "분양", "청약", "재건축",
    "재개발", "공시가격", "주택", "임대", "매매", "토지", "지가", "정비사업",
]


def build_realestate_section(client=None):
    return build_briefing(
        header="🏘️ 부동산 PART",
        queries=QUERIES,
        feeds=REALESTATE_FEEDS, keywords=REALESTATE_KEYWORDS,
        role="한국 부동산 시장 애널리스트",
        scope="전국·수도권 종합 관점의 ",
        theme_options="정책, 매매, 전세, 분양청약, 재건축, 금리, 공급, 기타",
        pick_criteria="시장·정책·가격 관점에서 중요한 순으로",
        today_label="[오늘의 부동산 한눈에]",
        today_hint="오늘 부동산 시장 요약 2~3문장(무슨 일/전반 분위기)",
        empty_msg="오늘 수집된 부동산 뉴스가 없습니다.",
        top_n=TOP_N, pool_per_query=POOL_PER_QUERY, client=client,
    )


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(build_realestate_section())
