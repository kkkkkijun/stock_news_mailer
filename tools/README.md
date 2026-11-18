# tools/

메인 파이프라인(수집→요약→HTML)과는 무관하게, 필요할 때만 선택 실행하는 보조 도구.

## store.py — 브리핑 구조화 인덱스(SQLite)

`data/*.txt`(+`*.quotes.json`)로 저장된 브리핑 원문을 조회 가능한 SQLite DB로
색인한다. 검색·이력·전일 대비 변화 등을 만들 때 쓰는 파생 인덱스일 뿐, 원문
텍스트가 항상 진실의 원천이며 DB는 언제든 원문에서 재생성할 수 있다(그래서
DB 파일은 `.gitignore`에 있고 커밋하지 않는다).

저장소 루트에서 실행:

```bash
python tools/store.py reindex          # data/*.txt 전체를 DB로 재색인
python tools/store.py search 금리       # 헤드라인/요약 검색
python tools/store.py stats            # 색인 현황(회차/항목/시세 수)
```

DB 파일은 저장소 루트의 `data/briefings.db`에 생성된다.

## report_status.py — 실적 보고서 게시 현황

`data/reports.json`의 게시/보류 현황을 마크다운 표로 출력한다. `Earnings Refresh` 워크플로가
실행 요약(Summary)에 붙이고, 최근 14일 안의 보류 보고서는 경고(annotation)로 띄운다.

```bash
python tools/report_status.py          # 표 출력
```

보류된 보고서 다시 만들기: GitHub → Actions → **Earnings Refresh** → Run workflow →
`retry`에 티커(예: `NVDA,HIMS`) 또는 `all` 입력. 보고서 로직(`earnings.py`·`report_agents.py`·
`report_check.py`)을 main에 푸시해도 이 워크플로가 자동으로 돌아 새 규칙으로 다시 만든다.
