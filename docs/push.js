/* 브리핑노트 푸시 구독 토글. 켜기=구독+Firestore저장, 끄기=구독해제+정리.
   VAPID 공개키는 공개 정보. 비공개키는 서버(GitHub Secret)에만. */
(function () {
  var PUB = "BJvb73S-fmZaD0s6ZsqcC2CR-1d9jk3aJQVP_gosxxVeSEAbmPTYiFHARRpB6oT1WCHPrE7wFzpxOte2yHN6tNE";
  var PROJ = "stock-news-mailer-6f86b";
  var KEY = "AIzaSyCIsIbniZhAc4mdSCdtwgvafwRC0nuetl4";
  var DOCS = "https://firestore.googleapis.com/v1/projects/" + PROJ +
             "/databases/(default)/documents";

  function u8(b64) {
    var pad = "=".repeat((4 - (b64.length % 4)) % 4);
    var s = (b64 + pad).replace(/-/g, "+").replace(/_/g, "/");
    var raw = atob(s), arr = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
    return arr;
  }

  function setBtn(on) {
    var b = document.getElementById("pushBtn");
    if (!b) return;
    if (on) { b.textContent = "🔔 알림 켜짐"; b.setAttribute("data-on", "1"); }
    else { b.textContent = "🔔 알림"; b.removeAttribute("data-on"); }
  }

  function saveSub(sub) {
    var j = sub.toJSON();
    var body = { fields: {
      endpoint: { stringValue: j.endpoint },
      p256dh: { stringValue: j.keys.p256dh },
      auth: { stringValue: j.keys.auth },
      ua: { stringValue: (navigator.userAgent || "").slice(0, 180) }
    } };
    return fetch(DOCS + "/push_subs?key=" + KEY, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    }).then(function (doc) {
      try { localStorage.setItem("push_doc", doc.name || ""); } catch (e) {}
    });
  }

  function deleteStoredDoc() {
    var name = "";
    try { name = localStorage.getItem("push_doc") || ""; } catch (e) {}
    if (!name) return Promise.resolve();
    return fetch("https://firestore.googleapis.com/v1/" + name + "?key=" + KEY,
                 { method: "DELETE" }).catch(function () {}).then(function () {
      try { localStorage.removeItem("push_doc"); } catch (e) {}
    });
  }

  function subscribe() {
    return Notification.requestPermission().then(function (perm) {
      if (perm !== "granted") {
        alert("알림이 꺼져 있어요. 설정 > 알림에서 허용해 주세요.");
        return false;
      }
      return navigator.serviceWorker.ready.then(function (reg) {
        return reg.pushManager.getSubscription().then(function (ex) {
          return ex || reg.pushManager.subscribe({
            userVisibleOnly: true, applicationServerKey: u8(PUB)
          });
        });
      }).then(function (sub) {
        return saveSub(sub);
      }).then(function () {
        if (navigator.clearAppBadge) { try { navigator.clearAppBadge(); } catch (e) {} }
        setBtn(true);
        alert("알림을 켰어요! 새 브리핑이 나오면 아이콘에 배지와 알림이 떠요.");
        return true;
      });
    });
  }

  function unsubscribe() {
    return navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription();
    }).then(function (sub) {
      var p = sub ? sub.unsubscribe() : Promise.resolve();
      return p;
    }).then(function () {
      return deleteStoredDoc();
    }).then(function () {
      if (navigator.clearAppBadge) { try { navigator.clearAppBadge(); } catch (e) {} }
      setBtn(false);
      alert("알림을 껐어요. 언제든 다시 켤 수 있어요.");
      return true;
    });
  }

  window.togglePush = function () {
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
      alert("이 브라우저는 알림을 지원하지 않아요.\n아이폰은 '홈 화면에 추가'로 설치한 앱에서, iOS 16.4 이상이어야 합니다.");
      return;
    }
    navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription();
    }).then(function (sub) {
      return sub ? unsubscribe() : subscribe();
    }).catch(function (e) {
      alert("알림 전환 실패: " + (e && e.message ? e.message : e));
    });
  };
  window.enablePush = window.togglePush;  // 이전 HTML 호환

  /* 앱 열면 배지 제거 + 현재 구독 상태로 버튼 반영 */
  if (navigator.clearAppBadge) { try { navigator.clearAppBadge(); } catch (e) {} }
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.ready.then(function (reg) {
      if (reg.pushManager) reg.pushManager.getSubscription().then(function (s) {
        setBtn(!!s);
      });
    }).catch(function () {});
  }
})();
