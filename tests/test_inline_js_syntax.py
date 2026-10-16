# -*- coding: utf-8 -*-
"""사이트에 들어가는 인라인/추출 JS의 문법 검사(node --check). node가 없으면 건너뜀.

입력: render/* 의 *_JS 상수
출력: 없음(assert)
실행: pytest -q tests/test_inline_js_syntax.py
관련: render/rwamap.py(지도 실시간 갱신), render/schedule.py, render/growth.py, render/layout.py
"""
import re
import shutil
import subprocess

import pytest

from render import growth, layout, rwamap, schedule

SCRIPTS = {
    "rwa": rwamap._RWA_JS, "sched": schedule._SCHED_JS, "growth": growth._GROWTH_JS,
    "tab": layout._TAB_JS, "goal_loader": layout._GOAL_LOADER_JS,
    "top": layout._TOP_JS, "theme": layout._THEME_JS, "pwa": layout._PWA_JS,
}


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_script_parses(name, tmp_path):
    blocks = re.findall(r"<script>(.*?)</script>", SCRIPTS[name], re.S)
    assert blocks, f"{name}: <script> 블록 없음"
    for i, js in enumerate(blocks):
        f = tmp_path / f"{name}_{i}.js"
        f.write_text(js, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
        assert r.returncode == 0, f"{name}[{i}] 문법 오류:\n{r.stderr[:500]}"
