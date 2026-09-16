# -*- coding: utf-8 -*-
"""브리핑 완료 알림. 기본은 앱 푸시, `SEND_EMAIL=1`이면 이메일도 발송(선택).

입력: main.py의 발행 결과(발행 시각, 사이트 URL, 알림 문구), 환경변수 SEND_EMAIL/EMAIL_USER/EMAIL_PASS/EMAIL_RECIPIENTS
출력: 앱 푸시 알림(push_send.send_push 경유), 선택적으로 이메일 발송
실행: 모듈로만 사용(main.py가 notify_briefing() 호출)
관련: push_send.py, main.py
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import pytz

KST = pytz.timezone("Asia/Seoul")

# 수신자 (env로 override 가능)
recipients = os.getenv(
    "EMAIL_RECIPIENTS", "seo930714@gmail.com,mjikshouse@naver.com"
).split(",")
recipients = [r.strip() for r in recipients if r.strip()]


# =========================================================
# 이메일 발송
# =========================================================
def send_email(body, subject=None):
    # 발송 시각 표기는 항상 KST(timezone-aware)로 고정
    now = datetime.now(KST)
    hour = now.hour

    if subject is None:
        # 실제 스케줄(07:37 / 17:13) 기준으로 오전/오후 판정
        time_tag = "1차 (오전)" if hour < 12 else "2차 (오후)"
        # %-m/%-d 는 리눅스 전용이라 OS 무관하게 직접 조합
        subject = f"[{now.month}/{now.day} 뉴스 요약 - {time_tag}]"

    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    if not email_user or not email_pass:
        raise RuntimeError("EMAIL_USER / EMAIL_PASS 환경변수가 설정되지 않았습니다.")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_user, email_pass)
        server.sendmail(email_user, recipients, msg.as_string())


def notify_briefing(now, site_url, notice_text):
    """새 브리핑 알림: 앱 푸시(항상 시도) + 이메일(SEND_EMAIL=1일 때만)."""
    tag = "오전" if now.hour < 12 else "오후"

    # 앱 푸시 — 이메일 대체. 구독자·VAPID 키 없으면 조용히 건너뜀.
    try:
        from push_send import send_push
        send_push(f"{now.month}/{now.day} {tag} 브리핑",
                  "새 뉴스 브리핑이 준비됐어요. 눌러서 확인하세요.",
                  url=site_url)
    except Exception as pe:
        print(f"[push] 발송 실패: {pe}")

    # 이메일 알림은 기본 꺼짐(앱 푸시로 대체). 다시 켜려면 SEND_EMAIL=1.
    # 메일이 오지 않으면 파이프라인 문제 신호로 쓰고 싶을 때 사용.
    if os.getenv("SEND_EMAIL", "0") == "1":
        send_email(notice_text,
                   subject=f"[{now.month}/{now.day} {tag}] "
                           "뉴스 브리핑이 준비됐습니다")
