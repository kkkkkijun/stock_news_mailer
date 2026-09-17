# -*- coding: utf-8 -*-
"""streaming/aggregate.py 단위 테스트. Kafka·네트워크 없이 순수 로직만 검증한다.

입력: 없음(고정된 틱 시퀀스를 테스트 내부에서 구성)
출력: 없음(pytest assert)
실행: python -m pytest -q tests/test_stream_aggregate.py
관련: streaming/aggregate.py, tests/conftest.py(저장소 루트를 sys.path에 추가)
"""
from __future__ import annotations

from streaming import aggregate


def _ticks():
    return [
        {"coin": "BTC", "px": 100, "ts": 1},
        {"coin": "ETH", "px": 50, "ts": 1},
        {"coin": "BTC", "px": 110, "ts": 2},
        {"coin": "ETH", "px": 55, "ts": 2},
        {"coin": "BTC", "px": 95, "ts": 3},
    ]


def test_update_rolls_up_per_coin_state():
    state: dict = {}
    for msg in _ticks():
        state = aggregate.update(state, msg)

    btc = state["BTC"]
    assert btc["n"] == 3
    assert btc["first"] == 100
    assert btc["last"] == 95
    assert btc["min"] == 95
    assert btc["max"] == 110

    eth = state["ETH"]
    assert eth["n"] == 2
    assert eth["first"] == 50
    assert eth["last"] == 55


def test_snapshot_chg_pct_and_ordering():
    state: dict = {}
    for msg in _ticks():
        state = aggregate.update(state, msg)

    snap = aggregate.snapshot(state)
    by_coin = {row["coin"]: row for row in snap["coins"]}

    assert by_coin["BTC"]["chg_pct"] == -5.0
    assert by_coin["ETH"]["chg_pct"] == 10.0

    # abs(chg_pct) 내림차순: ETH(10.0) 먼저, BTC(-5.0) 다음
    order = [row["coin"] for row in snap["coins"]]
    assert order.index("ETH") < order.index("BTC")

    assert snap["asof"] == 3


def test_bad_message_is_ignored():
    state: dict = {}
    state = aggregate.update(state, {"coin": "BTC", "px": 100, "ts": 1})
    n_before = state["BTC"]["n"]

    state = aggregate.update(state, {"coin": "BTC", "ts": 2})  # px 누락
    state = aggregate.update(state, {"coin": "BTC", "px": "not-a-number", "ts": 3})  # px 비숫자
    state = aggregate.update(state, {"px": 999, "ts": 4})  # coin 누락

    assert state["BTC"]["n"] == n_before


def test_empty_state_snapshot_is_total():
    assert aggregate.snapshot({}) == {"asof": None, "coins": []}
