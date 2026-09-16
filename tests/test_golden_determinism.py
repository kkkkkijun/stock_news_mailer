# -*- coding: utf-8 -*-
"""rebuild_all()의 결정성(같은 입력 → 항상 같은 출력) 검증.

tests/golden_render.py 와 같은 방식(시각 고정 + DOCS_DIR/ARCHIVE_DIR 를 임시 디렉터리로
치환)으로 두 번 렌더링해 출력 트리가 바이트 단위로 동일한지 확인한다. 저장소의 실제
data/*.txt(커밋된 과거 회차)를 입력으로 쓰되, 결과물은 tmp_path 아래에만 쓰므로
repo docs/ 는 건드리지 않는다.

입력: 저장소의 data/*.txt(네트워크·LLM 호출 없음)
출력: 없음(assert). 렌더 결과는 pytest tmp_path 에만 기록.
실행: pytest -q tests/test_golden_determinism.py
관련: tests/golden_render.py, render/publish.py, render/config.py
"""
import os
from datetime import datetime

import pytz

from render import clock, config

FIXED_NOW = pytz.timezone("Asia/Seoul").localize(datetime(2026, 9, 16, 12, 0, 0))


def _rebuild_into(tmp_path, name, monkeypatch):
    out_dir = tmp_path / name
    docs_dir = str(out_dir)
    archive_dir = os.path.join(docs_dir, "archive")
    monkeypatch.setattr(config, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(config, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(clock, "now", lambda: FIXED_NOW)
    import publish_site as ps
    n = ps.rebuild_all()
    return docs_dir, n


def _walk_files(root):
    out = {}
    for dp, _dn, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            with open(p, "rb") as fh:
                out[rel] = fh.read()
    return out


def test_rebuild_all_is_byte_identical_across_runs(tmp_path, monkeypatch):
    docs_a, n_a = _rebuild_into(tmp_path, "a", monkeypatch)
    docs_b, n_b = _rebuild_into(tmp_path, "b", monkeypatch)

    assert n_a > 0, "data/*.txt 가 하나도 없으면 이 테스트는 의미가 없다"
    assert n_a == n_b

    files_a = _walk_files(docs_a)
    files_b = _walk_files(docs_b)

    assert set(files_a) == set(files_b)
    diffs = [rel for rel in files_a if files_a[rel] != files_b[rel]]
    assert diffs == [], f"non-deterministic output for: {diffs}"

    # 실제 repo docs/ 는 건드리지 않았어야 한다(출력은 tmp_path 아래에만 있음).
    repo_docs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    if os.path.isdir(repo_docs):
        assert not os.path.samefile(docs_a, repo_docs)


def test_rebuild_all_writes_expected_assets_and_links(tmp_path, monkeypatch):
    docs_dir, n = _rebuild_into(tmp_path, "out", monkeypatch)
    assert n > 0

    assets_dir = os.path.join(docs_dir, "assets")
    assert os.path.isfile(os.path.join(assets_dir, "site.css"))
    assert os.path.isfile(os.path.join(assets_dir, "site.js"))
    assert os.path.isfile(os.path.join(assets_dir, "tab.js"))

    html_files = []
    for dp, _dn, fs in os.walk(docs_dir):
        for f in fs:
            if f.endswith(".html"):
                html_files.append(os.path.join(dp, f))
    assert html_files

    for path in html_files:
        with open(path, encoding="utf-8") as f:
            html = f.read()
        rel = os.path.relpath(path, docs_dir).replace(os.sep, "/")
        if rel.startswith("archive/"):
            assert 'href="../assets/site.css?v=' in html, rel
        else:
            assert 'href="assets/site.css?v=' in html, rel

    index_path = os.path.join(docs_dir, "index.html")
    assert os.path.isfile(index_path)
    with open(index_path, encoding="utf-8") as f:
        index_html = f.read()
    for tab in ("뉴스", "주식", "일정"):
        assert f">{tab}<" in index_html, f"nav tab missing: {tab}"
