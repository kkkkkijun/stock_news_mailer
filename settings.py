# -*- coding: utf-8 -*-
"""파이프라인 설정 단일 출처. 환경변수 로딩, 시간대, 티커 목록, 상수.

입력: 환경변수(.env 또는 GitHub Actions secrets) — OPENAI_API_KEY, STOCK_TICKERS, CRYPTO_TICKERS 등
출력: KST, stock_tickers/crypto_tickers, TICKER_NAMES, NEWS_PER_TICKER, SUMMARY_MODEL/SUMMARY_MAX_TOKENS, EARNINGS_TICKERS, _EARN_KO, configure_logging()
실행: 별도 실행 없음 — 다른 모듈이 import해서 사용
관련: main.py, quotes.py, earnings.py
"""
from __future__ import annotations

import logging
import os

import pytz

# .env 로컬 테스트 지원 (GitHub Actions에서는 secrets로 주입되므로 없어도 됨)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# =========================================================
# 설정 (가능한 값은 환경변수로 override, 없으면 기본값 사용)
# =========================================================
KST = pytz.timezone("Asia/Seoul")

# 요약 모델: 코드에 하드코딩하지 않고 env로 변경 가능.
# 기본값 gpt-4o-mini = 저비용/충분한 한국어 요약 품질.
# 품질 우선이면 gpt-4.1-mini 등으로 교체 가능.
SUMMARY_MODEL = os.getenv("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
SUMMARY_MAX_TOKENS = int(os.getenv("OPENAI_SUMMARY_MAX_TOKENS", "500"))

# 종목 리스트 (env로 override 가능, 콤마 구분)
stock_tickers = os.getenv("STOCK_TICKERS", "NVDA,TSLA,HIMS,RDW,IREN,RKLB").split(",")
crypto_tickers = os.getenv("CRYPTO_TICKERS", "BTC-USD,ETH-USD,SOL-USD,BMNR").split(",")
stock_tickers = [t.strip() for t in stock_tickers if t.strip()]
crypto_tickers = [t.strip() for t in crypto_tickers if t.strip()]


# 티커별 최대 뉴스 개수
NEWS_PER_TICKER = int(os.getenv("NEWS_PER_TICKER", "3"))

# 기업명 매핑 (제목/요약에 기업명 포함 뉴스 우선 정렬용)
TICKER_NAMES = {
    "NVDA": "Nvidia",
    "TSLA": "Tesla",
    "HIMS": "Hims",
    "RDW": "Redwire Corp",
    "IREN": "IREN Limited",
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "RKLB": "Rocket Lab",
    "BMNR": "BitMine Immersion",
}

# 기업 실적 일정 대상 (M7 + 관심종목) — earnings.py가 사용
_EARN_KO = {
    "NVDA": "엔비디아", "MSFT": "마이크로소프트", "AAPL": "애플",
    "GOOGL": "알파벳", "AMZN": "아마존", "META": "메타", "TSLA": "테슬라",
    "HIMS": "힘스앤허스", "RDW": "레드와이어", "IREN": "아이렌", "PLTR": "팔란티어",
    "RKLB": "로켓랩",
}
# M7 필수 + 관심종목(HIMS·RDW·IREN) + PLTR·RKLB(일정 전용)
EARNINGS_TICKERS = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "TSLA",
                    "HIMS", "RDW", "IREN", "PLTR", "RKLB"]


def configure_logging(level: int = logging.INFO) -> None:
    """루트 로거 기본 설정(entry point에서 1회만 호출). 이미 설정돼 있으면 무시."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(level=level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
