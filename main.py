
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import feedparser
import openai

# 종목 리스트
tickers = ["CHGG", "SLDP", "TSLA", "TSLL", "PL", "HIMS", "OSCR"]

# 수신자 이메일
recipients = ["seo930714@gmail.com", "mjikshouse@naver.com"]

# 뉴스 요약 함수
def fetch_and_summarize_news(ticker):
    rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    feed = feedparser.parse(rss_url)
    summaries = []
    for entry in feed.entries[:2]:  # 상위 2개 뉴스만
        title = entry.title
        link = entry.link
        summary = chatgpt_summarize(title + "\n" + entry.get("summary", ""))
        summaries.append(f"📰 [{ticker}] {title}\n→ {summary}\n")
    return summaries

# ChatGPT 요약 호출
def chatgpt_summarize(text):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": f"다음 뉴스 내용을 한국어로 간결히 요약해줘:\n{text}"}],
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"(요약 실패: {e})"

# 이메일 발송
def send_email(body):
    msg = MIMEMultipart()
    msg["Subject"] = "[오늘의 미국 주식 뉴스 요약]"
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        server.sendmail(msg["From"], recipients, msg.as_string())

# 메인 실행
if __name__ == "__main__":
    all_summaries = []
    for ticker in tickers:
        all_summaries.extend(fetch_and_summarize_news(ticker))
    final_body = "\n".join(all_summaries)
    send_email(final_body)
