# -*- coding: utf-8 -*-
"""Yahoo Finance 시세 수집과 docs/prices.json 생성.

입력: Yahoo Finance chart JSON(무인증), settings.stock_tickers/crypto_tickers/EARNINGS_TICKERS/KST
출력: fetch_quote()/fetch_all_quotes()의 시세 dict, docs/prices.json(build_prices)
실행: 별도 실행 없음 — main.py가 import해서 사용
관련: settings.py, main.py, earnings.py, netutil.py
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import netutil
from settings import stock_tickers, crypto_tickers, EARNINGS_TICKERS, KST

log = logging.getLogger(__name__)

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


def fetch_quote(symbol: str) -> dict[str, Any] | None:
    """티커 하나의 {ticker, price, chg(%), spark[종가…]} 반환. 실패 시 None."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           "?range=1mo&interval=1d")
    try:
        r = netutil.get(url, headers=_QUOTE_UA, timeout=15)
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
    except Exception as e:
        log.warning("[prices] %s 시세 조회 실패: %s", symbol, e)
        return None


def fetch_all_quotes() -> dict[str, list[dict[str, Any]]]:
    """설정된 모든 티커(주식+코인) 시세 수집. 파트 id(os/coin)로 묶는다.

    각 카드에 수집 기준시각(asof, KST)을 붙여 화면에 '언제 가격인지' 표기한다.
    티커별 조회는 서로 독립적이므로 병렬로 실행하되, executor.map은 입력
    순서를 보존해 반환하므로 결과 구조·순서는 순차 실행과 동일하다.
    """
    all_tickers = list(stock_tickers) + list(crypto_tickers)
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(fetch_quote, all_tickers))
    n_stock = len(stock_tickers)

    out = {"os": [q for q in results[:n_stock] if q],
          "coin": [q for q in results[n_stock:] if q]}
    asof = datetime.now(KST).strftime("%m/%d %H:%M")
    for group in out.values():
        for card in group:
            card["asof"] = asof
    return out


def build_prices(path: str | None = None, quotes: dict[str, Any] | None = None) -> None:
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
        log.warning("[prices] 전부 실패 → 기존 파일 유지")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"asof": datetime.now(KST).strftime("%m/%d %H:%M"),
                   "prices": prices}, f, ensure_ascii=False, indent=1)
    log.info(f"[prices] 저장: {len(prices)}개 종목")
