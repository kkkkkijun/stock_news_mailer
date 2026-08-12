/* 브리핑노트 PWA 서비스워커.
   전략: 같은 출처(HTML·아이콘·prices.json 등)는 '네트워크 우선'(열 때마다 최신) →
   실패(오프라인) 시 캐시. 외부(폰트·환율·Firebase)는 가로채지 않고 그대로 통과. */
const CACHE = "briefing-v2";
const HOME = "/stock_news_mailer/index.html";

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
