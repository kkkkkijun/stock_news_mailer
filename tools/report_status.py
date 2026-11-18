# -*- coding: utf-8 -*-
"""실적 보고서 게시 현황(data/reports.json) → 마크다운 표. GitHub Actions 실행 요약($GITHUB_STEP_SUMMARY)용.

최근 RECENT_DAYS일 안에 발표된 보고서가 검수 보류면 ::warning:: 주석을 남겨 Actions 화면에서 바로 보이게 한다.
보류된 종목은 Actions → 'Earnings Refresh' → Run workflow → retry 칸에 티커(또는 all)를 넣어 다시 시도한다.

사용(저장소 루트): python tools/report_status.py [data/reports.json]
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

RECENT_DAYS = 14


def status_markdown(reports: list[dict], today: date) -> tuple[str, list[str]]:
    """(마크다운 표, 경고 문구 목록)."""
    rows, warns = [], []
    for r in reports:
        chk = r.get("check") or {}
        ok = chk.get("ok") is True
        state = "✅ 게시" + (" (수동)" if chk.get("by") == "manual" else "") if ok else "⏸ 보류"
        issue = "" if ok else "; ".join(str(x) for x in (chk.get("issues") or [])[:2])
        issue = issue.replace("|", "/").replace("\n", " ")[:160]
        rows.append(f"| {r.get('ticker', '')} | {r.get('date', '')} | {r.get('quarter', '')} | {state} "
                    f"| {r.get('attempts', '-')} | {issue} |")
        try:
            recent = date.fromisoformat(r.get("date", "")) >= today - timedelta(days=RECENT_DAYS)
        except ValueError:
            recent = False
        if not ok and recent:
            warns.append(f"{r.get('ticker')} {r.get('quarter', '')} 보고서 검수 보류(시도 {r.get('attempts', '-')}회): {issue}")
    n_ok = sum(1 for r in reports if (r.get("check") or {}).get("ok") is True)
    head = (f"### 실적 보고서 현황 — 게시 {n_ok} / 전체 {len(reports)}\n\n"
            "| 종목 | 발표일 | 분기 | 상태 | 시도 | 보류 사유 |\n|---|---|---|---|---|---|\n")
    return head + "\n".join(rows) + "\n", warns


def main(path: str = "data/reports.json") -> int:
    try:
        reports = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"reports.json 읽기 실패: {e}")
        return 0
    md, warns = status_markdown(reports, date.today())
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:                                  # Actions: 실행 요약 페이지에 표
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md)
    print(md)
    for w in warns:                              # Actions: 경고 주석(stdout 워크플로 명령)
        print(f"::warning title=실적 보고서 보류::{w}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
