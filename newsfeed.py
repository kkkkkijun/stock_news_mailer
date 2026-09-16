# -*- coding: utf-8 -*-
"""티커별 뉴스 기사 수집(Yahoo Finance RSS + Google News RSS). main.py에서 분리.

[중요 - 수집 기준 명확화]
Yahoo Finance RSS(및 yfinance)는 "조회수/인기순/트렌딩" 정렬을 제공하지 않는다.
  - RSS 피드는 발행시간 역순(최신순)으로만 내려온다.
  - 조회수(view count) 데이터 자체가 공개 API로 노출되지 않으므로
    "조회수 많은 뉴스" 정렬은 기술적으로 불가능하다.
따라서 현실적인 대체 정렬 기준을 적용한다:
  1) 발행시간 최신순
  2) 제목/요약에 티커명 또는 기업명이 포함된 뉴스 우선 (관련성)
  3) 동일 뉴스 중복 제거 (제목/링크 기준)
  4) Google News RSS로 티커별 최신 뉴스를 보완
각 기사: publisher, published_at, link, title, related_ticker 저장.

입력: settings.TICKER_NAMES/NEWS_PER_TICKER, Yahoo Finance RSS, Google News RSS
출력: fetch_news_articles(ticker) → 구조화된 기사 dict 리스트
실행: 별도 실행 없음 — main.py가 import해서 사용
관련: main.py, earnings.py, settings.py
"""
from __future__ import annotations

import html
import re
import time
from urllib.parse import quote

import feedparser

from settings import TICKER_NAMES, NEWS_PER_TICKER

__all__ = ["fetch_news_articles"]


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


def fetch_news_articles(ticker: str) -> list[dict]:
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
