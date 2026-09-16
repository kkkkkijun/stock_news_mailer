# -*- coding: utf-8 -*-
"""netutil.get() 재시도/백오프 동작 단위 테스트. 네트워크 없음(requests 스텁).

입력: 없음
출력: 없음(pytest 결과)
실행: pytest tests/test_netutil.py
관련: netutil.py
"""
import requests

import netutil


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


def test_get_retries_once_on_500_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResponse(500)
        return _FakeResponse(200)

    sleeps = []
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(netutil.time, "sleep", lambda s: sleeps.append(s))

    resp = netutil.get("https://example.com", retries=2, backoff=1.5)
    assert resp.status_code == 200
    assert calls["n"] == 2
    assert sleeps == [1.5 ** 0]


def test_get_raises_immediately_on_404_without_retry(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse(404)

    sleeps = []
    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(netutil.time, "sleep", lambda s: sleeps.append(s))

    try:
        netutil.get("https://example.com", retries=2, backoff=1.5)
        assert False, "404는 재시도 없이 예외를 던져야 한다"
    except requests.HTTPError:
        pass
    assert calls["n"] == 1
    assert sleeps == []
