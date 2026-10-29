"""브리핑 회차(오전·오후·밤): 파일 이름 정렬 = 시간 순서, 아카이브가 세 회차를 모두 인식."""
from datetime import datetime

from render.files import _slug
from settings import KST, briefing_slot


def _at(h, m=0):
    return KST.localize(datetime(2026, 10, 29, h, m))


def test_slots_by_hour():
    assert briefing_slot(_at(6, 30)) == ("am", "오전")
    assert briefing_slot(_at(17, 0)) == ("pm", "오후")
    assert briefing_slot(_at(19, 59)) == ("pm", "오후")
    assert briefing_slot(_at(22, 30)) == ("pm2", "밤")
    assert briefing_slot(_at(23, 59)) == ("pm2", "밤")


def test_slug_string_order_is_time_order():
    slugs = [_slug(_at(22, 30)), _slug(_at(6, 30)), _slug(_at(17, 0))]
    # rebuild_all은 data/*.txt를 문자열 정렬해 마지막을 최신으로 쓴다 → 밤 회차가 마지막이어야 함
    assert sorted(slugs) == ["2026-10-29-am", "2026-10-29-pm", "2026-10-29-pm2"]


def test_archive_and_store_accept_pm2():
    import re
    from render import archive
    from tools import store
    src = open(archive.__file__, encoding="utf-8").read()
    assert src.count("(am|pm|pm2)") == 2 and "v.pm2" in src
    assert store._SLUG_RE.fullmatch("2026-10-29-pm2")
    assert re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})-(am|pm|pm2)", "2026-10-29-pm2")
