/* Kali Code PWA service worker - offline shell + background sync. */
const CACHE = "kali-code-v1";
const SHELL = ["/", "/manifest.json", "/icon.svg", "/app.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // Never cache API or WebSocket traffic.
  if (url.pathname.startsWith("/ws") || url.pathname.startsWith("/health") ||
      url.pathname.startsWith("/push")) {
    return;
  }
  if (e.request.method !== "GET") return;

  e.respondWith(
    caches.match(e.request).then((cached) => {
      const fetched = fetch(e.request)
        .then((resp) => {
          if (resp && resp.status === 200 && resp.type === "basic") {
            const copy = resp.clone();
            caches.open(CACHE).then((c) => c.put(e.request, copy));
          }
          return resp;
        })
        .catch(() => cached || caches.match("/"));
      return cached || fetched;
    })
  );
});

self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (err) {}
  const title = data.title || "Kali Code";
  const body = data.body || data.text || "";
  e.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: data,
    })
  );
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: "window" }).then((list) => {
      for (const c of list) {
        if ("focus" in c) return c.focus();
      }
      return self.clients.openWindow("/");
    })
  );
});
