"""
[선택] always-on 서버에서 정시 발송이 필요할 때 사용하는 스케줄러.

GitHub Actions의 cron은 best-effort라 수 분~수십 분 지연될 수 있다.
분 단위로 정확히 07:30 / 17:00 KST에 발송해야 한다면,
24시간 켜져 있는 서버(또는 컨테이너)에서 이 파일을 실행한다.

CronTrigger(timezone="Asia/Seoul") 로 타임존을 명시 고정하므로
서버/OS의 기본 타임존에 의존하지 않는다.

실행:  python scheduler.py
"""
import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from main import build_body, send_email, get_openai_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
KST = pytz.timezone("Asia/Seoul")


def job():
    logging.info("뉴스 메일 작업 시작 (KST %s)", datetime.now(KST))
    try:
        client = get_openai_client()
        send_email(build_body(client=client))
        logging.info("발송 완료")
    except Exception as e:
        logging.exception("발송 실패: %s", e)


def main():
    # misfire_grace_time: 서버가 잠깐 멈춰도 일정 시간 내면 따라잡아 실행
    # coalesce: 누적 지연 시 중복 실행을 1회로 합침 → 드리프트/누적지연 방지
    scheduler = BlockingScheduler(timezone=KST)
    common = dict(misfire_grace_time=600, coalesce=True, max_instances=1)

    scheduler.add_job(job, CronTrigger(hour=7, minute=30, timezone=KST), **common)
    scheduler.add_job(job, CronTrigger(hour=17, minute=0, timezone=KST), **common)

    logging.info("스케줄러 시작: 매일 07:30, 17:00 (Asia/Seoul)")
    scheduler.start()


if __name__ == "__main__":
    main()
