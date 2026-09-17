# -*- coding: utf-8 -*-
"""공용 렌더링 헬퍼(publish_site.py 분리)."""
from __future__ import annotations

import html as _html
import re
from datetime import date

from render.config import DDAY_START, DDAY_TARGET, EVENT_DDAYS, TICKER_COLORS, _WD_KO


# =========================================================
# 렌더링
# =========================================================
def _e(s):
    return _html.escape(s or "")


def _ticker_color(label):
    """티커 → 브랜드 컬러. 미등록 티커는 이름 해시로 고정 색을 배정."""
    key = (label or "").upper().split("-")[0].strip()
    if key in TICKER_COLORS:
        return TICKER_COLORS[key]
    h = sum(ord(c) * (i + 3) for i, c in enumerate(key)) % 360
    return f"hsl({h},58%,38%)"


def _text_on(bg):
    """배경 밝기에 따라 글자색을 고른다(WCAG 상대휘도 기준).

    단순 대비 비교를 쓰면 Tesla 레드·Ethereum 블루처럼 중간 톤에서 검정이
    간발의 차로 선택되는데, 실제 브랜드는 흰 글자를 쓴다. 밝은 배경
    (NVIDIA 그린·Bitcoin 오렌지 등)에서만 어두운 글자를 쓰도록 임계값을 둔다.
    """
    if not bg.startswith("#"):
        return "#fff"

    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16))
    lum = 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
    return "#0f1b2d" if lum > 0.35 else "#fff"


def _spark_svg(vals, color, w=58, h=20, pad=2):
    """종가 시계열 → 미니 스파크라인 SVG(폴리라인)."""
    vals = [v for v in (vals or []) if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = pad + (w - 2 * pad) * i / (n - 1)
        y = pad + (h - 2 * pad) * (1 - (v - lo) / rng)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'aria-hidden="true"><polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round"/></svg>')


def _dday_text(now):
    d = (DDAY_TARGET - now.date()).days
    if d > 0:
        return f"🗓️ D-{d:,}"
    if d == 0:
        return "🗓️ D-DAY"
    return "🗓️ 달성"


def _event_ddays(now) -> list[tuple[str, str, str]]:
    """EVENT_DDAYS 중 아직 지나지 않은 이벤트를 (라벨, 'D-n'/'D-DAY', 'MM.DD(요일)')로.

    당일까지 표시하고 다음 날부터는 목록에서 빠진다(자동 숨김)."""
    out = []
    for label, day in EVENT_DDAYS:
        d = (day - now.date()).days
        if d < 0:
            continue
        dtxt = "D-DAY" if d == 0 else f"D-{d}"
        out.append((label, dtxt, f"{day:%m.%d}({_WD_KO[day.weekday()]})"))
    return out


def _dday_progress(now):
    """DDAY_START → DDAY_TARGET 경과율(%). 하루 지날수록 바가 찬다."""
    total = (DDAY_TARGET - DDAY_START).days
    if total <= 0:
        return 100.0
    done = (now.date() - DDAY_START).days
    return max(0.0, min(100.0, done / total * 100))


def _hl(s):
    """실적 요약 가독성: 수치 볼드 + 방향/부호 색(상승·+=빨강 / 하락·−=파랑)."""
    s = _e(s)
    # 금액 단위 축약 먼저: '$265 million' → '$265M' (아래 통화 볼드가 'm'을 깨는 것 방지)
    s = re.sub(r'(\d[\d,.]*)\s*billion\b', r'\1B', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*)\s*million\b', r'\1M', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*\s?%?)(\s*)(증가|성장|상승|개선|급증|확대|호조|흑자)',
               r'<b style="color:#e5484d">\1</b>\2\3', s)
    s = re.sub(r'(\d[\d,.]*\s?%?)(\s*)(감소|하락|부진|축소|악화|손실|둔화|적자)',
               r'<b style="color:#3b82f6">\1</b>\2\3', s)
    s = re.sub(r'(?<![\w>])\+(\d[\d,.]*\s?%?)', r'<b style="color:#e5484d">+\1</b>', s)
    s = re.sub(r'(?<![\w>])-(\d[\d,.]*\s?%?)', r'<b style="color:#3b82f6">-\1</b>', s)
    s = re.sub(r'(\$-?\d[\d,.]*[BMK]?)', r'<b>\1</b>', s)   # 접미사는 대문자만
    return s


def _rec_color(lab):
    """투자의견 단계별 색: 적극매수=진빨강 / 매수=빨강 / 보유=주황 / 매도=파랑 / 적극매도=진파랑."""
    lab = lab or ""
    if "적극 매수" in lab or "strong" in lab.lower() and "buy" in lab.lower():
        return "#b91c1c"
    if "적극 매도" in lab:
        return "#1e40af"
    if "매수" in lab:
        return "#e5484d"
    if "매도" in lab or "축소" in lab:
        return "#3b82f6"
    if "보유" in lab:
        return "#f59e0b"
    return "#64748b"


def _fmt_money(v, k=""):
    """'234 million'→'$234M', '2.36 billion'→'$2.36B'. 통화 지표면 $ 보강."""
    s = str(v or "")
    if "%" in s:
        return s
    s = re.sub(r'(\d[\d,.]*)\s*billion\b', r'\1B', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*)\s*million\b', r'\1M', s, flags=re.I)
    s = re.sub(r'(\d[\d,.]*)\s*thousand\b', r'\1K', s, flags=re.I)
    kl = (k or "").lower()
    money_kw = ("매출", "revenue", "이익", "손익", "손실", "income", "ebitda",
                "현금", "유동성", "backlog", "백로그", "계약", "가치", "자산", "부채")
    if ("$" not in s) and (any(w in kl for w in money_kw)):
        s = re.sub(r'^(-?)(\d)', r'\1$\2', s)   # 음수부호 뒤에 $
    return s


def _mv_color(v, dir_=None):
    """지표 값 색: 음수(적자·감소)는 항상 파랑, 그 외 dir(up=빨강/down=파랑), 없으면 부호."""
    vt = (v or "").strip()
    if vt[:1] == "-" or vt[:2] in ("$-", "-$"):   # 음수 값은 무조건 파랑
        return f'<span style="color:#3b82f6">{_e(v)}</span>'
    if dir_ == "up":
        return f'<span style="color:#e5484d">{_e(v)}</span>'
    if dir_ == "down":
        return f'<span style="color:#3b82f6">{_e(v)}</span>'
    if vt[:1] == "+":
        return f'<span style="color:#e5484d">{_e(v)}</span>'
    return _e(v)


def _pct_num(s):
    try:
        return float(str(s).replace("%", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None


def _fmt_md(s):
    try:
        d = date.fromisoformat(s)
        return f"{d.month}/{d.day}"
    except (TypeError, ValueError):
        return s or ""


def _rep_cq(r):
    """보고서 분기 라벨('2026 2Q') → cq('2026-2')."""
    p = (r.get("quarter") or "").split()
    return f"{p[0]}-{p[1][:-1]}" if len(p) == 2 and p[1].endswith("Q") else ""
