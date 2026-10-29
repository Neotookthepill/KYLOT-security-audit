const CACHE = "qylot-shell-v2";
const SHELL = ["/", "/index.html", "/manifest.json", "/favicon.ico", "/logo192.png"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

// Keep the offline cache under our control. Third-party fonts, map tiles and
// CDN responses can change independently, disclose browsing patterns and grow
// without a predictable bound; the browser may fetch them normally online.
const cacheable = (url) => url.origin === self.location.origin;

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api")) return;

  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put("/index.html", copy)); return r; })
        .catch(() => caches.match("/index.html"))
    );
    return;
  }
  if (!cacheable(url)) return;
  e.respondWith(
    caches.match(req).then((hit) => {
      const net = fetch(req)
        .then((r) => { if (r && (r.ok || r.type === "opaque")) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); } return r; })
        .catch(() => hit);
      return hit || net;
    })
  );
});
