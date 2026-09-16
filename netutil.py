# -*- coding: utf-8 -*-
"""HTTP 호출 공통 헬퍼: 타임아웃 기본값, 일시 오류(연결 오류·429·5xx) 재시도(backoff), JSON 디코딩.

입력: requests가 받는 것과 동일(url, headers, params, json 등)
출력: requests.Response(get/post_json 결과) 또는 파싱된 JSON(get_json)
실행: 별도 실행 없음 — 다른 모듈이 import해서 사용
관련: main.py, quotes.py, sec.py, earnings.py, fundamentals.py, econ_results.py, rwa.py, whales.py, push_send.py
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

__all__ = ["get", "get_json", "post_json"]

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _should_retry_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def get(url: str, *, headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None, timeout: int = 20,
        retries: int = 2, backoff: float = 1.5,
        session: requests.Session | None = None) -> requests.Response:
    """GET 요청. 연결오류·타임아웃·429/5xx는 backoff 재시도, 그 외 4xx는 즉시 예외."""
    caller = session or requests
    last_exc: Exception | None = None
    resp: requests.Response | None = None
    for attempt in range(retries + 1):
        try:
            resp = caller.get(url, headers=headers, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < retries:
                log.warning("GET %s 연결 실패(재시도 %d/%d): %s",
                           url, attempt + 1, retries, e)
                time.sleep(backoff ** attempt)
                continue
            raise
        if resp.status_code in _RETRY_STATUS and attempt < retries:
            log.warning("GET %s 응답 %s(재시도 %d/%d)",
                       url, resp.status_code, attempt + 1, retries)
            time.sleep(backoff ** attempt)
            continue
        break
    if resp is None:
        if last_exc:
            raise last_exc
        raise RuntimeError(f"GET {url}: 응답 없음")
    resp.raise_for_status()
    return resp


def get_json(url: str, *, headers: dict[str, str] | None = None,
            params: dict[str, Any] | None = None, timeout: int = 20,
            retries: int = 2, backoff: float = 1.5,
            session: requests.Session | None = None) -> Any:
    """get()과 동일하게 재시도 후 JSON으로 디코딩해 반환."""
    return get(url, headers=headers, params=params, timeout=timeout,
              retries=retries, backoff=backoff, session=session).json()


def post_json(url: str, json: Any, *, headers: dict[str, str] | None = None,
              timeout: int = 20, retries: int = 2, backoff: float = 1.5) -> requests.Response:
    """POST 요청(JSON 바디). 연결오류·타임아웃·429/5xx는 backoff 재시도."""
    last_exc: Exception | None = None
    resp: requests.Response | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=json, headers=headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < retries:
                log.warning("POST %s 연결 실패(재시도 %d/%d): %s",
                           url, attempt + 1, retries, e)
                time.sleep(backoff ** attempt)
                continue
            raise
        if resp.status_code in _RETRY_STATUS and attempt < retries:
            log.warning("POST %s 응답 %s(재시도 %d/%d)",
                       url, resp.status_code, attempt + 1, retries)
            time.sleep(backoff ** attempt)
            continue
        break
    if resp is None:
        if last_exc:
            raise last_exc
        raise RuntimeError(f"POST {url}: 응답 없음")
    resp.raise_for_status()
    return resp
