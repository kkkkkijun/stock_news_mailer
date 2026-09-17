# streaming/ — Kafka 실시간 시세 집계 프로토타입

Hyperliquid의 실시간 중간가(mid price)를 Kafka로 흘려보내고, 코인별 롤링 집계(상위 변동 코인)를 몇 초 간격으로 JSON 스냅샷에 기록하는 스트리밍 ETL 프로토타입입니다. 포트폴리오용으로 만든 독립 모듈이며, 저장소 루트의 배치 파이프라인과는 코드를 공유하지 않습니다.

## 토폴로지

```
Hyperliquid allMids
        |
        v
   producer.py  --publish-->  Kafka topic(market.ticks)
                                        |
                                        v
                              consumer.py (코인별 롤링 집계)
                                        |
                                        v
                          streaming/out/stream.json (원자적 쓰기)
```

## 실행 방법

```bash
cd streaming
cp .env.example .env   # 필요하면 값 수정
docker compose up -d
```

`streaming/out/stream.json`을 tail로 지켜보면 몇 초마다 갱신되는 상위 변동 코인 스냅샷을 볼 수 있습니다.

```bash
tail -f streaming/out/stream.json
```

## 왜 Kafka인가

- **수집 속도와 처리 속도 분리**: producer는 Hyperliquid를 폴링하는 속도로, consumer는 자기 페이스로 소비합니다. 한쪽이 느려져도 다른 쪽이 막히지 않습니다.
- **재생 가능한 로그**: 토픽에 쌓인 메시지는 컨슈머 그룹을 새로 만들어 처음부터 다시 읽을 수 있습니다. 집계 로직을 바꿔도 원본 틱은 그대로 남아 재계산이 가능합니다.
- **컨슈머 수평 확장**: 같은 group_id로 컨슈머를 여러 개 띄우면 파티션 단위로 부하가 분산됩니다(이 프로토타입은 단일 파티션·단일 컨슈머로 단순화했습니다).
- **배치 대비 실시간**: 저장소 루트의 뉴스/시세 파이프라인은 몇 시간 간격 배치(Airflow 프로토타입 포함)로 충분하지만, 이 스트리밍 구조는 초 단위로 갱신되는 데이터에 맞습니다.

## 정직한 참고사항

실제 운영 중인 사이트(`docs/`로 발행되는 브리핑)는 지금도 배치 파이프라인 + `airflow/` 오케스트레이션 프로토타입으로 동작합니다. 이 `streaming/` 디렉터리는 같은 종류의 시세 데이터를 스트리밍 방식으로 처리해보는 별도의 포트폴리오 프로토타입이며, 운영 사이트를 대체하지 않습니다.

## 구성 파일

| 파일 | 역할 |
|---|---|
| `aggregate.py` | 순수 집계 로직(Kafka·네트워크 의존 없음, 단위 테스트 대상) |
| `producer.py` | Hyperliquid allMids 폴링 → Kafka 발행 |
| `consumer.py` | Kafka 소비 → 롤링 집계 → JSON 스냅샷 원자적 기록 |
| `Dockerfile` | producer/consumer 공용 이미지(빌드 컨텍스트는 저장소 루트) |
| `docker-compose.yml` | kafka(KRaft 단일 노드) + producer + consumer |
| `.env.example` | 환경변수 기본값 예시 |

## 테스트

Kafka 없이 `aggregate.py`만 단위 테스트합니다.

```bash
python -m pytest -q tests/test_stream_aggregate.py
```
