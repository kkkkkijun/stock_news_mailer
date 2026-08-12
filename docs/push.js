/* 브리핑노트 푸시 구독. Firestore REST에 구독정보 저장(SDK 불필요).
   VAPID 공개키는 공개 정보. 비공개키는 서버(GitHub Secret)에만. */
(function () {
  var PUB = "BJvb73S-fmZaD0s6ZsqcC2CR-1d9jk3aJQVP_gosxxVeSEAbmPTYiFHARRpB6oT1WCHPrE7wFzpxOte2yHN6tNE";
  var PROJ = "stock-news-mailer-6f86b";
  var KEY = "AIzaSyCIsIbniZhAc4mdSCdtwgvafwRC0nuetl4";
  var FS = "https://firestore.googleapis.com/v1/projects/" + PROJ +
           "/databases/(default)/documents/push_subs?key=" + KEY;

  function u8(b64) {
    var pad = "=".repeat((4 - (b64.length % 4)) % 4);
    var s = (b64 + pad).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(s), arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  function saveSub(sub) {
    var j = sub.toJSON();
    var body = { fields: {
      endpoint: { stringValue: j.endpoint },
      p256dh: { stringValue: j.keys.p256dh },
      auth: { stringValue: j.keys.auth },
      ua: { stringValue: (navigator.userAgent || "").slice(0, 180) }
    } };
    return fetch(FS, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  function markOn() {
    var b = document.getElementById("pushBtn");
    if (b) { b.textContent = "🔔 알림 켜짐"; b.setAttribute("data-on", "1"); }
  }

  window.enablePush = function () {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      alert("이 브라우저는 알림을 지원하지 않아요.\n아이폰은 '홈 화면에 추가'로 설치한 앱에서, iOS 16.4 이상이어야 합니다.");
      return;
    }
    Notification.requestPermission().then(function (perm) {
      if (perm !== "granted") {
        alert("알림이 꺼져 있어요. 설정 > 알림에서 허용해 주세요.");
        return;
      }
      navigator.serviceWorker.ready.then(function (reg) {
        return reg.pushManager.getSubscription().then(function (ex) {
          return ex || reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: u8(PUB)
          });
        });
      }).then(function (sub) {
        return saveSub(sub);
      }).then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        if (navigator.clearAppBadge) { try { navigator.clearAppBadge(); } catch (e) {} }
        markOn();
        alert("알림을 켰어요! 새 브리핑이 나오면 아이콘에 배지와 알림이 떠요.");
      }).catch(function (e) {
        alert("알림 켜기 실패: " + (e && e.message ? e.message : e));
      });
    });
  };

  /* 앱 열면 배지 제거 + 이미 구독돼 있으면 버튼 상태 반영 */
  if (navigator.clearAppBadge) { try { navigator.clearAppBadge(); } catch (e) {} }
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.ready.then(function (reg) {
      if (reg.pushManager) reg.pushManager.getSubscription().then(function (s) {
        if (s) markOn();
      });
    }).catch(function () {});
  }
})();
