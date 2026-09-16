# -*- coding: utf-8 -*-
"""render/parse.py 순수 파싱 로직 테스트(네트워크·LLM 호출 없음).

입력: data/*.txt 에 실제로 저장되는 것과 동일한 plain-text 마커로 구성한 소형 본문 문자열
출력: 없음(assert)
실행: pytest -q tests/test_parse.py
관련: render/parse.py, data/*.txt
"""
from render.parse import _is_new, _news_toks, _parse_part, _split_sections

BODY = """2026-07-24T08:34:49.803387+09:00

[오늘의 뉴스 요약] 2026-07-24 08:33 KST

💹 경제 PART

[오늘 한눈에]
오늘 한국은 환율 관찰대상국으로 지정되며 우려가 커지고 있다.
동시에 미국 주택담보대출 금리도 최고치를 기록했다.

[핵심 뉴스]
1. (환율) 한국, 환율 관찰대상국으로 다시 지정
   → 미국 재무부는 한국을 환율 관찰대상국으로 지정했다.
   (연합뉴스 · 07/24 08:06)
2. (금리) 미 주택담보대출 금리 11개월 만에 최고치
   → 미국의 30년 고정 주택담보대출 금리가 6.58%로 상승했다.
   (연합뉴스 · 07/24 05:57)

[흐름·전망]
• 환율 관찰대상국 지정으로 외환시장 변동성이 주목받을 것이다.
• 주택담보대출 금리 상승이 주택시장에 미치는 영향을 주시해야 한다.

📈 해외주식 PART
📰 [NVDA] NVIDIA and KAIST Launch Joint AI Research Lab in Seoul
   (Quiver Quantitative · 07/24 08:10)
→ NVIDIA와 KAIST가 서울에 공동 AI 연구소를 설립했다.

📰 [TSLA] Wall St falls as tech earnings spark AI spending worries
   (Yahoo Finance · 07/24 08:04)
→ 월스트리트 주식 시장이 큰 폭으로 하락했다.

📊 공포탐욕지수
  - CNN 기준: 40 (Fear)
  - 크립토 기준: 31 (Fear)

🏘️ 부동산 PART

[오늘의 부동산 한눈에]
서울 강남구의 재건축 인허가 기간이 단축되고 있다.

[핵심 뉴스]
1. (재건축) 강남구, 재건축추진위 10일만에 승인
   → 서울 강남구가 재건축 인허가 기간을 열흘 만에 승인했다.
   (연합뉴스 · 07/24 07:14)

[흐름·전망]
• 재건축 사업 속도 개선은 공급 증가에 긍정적일 것으로 예상된다.

※ 본 브리핑은 자동 생성되었습니다.
"""


def test_split_sections_extracts_titles_and_lines():
    sections = _split_sections(BODY)
    titles = [t for t, _lines in sections]
    assert "💹 경제 PART" in titles
    assert "📈 해외주식 PART" in titles
    assert "📊 공포탐욕지수" in titles
    assert "🏘️ 부동산 PART" in titles
    # 헤더 앞의 두 줄(타임스탬프·요약 제목)은 어느 섹션에도 속하지 않아 버려진다.
    eco_lines = next(ls for t, ls in sections if t == "💹 경제 PART")
    assert "[오늘 한눈에]" in eco_lines
    assert "1. (환율) 한국, 환율 관찰대상국으로 다시 지정" in eco_lines


def test_parse_part_summary_and_items():
    sections = _split_sections(BODY)
    eco_lines = next(ls for t, ls in sections if t == "💹 경제 PART")
    summary, items, blocks, note = _parse_part(eco_lines)

    assert summary == (
        "오늘 한국은 환율 관찰대상국으로 지정되며 우려가 커지고 있다. "
        "동시에 미국 주택담보대출 금리도 최고치를 기록했다."
    )

    assert len(items) == 2
    it0 = items[0]
    assert it0["kind"] == "tag"
    assert it0["label"] == "환율"
    assert it0["title"] == "한국, 환율 관찰대상국으로 다시 지정"
    assert it0["desc"] == "미국 재무부는 한국을 환율 관찰대상국으로 지정했다."
    assert it0["src"] == "연합뉴스 · 07/24 08:06"

    it1 = items[1]
    assert it1["label"] == "금리"
    assert it1["title"] == "미 주택담보대출 금리 11개월 만에 최고치"

    assert len(blocks) == 1
    label, bullets = blocks[0]
    assert label == "흐름·전망"
    assert bullets == [
        "환율 관찰대상국 지정으로 외환시장 변동성이 주목받을 것이다.",
        "주택담보대출 금리 상승이 주택시장에 미치는 영향을 주시해야 한다.",
    ]
    assert note == ""


def test_parse_part_ticker_items_and_note():
    sections = _split_sections(BODY)
    os_lines = next(ls for t, ls in sections if t == "📈 해외주식 PART")
    _summary, items, _blocks, note = _parse_part(os_lines)
    assert len(items) == 2
    assert items[0]["kind"] == "ticker"
    assert items[0]["label"] == "NVDA"
    assert items[0]["title"] == "NVIDIA and KAIST Launch Joint AI Research Lab in Seoul"
    assert items[0]["desc"] == "NVIDIA와 KAIST가 서울에 공동 AI 연구소를 설립했다."
    assert items[0]["src"] == "Quiver Quantitative · 07/24 08:10"
    assert items[1]["label"] == "TSLA"
    assert note == ""

    re_lines = next(ls for t, ls in sections if t == "🏘️ 부동산 PART")
    _s, _i, _b, re_note = _parse_part(re_lines)
    assert re_note == "본 브리핑은 자동 생성되었습니다."


def test_news_toks_extracts_two_char_plus_tokens():
    toks = _news_toks("한국 환율 관찰대상국 지정 A")
    assert "한국" in toks
    assert "환율" in toks
    assert "A" not in toks   # 2글자 미만은 제외


def test_news_toks_empty_for_blank_input():
    assert _news_toks("") == set()
    assert _news_toks(None) == set()


def test_is_new_false_when_no_prev_sets():
    assert _is_new("완전히 새로운 헤드라인 입니다", None) is False
    assert _is_new("완전히 새로운 헤드라인 입니다", []) is False


def test_is_new_overlap_threshold():
    prev = [_news_toks("한국 환율 관찰대상국 지정 뉴스")]
    # 토큰이 60% 이상 겹치면 새 뉴스가 아니다.
    assert _is_new("한국 환율 관찰대상국 지정 소식", prev) is False
    # 거의 겹치지 않으면 새 뉴스로 본다.
    assert _is_new("전혀 다른 주제의 헤드라인 본문", prev) is True
