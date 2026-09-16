# -*- coding: utf-8 -*-
"""발행 / 재렌더링(publish_site.py 분리)."""
import os

from render import assets, clock, config
from render.archive import render_archive_index
from render.config import _LINKS_HOME, _LINKS_SNAP
from render.files import _load_body, _load_quotes, _save_body, _save_quotes, _slug, _write
from render.layout import render_html


def rebuild_all():
    """저장된 원문으로 모든 페이지를 다시 렌더링(뉴스 수집·LLM 호출 없음)."""
    if not os.path.isdir(config.DATA_DIR):
        return 0
    assets.write_assets(config)
    os.makedirs(config.ARCHIVE_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(config.DATA_DIR) if f.endswith(".txt"))
    latest = None
    for fn in files:
        now, body = _load_body(os.path.join(config.DATA_DIR, fn))
        if now is None or not body.strip():
            continue
        quotes = _load_quotes(fn[:-4])
        _write(os.path.join(config.ARCHIVE_DIR, fn[:-4] + ".html"),
               render_html(body, now=now, links=_LINKS_SNAP, quotes=quotes,
                           mark_new=True, asset_prefix="../"))
        latest = (body, now, quotes)
    if latest:
        _write(os.path.join(config.DOCS_DIR, "index.html"),
               render_html(latest[0], now=latest[1], links=_LINKS_HOME,
                           quotes=latest[2], mark_new=True, schedule=True))
    _write(os.path.join(config.ARCHIVE_DIR, "index.html"), render_archive_index())
    return len(files)


def publish(body, now=None, quotes=None):
    """최신 페이지 + 회차 스냅샷 + 캘린더 생성. 최신 경로 반환."""
    now = now or clock.now()
    assets.write_assets(config)
    os.makedirs(config.ARCHIVE_DIR, exist_ok=True)
    _save_body(body, now)
    _save_quotes(quotes, now)
    _write(os.path.join(config.ARCHIVE_DIR, _slug(now) + ".html"),
           render_html(body, now=now, links=_LINKS_SNAP, quotes=quotes,
                       mark_new=True, asset_prefix="../"))
    path = os.path.join(config.DOCS_DIR, "index.html")
    _write(path, render_html(body, now=now, links=_LINKS_HOME, quotes=quotes,
                             mark_new=True, schedule=True))
    _write(os.path.join(config.ARCHIVE_DIR, "index.html"), render_archive_index())
    return path
