"""새 브리핑 발행 시 구독자에게 Web Push 전송(→ 앱 배지 + 팝업).
구독정보는 Firestore(push_subs)에서 REST로 읽고, 죽은 구독은 정리한다.
VAPID 비공개키는 환경변수(GitHub Secret) VAPID_PRIVATE_KEY(PEM)에서 읽는다."""
import json
import os
import tempfile

import requests

PROJ = "stock-news-mailer-6f86b"
API_KEY = "AIzaSyCIsIbniZhAc4mdSCdtwgvafwRC0nuetl4"
FS = f"https://firestore.googleapis.com/v1/projects/{PROJ}/databases/(default)/documents"
SITE = "https://kkkkkijun.github.io/stock_news_mailer/"


def _subs():
    out = []
    try:
        r = requests.get(f"{FS}/push_subs?key={API_KEY}&pageSize=300", timeout=20).json()
    except Exception as e:
        print(f"[push] 구독 조회 실패: {e}")
        return out
    for d in r.get("documents", []):
        f = d.get("fields", {})
        ep = f.get("endpoint", {}).get("stringValue")
        p = f.get("p256dh", {}).get("stringValue")
        a = f.get("auth", {}).get("stringValue")
        if ep and p and a:
            out.append({"name": d["name"], "endpoint": ep, "p256dh": p, "auth": a})
    return out


def _delete(name):
    try:
        requests.delete(f"https://firestore.googleapis.com/v1/{name}?key={API_KEY}", timeout=15)
    except Exception:
        pass


def send_push(title, body, url=None):
    pem = os.getenv("VAPID_PRIVATE_KEY")
    if not pem:
        print("[push] VAPID_PRIVATE_KEY 없음 — 건너뜀")
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[push] pywebpush 미설치 — 건너뜀")
        return 0
    subs = _subs()
    if not subs:
        print("[push] 구독자 없음")
        return 0
    claim = {"sub": os.getenv("VAPID_SUBJECT", "mailto:tjrlwns93@ermore.co.kr")}
    payload = json.dumps({"title": title, "body": body, "url": url or SITE})

    tf = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False, encoding="utf-8")
    tf.write(pem)
    tf.close()
    sent, seen = 0, set()
    try:
        for s in subs:
            if s["endpoint"] in seen:      # 중복 구독 정리
                _delete(s["name"])
                continue
            seen.add(s["endpoint"])
            info = {"endpoint": s["endpoint"],
                    "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}}
            try:
                webpush(subscription_info=info, data=payload,
                        vapid_private_key=tf.name, vapid_claims=dict(claim))
                sent += 1
            except WebPushException as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code in (404, 410):     # 죽은 구독 정리
                    _delete(s["name"])
                print(f"[push] 실패({code}): {str(e)[:70]}")
            except Exception as e:
                print(f"[push] 오류: {str(e)[:70]}")
    finally:
        try:
            os.remove(tf.name)
        except OSError:
            pass
    print(f"[push] 전송 {sent}건 / 구독 {len(seen)}")
    return sent


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "브리핑노트"
    b = sys.argv[2] if len(sys.argv) > 2 else "테스트 알림입니다."
    send_push(t, b)
