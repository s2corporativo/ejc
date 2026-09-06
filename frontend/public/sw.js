// Service worker mínimo — cache de shell para PWA instalável.
// API nunca é cacheada (dados jurídicos sempre frescos).
// FE-10: o cache é RESTRITO ao shell — bundles versionados em /assets/, a
// página raiz, ícones e manifesto. Qualquer outro GET same-origin (uploads,
// previews, vídeos de marca) passa direto pela rede, sem cópia local.
const CACHE = "ejc-v3";
const SHELL_PATHS = new Set(["/", "/index.html", "/manifest.json", "/icon-192.png", "/icon-512.png"]);

function cacheavel(request) {
  if (request.method !== "GET") return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  if (url.pathname.startsWith("/api/")) return false; // network-only
  return url.pathname.startsWith("/assets/") || SHELL_PATHS.has(url.pathname);
}

self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => clients.claim())
));
self.addEventListener("fetch", (e) => {
  if (!cacheavel(e.request)) return; // rede normal, sem cache
  e.respondWith(
    caches.open(CACHE).then(async (cache) => {
      try {
        const fresh = await fetch(e.request);
        if (fresh.ok) cache.put(e.request, fresh.clone());
        return fresh;
      } catch {
        const cached = await cache.match(e.request);
        return cached || Response.error();
      }
    })
  );
});

// ── Web Push (v3.x) ──────────────────────────────────────
self.addEventListener("push", (event) => {
  let data = { title: "EJC", body: "", url: "/" };
  try { data = { ...data, ...event.data.json() }; } catch {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url: data.url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window" }).then((list) => {
      for (const c of list) {
        if ("focus" in c) { c.navigate(url); return c.focus(); }
      }
      return clients.openWindow(url);
    })
  );
});
