# -*- coding: utf-8 -*-
"""Kafka 틱 스트림을 소비해 코인별 롤링 집계 -> streaming/out/stream.json 원자적 기록.

입력: Kafka 토픽(KAFKA_TOPIC)의 {"coin","px","ts"} 메시지
출력: OUT_PATH(기본 streaming/out/stream.json)에 top-movers 스냅샷 JSON(원자적 쓰기)
실행: python streaming/consumer.py (환경변수로 설정, 아래 참고)
관련: streaming/producer.py, streaming/aggregate.py
"""
from __future__ import annotations

import json
import logging
import os
import time

from kafka import KafkaConsumer

from streaming import aggregate

log = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "market.ticks")
GROUP_ID = os.environ.get("GROUP_ID", "market-agg")
FLUSH_INTERVAL = float(os.environ.get("FLUSH_INTERVAL", "5.0"))
OUT_PATH = os.environ.get("OUT_PATH", "streaming/out/stream.json")


def write_snapshot_atomic(snap: dict, out_path: str) -> None:
    """스냅샷 dict를 out_path에 원자적으로(같은 디렉터리 임시파일 + os.replace) 기록한다."""
    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, out_path)


def run() -> None:
    """소비 -> 집계 -> 주기적 스냅샷 기록 루프."""
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        value_deserializer=lambda b: json.loads(b),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        consumer_timeout_ms=1000,
    )
    log.info(
        "consumer 시작: bootstrap=%s topic=%s group=%s out=%s",
        KAFKA_BOOTSTRAP,
        KAFKA_TOPIC,
        GROUP_ID,
        OUT_PATH,
    )

    state: dict = {}
    last_flush = time.monotonic()

    while True:
        # consumer_timeout_ms에 도달하면 for 루프가 StopIteration으로 자연히 끝나고
        # 여기로 돌아와 유휴 상태에서도 플러시 타이머가 계속 확인되게 한다.
        for msg in consumer:
            state = aggregate.update(state, msg.value)
            now = time.monotonic()
            if now - last_flush >= FLUSH_INTERVAL:
                snap = aggregate.snapshot(state)
                write_snapshot_atomic(snap, OUT_PATH)
                log.info("스냅샷 기록: 코인 %d개", len(snap["coins"]))
                last_flush = now

        now = time.monotonic()
        if now - last_flush >= FLUSH_INTERVAL:
            snap = aggregate.snapshot(state)
            write_snapshot_atomic(snap, OUT_PATH)
            log.info("스냅샷 기록(유휴): 코인 %d개", len(snap["coins"]))
            last_flush = now


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
