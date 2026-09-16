# -*- coding: utf-8 -*-
"""quotes.fetch_all_quotes()의 병렬 수집이 순차 실행과 동일한 순서/구조를 내는지 검증.

fetch_quote를 완료 순서가 입력 순서와 반대가 되도록 만든 가짜 함수로 치환해,
executor.map이 입력 순서를 보존해 반환한다는 성질에 의존한 코드가 실제로도
순서를 지키는지 확인한다. 네트워크 없음.

입력: 없음
출력: 없음(pytest 결과)
실행: pytest tests/test_quotes_order.py
관련: quotes.py
"""
import time

import quotes


def test_fetch_all_quotes_preserves_order(monkeypatch):
    monkeypatch.setattr(quotes, "stock_tickers", ["A", "B", "C"])
    monkeypatch.setattr(quotes, "crypto_tickers", ["X", "Y"])

    all_tickers = ["A", "B", "C", "X", "Y"]

    def fake_fetch_quote(t):
        # 인덱스가 클수록 먼저 끝나도록(완료 순서를 입력 순서와 반대로) sleep.
        idx = all_tickers.index(t)
        time.sleep((len(all_tickers) - idx) * 0.01)
        return {"ticker": t, "price": 1.0, "chg": 0.0, "spark": []}

    monkeypatch.setattr(quotes, "fetch_quote", fake_fetch_quote)

    out = quotes.fetch_all_quotes()

    assert [c["ticker"] for c in out["os"]] == ["A", "B", "C"]
    assert [c["ticker"] for c in out["coin"]] == ["X", "Y"]
    for group in out.values():
        for card in group:
            assert "asof" in card
