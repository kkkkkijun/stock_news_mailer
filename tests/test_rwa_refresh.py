"""rwa.py — Ostium 엔드포인트 예비 전환과 일시 장애 시 기존 스냅샷 유지."""
import json
from datetime import datetime, timedelta

import rwa


def test_fetch_all_falls_back_to_next_endpoint(monkeypatch):
    calls = []

    def fake(url):
        calls.append(url)
        if url == "a":
            raise RuntimeError("429")
        return [{"x": 1}]
    monkeypatch.setattr(rwa, "_fetch_from", fake)
    assert rwa._fetch_all(("a", "b")) == [{"x": 1}]
    assert calls == ["a", "b"]


def _boom(*a, **k):
    raise RuntimeError("모든 Ostium 엔드포인트 실패")


def _snap(path, hours_ago):
    asof = (datetime.now(rwa.KST) - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M")
    path.write_text(json.dumps({"asof": asof, "assets": []}), encoding="utf-8")


def test_refresh_keeps_recent_snapshot_on_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(rwa, "build_rwa", _boom)
    p = tmp_path / "rwamap.json"
    _snap(p, 3)
    before = p.read_text(encoding="utf-8")
    assert rwa.refresh(str(p)) == 0
    assert p.read_text(encoding="utf-8") == before
    assert "::warning" in capsys.readouterr().out


def test_refresh_fails_when_snapshot_stale_or_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(rwa, "build_rwa", _boom)
    p = tmp_path / "rwamap.json"
    assert rwa.refresh(str(p)) == 1           # 없음
    _snap(p, 30)
    assert rwa.refresh(str(p)) == 1           # 12시간 초과


def test_primary_endpoint_is_official_ostium():
    assert rwa.URL.startswith("https://builder.prod.bedrock.ostium.io/")
    assert rwa.URLS[0] == rwa.URL
