import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
from openai import OpenAI
from datetime import datetime
import requests
import pytz

# 종목 리스트
stock_tickers = ["NVDA", "SLDP", "TSLA", "PL", "HIMS", "OSCR"]
crypto_tickers = ["BTC-USD", "ETH-USD", "SOL-USD", "SUI-USD"]

# 수신자 이메일
recipients = ["seo930714@gmail.com", "mjikshouse@naver.com"]

# ChatGPT 요약 호출 함수
def chatgpt_summarize(text):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"다음 뉴스 내용을 한국어로 간결히 요약해줘:\n{text}"}],
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"(요약 실패: {e})"

# 뉴스 가져오고 요약하는 함수
def fetch_and_summarize_news(ticker):
    rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    feed = feedparser.parse(rss_url)
    summaries = []
    for entry in feed.entries[:3]:  # 상위 3개 뉴스만
        title = entry.title
        summary = chatgpt_summarize(title + "\n" + entry.get("summary", ""))
        summaries.append(f"📰 [{ticker}] {title}\n→ {summary}\n")
    return summaries

# 공포탐욕지수 가져오기
def get_fear_greed_index():
    try:
        response = requests.get("https://api.alternative.me/fng/?limit=1")
        data = response.json()["data"][0]
        value = data["value"]
        value_class = data["value_classification"]
        return f"\n📊 공포탐욕지수: {value} ({value_class})\n"
    except Exception as e:
        return f"\n📊 공포탐욕지수 가져오기 실패: {e}\n"

# 이메일 발송 함수
def send_email(body):
    kst = pytz.timezone("Asia/Seoul")
    now = datetime.now(kst)
    hour = now.hour

    time_tag = "1차 (오전)" if hour < 12 else "2차 (오후)"
    today_str = now.strftime("%-m/%-d")  # 예: 6/26

    subject = f"[{today_str} 뉴스 요약 - {time_tag}]"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        server.sendmail(msg["From"], recipients, msg.as_string())

# 메인 실행
if __name__ == "__main__":
    stock_summaries = []
    crypto_summaries = []

    for ticker in stock_tickers:
        stock_summaries.extend(fetch_and_summarize_news(ticker))

    for ticker in crypto_tickers:
        crypto_summaries.extend(fetch_and_summarize_news(ticker))

    final_body = "[오늘의 뉴스 요약]\n\n"
    final_body += "📈 해외주식 PART\n"
    final_body += "\n".join(stock_summaries) + "\n\n"
    final_body += "🪙 코인 PART\n"
    final_body += "\n".join(crypto_summaries)
    final_body += get_fear_greed_index()

    send_email(final_body)
