/**
 * SMART PARKING IoT — SERVICE WORKER (PWA)
 * Cache App Shell for ultra-fast startup while strictly excluding realtime APIs.
 * Zero Fake Data — Live API data is always fetched from the network.
 */

const CACHE_NAME = "smart-parking-shell-v2";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/css/style.css",
  "/js/app.js",
  "/manifest.json",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/apple-touch-icon.png",
  "/icons/favicon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn("[SW] Cache addAll warning:", err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // QUY TẮC QUAN TRỌNG: Không bao giờ cache các API realtime, SSE hoặc upload frames
  if (
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/uploads/") ||
    event.request.method !== "GET"
  ) {
    // Network-only trực tiếp
    event.respondWith(fetch(event.request));
    return;
  }

  // Đối với static assets (HTML/CSS/JS/Fonts): Stale-while-revalidate
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
