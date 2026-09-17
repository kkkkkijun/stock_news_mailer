# -*- coding: utf-8 -*-
"""Hyperliquid allMids를 폴링해 코인별 시세 틱을 Kafka 토픽으로 발행.

입력: 없음(Hyperliquid https://api.hyperliquid.xyz/info POST {"type":"allMids"} 폴링)
출력: Kafka 토픽(KAFKA_TOPIC)에 코인별 {"coin","px","ts"} 메시지 발행
실행: python streaming/producer.py (환경변수로 설정, 아래 참고)
관련: streaming/consumer.py, streaming/aggregate.py
"""
from __future__ import annotations

import json
import logging
import os
import time

import requests
from kafka import KafkaProducer

log = logging.getLogger(__name__)

HYPERLIQUID_URL = "https://api.hyperliquid.xyz/info"

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "market.ticks")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "2.0"))


def fetch_all_mids() -> dict[str, str]:
    """Hyperliquid allMids를 한 번 조회해 {coin: px_str} dict를 반환한다."""
    resp = requests.post(HYPERLIQUID_URL, json={"type": "allMids"}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def run() -> None:
    """폴링 -> 발행 루프. 한 사이클의 오류는 로그만 남기고 계속 진행한다."""
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode(),
        key_serializer=lambda k: k.encode(),
        retries=3,
        linger_ms=50,
    )
    log.info("producer 시작: bootstrap=%s topic=%s interval=%.1fs", KAFKA_BOOTSTRAP, KAFKA_TOPIC, POLL_INTERVAL)

    while True:
        try:
            mids = fetch_all_mids()
            ts = int(time.time() * 1000)
            count = 0
            for coin, px_str in mids.items():
                try:
                    px = float(px_str)
                except (TypeError, ValueError):
                    continue
                producer.send(KAFKA_TOPIC, key=coin, value={"coin": coin, "px": px, "ts": ts})
                count += 1
            producer.flush()
            log.info("발행 완료: %d개 코인", count)
        except Exception:
            log.exception("폴링/발행 중 오류 발생, 다음 주기로 계속 진행")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
