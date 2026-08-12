/* 브리핑노트 PWA 서비스워커.
   전략: 같은 출처(HTML·아이콘·prices.json 등)는 '네트워크 우선'(열 때마다 최신) →
   실패(오프라인) 시 캐시. 외부(폰트·환율·Firebase)는 가로채지 않고 그대로 통과. */
const CACHE = "briefing-v3";
const HOME = "/stock_news_mailer/index.html";
const BASE = "/stock_news_mailer/";

self.addEventListener("install", function () {
  self.skipWaiting();
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys()
      .then(function (ks) {
        return Promise.all(
          ks.filter(function (k) { return k !== CACHE; })
            .map(function (k) { return caches.delete(k); })
        );
      })
      .then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== location.origin) return; // 외부 리소스는 그대로

  e.respondWith(
    fetch(req)
      .then(function (res) {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
        return res;
      })
      .catch(function () {
        return caches.match(req).then(function (r) {
          return r || caches.match(HOME);
        });
      })
  );
});

/* 푸시 수신 → 팝업 알림 + 앱 아이콘 배지 */
self.addEventListener("push", function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) {
    d = { body: (e.data && e.data.text()) || "" };
  }
  var title = d.title || "브리핑노트";
  var body = d.body || "새 브리핑이 준비됐습니다.";
  var url = d.url || BASE;
  var badge = typeof d.count === "number" ? d.count : 1;
  e.waitUntil(
    Promise.all([
      self.registration.showNotification(title, {
        body: body,
        icon: BASE + "icon-192.png",
        badge: BASE + "icon-192.png",
        tag: "briefing",
        renotify: true,
        data: { url: url }
      }),
      (self.navigator && self.navigator.setAppBadge)
        ? self.navigator.setAppBadge(badge).catch(function () {})
        : Promise.resolve()
    ])
  );
});

/* 알림 탭 → 앱 열기 + 배지 제거 */
self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || BASE;
  e.waitUntil(
    Promise.resolve(
      (self.navigator && self.navigator.clearAppBadge)
        ? self.navigator.clearAppBadge().catch(function () {})
        : null
    ).then(function () {
      return clients.matchAll({ type: "window", includeUncontrolled: true });
    }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if (list[i].url.indexOf(BASE) >= 0 && "focus" in list[i]) return list[i].focus();
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
