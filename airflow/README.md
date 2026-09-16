# Airflow Orchestration Layer

기존 배치 파이프라인을 Airflow DAG로 오케스트레이션(포트폴리오용 로컬 프로토타입).

## 아키텍처

```
                      +-------------------+
                      |   sources (API,   |
                      |  RSS, OpenAI, ...)|
                      +---------+---------+
                                |
        +---------------+------+------+----------------+
        |               |             |                |
        v               v             v                v
  [fetch_quotes]  [build_earnings]  [build_fundamentals] [refresh_econ]
        |               |             |                |
        v               v             v                |
  [build_prices]  [build_reports] [build_qualitative]   |
        |               |             |                |
        +-------+-------+------+------+----------------+
                |              |
                |         [build_news]
                |              |
                +------+-------+
                       v
                   [publish]
                       |
                       v
                  [send_push]
```

daily_briefing DAG은 위 그래프대로 하루 두 번(06:00, 17:00 KST) 돈다. 이와
별개로 map_refresh DAG이 매시 정각에 RWA 지도와 고래 지갑 데이터를 갱신한다
(daily_briefing과 독립적인 태스크, 의존 관계 없음).

## DAG 목록

| DAG | 스케줄 (KST) | 태스크 |
| --- | --- | --- |
| `daily_briefing` | 매일 06:00, 17:00 (`0 6,17 * * *`) | fetch_quotes, build_earnings, build_prices, build_reports, build_fundamentals, build_qualitative, refresh_econ, build_news, publish, send_push |
| `map_refresh` | 매시 정각 (`0 * * * *`) | rwa_refresh, whales_refresh |

## 실행 방법 A — 외부 접속 (GitHub Codespaces, 무료·관리자 불필요, 추천)

로컬에 Docker/WSL/관리자 권한이 없어도 되고, 공개 HTTPS URL로 외부에서 접속된다.
회사/개인 PC를 인터넷에 여는 게 아니라 **GitHub 클라우드 컨테이너**만 열린다.

1. 저장소 페이지 → **Code ▸ Codespaces ▸ Create codespace on main**.
2. 컨테이너가 뜨면 `.devcontainer/postCreate.sh`가 자동으로 `airflow/.env`를
   임의 시크릿·강한 admin 비밀번호로 생성하고 `docker compose up -d`까지 실행한다.
   터미널 로그에 **admin 비밀번호가 1회 출력**되니 저장해 둘 것.
3. 아래 **PORTS** 탭에서 포트 **8080** 우클릭 → **Port Visibility ▸ Public**.
4. 그 포트의 URL을 열어 `admin` + (2에서 받은 비번)으로 로그인.
5. DAG 목록에서 `daily_briefing`·`map_refresh`를 Unpause.

> 태스크가 실제로 뉴스·시세를 처리하게 하려면 `airflow/.env`의 `OPENAI_API_KEY`
> 등을 실제 값으로 바꾸고 `docker compose up -d`를 다시 실행한다. 키가 없어도
> UI·DAG 구조는 정상적으로 뜬다.

## 실행 방법 B — 로컬 (Docker 필요)

로컬에 Docker Desktop(관리자 권한·WSL2 필요)이 있는 경우:

```bash
cp .env.template .env      # AIRFLOW_ADMIN_PASSWORD, SECRET_KEY, OPENAI_API_KEY 채우기
docker compose up -d
```

브라우저에서 http://localhost:8080 접속, `.env`에 설정한 계정으로 로그인.

> ⚠️ Airflow는 임의 파이썬 코드를 실행한다. UI를 외부에 노출한다면 **약한 비밀번호
> 금지** — `.env`의 `AIRFLOW_ADMIN_PASSWORD`를 반드시 길고 임의의 값으로. 개인 PC를
> 포트포워딩으로 직접 여는 방식은 권장하지 않는다(방법 A 사용).

## 참고

운영(실제 발송)은 지금도 GitHub Actions + cron-job.org로 돌아간다. 이 Airflow
레이어는 같은 ETL 태스크를 대상으로 DAG 설계, 태스크 의존성, 재시도, 스케줄링,
백필(backfill)을 보여주기 위한 오케스트레이션 프로토타입이다.

## 설계 포인트

- 병렬 추출/변환 후 fan-in: 여러 독립 태스크가 끝난 뒤 `publish` 한 곳으로 모인다.
- XCom으로 `quotes`·`body` 전달: `fetch_quotes`/`build_news`의 리턴값을 `publish`가
  `ti.xcom_pull`로 받아 사용한다.
- 멱등 태스크: 각 태스크는 기존 파이프라인 함수처럼 파일을 원자적으로 재빌드하므로
  같은 인터벌을 재실행(backfill/재시도)해도 안전하다.
- 재시도 2회 (`retries=2`, `retry_delay=5분`)로 일시적 실패(네트워크, API 레이트리밋)를
  흡수한다.
- tz-aware 스케줄: `pendulum`으로 `Asia/Seoul` 타임존을 명시해 DST 등 이슈 없이
  06:00/17:00 KST에 정확히 트리거된다.
