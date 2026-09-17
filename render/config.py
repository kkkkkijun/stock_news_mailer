# -*- coding: utf-8 -*-
"""경로 상수·전역 설정값(publish_site.py 분리)."""
from __future__ import annotations

import os
from datetime import date

import pytz

KST = pytz.timezone("Asia/Seoul")
# render/ 패키지 안이므로 한 단계 위가 저장소 루트.
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(HERE, "docs")
ARCHIVE_DIR = os.path.join(DOCS_DIR, "archive")
# 원문 텍스트 보관소. 디자인만 바꿀 때 뉴스 재수집 없이 재렌더링(rebuild_all).
DATA_DIR = os.path.join(HERE, "data")

# (앵커 id, 아이콘, 표시명, 본문 섹션 키워드)
PARTS = [
    ("eco", "💹", "경제", "경제 PART"),
    ("cm", "🌐", "코인시장", "코인시장 PART"),
    ("os", "📈", "해외주식", "해외주식 PART"),
    ("coin", "🪙", "코인", "코인 PART"),
    ("re", "🏘️", "부동산", "부동산 PART"),
    ("trump", "💬", "트럼프", "트럼프 PART"),
]

# 핵심(히어로) 강조를 적용할 섹션 = LLM 중요도 랭킹이 있는 섹션만.
# 주식(os)·코인(coin)은 '관련성+최신' 정렬이라 1번=최중요가 아니므로 제외.
HERO_PARTS = {"eco", "cm", "re", "trump"}

# 탭 구성: (탭 이름, 포함할 파트 id)
TABS = [
    ("뉴스", ["eco", "cm"]),
    ("주식", ["os", "coin"]),
    ("부동산", ["re"]),
    ("트럼프", ["trump"]),
]

# 티커 뱃지 색상 = 각 기업/코인의 브랜드 컬러
# 여기에 없는 티커는 이름 해시로 색을 자동 배정하므로 종목을 바꿔도 동작한다.
TICKER_COLORS = {
    "NVDA": "#76B900",   # NVIDIA 시그니처 그린
    "TSLA": "#E82127",   # Tesla 레드
    "HIMS": "#0F6B5C",   # Hims & Hers 딥그린
    "RDW": "#D0202E",    # Redwire 레드
    "BTC": "#F7931A",    # Bitcoin 오렌지
    "ETH": "#627EEA",    # Ethereum 블루퍼플
    "SOL": "#9945FF",    # Solana 퍼플
    "XRP": "#23292F",
    "DOGE": "#C2A633",
    "AAPL": "#555555",
    "MSFT": "#0078D4",
    "GOOGL": "#4285F4",
    "AMZN": "#FF9900",
    "META": "#0866FF",
    "AMD": "#ED1C24",
    "PLTR": "#101820",   # Palantir 블랙
    "IREN": "#12B886",   # IREN 그린
    "RKLB": "#1A2A4A",   # Rocket Lab 네이비
    "BMNR": "#F7931A",   # BitMine 비트코인 오렌지
}

# 티커 → 한글 표기(그룹 헤더용). 없으면 티커만 표시.
_TICKER_KO = {
    "NVDA": "엔비디아", "TSLA": "테슬라", "HIMS": "힘스앤허스",
    "RDW": "레드와이어", "IREN": "아이렌", "RKLB": "로켓랩",
    "BTC": "비트코인", "ETH": "이더리움", "SOL": "솔라나", "BMNR": "비트마인",
}

_DOW = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

# 브라우저 탭에 표시되는 사이트 제목(고정)
SITE_TITLE = "MARKET BRIEF | 경제·주식·코인·부동산 핵심 뉴스"
# 헤더 우측 하단(최종 업데이트와 같은 줄)에 표시되는 슬로건 + 디데이
SLOGAN = "🎯 40살 140억"
DDAY_TARGET = date(2032, 12, 31)   # 93년생 만 40세 진입 직전
DDAY_START = date(2026, 7, 30)     # 진행 바 0% 기준(추적 시작일) → 목표일에 100%

# 헤더 좌측(요일·최종 업데이트 아래)에 pill로 표시되는 단기 이벤트 디데이.
# (라벨, 날짜) 한 줄 추가로 확장. 날짜가 지나면 자동으로 사라지고 당일은 D-DAY.
EVENT_DDAYS: list[tuple[str, date]] = [
    ("🗳️ 미국 중간선거", date(2026, 11, 3)),
]

# =========================================================
# 경제지표 일정 (FXStreet CSV → PC 우측 레일 / 모바일 '일정' 탭)
#   data/econ/*.csv (컬럼: Id,Start[UTC],Name,Impact,Currency)
# =========================================================
ECON_DIR = os.path.join(DATA_DIR, "econ")
_WD_KO = ["월", "화", "수", "목", "금", "토", "일"]
# 통화 → ISO 국가코드(flagcdn 국기 이미지용). Windows는 이모지 국기를 못 그려
# 'CN' 같은 글자로 나오므로 실제 국기 이미지를 쓴다.
_CUR_CC = {
    "USD": "us", "EUR": "eu", "JPY": "jp", "CNY": "cn", "KRW": "kr",
    "GBP": "gb", "AUD": "au", "CAD": "ca", "NZD": "nz", "CHF": "ch",
    "HKD": "hk", "INR": "in", "BRL": "br", "MXN": "mx", "ZAR": "za",
}
# 일정에 표시할 통화(국가) 화이트리스트 — 미국·한국·일본만. 유럽/중국 등 제외.
_ECON_CCY = {"USD", "KRW", "JPY"}

EARN_FILE = os.path.join(DATA_DIR, "earnings.json")
REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")

_WHEN_KO = {"amc": "장 마감 후", "bmo": "장 전", "": ""}

FUND_FILE = os.path.join(DATA_DIR, "fundamentals.json")
_GR_SIG = {"g": "#16a37f", "y": "#e0930a", "r": "#e5484d"}
_GR_SIGTXT = {"g": "양호", "y": "주의", "r": "경고"}

_DOW_SHORT = ["일", "월", "화", "수", "목", "금", "토"]

_LINKS_HOME = '<a class="hd-archive" href="archive/index.html">지난 브리핑</a>'
_LINKS_SNAP = ('<a class="hd-archive" href="../index.html">🏠 홈</a>'
               '<a class="hd-archive" href="index.html">지난 브리핑</a>')
