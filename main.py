import os
import smtplib
import requests
import feedparser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI

# 📌 종목 리스트
stock_tickers = ["CHGG", "SLDP", "TSLA", "PL", "HIMS", "OSCR"]
crypto_tickers = ["BTC-USD", "ETH-USD"]

# 📌 수신자 이메일
recipients = ["seo930714@gmail.com", "mjikshouse@naver.com"]

# ✅ ChatGPT 요약 함수
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

# ✅ RSS 뉴스 요약 수집 함수
def fetch_and_summarize_news(ticker):
    rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    feed = feedparser.parse(rss_url)
    summaries = []
    for entry in feed.entries[:2]:  # 상위 2개 뉴스만
        title = entry.title
        summary = chatgpt_summarize(title + "\n" + entry.get("summary", ""))
        summaries.append(f"📰 [{ticker}] {title}\n→ {summary}\n")
    return summaries

# ✅ 공포탐욕지수 함수
def get_fear_and_greed_index():
    try:
        url = "https://api.alternative.me/fng/?limit=1"
        response = requests.get(url)
        data = response.json()
        index_value = data["data"][0]["value"]
        index_text = data["data"][0]["value_classification"]
        return f"📊 공포탐욕지수: {index_value} ({index_text})"
    except Exception as e:
        return f"(공포탐욕지수 가져오기 실패: {e})"

# ✅ 이메일 발송 함수
def send_email(body):
    msg = MIMEMultipart()
    msg["Subject"] = "[오늘의 미국 주식 뉴스 요약]"
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        server.sendmail(msg["From"], recipients, msg.as_string())

# ✅ 메인 실행
if __name__ == "__main__":
    stock_summaries = []
    crypto_summaries = []

    for ticker in stock_tickers:
        stock_summaries.extend(fetch_and_summarize_news(ticker))

    for ticker in crypto_tickers:
        crypto_summaries.extend(fetch_and_summarize_news(ticker))

    fear_greed = get_fear_and_greed_index()

    final_body = "[오늘의 뉴스 요약]\n\n"
    final_body += "📈 해외주식 PART\n"
    final_body += "\n".join(stock_summaries) + "\n\n"
    final_body += "🪙 코인 PART\n"
    final_body += fear_greed + "\n\n"
    final_body += "\n".join(crypto_summaries)

    send_email(final_body)
