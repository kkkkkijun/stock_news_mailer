"""주식 탭 뉴스(B안): 수집 정제 → AI 판정 파싱 → 본문 형식 → 파서 → 렌더까지 왕복."""
from types import SimpleNamespace

import llm
import main
import newsfeed as N
from render.news import _render_ticker_groups
from render.parse import _parse_part


def test_strip_publisher_and_quote_pages():
    t = "The $5 Trillion Club: Which Is the Better Stock to Own, Apple or Nvidia?"
    assert N._strip_publisher(t + " - The Motley Fool", "The Motley Fool") == t
    assert N._title_key(t + " - The Motley Fool", "The Motley Fool") == N._title_key(t, "Yahoo Finance")
    assert N._strip_publisher("5 Technologies Make Tesla Roadster a $250K Outlier [2026] - https://tech-insider.org/",
                              "https://tech-insider.org/") == "5 Technologies Make Tesla Roadster a $250K Outlier [2026]"
    assert N._is_quote_page("RDW Oct 2026 17.000 call (RDW261030C00017000) stock price, news, quote and history")
    assert N._is_quote_page("Hims & Hers Health - Backpack Securities Price, HIMS Price, Live Charts, and Marketcap")
    assert not N._is_quote_page("IREN Stock Drops Below Key Support as AI Pivot Faces Major Headwinds")


def test_parse_news_json_normalizes():
    d = llm._parse_news_json('{"headline_ko":"자금 조달 | 위험","summary":"요약 문장.","sentiment":"부정",'
                             '"reason":"r","is_news":"false"}')
    assert d["sentiment"] == "중립"                 # 정해진 세 값 밖 → 중립
    assert d["is_news"] is False and "|" not in d["headline_ko"]
    assert llm._parse_news_json('{"sentiment":"호재"}') is None          # 요약 없으면 실패로 봄
    assert llm._parse_news_json("not json") is None


class _FakeClient:
    def __init__(self, content=None, exc=None):
        def create(**kw):
            if exc:
                raise exc
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def test_analyze_news_ok_and_fallback():
    ok = llm.analyze_news("t", "s", "RDW", "레드와이어", client=_FakeClient(
        '{"headline_ko":"9.8억 달러 계약","summary":"요약.","sentiment":"호재","reason":"국방 수주","is_news":true}'))
    assert ok["sentiment"] == "호재" and ok["headline_ko"] == "9.8억 달러 계약"
    bad = llm.analyze_news("t", "s", "RDW", client=_FakeClient(exc=RuntimeError("boom")))
    assert bad["sentiment"] is None and bad["summary"].startswith("(요약 실패")   # 예전 형식으로 폴백


def _fake_pipeline(monkeypatch, sents):
    arts = [{"title": f"Title {i}", "summary": "", "link": f"https://ex.com/{i}", "publisher": "Pub",
             "published_at": 0, "dups": i} for i in range(len(sents))]
    monkeypatch.setattr(main, "fetch_news_articles", lambda t: arts)
    res = iter([{"headline_ko": f"헤드라인 {i}", "summary": f"요약 {i}", "sentiment": s,
                 "reason": f"근거 {i}", "is_news": s != "제외"} for i, s in enumerate(sents)])

    def fake_analyze(*a, **k):
        r = next(res)
        if r["sentiment"] == "제외":
            r["sentiment"] = "중립"
        return r
    monkeypatch.setattr(main, "analyze_news", fake_analyze)
    monkeypatch.setattr(main, "ticker_brief", lambda *a, **k: "자금 조달 우려로 약세")


def test_body_format_roundtrip(monkeypatch):
    _fake_pipeline(monkeypatch, ["악재", "호재", "제외"])
    body = "\n".join(main.fetch_and_summarize_news("IREN"))
    assert body.startswith("🧭 [IREN] 자금 조달 우려로 약세")
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    _s, items, _b, _n = _parse_part(lines)
    assert [it["sent"] for it in items] == ["b", "g", "x"]
    assert items[0]["brief"] == "자금 조달 우려로 약세" and "brief" not in items[1]
    assert items[1]["ko"] == "헤드라인 1" and items[1]["why"] == "근거 1" and items[1]["dups"] == 1
    assert items[2]["link"] == "https://ex.com/2" and items[0]["desc"] == "요약 0"
    html = _render_ticker_groups(items, None, [{"ticker": "IREN", "price": 26.99, "chg": -11.19, "spark": [3, 2, 1]}])
    assert 'class="nb-bar"' in html and "호재 1 · 악재 1 · 중립 0" in html
    assert "기사 아닌 페이지 1건 숨김" in html and "같은 내용 1곳 더" in html
    assert "$26.99" in html and "▼ 11.19%" in html and 'href="https://ex.com/0"' in html
    assert html.count('class="nb-row open"') == 1                 # 첫 기사만 펼침
    _s, items2, _b, _n = _parse_part(
        ["📰 [X] a", "🏷 중립 | 중립기사 | r | 0", "→ s", "📰 [X] b", "🏷 악재 | 악재기사 | r | 0", "→ s"])
    h2 = _render_ticker_groups(items2, None)
    assert h2.index("악재기사") < h2.index("중립기사")             # 호재·악재가 위로


def test_old_format_still_renders():
    lines = ["📰 [NVDA] Old English Title", "(Yahoo Finance · 10/01 05:20)", "→ 예전 요약"]
    _s, items, _b, _n = _parse_part(lines)
    assert "sent" not in items[0]
    html = _render_ticker_groups(items, None)
    assert "nb-bar" not in html and "nb-sum" not in html and "Old English Title" in html and "예전 요약" in html
