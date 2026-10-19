# -*- coding: utf-8 -*-
"""ChatGPT 클라이언트 생성과 뉴스 요약. main.py에서 분리(순환 의존 제거).

입력: 환경변수 OPENAI_API_KEY, settings.SUMMARY_MODEL/SUMMARY_MAX_TOKENS
출력: OpenAI 클라이언트(get_openai_client) 또는 None, 한국어 요약 문자열(chatgpt_summarize)
실행: 별도 실행 없음 — main.py/earnings.py/fundamentals.py 등이 import해서 사용
관련: main.py, earnings.py, fundamentals.py, settings.py
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

from openai import OpenAI

from settings import SUMMARY_MODEL, SUMMARY_MAX_TOKENS

__all__ = ["get_openai_client", "chatgpt_summarize", "analyze_news", "ticker_brief", "SENTIMENTS"]

SENTIMENTS = ("호재", "악재", "중립")
log = logging.getLogger(__name__)


# =========================================================
# ChatGPT 요약 (모델 env화 + fallback + rate limit 처리)
# =========================================================
def get_openai_client() -> OpenAI | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def chatgpt_summarize(text: str, client: OpenAI | None = None, max_retries: int = 2) -> str:
    """뉴스 텍스트를 한국어로 요약.
    - 모델명은 SUMMARY_MODEL(env)에서 가져옴 (하드코딩 금지)
    - 빈 입력 / API 에러 / rate limit 처리
    - 실패 시 원문 일부를 fallback 으로 반환
    """
    text = (text or "").strip()
    if not text:
        return "(요약할 뉴스 본문이 없습니다)"

    if client is None:
        client = get_openai_client()
    if client is None:
        # API 키가 없으면 요약 없이 원문 앞부분만 fallback
        return text[:200] + ("..." if len(text) > 200 else "")

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=SUMMARY_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": f"다음 뉴스 내용을 한국어로 2~3문장으로 간결히 요약해줘:\n{text}",
                    }
                ],
                max_tokens=SUMMARY_MAX_TOKENS,
            )
            content = response.choices[0].message.content
            return content.strip() if content else "(요약 결과가 비어 있습니다)"
        except Exception as e:
            msg = str(e).lower()
            # rate limit / 일시적 오류는 지수 백오프 재시도
            if "rate" in msg or "429" in msg or "timeout" in msg or "503" in msg:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
            break

    # 최종 실패 시: 원문 앞부분 fallback (메일이 깨지지 않도록)
    fallback = text[:200] + ("..." if len(text) > 200 else "")
    return f"(요약 실패, 원문 일부) {fallback}"


# =========================================================
# 종목 뉴스 분석: 요약 + 한글 헤드라인 + 호재/악재 판정을 기사당 한 번의 호출로
# =========================================================
_NEWS_PROMPT = """너는 미국 주식·코인 뉴스 편집자다. 아래 기사를 {ticker}({name}) 보유자 관점에서 정리해 JSON 하나로만 답해.
{{"headline_ko": "한국어 헤드라인 30자 이내",
 "summary": "한국어 2~3문장 요약",
 "sentiment": "호재" 또는 "악재" 또는 "중립",
 "reason": "판정 근거 25자 이내",
 "is_news": true 또는 false}}

판정 기준 — 질문은 '이 기사의 사실이 {ticker} 보유자에게 좋은 소식인가'이며 주가 예측이 아니다.
- 호재: 실적·가이던스 상향, 수주·계약, 신제품 출시, 투자의견·목표가 상향, 자사주 매입, 규제 승인, 기관 대량 매수
- 악재: 실적·가이던스 하향, 소송·조사, 리콜, 자금 조달·주식 희석, 투자의견 하향, 경영진 이탈, 규제 제재
- 중립: 비교·전망 칼럼, 마케팅, 새로운 사실 없음, 다른 회사 이야기라 {ticker}에 직접 영향이 작음
- 애매하면 중립. '주가가 올랐다/내렸다'는 사실만으로 판정하지 말고 그 원인으로 판정(원인이 없으면 중립).
- 호재와 악재가 섞이면 기사의 핵심 사실로 판정하고 reason에 둘 다 적는다.
- is_news=false: 시세·차트·옵션 가격 페이지, 광고처럼 기사가 아닌 것.

기사:
{text}"""


def _clip(s, n):
    s = " ".join(str(s or "").replace("|", "/").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _parse_news_json(raw: str) -> dict | None:
    """모델 응답(JSON 문자열) → 정규화된 dict. 형식이 틀리면 None."""
    try:
        m = re.search(r"\{.*\}", raw or "", re.S)
        d = json.loads(m.group(0) if m else raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or not str(d.get("summary") or "").strip():
        return None
    sent = str(d.get("sentiment") or "").strip()
    is_news = d.get("is_news")
    return {
        "headline_ko": _clip(d.get("headline_ko"), 40),
        "summary": " ".join(str(d["summary"]).split()),
        "sentiment": sent if sent in SENTIMENTS else "중립",      # 정해진 값 밖이면 중립
        "reason": _clip(d.get("reason"), 40),
        "is_news": not (is_news is False or str(is_news).lower() == "false"),
    }


def analyze_news(title: str, summary: str, ticker: str, name: str = "",
                 client: OpenAI | None = None, max_retries: int = 2) -> dict:
    """기사 1건 → {headline_ko, summary, sentiment, reason, is_news}.

    JSON 응답이 깨지거나 API가 실패하면 기존 chatgpt_summarize 요약 + 판정 없음(sentiment=None)으로 되돌린다."""
    text = ((title or "") + "\n" + (summary or "")).strip()
    if client is None:
        client = get_openai_client()
    if client is not None and text:
        prompt = _NEWS_PROMPT.format(ticker=ticker, name=name or ticker, text=text[:3000])
        for attempt in range(max_retries + 1):
            try:
                r = client.chat.completions.create(
                    model=SUMMARY_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=SUMMARY_MAX_TOKENS,
                    response_format={"type": "json_object"},
                )
                d = _parse_news_json(r.choices[0].message.content)
                if d:
                    return d
                log.warning("[news] %s: 판정 JSON 형식 오류 → 기존 요약으로 폴백", ticker)
                break                                   # 형식 오류는 재시도해도 비슷 → 폴백
            except Exception as e:
                msg = str(e).lower()
                if ("rate" in msg or "429" in msg or "timeout" in msg or "503" in msg) and attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                log.warning("[news] %s: 판정 호출 실패 → 기존 요약으로 폴백: %s", ticker, e)
                break
    return {"headline_ko": "", "summary": chatgpt_summarize(text, client=client),
            "sentiment": None, "reason": "", "is_news": True}


def ticker_brief(ticker: str, name: str, items: list[dict], client: OpenAI | None = None) -> str:
    """그 종목 기사들(판정 포함) → 한 줄 총평(25자 안팎). 판정된 기사가 없거나 실패하면 ""."""
    rows = [f"- [{it['sentiment']}] {it.get('headline_ko') or it.get('title', '')}: {it.get('reason', '')}"
            for it in items if it.get("sentiment") and it.get("is_news", True)]
    if not rows:
        return ""
    if client is None:
        client = get_openai_client()
    if client is None:
        return ""
    prompt = (f"{ticker}({name or ticker}) 관련 오늘 기사들이다. 보유자 관점에서 전체 흐름을 한국어 한 줄"
              "(25자 안팎, 마침표 없이)로 요약해. 새 재료가 없으면 그렇다고 말해. 그 한 줄만 출력.\n" + "\n".join(rows))
    try:
        r = client.chat.completions.create(model=SUMMARY_MODEL, max_tokens=80,
                                           messages=[{"role": "user", "content": prompt}])
        return _clip((r.choices[0].message.content or "").strip().strip('"').rstrip("."), 50)
    except Exception:
        return ""
