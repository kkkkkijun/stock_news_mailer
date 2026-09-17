# -*- coding: utf-8 -*-
"""스트림 집계 순수 로직. Kafka·네트워크 의존 없이 테스트 가능.

입력: {"coin","px","ts"} 틱 메시지
출력: 코인별 롤링 상태 dict, 스냅샷(top movers) dict
실행: 모듈로만 사용(consumer.py가 호출)
관련: consumer.py
"""
from __future__ import annotations

from typing import Any


def update(state: dict[str, dict[str, Any]], msg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """틱 메시지 하나로 코인별 롤링 상태를 갱신한다.

    잘못된 메시지(coin 누락, px 누락/숫자 아님)는 조용히 무시하고 state를 그대로 반환한다.
    """
    coin = msg.get("coin") if isinstance(msg, dict) else None
    if not coin or not isinstance(coin, str):
        return state

    px_raw = msg.get("px")
    try:
        px = float(px_raw)
    except (TypeError, ValueError):
        return state

    ts = msg.get("ts")

    row = state.get(coin)
    if row is None:
        state[coin] = {
            "first": px,
            "last": px,
            "min": px,
            "max": px,
            "n": 1,
            "first_ts": ts,
            "last_ts": ts,
        }
        return state

    row["last"] = px
    row["min"] = min(row["min"], px)
    row["max"] = max(row["max"], px)
    row["n"] += 1
    row["last_ts"] = ts
    return state


def snapshot(state: dict[str, dict[str, Any]], top: int = 15) -> dict[str, Any]:
    """현재 상태로부터 상위 변동 코인 스냅샷을 만든다.

    state가 비어 있으면 {"asof": None, "coins": []}를 반환한다(예외 없이 항상 성공).
    """
    if not state:
        return {"asof": None, "coins": []}

    last_ts_values = [row.get("last_ts") for row in state.values() if row.get("last_ts") is not None]
    asof = max(last_ts_values) if last_ts_values else None

    rows = []
    for coin, row in state.items():
        first = row["first"]
        last = row["last"]
        chg_pct = round((last / first - 1) * 100, 2) if first else 0.0
        rows.append(
            {
                "coin": coin,
                "px": last,
                "chg_pct": chg_pct,
                "ticks": row["n"],
                "lo": row["min"],
                "hi": row["max"],
            }
        )

    rows.sort(key=lambda r: (-abs(r["chg_pct"]), r["coin"]))
    return {"asof": asof, "coins": rows[:top]}
