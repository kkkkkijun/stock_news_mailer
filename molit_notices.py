# -*- coding: utf-8 -*-
"""국토교통부 고시(행정규칙) 신규 등록 요약 → 이메일 발송 (기존 메일러에 추가되는 모듈).

기존 stock_news_mailer 시스템의 하루 2회(오전/오후) 스케줄에 얹혀,
전일자~당일 신규 고시를 수집·요약해 메일 본문으로 발송한다.

- 리스트: https://www.molit.go.kr/USR/I0204/m_45/lst.jsp?gubun=4
- 신규 판별: GitHub Actions에는 상태파일이 유지되지 않으므로
  '게시일이 최근 MOLIT_LOOKBACK_DAYS일 이내'인 고시를 신규로 본다(기본 1일).
- 각 고시: 상세페이지에서 고시번호·첨부(PDF/HWPX) 추출 → 본문 텍스트화
  → 개정이유/주요내용 발췌 → (OpenAI 있으면) 한국어 요약.
- 전체 신규 목록 + 부동산 관련 강조 요약을 plain-text 메일로 발송.

의존성: 표준 라이브러리 + (선택) pypdf(권장) 또는 시스템 pdftotext.
OpenAI/이메일 설정은 기존 프로젝트의 환경변수(OPENAI_API_KEY, EMAIL_USER/PASS,
EMAIL_RECIPIENTS)를 그대로 사용한다.

환경변수:
  MOLIT_LOOKBACK_DAYS   신규 판별 창(일). 기본 1 (전일자+당일)
  MOLIT_MAX_ITEMS       본문추출 대상 최대 개수. 기본 15
  MOLIT_SEND_IF_EMPTY   신규 0건일 때도 '신규 없음' 메일 발송(1) / 미발송(0). 기본 1
  OPENAI_SUMMARY_MODEL  요약 모델(기본 gpt-4o-mini) — main.py와 동일 규칙
"""
import os
import re
import sys
import html
import time
import subprocess
import datetime
import io
import zipfile
import urllib.request
import urllib.parse
import http.cookiejar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE = "https://www.molit.go.kr"
LIST_URL = BASE + "/USR/I0204/m_45/lst.jsp?gubun=4"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

LOOKBACK_DAYS = int(os.getenv("MOLIT_LOOKBACK_DAYS", "1"))
MAX_ITEMS = int(os.getenv("MOLIT_MAX_ITEMS", "15"))
# 해외(GitHub Actions) 러너에서 국토부 서버 응답이 느릴 수 있어 타임아웃/재시도를 넉넉히.
TIMEOUT = int(os.getenv("MOLIT_TIMEOUT", "60"))
RETRIES = int(os.getenv("MOLIT_RETRIES", "3"))
SEND_IF_EMPTY = os.getenv("MOLIT_SEND_IF_EMPTY", "1") != "0"
SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")

# 부동산 관련 강조용 키워드 (제목/본문 매칭)
REALTY_KEYWORDS = [
    "감정평가", "공시지가", "개별공시지가", "표준지", "표준주택", "공동주택가격",
    "부동산 가격공시", "부동산가격공시", "가격공시", "실거래", "주택", "택지",
    "분양가", "재건축", "재개발", "도시정비", "정비사업", "임대주택", "전월세",
    "부동산거래", "부동산", "토지", "지가", "개발부담금", "재건축부담금",
    "공인중개사", "중개보수", "리츠", "부동산투자", "청약", "보금자리", "지구단위",
]

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(s):
    return html.unescape(TAG_RE.sub("", s)).strip()


# =========================================================
# 수집
# =========================================================
def build_opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [
        ("User-Agent", UA),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"),
        ("Referer", BASE + "/USR/I0204/m_45/lst.jsp"),
    ]
    return op


def fetch(op, url, timeout=None):
    """지수 백오프 재시도 포함 GET. 해외 러너의 일시적 지연/타임아웃 완화."""
    timeout = timeout or TIMEOUT
    last = None
    for attempt in range(RETRIES):
        try:
            with op.open(url, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            if attempt < RETRIES - 1:
                time.sleep(2 ** attempt)
    raise last


def fetch_text(op, url, timeout=40):
    return fetch(op, url, timeout).decode("utf-8", "replace")


def parse_list(page):
    items = []
    for row in ROW_RE.findall(page):
        m_idx = re.search(r"dtl\.jsp\?[^\"']*idx=(\d+)", row)
        m_title = re.search(r"bd_title[^>]*>\s*<a[^>]*>(.*?)</a>", row, re.S)
        if not (m_idx and m_title):
            continue
        m_part = re.search(r"bd_part[^>]*>(.*?)</td>", row, re.S)
        m_date = re.search(r"bd_date_publish[^>]*>(.*?)</td>", row, re.S)
        items.append({
            "idx": int(m_idx.group(1)),
            "title": strip_tags(m_title.group(1)),
            "dept": strip_tags(m_part.group(1)) if m_part else "",
            "date": strip_tags(m_date.group(1)) if m_date else "",
        })
    return items


def parse_detail(op, idx):
    url = f"{BASE}/USR/I0204/m_45/dtl.jsp?gubun=4&idx={idx}"
    page = fetch_text(op, url)
    m = re.search(r"((?:국토교통부?|해양수산부|행정안전부)?\s*고시\s*제\s*\d{4}\s*-\s*\d+\s*호)", page)
    gosi_no = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip() if m else ""
    atts, seen = [], set()
    for am in re.finditer(r"/LCMS/DWN\.jsp\?[^\"'>]+", page):
        href = html.unescape(am.group(0))
        if href in seen:
            continue
        seen.add(href)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        atts.append({"url": BASE + href, "filename": q.get("fileName", [""])[0]})
    return url, gosi_no, atts


# =========================================================
# 첨부 본문 추출 (PDF: pypdf 우선, 없으면 pdftotext / HWPX: zip+xml)
# =========================================================
def _pdf_to_text(data):
    # 1순위: pypdf (순수 파이썬, CI에서 시스템 의존성 불필요)
    try:
        from pypdf import PdfReader
        txt = "\n".join((p.extract_text() or "")
                        for p in PdfReader(io.BytesIO(data)).pages)
        if txt.strip():
            return txt
    except Exception:
        pass
    # 2순위: 시스템 pdftotext (임시파일 경유 — Xpdf 계열은 stdin 미지원)
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        p = subprocess.run(["pdftotext", "-enc", "UTF-8", path, "-"],
                           capture_output=True, timeout=120)
        return p.stdout.decode("utf-8", "replace")
    except Exception as e:  # noqa
        return f"[PDF 추출실패: {e}]"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _hwpx_to_text(data):
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = sorted(n for n in z.namelist()
                       if re.search(r"Contents/section\d+\.xml$", n, re.I))
        for n in names:
            xml = z.read(n).decode("utf-8", "replace")
            xml = re.sub(r"</hp:p>", "\n", xml)
            xml = re.sub(r"<[^>]+>", "", xml)
            parts.append(html.unescape(xml))
    text = re.sub(r"[ \t]+", " ", "\n".join(parts))
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def extract_text(op, att):
    fn = (att.get("filename") or "att").lower()
    try:
        data = fetch(op, att["url"])
    except Exception as e:  # noqa
        return f"[다운로드실패: {e}]"
    try:
        if fn.endswith(".pdf"):
            return _pdf_to_text(data)
        if fn.endswith(".hwpx"):
            return _hwpx_to_text(data)
        return None
    except Exception as e:  # noqa
        return f"[추출실패: {e}]"


def best_content(op, atts):
    """규제심사확인증 제외, stem별 최장 본문만 남겨 [(file,text)] 반환."""
    by_stem = {}
    for a in atts:
        fn = a.get("filename") or ""
        if "규제심사" in fn:
            continue
        t = extract_text(op, a)
        if not (t and t.strip()):
            continue
        t = t.strip()
        stem = re.sub(r"\.(pdf|hwpx?|hwp)$", "", fn, flags=re.I)
        if stem not in by_stem or len(t) > len(by_stem[stem][1]):
            by_stem[stem] = (fn, t)
    return list(by_stem.values())


def excerpt(text, limit=1400):
    """개정이유/주요내용 우선 발췌, 없으면 앞부분."""
    t = re.sub(r"\n{2,}", "\n", text)
    m = re.search(r"(개정\s*이유|제안\s*이유|제정\s*이유|주요\s*내용)", t)
    return (t[m.start():m.start() + limit] if m else t[:limit]).strip()


def within_days(datestr, days):
    try:
        d = datetime.date.fromisoformat(datestr)
    except ValueError:
        return False
    return 0 <= (datetime.date.today() - d).days <= days


# =========================================================
# 요약 (OpenAI 있으면 사용, 없으면 발췌 그대로)
# =========================================================
def summarize_notice(item, client):
    body = excerpt(item.get("_excerpt", ""), 1400)
    if not body:
        return item["title"] + " (첨부 본문 자동추출 불가)"
    if client is None:
        return body
    prompt = (
        "다음은 대한민국 국토교통부 고시 개정문에서 발췌한 내용입니다. "
        "행정 실무자가 빠르게 이해할 수 있도록 핵심 변경점을 한국어 불릿 2~4개로 "
        "간결히 정리해줘. 수치·시행일·비율 등 구체적 값은 반드시 포함하고, "
        "불필요한 서론 없이 불릿만 출력해:\n\n"
        f"[제목] {item['title']}\n[발췌]\n{body}"
    )
    try:
        resp = client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=int(os.getenv("MOLIT_SUMMARY_MAX_TOKENS", "500")),
        )
        out = (resp.choices[0].message.content or "").strip()
        return out or body
    except Exception as e:  # noqa
        return f"(요약 실패, 발췌) {body[:300]}"


# =========================================================
# 본문 조립
# =========================================================
def collect_new(op):
    items = parse_list(fetch_text(op, LIST_URL))
    new = [it for it in items if within_days(it["date"], LOOKBACK_DAYS)]
    new.sort(key=lambda x: -x["idx"])
    return new[:MAX_ITEMS]


def build_molit_body(client=None):
    op = build_opener()
    new = collect_new(op)

    today = datetime.date.today().strftime("%Y-%m-%d")
    if not new:
        return None if not SEND_IF_EMPTY else (
            f"[국토교통부 고시 요약] {today}\n\n"
            f"최근 {LOOKBACK_DAYS}일 이내 신규 등록된 고시가 없습니다.\n"
            f"목록: {LIST_URL}\n"
        )

    # 상세/첨부/발췌
    for it in new:
        _, gosi, atts = parse_detail(op, it["idx"])
        it["gosi_no"] = gosi
        it["detail_url"] = f"{BASE}/USR/I0204/m_45/dtl.jsp?gubun=4&idx={it['idx']}"
        contents = best_content(op, atts)
        it["_excerpt"] = max((c[1] for c in contents), key=len, default="")
        hay = it["title"] + " " + it["_excerpt"][:3000]
        it["is_realty"] = any(k in hay for k in REALTY_KEYWORDS)

    realty = [it for it in new if it["is_realty"]]
    others = [it for it in new if not it["is_realty"]]

    lines = [f"[국토교통부 고시 요약] {today}",
             f"최근 {LOOKBACK_DAYS}일 신규 {len(new)}건 "
             f"(부동산 관련 {len(realty)}건)", ""]

    if realty:
        lines.append("=" * 40)
        lines.append("[부동산 관련 고시 - 상세]")
        lines.append("=" * 40)
        for i, it in enumerate(realty, 1):
            lines.append(f"\n{i}. {it['title']}")
            lines.append(f"   · {it.get('gosi_no') or '고시번호 미상'} "
                         f"| {it['dept']} | {it['date']}")
            summary = summarize_notice(it, client)
            for ln in summary.splitlines():
                ln = ln.strip()
                if ln:
                    lines.append(f"   {ln}")
            lines.append(f"   · 원문: {it['detail_url']}")

    lines.append("")
    lines.append("=" * 40)
    lines.append(f"[전체 신규 고시 목록 - {len(new)}건]")
    lines.append("=" * 40)
    for it in new:
        tag = " [부동산]" if it["is_realty"] else ""
        lines.append(f"- ({it['date']}) {it['title']}{tag}")
        lines.append(f"    {it.get('gosi_no') or ''} | {it['dept']} | {it['detail_url']}")

    lines.append("")
    lines.append(f"목록 페이지: {LIST_URL}")
    return "\n".join(lines)


def build_molit_section(client=None):
    """다른 메일 본문에 덧붙이기 위한 국토부 고시 섹션 문자열.
    신규가 없으면 짧은 한 줄 안내만 반환(빈 값 반환하지 않음)."""
    body = build_molit_body(client=client)
    if not body:
        today = datetime.date.today().strftime("%Y-%m-%d")
        body = (f"[국토교통부 고시 요약] {today}\n"
                f"최근 {LOOKBACK_DAYS}일 이내 신규 등록된 고시가 없습니다.")
    return body


def _time_tag():
    import pytz
    now = datetime.datetime.now(pytz.timezone("Asia/Seoul"))
    return "오전" if now.hour < 12 else "오후"


def _get_openai_client():
    """OPENAI_API_KEY 있으면 OpenAI 클라이언트, 없으면 None (발췌 기반 fallback)."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=key)
    except Exception:
        return None


def _send_email(body, subject):
    """Gmail SMTP 발송 (기존 프로젝트와 동일한 환경변수 사용)."""
    import smtplib
    from email.mime.text import MIMEText

    user = os.getenv("EMAIL_USER")
    pw = os.getenv("EMAIL_PASS")
    if not user or not pw:
        raise RuntimeError("EMAIL_USER / EMAIL_PASS 환경변수가 설정되지 않았습니다.")
    recipients = [r.strip() for r in os.getenv(
        "EMAIL_RECIPIENTS", "seo930714@gmail.com,mjikshouse@naver.com"
    ).split(",") if r.strip()]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, pw)
        server.sendmail(user, recipients, msg.as_string())


def main():
    client = _get_openai_client()
    body = build_molit_body(client=client)
    if body is None:
        print("[molit] 신규 없음 + SEND_IF_EMPTY=0 → 발송 생략")
        return

    tag = _time_tag()
    today = datetime.date.today().strftime("%m/%d")
    subject = f"[{today} 국토부 고시 요약 - {tag}]"

    if os.getenv("DRY_RUN") == "1":
        print("SUBJECT:", subject)
        print(body)
        return
    _send_email(body, subject)
    print(f"[molit] 발송 완료: {subject}")


if __name__ == "__main__":
    main()
