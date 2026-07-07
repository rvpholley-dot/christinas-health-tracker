/* Offline support. Caches the app shell so the tracker opens with no signal.
   IMPORTANT: bump CACHE_VERSION whenever you change any app file, so phones
   pick up the new version instead of serving the old cached one. */
const CACHE_VERSION = "cht-v5";
const SHELL = [
  "./",
  "index.html",
  "styles.css",
  "app.js",
  "manifest.json",
  "icons/icon-180.png",
  "icons/icon-192.png",
  "icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  // Cache-first for the shell; fall back to network, then cache the result.
  event.respondWith(
    caches.match(event.request).then((cached) =>
      cached ||
      fetch(event.request)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, copy));
          return resp;
        })
        .catch(() => cached)
    )
  );
});
