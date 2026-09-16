# -*- coding: utf-8 -*-
"""ChatGPT 클라이언트 생성과 뉴스 요약. main.py에서 분리(순환 의존 제거).

입력: 환경변수 OPENAI_API_KEY, settings.SUMMARY_MODEL/SUMMARY_MAX_TOKENS
출력: OpenAI 클라이언트(get_openai_client) 또는 None, 한국어 요약 문자열(chatgpt_summarize)
실행: 별도 실행 없음 — main.py/earnings.py/fundamentals.py 등이 import해서 사용
관련: main.py, earnings.py, fundamentals.py, settings.py
"""
from __future__ import annotations

import os
import time

from openai import OpenAI

from settings import SUMMARY_MODEL, SUMMARY_MAX_TOKENS

__all__ = ["get_openai_client", "chatgpt_summarize"]


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
